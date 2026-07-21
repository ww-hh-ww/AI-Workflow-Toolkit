"""Record one independent Reviewer judgment."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ._common import BLOCKING_REVIEW_RESULTS


def invalidated_review(task_id: str, previous: Dict[str, Any]) -> Dict[str, Any]:
    """Invalidate the verdict while keeping observations available to Planner."""
    from ..state_schema import default_review

    review = default_review(task_id)
    review["adversarial_observations"] = [
        dict(item)
        for item in (previous.get("adversarial_observations", []) or [])
        if isinstance(item, dict)
    ]
    return review


def _merge_observations(
    previous: List[Dict[str, Any]], current: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    merged = [dict(item) for item in previous if isinstance(item, dict)]
    signatures = {
        (item.get("severity"), item.get("kind"), item.get("message"))
        for item in merged
    }
    next_id = max(
        [
            int(str(item.get("id") or "").removeprefix("ADV-"))
            for item in merged
            if str(item.get("id") or "").removeprefix("ADV-").isdigit()
        ]
        or [0]
    )
    for item in current:
        if not isinstance(item, dict):
            continue
        signature = (item.get("severity"), item.get("kind"), item.get("message"))
        if signature in signatures:
            continue
        next_id += 1
        added = dict(item)
        added["id"] = f"ADV-{next_id:03d}"
        added.setdefault("disposition", "pending")
        merged.append(added)
        signatures.add(signature)
    return merged


def record_review(
    base_dir: str,
    result: str,
    closure_allowed: bool = False,
    blockers: Optional[List[str]] = None,
    adversarial_observations: Optional[List[Dict[str, Any]]] = None,
    cleanup_status: str = "",
    structure_status: str = "",
    summary: str = "",
    task_id: str = "",
) -> Dict[str, Any]:
    """Validate and replace one Task's review judgment."""
    from ..state_schema import VALID_REVIEW_RESULTS

    if result not in VALID_REVIEW_RESULTS or result == "unknown":
        raise ValueError(f"invalid review result: {result}")

    base = Path(base_dir)
    from ..task_ledger import load_ledger, resolve_active_task_id, update_task_runtime
    from ..task_records import load_task_record, update_task_record
    from ..worktree_context import resolve_control_root, resolve_worktree_root, same_path

    task_id = resolve_active_task_id(base_dir, task_id)
    task_record = load_task_record(base_dir, task_id) if task_id else {}
    testing = task_record.get("testing", {}) or {}
    tested_ref = str(testing.get("tested_ref") or "")
    if not task_id:
        raise ValueError("review requires an active Task")
    if testing.get("task_id") != task_id or not tested_ref:
        raise ValueError("review requires a current tested snapshot for the active Task")
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
        raise ValueError(f"run review in Task {task_id}'s assigned worktree")

    from ..git_snapshots import worktree_matches_ref

    if not worktree_matches_ref(worktree, tested_ref):
        raise ValueError("project files changed after testing; record testing again before review")

    observations = _merge_observations(
        list((task_record.get("review", {}) or {}).get("adversarial_observations", []) or []),
        list(adversarial_observations or []),
    )
    unresolved_high = [
        item for item in observations
        if (
            isinstance(item, dict)
            and item.get("severity") in ("critical", "high")
            and item.get("disposition") != "resolved"
        )
    ]
    if result == "accepted" and unresolved_high:
        raise ValueError("critical/high observations cannot be accepted")

    from ..index_ops import remove_narrative_section

    task_doc = resolve_control_root(base) / ".aiwf" / "tasks" / f"{task_id}.md"
    remove_narrative_section(task_doc, "Closure Calibration")

    review: Dict[str, Any] = {
        "task_id": task_id,
        "result": result,
        "closure_allowed": result == "accepted" and bool(closure_allowed),
        "blockers": list(blockers or []),
        "summary": summary.strip() or f"review result={result}",
        "reviewed_ref": tested_ref,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    if observations:
        review["adversarial_observations"] = observations
    if result == "accepted":
        review["cleanup_status"] = cleanup_status or "fresh"
        review["structure_status"] = structure_status or "sound"
    else:
        if cleanup_status:
            review["cleanup_status"] = cleanup_status
        if structure_status:
            review["structure_status"] = structure_status
    update_task_record(base_dir, task_id, lambda record: record.__setitem__("review", review))
    update_task_runtime(base_dir, task_id, phase="closing")

    if result in BLOCKING_REVIEW_RESULTS:
        current = (load_task_record(base_dir, task_id).get("fix_loop", {}) or {})
        if not (current.get("status") == "open" and current.get("route") == "planner"):
            from .fixloop_ops import open_fix_loop

            open_fix_loop(
                base_dir,
                route="executor",
                reason=review["summary"],
                required_fixes=review["blockers"],
                source="reviewer",
                task_id=task_id,
            )
    return review
