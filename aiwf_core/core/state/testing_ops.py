"""Record one Tester validation pass."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

def record_testing(
    base_dir: str,
    status: str,
    commands: Optional[List[str]] = None,
    coverage_summary: str = "",
    failure_summary: str = "",
    failed_commands: Optional[List[str]] = None,
    verification_results: Optional[List[Dict[str, Any]]] = None,
    task_id: str = "",
) -> Dict[str, Any]:
    """Validate and replace one Task's testing record."""
    from ..state_schema import VALID_TESTING_STATUSES

    if status not in VALID_TESTING_STATUSES:
        raise ValueError(f"invalid testing status: {status}")

    base = Path(base_dir)
    summary = coverage_summary or failure_summary or f"testing status={status}"
    from ..task_ledger import load_ledger, resolve_active_task_id, update_task_runtime
    from ..task_records import load_task_record, update_task_record
    from ..worktree_context import resolve_worktree_root, same_path

    task_id = resolve_active_task_id(base_dir, task_id)
    if not task_id:
        raise ValueError("testing record requires an active Task")

    task = next(
        (
            item for item in load_ledger(base_dir).get("tasks", []) or []
            if isinstance(item, dict) and item.get("id") == task_id
        ),
        None,
    )
    if not task:
        raise ValueError(f"active Task not found: {task_id}")
    worktree = str(task.get("worktree_path") or "")
    if not worktree or not same_path(resolve_worktree_root(base), worktree):
        raise ValueError(f"run testing in Task {task_id}'s assigned worktree")
    task_record = load_task_record(base_dir, task_id)
    implementation = task_record.get("implementation", {}) or {}
    implementation_ref = str(implementation.get("implementation_ref") or "")
    if implementation.get("task_id") != task_id:
        implementation_ref = ""
    executor_required = bool((task.get("requirements", {}) or {}).get("executor_required", True))
    if executor_required and not implementation_ref:
        raise ValueError("testing requires a current implementation record for the active Task")
    parent_ref = implementation_ref or str(task.get("git_origin_ref") or "")

    from ..git_snapshots import create_task_snapshot

    snapshot = create_task_snapshot(
        worktree, task_id, "testing", parent_ref, summary=summary,
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

    from ..state_schema import default_review

    def store(record):
        record["testing"] = testing
        record["review"] = default_review(task_id)

    update_task_record(base_dir, task_id, store)
    update_task_runtime(base_dir, task_id, phase="reviewing")

    if status == "failed":
        current = (load_task_record(base_dir, task_id).get("fix_loop", {}) or {})
        if not (current.get("status") == "open" and current.get("route") == "planner"):
            from .fixloop_ops import open_fix_loop

            open_fix_loop(
                base_dir,
                route="executor",
                reason=testing["failure_summary"],
                required_verification=testing["failed_commands"],
                source="tester",
                task_id=task_id,
            )
    return testing
