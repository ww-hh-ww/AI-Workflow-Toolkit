"""Record one independent Reviewer judgment."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ._common import BLOCKING_REVIEW_RESULTS, _read, _write


def record_review(
    base_dir: str,
    result: str,
    closure_allowed: bool = False,
    blockers: Optional[List[str]] = None,
    adversarial_observations: Optional[List[Dict[str, Any]]] = None,
    cleanup_status: str = "",
    structure_status: str = "",
    summary: str = "",
) -> Dict[str, Any]:
    """Validate and replace review.json with the current review judgment."""
    from ..state_schema import VALID_REVIEW_RESULTS

    if result not in VALID_REVIEW_RESULTS or result == "unknown":
        raise ValueError(f"invalid review result: {result}")

    base = Path(base_dir)
    review_path = base / ".aiwf/records/review.json"
    state_path = base / ".aiwf/state/state.json"
    state = _read(state_path)
    task_id = str(state.get("active_task_id") or "")
    testing = _read(base / ".aiwf/records/testing.json")
    tested_ref = str(testing.get("tested_ref") or "")
    if not task_id:
        raise ValueError("review requires an active Task")
    if testing.get("task_id") != task_id or not tested_ref:
        raise ValueError("review requires a current tested snapshot for the active Task")

    from ..git_snapshots import worktree_matches_ref

    if not worktree_matches_ref(base_dir, tested_ref):
        raise ValueError("project files changed after testing; record testing again before review")

    observations = list(adversarial_observations or [])
    unresolved_high = [
        item for item in observations
        if isinstance(item, dict) and item.get("severity") in ("critical", "high")
    ]
    if result == "accepted" and unresolved_high:
        raise ValueError("critical/high observations cannot be accepted")

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
    _write(review_path, review)

    if state.get("phase") not in ("closing", "closed"):
        state["phase"] = "closing"
        _write(state_path, state)

    if result in BLOCKING_REVIEW_RESULTS:
        current = _read(base / ".aiwf/state/fix-loop.json")
        if not (current.get("status") == "open" and current.get("route") == "planner"):
            from .fixloop_ops import open_fix_loop

            open_fix_loop(
                base_dir,
                route="executor",
                reason=review["summary"],
                required_fixes=review["blockers"],
                source="reviewer",
            )
    return review
