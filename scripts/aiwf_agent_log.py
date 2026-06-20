#!/usr/bin/env python3
import sys, os
from pathlib import Path

_AH_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_AH_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AH_PROJECT_ROOT))

def _ah_diag(msg: str) -> None:
    try:
        _dp = _AH_PROJECT_ROOT / ".aiwf" / "runtime" / "internal"
        _dp.mkdir(parents=True, exist_ok=True)
        with open(_dp / "hook-diag.log", "a") as _df:
            import datetime
            _df.write(f"{datetime.datetime.now().isoformat()} [{os.path.basename(__file__)}] {msg}\n")
    except Exception:
        pass

try:
    import aiwf_core
except ImportError:
    _TK_CFG = _AH_PROJECT_ROOT / ".aiwf" / "runtime" / "internal" / "toolkit-path.txt"
    if _TK_CFG.exists():
        _TK_ROOT = _TK_CFG.read_text().strip()
        if _TK_ROOT and Path(_TK_ROOT).exists() and _TK_ROOT not in sys.path:
            sys.path.insert(0, _TK_ROOT)

import json, sys
from pathlib import Path
from aiwf_core.adapters.claude.normalize_event import parse_claude_stdin, normalize

def main():
    data = parse_claude_stdin()
    if not data:
        sys.exit(0)

    event = normalize(data)
    if event.tool_name not in ("Agent", "Task"):
        sys.exit(0)

    subagent_type = event.tool_input.get("subagent_type", "")
    if not subagent_type:
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
        "subagent_type": subagent_type,
        "task_id": active_task_id or "",
    }

    log_path = base / ".aiwf" / "runtime" / "internal" / "agent-dispatch.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as f:
        f.write(json.dumps(entry) + "\n")

    sys.exit(0)

if __name__ == "__main__":
    main()
