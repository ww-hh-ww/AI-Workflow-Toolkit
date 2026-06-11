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
    result: str = "",
    verdict: str = "",
    quality_dimensions: Optional[Dict[str, Any]] = None,
    review_basis: Optional[Dict[str, Any]] = None,
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
    """Write review.json through a command and append reviewer role evidence.

    V2: accepts verdict (PASS/PASS_WITH_RISK/REVISE/REJECT) and quality_dimensions.
    V1 backward-compat: accepts result (accepted/needs_fix/rejected/...).
    When verdict is provided, result and closure_allowed are derived from it.
    """
    from ..state_schema import (
        VALID_REVIEW_RESULTS, VALID_REVIEW_VERDICTS, VERDICT_TO_RESULT,
        VERDICT_CLOSURE, QUALITY_DIMENSIONS, REVIEW_BASIS,
    )

    # V2 path: verdict drives result and closure
    if verdict:
        if verdict not in VALID_REVIEW_VERDICTS:
            raise ValueError(f"invalid verdict: {verdict} (valid: {', '.join(sorted(VALID_REVIEW_VERDICTS))})")
        result = VERDICT_TO_RESULT.get(verdict, "unknown")
        closure_allowed = VERDICT_CLOSURE.get(verdict, False)
    elif result:
        if result not in VALID_REVIEW_RESULTS or result == "unknown":
            raise ValueError(f"invalid review result: {result}")
    else:
        raise ValueError("either verdict or result is required")

    base = Path(base_dir)
    review_path = base / ".aiwf" / "quality" / "review.json"
    state = _read(base / ".aiwf" / "state" / "state.json")
    review = _read(review_path)

    review["verdict"] = verdict or "pending"
    review["result"] = result
    review["closure_allowed"] = bool(closure_allowed)
    review["accepted_evidence_ids"] = list(accepted_evidence_ids or [])
    review["rejected_evidence_ids"] = list(rejected_evidence_ids or [])
    review["blockers"] = list(blockers or [])

    # V2 quality dimensions
    if quality_dimensions:
        dims = review.setdefault("quality_dimensions", {})
        for dim_name in QUALITY_DIMENSIONS:
            if dim_name in quality_dimensions:
                entry = quality_dimensions[dim_name]
                if isinstance(entry, dict):
                    dims[dim_name] = {
                        "score": entry.get("score", "unscored"),
                        "note": str(entry.get("note", "") or ""),
                    }

    # V2 review basis
    if review_basis:
        basis = review.setdefault("review_basis", {})
        for basis_name in REVIEW_BASIS:
            if basis_name in review_basis:
                entry = review_basis[basis_name]
                if isinstance(entry, dict):
                    basis[basis_name] = {
                        "status": entry.get("status", "missing"),
                        "note": str(entry.get("note", "") or ""),
                    }

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

    summary_text = summary or f"review verdict={verdict or result}"
    ev = record_role_evidence(
        base_dir,
        "reviewer",
        summary=summary_text,
        command="aiwf state record-review",
        context_id=context_id or state.get("active_context_id") or "",
        status="pending",
        exit_code=0 if (verdict in ("PASS", "PASS_WITH_RISK") or result == "accepted") else 1,
    )
    if (verdict in ("PASS", "PASS_WITH_RISK") or result == "accepted") and ev["id"] not in review["accepted_evidence_ids"]:
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
