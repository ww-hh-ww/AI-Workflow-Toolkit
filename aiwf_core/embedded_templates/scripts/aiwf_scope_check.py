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
