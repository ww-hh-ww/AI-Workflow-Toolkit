"""Closure operations — cleanup and prepare-close."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ._common import _execution_contract_frozen, _freeze_explanation, _read, _write
from .context_ops import record_role_evidence
from ..evidence_schema import trust_level_rank

def _effective_closure_evidence_ids(testing: Dict[str, Any], review: Dict[str, Any]) -> set[str]:
    """Evidence IDs that are accepted for closure even if the record is pending.

    `record-testing` and `record-review` create role evidence records. Those
    records may remain pending until review promotion, but the testing/review
    artifacts are the authoritative links for closure-level role evidence.
    """
    ids: set[str] = set()

    if testing.get("status") in ("adequate", "passed"):
        if testing.get("evidence_id"):
            ids.add(str(testing.get("evidence_id")))
        ids.update(str(eid) for eid in (testing.get("evidence_ids", []) or []) if str(eid))
        ids.update(str(eid) for eid in (testing.get("reused_evidence_ids", []) or []) if str(eid))
        ids.difference_update(
            str(eid) for eid in (testing.get("invalidated_evidence_ids", []) or []) if str(eid)
        )

    if review.get("result") == "accepted" or review.get("verdict") in ("PASS", "PASS_WITH_RISK"):
        ids.update(str(eid) for eid in (review.get("accepted_evidence_ids", []) or []) if str(eid))
        if review.get("reviewer_evidence_id"):
            ids.add(str(review.get("reviewer_evidence_id")))

    ids.discard("")
    return ids


def mark_cleanup_fresh(
    base_dir: str,
    resolved_notes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Set cleanup_status=fresh, clear stale items and blockers.
    Replaces stale cleanup_notes with resolved notes.
    """
    base = Path(base_dir)
    review_path = base / ".aiwf" / "artifacts" / "quality" / "review.json"
    review = _read(review_path)

    review["cleanup_status"] = "fresh"
    from datetime import datetime, timezone
    review["cleanup_verified_at"] = datetime.now(timezone.utc).isoformat()
    review["cleanup_blockers"] = []
    review["stale_items"] = []
    if resolved_notes is not None:
        review["cleanup_notes"] = resolved_notes
    else:
        # Keep existing notes but filter out stale-looking ones
        existing = review.get("cleanup_notes", []) or []
        review["cleanup_notes"] = [n for n in existing if "stale" not in str(n).lower()]

    _write(review_path, review)
    state_path = base / ".aiwf" / "state" / "state.json"
    state = _read(state_path)
    if state.get("phase") not in ("closing", "closed"):
        state["phase"] = "reviewing"
        _write(state_path, state)
    return review


