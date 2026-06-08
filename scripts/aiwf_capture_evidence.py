#!/usr/bin/env python3
import sys
from pathlib import Path

# Add project root to sys.path for project-local imports.
_AH_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_AH_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AH_PROJECT_ROOT))

# Discover aiwf_core at runtime — no hardcoded paths.
# 1. Pip-installed aiwf_core is importable directly.
# 2. Otherwise, read the toolkit path recorded by aiwf install.
try:
    import aiwf_core  # noqa: F401
except ImportError:
    _TK_CFG = _AH_PROJECT_ROOT / ".aiwf" / "internal" / "toolkit-path.txt"
    if _TK_CFG.exists():
        _TK_ROOT = _TK_CFG.read_text().strip()
        if _TK_ROOT and Path(_TK_ROOT).exists() and _TK_ROOT not in sys.path:
            sys.path.insert(0, _TK_ROOT)
import json, sys
from pathlib import Path
from aiwf_core.adapters.claude.normalize_event import parse_claude_stdin, normalize
from aiwf_core.hooks.common.evidence_writer import record_post_tool_event, check_and_record_scope_violations, check_and_record_missing_active_task
from aiwf_core.hooks.common.gate_checker import load_all_state
from aiwf_core.hooks.common.snapshot import diff_snapshot, clear_snapshot, read_snapshot

def _log(msg: str) -> None:
    print(f"[aiwf_capture_evidence] {msg}", file=sys.stderr)

def main():
    data = parse_claude_stdin()
    if not data:
        _log("stdin empty, exiting")
        sys.exit(0)

    event = normalize(data)
    if event.tool_name not in ("Write", "Edit", "MultiEdit", "Bash", "Agent", "Task"):
        sys.exit(0)

    cwd = event.cwd or str(Path.cwd())
    base = Path(cwd) if cwd else Path.cwd()

    # Try pre/post snapshot diff first (true per-operation evidence)
    snap_diff = diff_snapshot(base)
    if snap_diff["source"] == "pre_post_snapshot":
        _log(f"snapshot diff found, changed_files={len(snap_diff['changed_files'])}")
        record = record_post_tool_event(
            event, str(base),
            operation_changed_files=snap_diff["changed_files"],
            op_source="pre_post_snapshot",
            op_attribution="strong",
        )
        clear_snapshot(base)
        _log(f"evidence recorded: id={record.id} tool={event.tool_name} attribution=strong changed={len(record.changed_files or [])}")
    else:
        _log(f"snapshot unavailable, source={snap_diff['source']}, falling back to dirty-set delta")
        record = record_post_tool_event(event, str(base))
        _log(f"evidence recorded: id={record.id} tool={event.tool_name} attribution=weak changed={len(record.changed_files or [])}")

    # Check for scope violations using operation-level changed_files
    op_files = list(record.changed_files) if record.changed_files else []

    if op_files:
        check_and_record_missing_active_task(op_files, base)
        state = load_all_state(base)
        active_ctx_id = state["state"].get("active_context_id")
        if active_ctx_id:
            for ctx in state["contexts"].get("contexts", []):
                if ctx.get("id") == active_ctx_id:
                    check_and_record_scope_violations(op_files, ctx, base)
                    break

    sys.exit(0)

if __name__ == "__main__":
    main()
