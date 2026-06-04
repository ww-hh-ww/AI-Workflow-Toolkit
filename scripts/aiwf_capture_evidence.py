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
from aiwf_core.hooks.common.evidence_writer import record_post_tool_event, check_and_record_scope_violations
from aiwf_core.hooks.common.gate_checker import load_all_state
from aiwf_core.hooks.common.snapshot import diff_snapshot, clear_snapshot, read_snapshot

def main():
    data = parse_claude_stdin()
    if not data:
        sys.exit(0)

    event = normalize(data)
    if event.tool_name not in ("Write", "Edit", "MultiEdit", "Bash"):
        sys.exit(0)

    cwd = event.cwd or str(Path.cwd())
    base = Path(cwd) if cwd else Path.cwd()

    # Try pre/post snapshot diff first (true per-operation evidence)
    snap_diff = diff_snapshot(base)
    if snap_diff["source"] == "pre_post_snapshot":
        # Use snapshot-level changed_files for evidence
        record = record_post_tool_event(
            event, str(base),
            operation_changed_files=snap_diff["changed_files"],
            op_source="pre_post_snapshot",
            op_attribution="strong",
        )
        clear_snapshot(base)
    else:
        # Fallback: dirty-set delta (weaker attribution)
        record = record_post_tool_event(event, str(base))

    # Check for scope violations using operation-level changed_files
    op_files = list(record.changed_files) if record.changed_files else []

    if op_files:
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
