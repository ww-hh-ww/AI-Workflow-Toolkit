import json, re, sys
from pathlib import Path
from aiwf_core.adapters.claude.normalize_event import parse_claude_stdin, normalize
from aiwf_core.core.state._common import _exclusive_operation_lock
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


def _append_completion(base, subagent_type, task_id="", session_id=""):
    log_path = base / ".aiwf" / "runtime" / "internal" / "agent-dispatch.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with _exclusive_operation_lock(str(base), "agent-dispatch", timeout=2):
        unfinished = {}
        if log_path.exists():
            for line in log_path.read_text(encoding="utf-8").splitlines():
                try:
                    entry = json.loads(line)
                except Exception:
                    continue
                if entry.get("subagent_type") != subagent_type:
                    continue
                entry_task_id = str(entry.get("task_id") or "")
                if entry.get("status") == "started":
                    unfinished[entry_task_id] = unfinished.get(entry_task_id, 0) + 1
                elif entry.get("status") == "completed":
                    unfinished[entry_task_id] = max(
                        0, unfinished.get(entry_task_id, 0) - 1
                    )
        if not task_id:
            candidates = [
                candidate for candidate, count in unfinished.items() if count > 0
            ]
            task_id = candidates[0] if len(candidates) == 1 else ""
        if not task_id:
            return
        from datetime import datetime, timezone
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "subagent_type": subagent_type,
            "task_id": task_id,
            "session_id": session_id,
            "status": "completed",
        }
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")


def main():
    data = parse_claude_stdin()
    if not data:
        sys.exit(0)

    base = resolve_control_root(Path(__file__).resolve().parent.parent)

    if data.get("hook_event_name") == "SubagentStop":
        agent_type = str(data.get("agent_type") or "")
        if agent_type not in {
            "aiwf-executor", "aiwf-tester", "aiwf-reviewer", "aiwf-architect",
        }:
            sys.exit(0)
        task_id = _task_from_text(
            base,
            "\n".join(str(data.get(key) or "") for key in ("last_assistant_message", "cwd")),
        )
        if agent_type != "aiwf-architect":
            reason = _return_reason(data.get("last_assistant_message"))
            if reason:
                _open_planner_fix_loop(
                    base, task_id, agent_type.removeprefix("aiwf-"), reason
                )
        _append_completion(
            base, agent_type, task_id, str(data.get("session_id") or "")
        )
        sys.exit(0)

    event = normalize(data)
    if event.tool_name not in ("Agent", "Task"):
        sys.exit(0)

    subagent_type = event.tool_input.get("subagent_type", "")
    if not subagent_type:
        sys.exit(0)

    if subagent_type in TASK_ROLES:
        prompt = "\n".join(
            str(event.tool_input.get(key) or "")
            for key in ("prompt", "description", "name")
        )
        task_id = _task_from_text(base, prompt)
        reason = _return_reason(_response_text(event.tool_response))
        if reason:
            _open_planner_fix_loop(
                base, task_id, subagent_type.removeprefix("aiwf-"), reason
            )
    else:
        task_id = ""

    if task_id:
        from aiwf_core.core.task_records import load_task_record
        fix_loop = load_task_record(base, task_id).get("fix_loop", {}) or {}
    else:
        fix_loop = {}
    if fix_loop.get("status") == "open" and fix_loop.get("route") == "planner":
        task_label = f" for {task_id}" if task_id else ""
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
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
                "hookEventName": "PostToolUse",
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
