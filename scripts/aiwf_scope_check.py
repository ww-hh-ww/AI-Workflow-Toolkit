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
from aiwf_core.adapters.claude.normalize_event import parse_claude_stdin, normalize
from aiwf_core.hooks.common.scope_checker import check_file_write
from aiwf_core.adapters.claude.responses import allow, deny_pre_tool_use

def main():
    data = parse_claude_stdin()
    if not data:
        allow()

    event = normalize(data)
    if event.tool_name not in ("Write", "Edit", "MultiEdit"):
        allow()

    result = check_file_write(event)

    if not result.allowed:
        deny_pre_tool_use(result.reason)

    allow()

if __name__ == "__main__":
    main()
