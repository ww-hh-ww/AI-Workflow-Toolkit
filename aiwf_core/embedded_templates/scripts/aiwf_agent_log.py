import json, re, sys
from datetime import datetime
from pathlib import Path
from aiwf_core.adapters.claude.normalize_event import parse_claude_stdin, normalize
from aiwf_core.core.agent_worktree import AgentWorktreeError, resolve_agent_assignment
from aiwf_core.core.agent_runtime import (
    TRACKED_ROLES,
    WORKFLOW_ROLES,
    bind_dispatch_agent,
    cancel_agent_dispatch,
    finish_dispatch,
    latest_agent_dispatch,
    running_dispatches,
    start_resumed_dispatch,
)
from aiwf_core.core.worktree_context import resolve_control_root

RETURN_MARKER = re.compile(r"(?m)^\s*(RETURN_TO_PLANNER|EXTERNAL_FINDING)\b\s*:?")
TASK_ROLES = WORKFLOW_ROLES | {"aiwf-architect"}
ROLE_LABELS = {
    "aiwf-architect": "Architect",
    "aiwf-executor": "Executor",
    "aiwf-experimenter": "Experimenter",
    "aiwf-reviewer": "Reviewer",
}
REPORT_LABELS = {
    "aiwf-architect": "the investigation evidence",
    "aiwf-executor": "the implementation report",
    "aiwf-experimenter": "the experiment evidence",
    "aiwf-reviewer": "REVIEW_REPORT",
}

ROLE_RECORD = {
    "aiwf-executor": ("implementation", "implementation_ref", "aiwf record implementation"),
    "aiwf-reviewer": ("review", "reviewed_ref", "aiwf record review"),
}

def _return_reason(message):
    if not isinstance(message, str):
        return ""
    match = RETURN_MARKER.search(message)
    if not match:
        return ""
    tail = message[match.end():].strip()
    return (tail.splitlines()[0].strip() if tail else match.group(1))[:500]


def _response_text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(_response_text(item) for item in value)
    if isinstance(value, dict):
        preferred = ["content", "output", "result", "text", "message"]
        parts = [_response_text(value[key]) for key in preferred if key in value]
        if parts:
            return "\n".join(parts)
        return "\n".join(_response_text(item) for item in value.values())
    return ""


def _task_from_text(base, text):
    try:
        ledger = json.loads((base / ".aiwf/state/tasks.json").read_text())
    except Exception:
        ledger = {"tasks": []}
    text = str(text or "")
    active_tasks = [
        task for task in ledger.get("tasks", []) or []
        if isinstance(task, dict) and task.get("status") == "active"
    ]
    id_matches = []
    for task in active_tasks:
        task_id = str(task.get("id") or "")
        if task_id and re.search(
            rf"(?<![A-Za-z0-9_-]){re.escape(task_id)}(?![A-Za-z0-9_-])", text
        ):
            id_matches.append(task_id)
    if len(id_matches) == 1:
        return id_matches[0]
    if len(id_matches) > 1:
        return ""

    path_matches = []
    for task in active_tasks:
        task_id = str(task.get("id") or "")
        worktree = str(task.get("worktree_path") or "")
        if task_id and worktree and worktree in text:
            path_matches.append((len(worktree), task_id))
    if path_matches:
        longest = max(length for length, _ in path_matches)
        longest_matches = [task_id for length, task_id in path_matches if length == longest]
        if len(longest_matches) == 1:
            return longest_matches[0]

    active = [
        str(task.get("id")) for task in active_tasks if task.get("id")
    ]
    return active[0] if len(active) == 1 else ""


def _experiment_from_text(base, text):
    """Resolve exactly one live experiment named in host prompt text."""
    from aiwf_core.core.experiment_records import list_experiments

    text = str(text or "")
    matches = []
    for item in list_experiments(base):
        experiment_id = str(item.get("experiment_id") or "")
        if (
            experiment_id
            and item.get("status") in ("open", "running", "recorded")
            and re.search(
                rf"(?<![A-Za-z0-9_-]){re.escape(experiment_id)}(?![A-Za-z0-9_-])",
                text,
            )
        ):
            matches.append(item)
    return matches[0] if len(matches) == 1 else {}


def _scope_from_text(base, text, agent_type):
    if agent_type in ("aiwf-experimenter", "aiwf-architect"):
        experiment = _experiment_from_text(base, text)
        return str((experiment.get("scope") or {}).get("id") or "")
    return _task_from_text(base, text)


