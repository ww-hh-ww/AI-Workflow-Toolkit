import json, sys
from datetime import datetime, timezone
from pathlib import Path
from aiwf_core.adapters.claude.normalize_event import parse_claude_stdin, normalize
from aiwf_core.adapters.claude.responses import allow, deny_pre_tool_use

AGENT_SKILL_MAP = {
    "aiwf-executor": "aiwf-implement",
    "aiwf-tester": "aiwf-test",
    "aiwf-reviewer": "aiwf-review",
    "aiwf-architect": "aiwf-architect",
}

def main():
    data = parse_claude_stdin()
    if not data:
        allow()

    event = normalize(data)
    if event.tool_name not in ("Agent", "Task"):
        allow()

    subagent_type = event.tool_input.get("subagent_type", "")
    if subagent_type not in AGENT_SKILL_MAP:
        allow()

    required_skill = AGENT_SKILL_MAP[subagent_type]

    base = Path(__file__).resolve().parent.parent

    try:
        state = json.loads((base / ".aiwf" / "state" / "state.json").read_text())
        active_task_id = state.get("active_task_id", "")
    except Exception:
        active_task_id = ""

    if not active_task_id:
        allow()

    # Check if required skill was loaded for this task
    log_path = base / ".aiwf" / "runtime" / "internal" / "skill-loads.jsonl"
    loaded = False
    if log_path.exists():
        for line in log_path.read_text().strip().split("\n"):
            try:
                d = json.loads(line)
                if d.get("skill") == required_skill and d.get("task_id") == active_task_id:
                    loaded = True
                    break
            except Exception:
                pass

    if not loaded:
        deny_pre_tool_use(
            f"Cannot dispatch {subagent_type}: skill not loaded.\n"
            f"  → Load /{required_skill} first, then dispatch {subagent_type}."
        )

    dispatch_path = base / ".aiwf" / "runtime" / "internal" / "agent-dispatch.jsonl"
    dispatch_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "subagent_type": subagent_type,
        "task_id": active_task_id,
        "status": "started",
    }
    with open(dispatch_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")

    allow()

if __name__ == "__main__":
    main()
