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
    """Evaluate all closure gates and return a GateResult-like dict.

    Returns dict with:
      passed, evidence_exists, evidence_accepted, testing_adequate,
      review_accepted, fix_loop_open, scope_violation, close_attempt,
      blockers, missing
    """
    close_attempt = bool(state.get("close_attempt", False))

    evidence_records = evidence.get("records", [])
    if not isinstance(evidence_records, list):
        evidence_records = []

    evidence_exists = len(evidence_records) > 0
    evidence_accepted = any(
        r.get("status") == "accepted" for r in evidence_records if isinstance(r, dict)
    )
    session_diversity_ok = evidence_session_diversity_ok(
        state, evidence, context_id=state.get("active_context_id", "")
    )

    testing_status = testing.get("status", "missing")
    testing_adequate = testing_status in ("adequate", "passed")

    review_accepted = review.get("result") == "accepted" and review.get("closure_allowed", False)

    fix_loop_open = fix_loop.get("status") == "open"

    scope_violation = bool(state.get("scope_violation", False))

    cleanup_status = review.get("cleanup_status", "unknown")
    stale_items = review.get("stale_items", []) or []
    cleanup_blockers_list = review.get("cleanup_blockers", []) or []
    cleanup_fresh = (
        cleanup_status == "fresh"
        and len(stale_items) == 0
        and len(cleanup_blockers_list) == 0
    )

    structure_status = review.get("structure_status", "unknown")
    structure_accepted = structure_status == "accepted"

    blockers = []
    missing = []

    if not close_attempt:
        # Not attempting to close — nothing to check
        pass
    else:
        if not evidence_exists:
            blockers.append("no evidence records")
            missing.append("evidence")
        if not evidence_accepted:
            blockers.append("no accepted evidence")
            missing.append("accepted evidence")
        if not session_diversity_ok:
            if state.get("planner_inline_session"):
                pass  # Planner explicitly waived via set-planner-inline
            else:
                count = len(accepted_evidence_session_ids(
                    evidence, context_id=state.get("active_context_id", "")
                ))
                blockers.append(
                    f"L2/L3 require accepted evidence from at least 3 distinct sessions; found {count}"
                )
                missing.append("independent session evidence")
        if not testing_adequate:
            blockers.append("testing not adequate")
            missing.append("testing")
        if not review_accepted:
            blockers.append("review not accepted")
            missing.append("accepted review")
        if fix_loop_open:
            blockers.append("fix-loop is open")
            missing.append("fix-loop resolution")
        if scope_violation:
            blockers.append("scope violation detected")
            missing.append("scope violation resolution")
        if not cleanup_fresh:
            if cleanup_status == "fresh" and len(stale_items) > 0:
                blockers.append("cleanup_status=fresh but stale_items is not empty")
            elif cleanup_status == "fresh" and len(cleanup_blockers_list) > 0:
                blockers.append("cleanup_status=fresh but cleanup_blockers is not empty")
            else:
                blockers.append("cleanup not fresh")
            missing.append("cleanup review")
        if not structure_accepted:
            blockers.append("structure review not accepted")
            missing.append("structure review")
        # Pending adversarial observations block closure
        from .review_contract import has_pending_adversarial_observations
        if has_pending_adversarial_observations(review):
            pending_count = sum(
                1 for o in (review.get("adversarial_observations", []) or [])
                if isinstance(o, dict) and o.get("disposition") == "pending"
            )
            blockers.append(f"{pending_count} adversarial observation(s) pending Planner disposition")
            missing.append("adversarial disposition")

    passed = bool(close_attempt and not blockers)

    return {
        "passed": passed,
        "evidence_exists": evidence_exists,
        "evidence_accepted": evidence_accepted,
        "session_diversity_ok": session_diversity_ok,
        "testing_adequate": testing_adequate,
        "review_accepted": review_accepted,
        "fix_loop_open": fix_loop_open,
        "scope_violation": scope_violation,
        "cleanup_fresh": cleanup_fresh,
        "structure_accepted": structure_accepted,
        "close_attempt": close_attempt,
        "blockers": blockers,
        "missing": missing,
    }