def _running_role(base, session_id, task_id="", agent_id=""):
    candidates = running_dispatches(base, task_id=task_id, session_id=session_id)
    if agent_id:
        candidates = [
            item for item in candidates
            if not item.get("agent_id") or item.get("agent_id") == agent_id
        ]
    roles = {
        str(item.get("subagent_type") or "")
        for item in candidates
        if item.get("subagent_type") in TRACKED_ROLES
    }
    return next(iter(roles)) if len(roles) == 1 else ""


def _open_planner_fix_loop(base, task_id, source, reason):
    if source == "architect":
        return
    if not task_id:
        return
    from aiwf_core.core.task_records import load_task_record
    current = load_task_record(base, task_id).get("fix_loop", {}) or {}
    if current.get("status") == "open" and current.get("route") == "planner":
        return

    from aiwf_core.core.state_ops import open_fix_loop
    open_fix_loop(str(base), route="planner", reason=reason,
                  source=source or "agent", task_id=task_id)


def _was_cancelled(value):
    if isinstance(value, str):
        text = value.lower()
        return any(
            phrase in text
            for phrase in (
                "was stopped",
                "was interrupted",
                "was cancelled",
                "was canceled",
            )
        )
    if isinstance(value, list):
        return any(_was_cancelled(item) for item in value)
    if not isinstance(value, dict):
        return False

    state = str(value.get("status") or value.get("state") or "").lower()
    if state in ("stopped", "interrupted", "cancelled", "canceled"):
        return True
    if any(
        value.get(key) is True
        for key in ("cancelled", "canceled", "interrupted", "is_interrupt")
    ):
        return True

    # A Claude async launch response includes the original dispatch prompt.
    # Prompt prose is not lifecycle evidence and may legitimately mention a
    # prior interrupted run, so inspect only result-bearing fields here.
    return any(
        _was_cancelled(value[key])
        for key in (
            "content",
            "output",
            "result",
            "text",
            "message",
            "last_assistant_message",
        )
        if key in value
    )


def _explicit_spawn_failure(value):
    """Recognize a host-reported spawn failure without guessing event order."""
    if not isinstance(value, dict):
        return False
    if value.get("is_error") is True or value.get("success") is False:
        return True
    state = str(value.get("status") or value.get("state") or "").lower()
    if state in ("error", "failed", "failure", "rejected"):
        return True
    return bool(value.get("error"))


def _spawned_agent_id(value):
    """Read a concrete child ID only from structured host launch output."""
    if not isinstance(value, dict):
        return ""
    for key in ("agent_id", "agentId"):
        if value.get(key):
            return str(value[key])
    nested = value.get("metadata")
    if isinstance(nested, dict):
        for key in ("agent_id", "agentId"):
            if nested.get(key):
                return str(nested[key])
    return ""


def _was_background_launch(value):
    return bool(
        isinstance(value, dict)
        and (
            value.get("isAsync") is True
            or str(value.get("status") or "") == "async_launched"
        )
    )


