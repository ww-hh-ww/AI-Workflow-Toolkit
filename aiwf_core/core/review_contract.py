"""Backend-neutral review contract.

Defines what constitutes a valid review and how review state is updated.
No Claude-specific logic.
"""
from __future__ import annotations

from typing import Any, Dict, List


def is_review_complete(review: Dict[str, Any]) -> bool:
    """Check if review.json has been written with a result."""
    return review.get("result", "unknown") != "unknown"


def is_closure_allowed(review: Dict[str, Any]) -> bool:
    """Check if review explicitly allows closure."""
    return bool(review.get("closure_allowed", False))


def review_blockers(review: Dict[str, Any]) -> List[str]:
    """Return current review blockers."""
    return review.get("blockers", []) or []


def set_review_accepted(
    review: Dict[str, Any],
    accepted_evidence_ids: List[str],
    rejected_evidence_ids: List[str],
) -> Dict[str, Any]:
    """Update review to accepted state."""
    review["result"] = "accepted"
    review["closure_allowed"] = True
    review["accepted_evidence_ids"] = accepted_evidence_ids
    review["rejected_evidence_ids"] = rejected_evidence_ids
    review["blockers"] = []
    return review


def set_review_rejected(
    review: Dict[str, Any],
    result: str,
    blockers: List[str],
    rejected_evidence_ids: List[str],
) -> Dict[str, Any]:
    """Update review to a rejected/blocking state."""
    review["result"] = result
    review["closure_allowed"] = False
    review["blockers"] = blockers
    review["rejected_evidence_ids"] = rejected_evidence_ids
    return review


def add_scope_violation_blocker(review: Dict[str, Any], file_path: str, context_id: str) -> Dict[str, Any]:
    """Add a scope violation blocker to the review."""
    review["closure_allowed"] = False
    blockers = review.setdefault("blockers", [])
    msg = f"scope_violation: '{file_path}' modified outside {context_id} scope"
    if msg not in blockers:
        blockers.append(msg)
    if review.get("result", "unknown") not in ("scope_violation", "rejected"):
        review["result"] = "scope_violation"
    return review


def promote_evidence(evidence: Dict[str, Any], review: Dict[str, Any]) -> Dict[str, Any]:
    """Promote evidence records based on review's accepted/rejected IDs.

    - Records in accepted_evidence_ids → status = "accepted"
    - Records in rejected_evidence_ids → status = "rejected"
    - Other records remain unchanged.

    Returns the updated evidence dict.
    """
    accepted_ids = set(review.get("accepted_evidence_ids", []) or [])
    rejected_ids = set(review.get("rejected_evidence_ids", []) or [])

    if not accepted_ids and not rejected_ids:
        return evidence

    records = evidence.get("records", [])
    if not isinstance(records, list):
        return evidence

    for record in records:
        if not isinstance(record, dict):
            continue
        rid = record.get("id", "")
        if rid in accepted_ids:
            record["status"] = "accepted"
        elif rid in rejected_ids:
            record["status"] = "rejected"

    return evidence


def has_pending_adversarial_observations(review: Dict[str, Any]) -> bool:
    """Check if review has adversarial observations pending Planner disposition."""
    obs = review.get("adversarial_observations", []) or []
    return any(
        o.get("disposition") == "pending"
        for o in obs if isinstance(o, dict)
    )


def promote_and_save(base_dir, evidence_path, review_path):
    """Load evidence + review, promote, and write back. Returns updated evidence."""
    import json
    from pathlib import Path

    base = Path(base_dir)
    ev_path = base / evidence_path if not str(evidence_path).startswith(str(base)) else Path(evidence_path)
    rv_path = base / review_path if not str(review_path).startswith(str(base)) else Path(review_path)

    if not ev_path.exists() or not rv_path.exists():
        return None

    try:
        evidence = json.loads(ev_path.read_text(encoding="utf-8"))
        review = json.loads(rv_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    result = promote_evidence(evidence, review)
    ev_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result
