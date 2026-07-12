import json, re, sys
from pathlib import Path
from aiwf_core.adapters.claude.normalize_event import parse_claude_stdin, normalize

RETURN_MARKER = re.compile(r"(?m)^\s*(RETURN_TO_PLANNER|EXTERNAL_FINDING)\b\s*:?")


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


def _open_planner_fix_loop(base, source, reason):
    path = base / ".aiwf" / "state" / "fix-loop.json"
    try:
        current = json.loads(path.read_text())
    except Exception:
        current = {}
    if current.get("status") == "open" and current.get("route") == "planner":
        return

    from aiwf_core.core.state_ops import open_fix_loop
    open_fix_loop(str(base), route="planner", reason=reason,
                  source=source or "agent")


def main():
    data = parse_claude_stdin()
    if not data:
        sys.exit(0)

    base = Path(__file__).resolve().parent.parent

    if data.get("hook_event_name") == "SubagentStop":
        agent_type = str(data.get("agent_type") or "")
        if agent_type not in {"aiwf-executor", "aiwf-tester", "aiwf-reviewer"}:
            sys.exit(0)
        reason = _return_reason(data.get("last_assistant_message"))
        if reason:
            _open_planner_fix_loop(base, agent_type.removeprefix("aiwf-"), reason)
        sys.exit(0)

    event = normalize(data)
    if event.tool_name not in ("Agent", "Task"):
        sys.exit(0)

    subagent_type = event.tool_input.get("subagent_type", "")
    if not subagent_type:
        sys.exit(0)

    if subagent_type in {"aiwf-executor", "aiwf-tester", "aiwf-reviewer"}:
        reason = _return_reason(_response_text(event.tool_response))
        if reason:
            _open_planner_fix_loop(
                base, subagent_type.removeprefix("aiwf-"), reason
            )

    try:
        state = json.loads((base / ".aiwf" / "state" / "state.json").read_text())
        active_task_id = state.get("active_task_id", "")
    except Exception:
        active_task_id = ""

    from datetime import datetime, timezone
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "subagent_type": subagent_type,
        "task_id": active_task_id or "",
        "status": "completed",
    }

    log_path = base / ".aiwf" / "runtime" / "internal" / "agent-dispatch.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    try:
        fix_loop = json.loads((base / ".aiwf" / "state" / "fix-loop.json").read_text())
    except Exception:
        fix_loop = {}
    if fix_loop.get("status") == "open" and fix_loop.get("route") == "planner":
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": (
                    "[AIWF] Stop normal progress. Load /aiwf-planner, read the returned "
                    "finding and the open fix-loop, then decide whether the active task still holds."
                ),
            }
        }))

    sys.exit(0)

if __name__ == "__main__":
    main()
