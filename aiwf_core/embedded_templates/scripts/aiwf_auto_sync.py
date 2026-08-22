import json, subprocess, sys
from pathlib import Path
from aiwf_core.adapters.claude.normalize_event import parse_claude_stdin, normalize
from aiwf_core.core.agent_worktree import apply_patch_paths

def main():
    data = parse_claude_stdin()
    if not data:
        sys.exit(0)

    event = normalize(data)
    if event.tool_name not in ("Write", "Edit", "MultiEdit", "apply_patch"):
        sys.exit(0)

    file_paths = (
        apply_patch_paths(event.tool_input)
        if event.tool_name == "apply_patch"
        else [str(event.tool_input.get("file_path") or "")]
    )
    if not any(file_paths):
        sys.exit(0)

    # Only sync when AIWF governance MD files change
    base = Path(__file__).resolve().parent.parent
    governance_changed = False
    for file_path in file_paths:
        path = Path(file_path).expanduser()
        try:
            relative = path.resolve().relative_to(base) if path.is_absolute() else path
        except ValueError:
            continue
        normalized = relative.as_posix()
        if normalized.startswith(".aiwf/") and normalized.endswith(".md"):
            governance_changed = True
            break
    if not governance_changed:
        sys.exit(0)

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
