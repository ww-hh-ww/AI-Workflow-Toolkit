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
    _ah_diag("import aiwf_core ok")
except ImportError:
    _TK_CFG = _AH_PROJECT_ROOT / ".aiwf" / "runtime" / "internal" / "toolkit-path.txt"
    if _TK_CFG.exists():
        _TK_ROOT = _TK_CFG.read_text().strip()
        if _TK_ROOT and Path(_TK_ROOT).exists() and _TK_ROOT not in sys.path:
            sys.path.insert(0, _TK_ROOT)

import json, subprocess, sys
from pathlib import Path
from aiwf_core.adapters.claude.normalize_event import parse_claude_stdin, normalize

def main():
    data = parse_claude_stdin()
    if not data:
        sys.exit(0)

    event = normalize(data)
    if event.tool_name not in ("Write", "Edit", "MultiEdit"):
        sys.exit(0)

    file_path = event.tool_input.get("file_path", "")
    if not file_path:
        sys.exit(0)

    if not file_path.startswith(".aiwf/") or not file_path.endswith(".md"):
        sys.exit(0)

    base = Path(__file__).resolve().parent.parent
    try:
        r = subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", "sync"],
            capture_output=True, text=True, timeout=15, cwd=str(base))
        if r.returncode != 0:
            print(f"[aiwf_auto_sync] sync error: {r.stderr.strip()[:200]}", file=sys.stderr)
    except Exception as e:
        print(f"[aiwf_auto_sync] sync failed: {e}", file=sys.stderr)

    sys.exit(0)

if __name__ == "__main__":
    main()
