
import json, sys
from pathlib import Path
from aiwf_core.hooks.common.snapshot import take_snapshot
from aiwf_core.adapters.claude.normalize_event import parse_claude_stdin, normalize

def _log(msg: str) -> None:
    print(f"[aiwf_pre_snapshot] {msg}", file=sys.stderr)

def main():
    cwd = Path.cwd()
    tool_name = "unknown"
    tool_input = {}
    data = parse_claude_stdin()
    if data:
        try:
            event = normalize(data)
            cwd = Path(event.cwd or str(Path.cwd()))
            tool_name = event.tool_name or tool_name
            tool_input = event.tool_input or tool_input
            _log(f"stdin ok, tool={tool_name} cwd={cwd}")
        except Exception as exc:
            _log(f"normalize failed: {exc}, falling back to cwd={cwd}")
    else:
        _log(f"stdin empty, using cwd={cwd}")
    snap = take_snapshot(cwd, tool_name, tool_input)
    _log(f"snapshot written: {snap.get('file_count', 0)} files")
    sys.exit(0)

if __name__ == "__main__":
    main()
