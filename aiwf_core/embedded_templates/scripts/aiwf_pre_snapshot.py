
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
