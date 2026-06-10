"""Review operations — record_review."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ._common import _execution_contract_frozen, _freeze_explanation, _read, _write
from ._common import BLOCKING_REVIEW_RESULTS
from .context_ops import record_role_evidence

def record_review(
    base_dir: str,
    result: str,
    closure_allowed: bool = False,
    accepted_evidence_ids: Optional[List[str]] = None,
    rejected_evidence_ids: Optional[List[str]] = None,
    blockers: Optional[List[str]] = None,
    adversarial_observations: Optional[List[Dict[str, Any]]] = None,
    cleanup_status: str = "",
    structure_status: str = "",
    summary: str = "",
    context_id: str = "",
    cleanup_code: str = "",
    docs_checked: str = "",
    root_cause: str = "",
) -> Dict[str, Any]:
    """Write review.json through a command and append reviewer role evidence."""
    from ..state_schema import VALID_REVIEW_RESULTS
    if result not in VALID_REVIEW_RESULTS or result == "unknown":
        raise ValueError(f"invalid review result: {result}")
    base = Path(base_dir)
    review_path = base / ".aiwf" / "quality" / "review.json"
    state = _read(base / ".aiwf" / "state" / "state.json")
    review = _read(review_path)

    review["result"] = result
    review["closure_allowed"] = bool(closure_allowed and result == "accepted")
    review["accepted_evidence_ids"] = list(accepted_evidence_ids or [])
    review["rejected_evidence_ids"] = list(rejected_evidence_ids or [])
    review["blockers"] = list(blockers or [])
    if adversarial_observations is not None:
        review["adversarial_observations"] = adversarial_observations
    if cleanup_status:
        review["cleanup_status"] = cleanup_status
    if structure_status:
        review["structure_status"] = structure_status
    if cleanup_code:
        review["cleanup_code"] = cleanup_code
    if docs_checked:
        review["docs_checked"] = docs_checked
    if root_cause:
        review["root_cause"] = root_cause

    ev = record_role_evidence(
        base_dir,
        "reviewer",
        summary=summary or f"review result={result}",
        command="aiwf state record-review",
        context_id=context_id or state.get("active_context_id") or "",
        status="pending",
        exit_code=0 if result == "accepted" else 1,
    )
    if result == "accepted" and ev["id"] not in review["accepted_evidence_ids"]:
        review["accepted_evidence_ids"].append(ev["id"])
    review["reviewer_evidence_id"] = ev["id"]

    if result != "accepted":
        from ..review_contract import set_review_rejected
        set_review_rejected(review, result, blockers or [], rejected_evidence_ids or [])

    _write(review_path, review)
    if state.get("phase") not in ("closing", "closed"):
        state["phase"] = "reviewing"
        _write(base / ".aiwf" / "state" / "state.json", state)
    return review

