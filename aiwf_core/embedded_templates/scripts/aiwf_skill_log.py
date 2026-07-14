import json, sys
from pathlib import Path
from aiwf_core.adapters.claude.normalize_event import parse_claude_stdin, normalize
from aiwf_core.core.state._common import _exclusive_operation_lock
from aiwf_core.core.worktree_context import resolve_control_root

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

    base = resolve_control_root(Path(__file__).resolve().parent.parent)
    from datetime import datetime, timezone
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "skill": skill_name,
        "session_id": event.session_id,
    }

    log_path = base / ".aiwf" / "runtime" / "internal" / "skill-loads.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with _exclusive_operation_lock(str(base), "skill-loads", timeout=2):
        with open(log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    sys.exit(0)

if __name__ == "__main__":
    main()
