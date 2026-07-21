import json, re, sys
from datetime import datetime
from pathlib import Path
from aiwf_core.adapters.claude.normalize_event import parse_claude_stdin, normalize
from aiwf_core.core.agent_worktree import AgentWorktreeError, resolve_agent_assignment
from aiwf_core.core.agent_runtime import (
    bind_dispatch_agent,
    cancel_agent_dispatch,
    finish_dispatch,
    latest_agent_dispatch,
    start_resumed_dispatch,
)
from aiwf_core.core.worktree_context import resolve_control_root

RETURN_MARKER = re.compile(r"(?m)^\s*(RETURN_TO_PLANNER|EXTERNAL_FINDING)\b\s*:?")
TASK_ROLES = {"aiwf-executor", "aiwf-tester", "aiwf-reviewer"}
ROLE_LABELS = {
    "aiwf-executor": "Executor",
    "aiwf-tester": "Tester",
    "aiwf-reviewer": "Reviewer",
}
REPORT_LABELS = {
    "aiwf-executor": "the implementation report",
    "aiwf-tester": "the testing report",
    "aiwf-reviewer": "REVIEW_REPORT",
}

ROLE_RECORD = {
    "aiwf-executor": ("implementation", "implementation_ref", "aiwf record implementation"),
    "aiwf-tester": ("testing", "tested_ref", "aiwf record testing"),
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


def _open_planner_fix_loop(base, task_id, source, reason):
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
    text = _response_text(value).lower()
    return any(word in text for word in ("was stopped", "interrupted", "cancelled", "canceled"))


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


def _completion_blocker(base, task_id, agent_type, agent_id):
    requirement = ROLE_RECORD.get(agent_type)
    if not requirement or not task_id or not agent_id:
        return ""
    dispatch = latest_agent_dispatch(
        base, agent_type, agent_id, task_id=task_id,
    )
    if not dispatch:
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
    if (
        fresh
        and agent_type == "aiwf-tester"
        and section.get("status") in ("partial", "passed")
    ):
        from aiwf_core.core.task_ledger import load_ledger
        from aiwf_core.core.task_proof import validate_testing_against_task

        task = next(
            (
                item for item in load_ledger(str(base)).get("tasks", []) or []
                if isinstance(item, dict) and item.get("id") == task_id
            ),
            None,
        )
        proof = validate_testing_against_task(str(base), task, section) if task else {}
        from aiwf_core.core.task_proof import testing_proof_gaps

        missing = testing_proof_gaps(proof)
        if proof.get("strict") and missing:
            named = ", ".join(dict.fromkeys(missing[:5]))
            return (
                f"The testing record for {task_id} is fresh, but it does not prove the "
                f"complete Verification Commands contract: {named}. Run only the missing "
                "or mismatched proof, then record each exact command, expected result, "
                "and observed result. Existing valid results are preserved while the "
                "tested worktree stays unchanged."
            )
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
        if agent_type not in {
            "aiwf-executor", "aiwf-tester", "aiwf-reviewer", "aiwf-architect",
        }:
            sys.exit(0)
        resumed_task = start_resumed_dispatch(
            base, agent_type, agent_id, str(data.get("session_id") or ""),
        )
        if resumed_task is not None:
            sys.exit(0)
        task_id = ""
        if agent_type != "aiwf-architect":
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
        sys.exit(0)

    if data.get("hook_event_name") == "SubagentStop":
        event = normalize(data)
        agent_type = str(event.agent_type or "")
        if agent_type not in {
            "aiwf-executor", "aiwf-tester", "aiwf-reviewer", "aiwf-architect",
        }:
            sys.exit(0)
        task_id = ""
        if agent_type != "aiwf-architect":
            try:
                assignment = resolve_agent_assignment(event, base)
                task_id = assignment.task_id if assignment else ""
            except AgentWorktreeError:
                pass
        if not task_id:
            task_id = _task_from_text(
                base,
                "\n".join(
                    str(data.get(key) or "")
                    for key in ("last_assistant_message", "cwd")
                ),
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

    subagent_type = event.tool_input.get("subagent_type", "")
    if not subagent_type:
        sys.exit(0)

    tool_failed = data.get("hook_event_name") == "PostToolUseFailure"

    if subagent_type in TASK_ROLES:
        prompt = "\n".join(
            str(event.tool_input.get(key) or "")
            for key in ("prompt", "description", "name")
        )
        task_id = _task_from_text(base, prompt)
    else:
        task_id = ""

    # Claude emits PostToolUse when a background Agent launch succeeds. That
    # event says nothing about whether the subagent has finished. SubagentStop
    # is the sole normal completion signal for Claude workflow roles.
    if (
        event.engine == "claude"
        and not tool_failed
        and not _was_cancelled(event.tool_response)
    ):
        if subagent_type in TASK_ROLES and _was_background_launch(event.tool_response):
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
        sys.exit(0)

    if subagent_type in TASK_ROLES:
        reason = "" if tool_failed else _return_reason(_response_text(event.tool_response))
        if reason:
            _open_planner_fix_loop(
                base, task_id, subagent_type.removeprefix("aiwf-"), reason
            )
    if subagent_type in TASK_ROLES:
        finish_dispatch(
            base,
            subagent_type,
            task_id=task_id,
            session_id=event.session_id,
            status="cancelled" if tool_failed or _was_cancelled(event.tool_response) else "completed",
            source="agent_failure" if tool_failed else "agent_cancelled",
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
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": hook_event,
                "additionalContext": (
                    f"[AIWF] {ROLE_LABELS[subagent_type]} returned{task_label}. Read "
                    f"{REPORT_LABELS[subagent_type]}, then run "
                    "`aiwf status --prompt` and follow its route."
                ),
            }
        }))

    sys.exit(0)

if __name__ == "__main__":
    main()
