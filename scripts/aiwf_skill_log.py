import json, sys
from pathlib import Path
from aiwf_core.adapters.claude.normalize_event import parse_claude_stdin, normalize

SKILL_AGENT_MAP = {
    "aiwf-implement": "aiwf-executor",
    "aiwf-test": "aiwf-tester",
    "aiwf-review": "aiwf-reviewer",
}

def main():
    data = parse_claude_stdin()
    if not data:
        sys.exit(0)

    event = normalize(data)
    if event.tool_name != "Skill":
        sys.exit(0)

    skill_name = event.tool_input.get("skill", "")
    if skill_name not in SKILL_AGENT_MAP:
        sys.exit(0)

    base = Path(__file__).resolve().parent.parent
    try:
        state = json.loads((base / ".aiwf" / "state" / "state.json").read_text())
        active_task_id = state.get("active_task_id", "")
    except Exception:
        active_task_id = ""

    from datetime import datetime, timezone
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "skill": skill_name,
        "task_id": active_task_id or "",
    }

    log_path = base / ".aiwf" / "runtime" / "internal" / "skill-loads.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as f:
        f.write(json.dumps(entry) + "\n")

    sys.exit(0)

if __name__ == "__main__":
    main()