def mark_cleanup_stale(
    base_dir: str,
    stale_items: List[str],
    blockers: Optional[List[str]] = None,
    notes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Set cleanup_status=stale with specific items and blockers."""
    base = Path(base_dir)
    review_path = base / ".aiwf" / "artifacts" / "quality" / "review.json"
    review = _read(review_path)

    review["cleanup_status"] = "stale"
    review["cleanup_verified_at"] = ""
    review["stale_items"] = stale_items
    if blockers is not None: review["cleanup_blockers"] = blockers
    if notes is not None: review["cleanup_notes"] = notes

    _write(review_path, review)
    return review


def prepare_close(base_dir: str) -> Dict[str, Any]:
    """Finalize the workflow cycle. Checks 5 process-compliance gates.

    Gates enforce that the workflow was followed — not that every field
    is populated correctly.  Mechanical detail belongs to aiwf status advisory.
    """
    base = Path(base_dir)
    state_path = base / ".aiwf" / "state" / "state.json"
    review_path = base / ".aiwf" / "artifacts" / "quality" / "review.json"
    evidence_path = base / ".aiwf" / "artifacts" / "evidence" / "records.json"
    testing_path = base / ".aiwf" / "artifacts" / "quality" / "testing.json"
    fix_loop_path = base / ".aiwf" / "state" / "fix-loop.json"

    state = _read(state_path)
    review = _read(review_path)
    evidence = _read(evidence_path)
    testing = _read(testing_path)
    fix_loop = _read(fix_loop_path)

    from ..review_contract import promote_evidence
    evidence = promote_evidence(evidence, review)
    _write(evidence_path, evidence)

    blockers = []

    # 0. Phase-gate field checks: review verdict, meta-critique, adversarial disposition
    try:
        from ..phase_gates import reviewing_to_closing_gates
        blockers.extend(reviewing_to_closing_gates(base_dir))
    except Exception:
        pass

    # 0b. Fix-loop gate: open fix-loop blocks closure unconditionally
    if fix_loop.get("status") == "open":
        blockers.append(
            "fix-loop is open — resolve or escalate before closing. "
            f"Route: {fix_loop.get('route', 'unknown')}. "
            f"Reason: {fix_loop.get('reason', 'not recorded')}"
        )

    # 1. Phase sequence — has the workflow progressed to a closeable state?
    phase = state.get("phase", "discussing")
    if phase in ("discussing", "planned", "closed"):
        blockers.append(
            f"phase not ready for close: {phase}. "
            "Progress through planning → implementing → testing → reviewing → closing."
        )

    # 2. Evidence exists — was any work actually done and captured?
    active_task_id = str(state.get("active_task_id") or "")
    effective_closure_ids = _effective_closure_evidence_ids(testing, review)
    all_accepted = [
        r for r in evidence.get("records", []) or []
        if r.get("status") == "accepted" or str(r.get("id") or "") in effective_closure_ids
    ]
    # Filter: include evidence from current task OR with no task_id (old/legacy).
    # Exclude evidence that belongs to a different task to prevent historical
    # pollution from satisfying session diversity and trust checks.
    if active_task_id:
        accepted = [
            r for r in all_accepted
            if str(r.get("task_id") or "") in ("", active_task_id)
        ]
    else:
        accepted = all_accepted
    if not accepted:
        blockers.append(
            "no accepted evidence. Run tool operations (Write/Edit/Bash) "
            "to produce machine-observed evidence."
        )

    # 2b. Trust level: L2+ requires minimum trust tier
    workflow_level = state.get("workflow_level", "L1_review_light")
    from ..evidence_schema import MIN_TRUST_FOR_CLOSURE, MIN_INDEPENDENT_SESSIONS, meets_trust_threshold
    min_trust = MIN_TRUST_FOR_CLOSURE.get(workflow_level, "role_recorded")
    trusted = [r for r in accepted if meets_trust_threshold(r.get("trust_level", "claimed"), min_trust)]
    if min_trust != "claimed" and not trusted:
        blockers.append(
            f"workflow level {workflow_level} requires at least one accepted evidence "
            f"at trust level {min_trust} or above; highest found: "
            f"{max((r.get('trust_level', 'claimed') for r in accepted), key=trust_level_rank, default='none')}"
        )

    # 2c. Session diversity: L2+ requires evidence from independent sessions
    min_sessions = MIN_INDEPENDENT_SESSIONS.get(workflow_level, 0)
    if min_sessions > 0:
        session_keys = set()
        for r in accepted:
            sid = str(r.get("session_id", "") or "").strip()
            aid = str(r.get("agent_id", "") or "").strip()
            if sid:
                session_keys.add(f"{sid}::{aid}" if aid else sid)
        if len(session_keys) < min_sessions:
            blockers.append(
                f"workflow level {workflow_level} requires evidence from at least "
                f"{min_sessions} independent sessions; found {len(session_keys)}"
            )

    # 3. Testing passed — did the Tester run AND pass?
    tstat = testing.get("status", "missing")
    if tstat == "missing":
        blockers.append(
            "testing not recorded. Run aiwf state record-testing --status passed."
        )
    elif tstat not in ("passed", "adequate"):
        blockers.append(
            f"testing status is '{tstat}', not passed/adequate. "
            "Fix the failures, re-run tests, then record-testing --status passed."
        )

    # 4. Review accepted — did the Reviewer run AND accept?
    rstat = review.get("result", "unknown")
    if rstat == "unknown":
        blockers.append(
            "review not recorded. Run aiwf state record-review --result accepted."
        )
    elif rstat != "accepted":
        blockers.append(
            f"review result is '{rstat}', not accepted. "
            "Resolve review blockers, then record-review --result accepted."
        )

    # 4b. Review must explicitly allow closure
    if rstat == "accepted" and not review.get("closure_allowed", False):
        blockers.append(
            "review result is accepted but closure_allowed is false. "
            "Re-run record-review with --verdict PASS or PASS_WITH_RISK."
        )

    from ..review_contract import quality_verdict_blockers
    blockers.extend(quality_verdict_blockers(review))

    # 5. Cleanup done — has the project been cleaned up?
    if review.get("cleanup_status") != "fresh" or review.get("stale_items"):
        blockers.append(
            "cleanup not fresh. Run aiwf state mark-cleanup-fresh."
        )

    # 6. Impact consistency — does the active plan's Impact match actual changes?
    active_task_id = state.get("active_task_id", "") or ""
    if active_task_id:
        try:
            from ..task_plan import validate_plan_impact, impact_review_check
            from ..task_ledger import load_ledger

            impact_plan_id = active_task_id
            for task in load_ledger(base_dir).get("tasks", []) or []:
                if isinstance(task, dict) and task.get("id") == active_task_id:
                    impact_plan_id = task.get("plan_id") or task.get("parent_plan") or active_task_id
                    break

            # 6a. Re-validate Impact completeness at close time
            impact_issues = validate_plan_impact(base_dir, impact_plan_id)
            if impact_issues:
                blockers.append(
                    f"Active plan Impact incomplete at close: {'; '.join(impact_issues[:3])}"
                )

            # 6b. Check Impact declarations against actual changed files
            changed_files = []
            for r in accepted:
                changed_files.extend(r.get("changed_files", []) or [])
            if changed_files:
                impact = impact_review_check(base_dir, impact_plan_id, changed_files)
                if impact.get("blockers"):
                    blockers.extend(impact["blockers"])
                # warnings are informational — surfaced in summary, not blocking
        except Exception as e:
            blockers.append(f"Impact consistency check failed: {e}")

    # 7. Post-hoc evidence cross-validation — did the work actually happen?
    # These are AFTER the pre-action gates. They verify that recorded claims
    # are traceable to actual machine evidence, not just filled-in fields.
    post_hoc_warnings: List[str] = []
    all_records = evidence.get("records", []) or []
    record_by_id = {str(r.get("id", "")): r for r in all_records if isinstance(r, dict) and r.get("id")}

    # 7a. Accepted evidence IDs must reference real records
    accepted_ids = review.get("accepted_evidence_ids", []) or []
    phantom_ids = [eid for eid in accepted_ids if str(eid) not in record_by_id]
    if phantom_ids:
        blockers.append(
            f"Post-hoc: {len(phantom_ids)} accepted evidence ID(s) reference nonexistent records: "
            f"{', '.join(str(eid) for eid in phantom_ids[:5])}. "
            f"Recovery: aiwf state record-review --verdict REVISE --blocker 'phantom-evidence' "
            f"--accepted-evidence-id <REAL-ID>, then re-run prepare-close."
        )

    # 7b. Testing commands should have trace evidence
    test_commands = testing.get("commands", []) or []
    test_evidence_ids = testing.get("evidence_ids", []) or []
    if test_commands and not test_evidence_ids:
        post_hoc_warnings.append(
            f"Testing recorded {len(test_commands)} command(s) but no evidence_ids — "
            "test commands are not traceable to machine evidence. "
            "Recovery: run aiwf state record-role-evidence --role tester --scan-git --command '<cmd>' "
            "to link test commands to evidence, or re-run aiwf state record-testing with --evidence-id."
        )
    if test_evidence_ids:
        missing_test_ev = [eid for eid in test_evidence_ids if str(eid) not in record_by_id]
        if missing_test_ev:
            post_hoc_warnings.append(
                f"Testing references {len(missing_test_ev)} evidence ID(s) that don't exist: "
                f"{', '.join(str(eid) for eid in missing_test_ev[:5])}. "
                "Recovery: re-run testing with aiwf state record-testing using real evidence IDs."
            )

    # 7c. Testing=passed with zero commands is suspicious
    if testing.get("status") == "passed" and not test_commands and not test_evidence_ids:
        post_hoc_warnings.append(
            "Testing status is 'passed' but no commands and no evidence_ids were recorded. "
            "Recovery: re-run tests and record with aiwf state record-testing --status passed "
            "--command 'pytest ...' --evidence-id <ID>, or if testing is genuinely not command-based, "
            "record manual testing evidence with aiwf state record-role-evidence --role tester."
        )

    # 7e. README.md: if it doesn't exist, remind Planner to create one.
    readme_path = base / "README.md"
    if not readme_path.exists():
        post_hoc_warnings.append(
            "README.md does not exist. Every project needs a README. "
            "Create one in the next task with Impact.docs=yes."
        )

    # 7d. Review PASS with all dimensions PASS and no adversarial observations
    verdict = review.get("verdict", "")
    if verdict in ("PASS", "PASS_WITH_RISK"):
        dims = review.get("quality_dimensions", {}) or {}
        all_pass = all(
            d.get("score") == "PASS"
            for d in (dims.values() if isinstance(dims, dict) else [])
            if isinstance(d, dict)
        )
        adv_obs = review.get("adversarial_observations", []) or []
        if all_pass and not adv_obs and verdict == "PASS":
            post_hoc_warnings.append(
                "Review verdict is PASS with all 8 quality dimensions scored PASS and zero "
                "adversarial observations. This is a valid but unusual pattern. "
                "Recovery: if review was not genuinely adversarial, open a fix-loop "
                "(aiwf fixloop open --route reviewer --reason 'insufficient-adversarial-review'), "
                "re-dispatch Reviewer with adversarial depth, then re-run prepare-close."
            )

    # 7e. Reviewer evidence ID should be traceable
    rev_ev_id = review.get("reviewer_evidence_id", "")
    if rev_ev_id and str(rev_ev_id) not in record_by_id:
        post_hoc_warnings.append(
            f"Reviewer evidence ID '{rev_ev_id}' does not match any evidence record. "
            "Recovery: re-record review with aiwf state record-review --verdict ... "
            "to generate a valid evidence ID."
        )

    # Post-hoc warnings are displayed but do NOT block closure.
    # Only phantom evidence IDs (7a) block — the rest are advisory.
    # Warnings are persisted to review.json so cross-task quality can detect
    # repeated patterns (e.g., "testing=passed no commands" 3 tasks in a row).

    # Finalize
    passed = len(blockers) == 0
    if passed:
        state["phase"] = "closing"
        state["close_attempt"] = False
        state["closure_allowed"] = True
        state["close_prepared_task_id"] = active_task_id
        state["close_prepared_at"] = datetime.now(timezone.utc).isoformat()
        _write(state_path, state)
        try:
            from ..cross_task_quality import sync_quality_escalation_state
            sync_quality_escalation_state(base_dir)
        except Exception:
            pass
        # Quality digest markdown is NOT auto-written here — Impact.quality_summary controls it
        try:
            from ..lifecycle_cleanup import auto_cleanup
            auto_cleanup(base_dir)
        except Exception:
            pass

    summary = build_close_summary(base_dir) if passed else ""

    return {
        "state": state,
        "passed": passed,
        "blockers": blockers,
        "can_proceed_to_gate": passed,
        "summary": summary,
        "post_hoc_warnings": post_hoc_warnings,
    }


def build_close_summary(base_dir: str) -> str:
    """Build a user-facing close summary. What was done and how thoroughly."""
    base = Path(base_dir)
    state = _read(base / ".aiwf" / "state" / "state.json")
    review = _read(base / ".aiwf" / "artifacts" / "quality" / "review.json")
    testing = _read(base / ".aiwf" / "artifacts" / "quality" / "testing.json")
    evidence = _read(base / ".aiwf" / "artifacts" / "evidence" / "records.json")
    goal = _read(base / ".aiwf" / "state" / "goal.json")
    lines = []
    warns = []

    records = evidence.get("records", []) or []
    accepted = [r for r in records if r.get("status") == "accepted"]
    strong = sum(1 for r in records if r.get("attribution") == "strong")

    def quality_dimension_summary(review_obj: Dict[str, Any]) -> str:
        dims = review_obj.get("quality_dimensions") or {}
        if not isinstance(dims, dict) or not dims:
            return "quality dimensions not scored"
        counts = {"PASS": 0, "RISK": 0, "FAIL": 0}
        non_pass = []
        for name, value in dims.items():
            score = value.get("score") if isinstance(value, dict) else str(value)
            score = score if score in counts else "UNKNOWN"
            if score in counts:
                counts[score] += 1
            if score != "PASS":
                non_pass.append(f"{name}={score}")
        summary = f"quality dimensions PASS={counts['PASS']} RISK={counts['RISK']} FAIL={counts['FAIL']}"
        if non_pass:
            summary += " (" + ", ".join(non_pass[:5]) + ")"
        return summary

    def review_basis_summary(review_obj: Dict[str, Any]) -> str:
        from ..state_schema import REVIEW_BASIS
        basis = review_obj.get("review_basis") or {}
        if not isinstance(basis, dict) or not basis:
            return "review basis not recorded"
        counts = {"covered": 0, "gap": 0, "not_applicable": 0, "missing": 0}
        exceptions = []
        for name in REVIEW_BASIS:
            value = basis.get(name, {})
            status = value.get("status") if isinstance(value, dict) else "missing"
            if status not in counts:
                status = "missing"
            counts[status] += 1
            if status != "covered":
                exceptions.append(f"{name}={status}")
        summary = (
            f"review basis covered={counts['covered']} gap={counts['gap']} "
            f"not_applicable={counts['not_applicable']} missing={counts['missing']}"
        )
        if exceptions:
            summary += " (" + ", ".join(exceptions[:5]) + ")"
        return summary

    # ── What Was Done ──
    lines.append("## What Was Done")

    # Evidence — human terms
    sessions = set()
    for r in accepted:
        sid = str(r.get("session_id", "") or "").strip()
        aid = str(r.get("agent_id", "") or "").strip()
        if sid:
            sessions.add(f"{sid}::{aid}" if aid else sid)
    evidence_quality = "solid" if strong >= len(records) * 0.7 else \
                       "mixed" if strong > 0 else "unverifiable"
    lines.append(f"  Work captured: {len(records)} operations, {evidence_quality} evidence "
                 f"({strong} machine-captured, {len(records) - strong} inferred or manual)")
    if strong == 0 and records:
        warns.append("No machine-captured evidence — all work claims are unverifiable")

    # Testing
    tstat = testing.get("status", "missing")
    tcmds = testing.get("commands", []) or []
    teids = testing.get("evidence_ids", []) or []
    fs_stat = testing.get("full_suite_status", "not_run")
    ru_stat = testing.get("real_usage_status", "not_run")
    test_line = f"  Tests: {tstat}"
    if tcmds:
        test_line += f", {len(tcmds)} runs recorded"
    if teids:
        test_line += f", linked to evidence"
    elif tcmds:
        test_line += f", not linked to evidence"
    lines.append(test_line)
    if tstat == "missing":
        warns.append("No testing recorded")
    if fs_stat == "not_run":
        warns.append("Full test suite was not run")
    if ru_stat == "not_run":
        warns.append("User-facing entrypoint was not tested")
    if tcmds and not teids:
        warns.append("Test results cannot be traced to actual command executions")

    # Review
    rstat = review.get("result", "unknown")
    verdict = review.get("verdict", "pending")
    reids = review.get("accepted_evidence_ids", []) or []
    advs = review.get("adversarial_observations", []) or []
    lines.append(f"  Review: {rstat}, verdict={verdict}" +
                 (f", examined {len(reids)} evidence records" if reids else ", examined no evidence"))
    if verdict not in ("", "pending", None):
        lines.append(f"  Quality verdict: {quality_dimension_summary(review)}")
        lines.append(f"  Review basis: {review_basis_summary(review)}")
    if rstat == "accepted" and not reids:
        warns.append("Reviewer approved without examining any evidence")
    if rstat == "unknown":
        warns.append("No review recorded")

    # Cleanup + docs
    cstat = review.get("cleanup_status", "unknown")
    lines.append(f"  Cleanup: {'done' if cstat == 'fresh' else cstat}")
    try:
        from ..current_state import current_state_freshness
        cs = current_state_freshness(base_dir)
        cs_stat = cs.get("status", "?")
        lines.append(f"  Project docs: {'up to date' if cs_stat == 'fresh' else 'stale'}")
        if cs_stat != "fresh":
            warns.append("Project documentation may be stale — Planner should refresh README and docs/")
    except Exception:
        pass

    # ── What Changed ──
    lines.append("")
    lines.append("## What Changed")
    changed_files = set()
    for r in records:
        for f in (r.get("changed_files", []) or []):
            changed_files.add(f)
    if changed_files:
        for f in sorted(changed_files)[:20]:
            lines.append(f"  {f}")
        if len(changed_files) > 20:
            lines.append(f"  ... and {len(changed_files) - 20} more")
    else:
        lines.append("  (no changes recorded)")

    # ── Pay Attention To ──
    if warns:
        lines.append("")
        lines.append("## Pay Attention To")
        for w in warns:
            lines.append(f"  - {w}")

    return "\n".join(lines)


def cancel_close(base_dir: str) -> Dict[str, Any]:
    """Reset close_attempt and related flags to recover from a stuck closing state.

    This is the safety valve when close is prepared but later discovered
    to be invalid — failed tests, rejected review, missing evidence, etc.
    Without this, the task activation gate stays frozen.
    """
    base = Path(base_dir)
    state_path = base / ".aiwf" / "state" / "state.json"
    state = _read(state_path)

    was_closed = state.get("phase") == "closed"
    state["close_attempt"] = False
    state["closure_allowed"] = False
    if state.get("phase") in ("closing", "closed"):
        state["phase"] = "reviewing"
    _write(state_path, state)

    message = (
        "close cancelled: phase reverted to reviewing, task activation unblocked."
        if was_closed
        else "close attempt cancelled: close_attempt=False, task activation unblocked."
    )
    return {"message": message, "state": state}
