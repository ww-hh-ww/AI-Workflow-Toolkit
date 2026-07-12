"""Record one Tester validation pass."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ._common import _read, _write


def record_testing(
    base_dir: str,
    status: str,
    commands: Optional[List[str]] = None,
    coverage_summary: str = "",
    failure_summary: str = "",
    failed_commands: Optional[List[str]] = None,
    verification_results: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Validate and replace testing.json with the current validation pass."""
    from ..state_schema import VALID_TESTING_STATUSES

    if status not in VALID_TESTING_STATUSES:
        raise ValueError(f"invalid testing status: {status}")

    base = Path(base_dir)
    testing_path = base / ".aiwf/records/testing.json"
    summary = coverage_summary or failure_summary or f"testing status={status}"
    state = _read(base / ".aiwf/state/state.json")
    task_id = str(state.get("active_task_id") or "")
    if not task_id:
        raise ValueError("testing record requires an active Task")
    from ..task_ledger import load_ledger

    task = next(
        (
            item for item in load_ledger(base_dir).get("tasks", []) or []
            if isinstance(item, dict) and item.get("id") == task_id
        ),
        None,
    )
    if not task:
        raise ValueError(f"active Task not found: {task_id}")
    implementation = _read(base / ".aiwf/records/implementation.json")
    implementation_ref = str(implementation.get("implementation_ref") or "")
    if implementation.get("task_id") != task_id:
        implementation_ref = ""
    executor_required = bool((task.get("requirements", {}) or {}).get("executor_required", True))
    if executor_required and not implementation_ref:
        raise ValueError("testing requires a current implementation record for the active Task")
    parent_ref = implementation_ref or str(task.get("git_origin_ref") or "")

    from ..git_snapshots import create_task_snapshot

    snapshot = create_task_snapshot(
        base_dir, task_id, "testing", parent_ref, summary=summary,
    )
    testing: Dict[str, Any] = {
        "task_id": task_id,
        "status": status,
        "commands": list(commands or []),
        "summary": summary,
        "based_on_ref": parent_ref,
        "tested_ref": snapshot["ref"],
        "snapshot_ref": snapshot["named_ref"],
        "test_changed_files": snapshot["files"],
        "attempt": snapshot["attempt"],
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    if verification_results:
        testing["verification_results"] = verification_results
    if status == "failed":
        testing["failure_summary"] = failure_summary or summary
        testing["failed_commands"] = list(failed_commands or commands or [])

    if task_id:
        try:
            from ..task_proof import validate_testing_against_task
            if task:
                testing["proof_validation"] = validate_testing_against_task(
                    base_dir, task, testing
                )
        except Exception as exc:
            testing["proof_validation"] = {"error": str(exc)}

    _write(testing_path, testing)

    from ..state_schema import default_review
    _write(base / ".aiwf/records/review.json", default_review(task_id))

    if state.get("phase") not in ("closing", "closed"):
        state["phase"] = "reviewing"
        _write(base / ".aiwf/state/state.json", state)

    if status == "failed":
        current = _read(base / ".aiwf/state/fix-loop.json")
        if not (current.get("status") == "open" and current.get("route") == "planner"):
            from .fixloop_ops import open_fix_loop

            open_fix_loop(
                base_dir,
                route="executor",
                reason=testing["failure_summary"],
                required_verification=testing["failed_commands"],
                source="tester",
            )
    return testing