def _timestamp(value):
    try:
        return datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _completion_blocker(base, task_id, agent_type, agent_id="", session_id=""):
    if agent_type not in TASK_ROLES or not task_id:
        return ""
    if not agent_id and not session_id:
        return ""
    if agent_id:
        dispatch = latest_agent_dispatch(
            base, agent_type, agent_id, task_id=task_id,
        )
    else:
        candidates = [
            item for item in running_dispatches(
                base, task_id=task_id, session_id=session_id,
            )
            if item["subagent_type"] == agent_type
        ]
        dispatch = candidates[0] if len(candidates) == 1 else None
    if not dispatch:
        return ""

    if dispatch.get("experiment_id"):
        from aiwf_core.core.experiment_records import load_experiment

        experiment_id = str(dispatch.get("experiment_id") or "")
        experiment = load_experiment(base, experiment_id) if experiment_id else {}
        started_at = _timestamp(dispatch.get("started_at"))
        recorded_at = _timestamp(experiment.get("recorded_at"))
        fresh = bool(
            experiment
            and experiment.get("experiment_id") == experiment_id
            and experiment.get("experiment_ref")
            and experiment.get("status") in ("recorded", "closed")
            and started_at
            and recorded_at
            and recorded_at >= started_at
        )
        if fresh:
            try:
                from aiwf_core.core.git_snapshots import worktree_matches_ref

                worktree = str(dispatch.get("worktree_path") or "")
                fresh = bool(
                    worktree
                    and worktree_matches_ref(worktree, str(experiment["experiment_ref"]))
                )
            except Exception:
                fresh = False
        if fresh:
            return ""
        return (
            f"This {agent_type} run for {experiment_id or task_id} has no fresh experiment "
            "snapshot and evidence record. If the experiment is complete, run "
            f"`aiwf experiment record {experiment_id}` from its disposable worktree with "
            "the commands, observations, conclusion, and summary already obtained. Then "
            "return the final report."
        )

    requirement = ROLE_RECORD.get(agent_type)
    if not requirement:
        return ""

    from aiwf_core.core.task_records import load_task_record
    section_name, ref_name, command = requirement
    section = load_task_record(base, task_id).get(section_name, {}) or {}
    started_at = _timestamp(dispatch.get("started_at"))
    recorded_at = _timestamp(section.get("recorded_at"))
    fresh = bool(
        section.get("task_id") == task_id
        and section.get(ref_name)
        and started_at
        and recorded_at
        and recorded_at >= started_at
    )
    if fresh:
        worktree = str(dispatch.get("worktree_path") or "")
        try:
            from aiwf_core.core.git_snapshots import worktree_matches_ref
            fresh = bool(worktree and worktree_matches_ref(worktree, str(section[ref_name])))
        except Exception:
            fresh = False
    if fresh:
        return ""

    return (
        f"This Agent run for {task_id} has no fresh {section_name} record matching "
        f"the current worktree. If the work is complete, "
        f"run `{command}` with the exact results already observed; do not rerun successful "
        "checks merely to create the record. Then return the final report."
    )


