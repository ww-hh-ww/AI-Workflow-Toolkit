"""Record the current Executor implementation handoff."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional



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

    from ..task_ledger import update_task_runtime

    update_task_runtime(str(base), task_id, scope_violation=True)
    return violations


def record_implementation(
    base_dir: str,
    summary: str,
    verification_results: Optional[List[Dict[str, Any]]] = None,
    task_id: str = "",
) -> Dict[str, Any]:
    """Record one stable Executor candidate with complete Task V-ID evidence."""
    from ..git_snapshots import create_task_snapshot
    from ..task_ledger import load_ledger, resolve_active_task_id, update_task_runtime
    from ..task_records import load_task_record, update_task_record
    from ..worktree_context import resolve_worktree_root, same_path

    base = Path(base_dir)
    active_task_id = resolve_active_task_id(base_dir, task_id)
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
    worktree = str(task.get("worktree_path") or "")
    if not worktree or not same_path(resolve_worktree_root(base), worktree):
        raise ValueError(f"run the implementation record in Task {active_task_id}'s assigned worktree")

    task_record = load_task_record(base_dir, active_task_id)
    prior_implementation = task_record.get("implementation", {}) or {}
    origin_ref = str(task.get("git_origin_ref") or "")
    parent_ref = str(
        prior_implementation.get("implementation_ref")
        or origin_ref
    )
    from ..experiment_records import list_experiments

    live_experiments = [
        item for item in list_experiments(base_dir, task_id=active_task_id)
        if item.get("status") in ("open", "running", "recorded")
    ]
    if live_experiments:
        item = live_experiments[0]
        raise ValueError(
            "finish current empirical work before replacing the stable implementation: "
            f"{item.get('experiment_id')} is {item.get('status')}"
        )

    from ..task_proof import (
        construction_proof_gaps,
        proof_contract_fingerprint,
        validate_implementation_against_task,
    )

    candidate_evidence = {
        "task_id": active_task_id,
        "verification_results": list(verification_results or []),
        "proof_contract_fingerprint": proof_contract_fingerprint(base_dir, task),
    }
    proof = validate_implementation_against_task(base_dir, task, candidate_evidence)
    gaps = construction_proof_gaps(proof)
    if gaps:
        raise ValueError(
            "implementation proof is incomplete: " + "; ".join(gaps[:8])
        )
    snapshot = create_task_snapshot(
        worktree, active_task_id, "implementation", parent_ref, summary=summary,
    )

    violations: List[str] = []
    try:
        from ...hooks.common.scope_checker import _get_task_forbidden_write

        forbidden = _get_task_forbidden_write(base, active_task_id)
        if forbidden:
            violations = _check_forbidden_write_violations(
                snapshot["files"], forbidden, Path(worktree), active_task_id,
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
        "verification_results": list(verification_results or []),
        "proof_contract_fingerprint": candidate_evidence["proof_contract_fingerprint"],
        "proof_validation": proof,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    from ..review_contract import add_scope_violation_blocker
    from .review_ops import invalidated_review

    def store(task_record):
        task_record["implementation"] = record
        task_record["review"] = invalidated_review(
            active_task_id, task_record.get("review", {}) or {},
        )
        if violations:
            fix_loop = task_record.get("fix_loop", {}) or {}
            fix_loop.update({
                "status": "open",
                "route": "planner",
                "reason": "Forbidden Write violation",
                "required_fixes": [
                    f"Revert: {path} - matched Forbidden Write from {active_task_id}.md"
                    for path in violations
                ],
            })
            task_record["fix_loop"] = fix_loop
            for path in violations:
                add_scope_violation_blocker(task_record["review"], path, active_task_id)
        else:
            fix_loop = task_record.get("fix_loop", {}) or {}
            if fix_loop.get("status") == "open" and fix_loop.get("route") == "executor":
                fix_loop["route"] = "reviewer"
                task_record["fix_loop"] = fix_loop

    update_task_record(base_dir, active_task_id, store)
    from ..experiment_records import stale_post_implementation_experiments

    stale_ids = stale_post_implementation_experiments(
        base_dir, active_task_id, record["implementation_ref"],
    )
    if stale_ids:
        record["stale_experiment_ids"] = stale_ids
        update_task_record(
            base_dir, active_task_id,
            lambda task_record: task_record["implementation"].update(
                {"stale_experiment_ids": stale_ids}
            ),
        )
    update_task_runtime(base_dir, active_task_id, phase="reviewing")
    return record
