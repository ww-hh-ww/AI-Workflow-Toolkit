"""Record one Tester validation pass."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _normalized_command(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).strip("` ")


def _merge_commands(previous: List[str], current: List[str]) -> List[str]:
    merged: Dict[str, str] = {}
    for command in [*previous, *current]:
        normalized = _normalized_command(command)
        if normalized:
            merged[normalized] = str(command)
    return list(merged.values())


def _merge_verification_results(
    previous: List[Dict[str, Any]], current: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    for result in [*previous, *current]:
        if not isinstance(result, dict):
            continue
        normalized = _normalized_command(result.get("command"))
        if normalized:
            merged[normalized] = dict(result)
    return list(merged.values())


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
    """Record testing, preserving valid results for an unchanged snapshot."""
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

    from ..git_snapshots import create_task_snapshot, worktree_matches_ref

    previous = task_record.get("testing", {}) or {}
    previous_ref = str(previous.get("tested_ref") or "")
    same_snapshot = bool(
        previous.get("task_id") == task_id
        and previous.get("based_on_ref") == parent_ref
        and previous_ref
        and worktree_matches_ref(worktree, previous_ref)
    )
    if same_snapshot:
        snapshot = {
            "ref": previous_ref,
            "named_ref": str(previous.get("snapshot_ref") or ""),
            "files": list(previous.get("test_changed_files", []) or []),
            "attempt": previous.get("attempt", 1),
        }
    else:
        snapshot = create_task_snapshot(
            worktree, task_id, "testing", parent_ref, summary=summary,
        )

    merged_commands = _merge_commands(
        list(previous.get("commands", []) or []) if same_snapshot else [],
        list(commands or []),
    )
    merged_results = _merge_verification_results(
        list(previous.get("verification_results", []) or []) if same_snapshot else [],
        list(verification_results or []),
    )

    unresolved_failed: Dict[str, str] = {}
    if same_snapshot:
        for command in previous.get("failed_commands", []) or []:
            normalized = _normalized_command(command)
            if normalized:
                unresolved_failed[normalized] = str(command)
    for result in verification_results or []:
        normalized = _normalized_command(result.get("command"))
        if not normalized:
            continue
        if result.get("matched") is True:
            unresolved_failed.pop(normalized, None)
        elif result.get("matched") is False:
            unresolved_failed[normalized] = str(result.get("command"))
    if status == "failed":
        for command in failed_commands or commands or []:
            normalized = _normalized_command(command)
            if normalized:
                unresolved_failed[normalized] = str(command)
    for result in merged_results:
        if result.get("matched") is False:
            normalized = _normalized_command(result.get("command"))
            if normalized:
                unresolved_failed[normalized] = str(result.get("command"))

    effective_status = "failed" if unresolved_failed else status
    testing: Dict[str, Any] = {
        "task_id": task_id,
        "status": effective_status,
        "commands": merged_commands,
        "summary": summary,
        "based_on_ref": parent_ref,
        "tested_ref": snapshot["ref"],
        "snapshot_ref": snapshot["named_ref"],
        "test_changed_files": snapshot["files"],
        "attempt": snapshot["attempt"],
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    if merged_results:
        testing["verification_results"] = merged_results
    if unresolved_failed:
        testing["failure_summary"] = (
            failure_summary
            or (str(previous.get("failure_summary") or "") if same_snapshot else "")
            or summary
        )
        testing["failed_commands"] = list(unresolved_failed.values())

    if task_id:
        try:
            from ..task_proof import testing_proof_gaps, validate_testing_against_task
            if task:
                testing["proof_validation"] = validate_testing_against_task(
                    base_dir, task, testing
                )
                if (
                    effective_status == "passed"
                    and testing_proof_gaps(testing["proof_validation"])
                ):
                    effective_status = "partial"
                    testing["status"] = "partial"
        except Exception as exc:
            testing["proof_validation"] = {"error": str(exc)}

    from .review_ops import invalidated_review

    def store(record):
        record["testing"] = testing
        record["review"] = invalidated_review(
            task_id, record.get("review", {}) or {},
        )

    update_task_record(base_dir, task_id, store)
    update_task_runtime(
        base_dir, task_id,
        phase="testing" if effective_status == "partial" else "reviewing",
    )

    if effective_status == "failed":
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
    elif effective_status in ("adequate", "passed"):
        current = (load_task_record(base_dir, task_id).get("fix_loop", {}) or {})
        if current.get("status") == "open" and current.get("route") == "tester":
            from .fixloop_ops import resolve_fix_loop

            try:
                resolve_fix_loop(
                    base_dir,
                    resolution=f"Tester verified the repair: {summary}",
                    source="tester",
                    task_id=task_id,
                )
                testing["fix_loop_resolved"] = True
                update_task_record(
                    base_dir, task_id,
                    lambda record: record["testing"].update({"fix_loop_resolved": True}),
                )
            except ValueError as exc:
                testing["fix_loop_pending_reason"] = str(exc)
                update_task_record(
                    base_dir, task_id,
                    lambda record: record["testing"].update(
                        {"fix_loop_pending_reason": str(exc)}
                    ),
                )
    return testing
