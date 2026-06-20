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

    # Only sync when AIWF governance MD files change
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
