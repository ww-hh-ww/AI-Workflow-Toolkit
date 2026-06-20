
import json, sys
from pathlib import Path
from aiwf_core.adapters.claude.normalize_event import parse_claude_stdin, normalize
from aiwf_core.hooks.common.evidence_writer import record_post_tool_event, check_and_record_scope_violations
from aiwf_core.hooks.common.snapshot import diff_snapshot, clear_snapshot

def _log(msg: str) -> None:
    print(f"[aiwf_capture_evidence] {msg}", file=sys.stderr)
    try:
        _ah_diag(msg)
    except NameError:
        pass

def main():
    data = parse_claude_stdin()
    if not data:
        _log("stdin empty, exiting")
        sys.exit(0)

    event = normalize(data)
    if event.tool_name not in ("Write", "Edit", "MultiEdit", "Bash", "Agent", "Task"):
        sys.exit(0)

    base = Path(__file__).resolve().parent.parent

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

    # Post-tool: check changed files against active Task.md's Forbidden Write
    # only when an active task exists. Without an active task, the pre-tool
    # Write guard blocks all project writes — no need to check further.
    op_files = list(record.changed_files) if record.changed_files else []

    if op_files:
        from aiwf_core.hooks.common.scope_checker import _get_task_forbidden_write
        state_data = json.loads((base / ".aiwf" / "state" / "state.json").read_text())
        task_id = state_data.get("active_task_id", "")
        if task_id:
            forbidden = _get_task_forbidden_write(base, task_id)
            if forbidden:
                check_and_record_scope_violations(
                    op_files,
                    {"id": task_id, "forbidden_write": forbidden},
                    base,
                )

    sys.exit(0)

if __name__ == "__main__":
    main()
