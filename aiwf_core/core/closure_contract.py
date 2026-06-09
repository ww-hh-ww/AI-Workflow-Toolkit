"""Backend-neutral closure contract.

Defines closure gate conditions and how they are evaluated.
No Claude-specific logic.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List


def _session_diversity_key(record: Dict[str, Any]) -> str:
    """Compound key for session diversity: session_id + agent_id if subagent.

    A Planner session and its subagents each count as distinct "sessions"
    for diversity. An empty agent_id means the main/Planner agent.
    """
    sid = str(record.get("session_id", "") or "").strip()
    aid = str(record.get("agent_id", "") or "").strip()
    if not sid:
        return ""
    if aid:
        return f"{sid}::{aid}"
    return sid


def accepted_evidence_session_ids(
    evidence: Dict[str, Any],
    context_id: str = "",
) -> List[str]:
    """Return distinct session diversity keys from accepted evidence records.

    When context_id is provided, only records matching that context are
    counted — each task's session diversity is independent of history.
    Agent identity (subagent vs Planner) is included in the key so that
    Planner, Tester, and Reviewer each count as distinct sessions.
    """
    records = evidence.get("records", [])
    if not isinstance(records, list):
        return []
    seen = []
    for record in records:
        if not isinstance(record, dict) or record.get("status") != "accepted":
            continue
        if context_id and record.get("context_id") != context_id:
            continue
        key = _session_diversity_key(record)
        if key and key not in seen:
            seen.append(key)
    return seen


def session_diversity_required(state: Dict[str, Any]) -> bool:
    """Independent session evidence is mechanical for L2/L3, not for light flows."""
    return state.get("workflow_level") in ("L2_standard_team", "L3_full_power")


def evidence_session_diversity_ok(
    state: Dict[str, Any],
    evidence: Dict[str, Any],
    context_id: str = "",
) -> bool:
    if not session_diversity_required(state):
        return True
    return len(accepted_evidence_session_ids(evidence, context_id=context_id)) >= 3


def closure_conditions_met(
    state: Dict[str, Any],
    evidence: Dict[str, Any],
    testing: Dict[str, Any],
    review: Dict[str, Any],
    fix_loop: Dict[str, Any],
) -> Dict[str, Any]:
    """Evaluate the 5 process-compliance closure gates.

    Mirrors prepare_close — same 5 gates. The Stop hook uses this
    to independently re-validate before allowing closure.
    """
    close_attempt = bool(state.get("close_attempt", False))
    evidence_records = evidence.get("records", []) or []
    blockers = []
    missing = []

    if close_attempt or state.get("phase") == "closed":
        if not evidence_records:
            blockers.append("no evidence records")
            missing.append("evidence")
        elif not any(r.get("status") == "accepted" for r in evidence_records if isinstance(r, dict)):
            blockers.append("no accepted evidence")
            missing.append("accepted evidence")

        if testing.get("status", "missing") == "missing":
            blockers.append("testing not recorded")
            missing.append("testing")

        if review.get("result", "unknown") == "unknown":
            blockers.append("review not recorded")
            missing.append("review")

        if review.get("cleanup_status") != "fresh" or review.get("stale_items"):
            blockers.append("cleanup not fresh")
            missing.append("cleanup")

    passed = bool(
        (close_attempt and not blockers)
        or state.get("phase") == "closed"
    )

    return {
        "passed": passed,
        "blockers": blockers,
        "missing": missing,
    }


