"""Record the current Executor implementation handoff."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from ._common import _read, _write


def _check_forbidden_write_violations(
    changed_files: List[str], forbidden_patterns: List[str], base: Path, task_id: str,
) -> List[str]:
    from ...hooks.common.diff_snapshot import filter_internal
    from ..scope_policy import _matches

    violations = [
        path for path in filter_internal(changed_files, cwd=base)
        if any(_matches(path, pattern) for pattern in forbidden_patterns)
    ]
    if not violations:
        return []

    state_path = base / ".aiwf/state/state.json"
    state = _read(state_path)
    state["scope_violation"] = True
    _write(state_path, state)

    from ..review_contract import add_scope_violation_blocker
    from ..state_schema import default_fix_loop, default_review

    fix_path = base / ".aiwf/state/fix-loop.json"
    fix_loop = _read(fix_path) or default_fix_loop()
    if fix_loop.get("status") != "open":
        fix_loop["status"] = "open"
        fix_loop["required_fixes"] = [
            f"Revert: {path} - matched Forbidden Write from {task_id}.md"
            for path in violations
        ]
        fix_loop["route"] = "planner"
        _write(fix_path, fix_loop)

    review_path = base / ".aiwf/records/review.json"
    review = _read(review_path) or default_review()
    for path in violations:
        add_scope_violation_blocker(review, path, task_id)
    _write(review_path, review)
    return violations


def record_implementation(
    base_dir: str,
    summary: str,
    command: str = "",
    exit_code: int = 0,
    task_id: str = "",
) -> Dict[str, Any]:
    """Replace implementation.json and preserve the implementation snapshot."""
    from ..git_snapshots import create_task_snapshot
    from ..task_ledger import load_ledger

    base = Path(base_dir)
    state_path = base / ".aiwf/state/state.json"
    state = _read(state_path)
    active_task_id = str(task_id or state.get("active_task_id") or "")
    if not active_task_id:
        raise ValueError("implementation record requires an active Task")
    task = next(
        (
            item for item in load_ledger(base_dir).get("tasks", []) or []
            if isinstance(item, dict) and item.get("id") == active_task_id
        ),
        None,
    )
    if not task:
        raise ValueError(f"active Task not found: {active_task_id}")

    prior_testing = _read(base / ".aiwf/records/testing.json")
    prior_implementation = _read(base / ".aiwf/records/implementation.json")
    origin_ref = str(task.get("git_origin_ref") or state.get("git_origin_ref") or "")
    parent_ref = str(
        prior_testing.get("tested_ref")
        or prior_implementation.get("implementation_ref")
        or origin_ref
    )
    snapshot = create_task_snapshot(
        base_dir, active_task_id, "implementation", parent_ref, summary=summary,
    )

    try:
        from ...hooks.common.scope_checker import _get_task_forbidden_write

        forbidden = _get_task_forbidden_write(base, active_task_id)
        if forbidden:
            _check_forbidden_write_violations(
                snapshot["files"], forbidden, base, active_task_id,
            )
    except Exception:
        pass

    record: Dict[str, Any] = {
        "task_id": active_task_id,
        "summary": summary.strip()[:1000],
        "implementation_ref": snapshot["ref"],
        "snapshot_ref": snapshot["named_ref"],
        "based_on_ref": snapshot["parent_ref"],
        "changed_files": snapshot["files"],
        "attempt": snapshot["attempt"],
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    if command:
        record["command"] = command[:1000]
        record["exit_code"] = exit_code
    _write(base / ".aiwf/records/implementation.json", record)

    from ..state_schema import default_review, default_testing

    _write(base / ".aiwf/records/testing.json", default_testing(active_task_id))
    _write(base / ".aiwf/records/review.json", default_review(active_task_id))
    state["phase"] = "testing"
    _write(state_path, state)
    return record