def closure_resume_audit(base_dir: str) -> Dict[str, Any]:
    """Return closure-resume gaps using existing state/report files only.

    This is intentionally conservative: strict resume checks apply only to
    L2/L3 flows after review has accepted closure. L0/L1 remain lightweight.
    """
    import json

    root = Path(base_dir)
    aiwf = root / ".aiwf"

    def _rj(rel: str, default=None) -> Dict[str, Any]:
        path = aiwf / rel
        try:
            return json.loads(path.read_text(encoding="utf-8")) if path.exists() else (default or {})
        except Exception:
            return default or {}

    state = _rj("state/state.json", {})
    review = _rj("quality/review.json", {})
    goal = _rj("state/goal.json", {})
    evidence = _rj("evidence/records.json", {"records": []})
    testing = _rj("quality/testing.json", {})
    level = state.get("workflow_level", "L1_review_light")
    review_accepted = review.get("result") == "accepted" and bool(review.get("closure_allowed"))
    strict = level in ("L2_standard_team", "L3_full_power") and review_accepted

    missing: List[str] = []
    blockers: List[str] = []
    warnings: List[str] = []

    if not strict:
        return {
            "status": "not_required",
            "strict": False,
            "blockers": blockers,
            "missing": missing,
            "warnings": warnings,
        }

    decisions = goal.get("decisions", []) or []
    structured_meta = goal.get("meta_critique", {}) or {}
    has_meta_critique = (
        structured_meta.get("status") == "completed"
        and str(structured_meta.get("recorded_by", "")).lower() == "planner"
        and bool(str(structured_meta.get("summary", "")).strip())
    ) or any(
        isinstance(d, dict)
        and "meta" in str(d.get("decision", "")).lower()
        and "critique" in str(d.get("decision", "")).lower()
        and str(d.get("source", "")).lower() == "planner"
        for d in decisions
    )
    if not has_meta_critique:
        blockers.append("missing Planner-sourced meta-critique decision after accepted review")
        missing.append("planner meta-critique")

    records = evidence.get("records", []) or []
    if not isinstance(records, list):
        records = []
    records_by_id = {
        str(r.get("id", "")): r for r in records if isinstance(r, dict) and r.get("id")
    }
    accepted_ids = [str(eid) for eid in (review.get("accepted_evidence_ids", []) or []) if str(eid)]
    if not accepted_ids:
        blockers.append("review accepted closure without accepted_evidence_ids")
        missing.append("review evidence provenance")
    accepted_records = []
    for eid in accepted_ids:
        rec = records_by_id.get(eid)
        if not rec:
            blockers.append(f"accepted evidence id not found: {eid}")
            missing.append("review evidence provenance")
            continue
        if rec.get("trust") != "machine_observed":
            blockers.append(f"accepted evidence is not machine_observed: {eid}")
            missing.append("machine-observed evidence")
        accepted_records.append(rec)

    # Preferred: evidence IDs directly reference accepted machine evidence.
    test_evidence_ids = [
        str(eid).strip() for eid in (testing.get("evidence_ids", []) or [])
        if str(eid).strip()
    ]
    if test_evidence_ids:
        # Include auto-accepted records, not just Reviewer's accepted_evidence_ids.
        all_accepted = {r.get("id", "") for r in records if r.get("status") == "accepted"}
        backed_ids = [eid for eid in test_evidence_ids if eid in all_accepted]
        if not backed_ids:
            blockers.append(
                f"testing evidence IDs ({', '.join(test_evidence_ids[:5])}) "
                "not found among accepted machine evidence"
            )
            missing.append("testing evidence ID provenance")
    else:
        # Fallback: substring match on command strings.
        test_commands = [
            str(cmd).strip() for cmd in (testing.get("commands", []) or [])
            if str(cmd).strip()
        ]
        if not test_commands:
            blockers.append("testing.json has no test commands")
            missing.append("testing command provenance")
        else:
            # Use ALL accepted machine-observed records (including auto-accepted),
            # not just the Reviewer's accepted_evidence_ids.
            successful_evidence_commands = {
                str(r.get("command", "")).strip()
                for r in records
                if r.get("status") == "accepted"
                and r.get("trust") == "machine_observed"
                and r.get("exit_code") == 0
                and str(r.get("command", "")).strip()
            }
            has_backed_test_command = any(
                any(tc in ec for ec in successful_evidence_commands)
                for tc in test_commands
            )
            if not has_backed_test_command:
                blockers.append("testing commands are not backed by accepted successful machine evidence")
                missing.append("testing command evidence")

    from .review_contract import has_pending_adversarial_observations
    if has_pending_adversarial_observations(review):
        blockers.append("adversarial observations still pending Planner disposition")
        missing.append("adversarial disposition")

    quality_digest = aiwf / "reports" / "质量摘要.md"
    if not quality_digest.exists():
        blockers.append("quality digest missing; run aiwf quality digest before prepare-close")
        missing.append("quality digest")

    project_map = aiwf / "reports" / "项目地图.md"
    if not project_map.exists():
        blockers.append("PROJECT-MAP missing; run aiwf project-map init/update before prepare-close")
        missing.append("project map")
    else:
        try:
            pm_text = project_map.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            pm_text = ""
        if "Planner TODO:" in pm_text or "Unknown yet." in pm_text:
            blockers.append("PROJECT-MAP still has default Planner TODO/Unknown content")
            missing.append("curated project map")

    from .current_state import current_state_freshness
    cs = current_state_freshness(base_dir)
    if cs.get("status") != "fresh":
        blockers.append(f"current-state.md not fresh: {cs.get('status', 'missing')}")
        missing.append("fresh current-state")

    return {
        "status": "passed" if not blockers else "blocked",
        "strict": True,
        "blockers": blockers,
        "missing": missing,
        "warnings": warnings,
    }


def set_close_attempt(state: Dict[str, Any]) -> Dict[str, Any]:
    """Mark state as attempting closure."""
    state["close_attempt"] = True
    state["phase"] = "closing"
    return state


def set_closure_complete(state: Dict[str, Any]) -> Dict[str, Any]:
    """Mark state as closed."""
    state["closure_allowed"] = True
    state["phase"] = "closed"
    state["close_attempt"] = False
    return state
