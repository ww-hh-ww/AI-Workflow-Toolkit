#!/usr/bin/env python3
"""AIWF hook script — uses backend-neutral core behind Claude adapter."""
import sys
from pathlib import Path
# Bootstrap: add AIWF toolkit to path so aiwf_core is importable
_AH_ROOT = Path(__file__).resolve().parent.parent
if str(_AH_ROOT) not in sys.path:
    sys.path.insert(0, str(_AH_ROOT))

import json, sys
from pathlib import Path
from aiwf_core.hooks.common.snapshot import take_snapshot
from aiwf_core.adapters.claude.normalize_event import parse_claude_stdin, normalize

def main():
    data = parse_claude_stdin()
    if not data:
        sys.exit(0)
    event = normalize(data)
    cwd = Path(event.cwd or str(Path.cwd()))
    take_snapshot(cwd, event.tool_name, event.tool_input)
    sys.exit(0)

if __name__ == "__main__":
    main()