def main():
    data = parse_claude_stdin()
    if not data:
        sys.exit(0)

    base = resolve_control_root(Path(__file__).resolve().parent.parent)

    if data.get("hook_event_name") == "SubagentStart":
        event = normalize(data)
        agent_type = str(event.agent_type or "")
        agent_id = str(event.agent_id or "")
        if event.engine == "codex" and agent_type not in TRACKED_ROLES:
            agent_type = _running_role(
                base, str(data.get("session_id") or ""), agent_id=agent_id,
            )
            event.agent_type = agent_type
        if agent_type not in TRACKED_ROLES:
            sys.exit(0)
        resumed_task = start_resumed_dispatch(
            base, agent_type, agent_id, str(data.get("session_id") or ""),
        )
        if resumed_task is not None:
            sys.exit(0)
        task_id = ""
        assignment = None
        if agent_type in TRACKED_ROLES:
            try:
                assignment = resolve_agent_assignment(event, base)
                task_id = assignment.task_id if assignment else ""
            except AgentWorktreeError:
                pass
        bind_dispatch_agent(
            base,
            agent_type,
            agent_id,
            task_id=task_id,
            session_id=str(data.get("session_id") or ""),
        )
        if event.engine == "codex" and assignment is not None:
            experiment = (
                _experiment_from_text(base, str(data))
                if agent_type in ("aiwf-experimenter", "aiwf-architect") else {}
            )
            experiment_id = str(experiment.get("experiment_id") or "")
            task_doc = base / ".aiwf" / "tasks" / f"{task_id}.md"
            context = (
                f"AIWF assignment: Experiment {experiment_id}. Question: "
                f"{experiment.get('question', '')} Subject ref: "
                f"{experiment.get('subject_ref', '')}. Disposable project worktree: "
                f"{assignment.worktree}. Record evidence with `aiwf experiment record "
                f"{experiment_id}` before returning."
                if experiment_id else
                f"AIWF assignment: Task {task_id}. Read {task_doc}. "
                f"Project worktree: {assignment.worktree}. Read `aiwf task proof {task_id}` "
                "before acting. Follow your installed AIWF role instructions; if the "
                "contract conflicts with reality, return RETURN_TO_PLANNER."
            )
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "SubagentStart",
                    "additionalContext": context,
                }
            }))
        sys.exit(0)

    if data.get("hook_event_name") == "SubagentStop":
        event = normalize(data)
        agent_type = str(event.agent_type or "")
        if event.engine == "codex" and agent_type not in TRACKED_ROLES:
            agent_type = _running_role(
                base,
                str(data.get("session_id") or ""),
                agent_id=str(data.get("agent_id") or ""),
            )
            event.agent_type = agent_type
        if agent_type not in TRACKED_ROLES:
            sys.exit(0)
        task_id = ""
        if data.get("agent_id"):
            dispatch = latest_agent_dispatch(base, agent_type, str(data["agent_id"]))
            task_id = str((dispatch or {}).get("task_id") or "")
        if agent_type in TRACKED_ROLES:
            try:
                assignment = resolve_agent_assignment(event, base)
                task_id = assignment.task_id if assignment else task_id
            except AgentWorktreeError:
                pass
        if not task_id:
            task_id = _scope_from_text(
                base,
                "\n".join(
                    str(data.get(key) or "")
                    for key in ("last_assistant_message", "cwd")
                ),
                agent_type,
            )
        marker = RETURN_MARKER.search(str(data.get("last_assistant_message") or ""))
        return_to_planner = bool(marker and marker.group(1) == "RETURN_TO_PLANNER")
        cancelled = _was_cancelled(data)
        if not return_to_planner and not cancelled:
            blocker = _completion_blocker(
                base,
                task_id,
                agent_type,
                str(data.get("agent_id") or ""),
            )
            if blocker:
                print(json.dumps({"decision": "block", "reason": blocker}))
                sys.exit(0)
        if agent_type != "aiwf-architect":
            reason = _return_reason(data.get("last_assistant_message"))
            if reason:
                _open_planner_fix_loop(
                    base, task_id, agent_type.removeprefix("aiwf-"), reason
                )
        finish_dispatch(
            base,
            agent_type,
            task_id=task_id,
            session_id=str(data.get("session_id") or ""),
            status="cancelled" if _was_cancelled(data) else "completed",
            source="subagent_stop",
            agent_id=str(data.get("agent_id") or ""),
        )
        sys.exit(0)

    event = normalize(data)
    if event.tool_name == "TaskStop":
        response = event.tool_response if isinstance(event.tool_response, dict) else {}
        if (
            data.get("hook_event_name") == "PostToolUse"
            and str(response.get("task_type") or "") == "local_agent"
        ):
            agent_id = str(
                response.get("task_id")
                or event.tool_input.get("task_id")
                or ""
            )
            stopped = cancel_agent_dispatch(base, agent_id, source="task_stop")
            if stopped:
                print(json.dumps({
                    "hookSpecificOutput": {
                        "hookEventName": "PostToolUse",
                        "additionalContext": (
                            f"[AIWF] {ROLE_LABELS.get(stopped['subagent_type'], 'Agent')} "
                            f"was stopped for {stopped['task_id']}; its running slot is released."
                        ),
                    }
                }))
        sys.exit(0)

    if event.tool_name not in ("Agent", "Task"):
        sys.exit(0)

    subagent_type = str(
        event.tool_input.get("subagent_type")
        or event.tool_input.get("agent_type")
        or event.tool_input.get("agent")
        or event.tool_input.get("agentName")
        or ""
    )
    if not subagent_type and event.engine == "codex":
        prompt = "\n".join(
            str(event.tool_input.get(key) or "")
            for key in ("prompt", "message", "description", "name")
        )
        inferred_task = _scope_from_text(base, prompt, "aiwf-experimenter") or _task_from_text(base, prompt)
        subagent_type = _running_role(
            base, event.session_id, task_id=inferred_task,
        )
    if not subagent_type:
        sys.exit(0)

    tool_failed = data.get("hook_event_name") == "PostToolUseFailure"
    if event.engine == "codex" and _explicit_spawn_failure(event.tool_response):
        tool_failed = True

    if subagent_type in TASK_ROLES:
        prompt = "\n".join(
            str(event.tool_input.get(key) or "")
            for key in ("prompt", "message", "description", "name")
        )
        task_id = _scope_from_text(base, prompt, subagent_type)
    else:
        task_id = ""

    # Codex emits a dedicated failure event when spawning fails. Successful
    # PostToolUse and SubagentStart can race, so only SubagentStart/Stop own
    # normal lifecycle binding and completion.
    if event.engine == "codex" and not tool_failed:
        child_agent_id = _spawned_agent_id(event.tool_response)
        if subagent_type in TASK_ROLES and child_agent_id:
            bind_dispatch_agent(
                base,
                subagent_type,
                child_agent_id,
                task_id=task_id,
                session_id=event.session_id,
            )
        sys.exit(0)

    # Claude emits PostToolUse when a background Agent launch succeeds. That
    # event says nothing about whether the subagent has finished. SubagentStop
    # is the sole normal completion signal for Claude workflow roles.
    if event.engine == "claude" and not tool_failed:
        background_launch = _was_background_launch(event.tool_response)
        if subagent_type in TASK_ROLES and background_launch:
            task_label = f" for {task_id}" if task_id else ""
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": (
                        f"[AIWF] {ROLE_LABELS[subagent_type]} is running in the background"
                        f"{task_label}. Process each Plan when its Agent returns; do not "
                        "wait for the other parallel Plans to finish."
                    ),
                }
            }))
        # A structured async launch is authoritative even when its embedded
        # prompt mentions cancelled or interrupted earlier work.
        if background_launch or not _was_cancelled(event.tool_response):
            sys.exit(0)

    reason = ""
    completion_note = ""
    child_agent_id = ""
    if subagent_type in TASK_ROLES:
        if event.engine == "opencode" and isinstance(event.tool_response, dict):
            metadata = event.tool_response.get("metadata", {}) or {}
            child_agent_id = str(
                metadata.get("sessionId") or metadata.get("sessionID") or ""
            )
            if child_agent_id:
                bind_dispatch_agent(
                    base,
                    subagent_type,
                    child_agent_id,
                    task_id=task_id,
                    session_id=event.session_id,
                )
        reason = "" if tool_failed else _return_reason(_response_text(event.tool_response))
        if reason:
            _open_planner_fix_loop(
                base, task_id, subagent_type.removeprefix("aiwf-"), reason
            )
        elif event.engine == "opencode" and not _was_cancelled(event.tool_response):
            completion_note = _completion_blocker(
                base, task_id, subagent_type, session_id=event.session_id,
            )
    if subagent_type in TASK_ROLES:
        cancelled = _was_cancelled(event.tool_response)
        finish_dispatch(
            base,
            subagent_type,
            task_id=task_id,
            session_id=event.session_id,
            status="cancelled" if tool_failed or cancelled else "completed",
            source=(
                "agent_failure" if tool_failed
                else "agent_cancelled" if cancelled
                else "agent_return"
            ),
            agent_id=child_agent_id,
        )

    if task_id:
        from aiwf_core.core.task_records import load_task_record
        fix_loop = load_task_record(base, task_id).get("fix_loop", {}) or {}
    else:
        fix_loop = {}
    hook_event = "PostToolUseFailure" if tool_failed else "PostToolUse"
    if tool_failed and subagent_type in TASK_ROLES:
        task_label = f" for {task_id}" if task_id else ""
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": hook_event,
                "additionalContext": (
                    f"[AIWF] {ROLE_LABELS[subagent_type]} dispatch failed{task_label}; "
                    "the running slot was released. Read the actual tool error, then run "
                    "`aiwf status --prompt`. Retry only after addressing that error; do not "
                    "substitute general-purpose."
                ),
            }
        }))
    elif (
        event.engine == "claude"
        and subagent_type in TASK_ROLES
        and _was_cancelled(event.tool_response)
    ):
        task_label = f" for {task_id}" if task_id else ""
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": hook_event,
                "additionalContext": (
                    f"[AIWF] {ROLE_LABELS[subagent_type]} dispatch stopped{task_label}; "
                    "the running slot was released. Run `aiwf status --prompt` before "
                    "deciding whether to retry."
                ),
            }
        }))
    elif fix_loop.get("status") == "open" and fix_loop.get("route") == "planner":
        task_label = f" for {task_id}" if task_id else ""
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": hook_event,
                "additionalContext": (
                    f"[AIWF] {ROLE_LABELS.get(subagent_type, 'Agent')} returned a problem"
                    f"{task_label}. "
                    "Stop normal progress. Run `aiwf status --prompt`, then read the "
                    "returned finding and open fix-loop and follow the Planner route."
                ),
            }
        }))
    elif subagent_type in TASK_ROLES:
        task_label = f" for {task_id}" if task_id else ""
        next_step = (
            completion_note
            + " Continue the same OpenCode child with the `task_id` returned by the "
            "Task tool. Do not dispatch the next workflow role yet."
            if completion_note else
            f"Read {REPORT_LABELS[subagent_type]}, then run `aiwf status --prompt` "
            "and follow its route."
        )
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": hook_event,
                "additionalContext": (
                    f"[AIWF] {ROLE_LABELS[subagent_type]} returned{task_label}. "
                    f"{next_step}"
                ),
            }
        }))

    sys.exit(0)

if __name__ == "__main__":
    main()
