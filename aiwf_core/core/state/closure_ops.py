"""Closure operations — cleanup and prepare-close."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ._common import _execution_contract_frozen, _freeze_explanation, _read, _write
from .context_ops import record_role_evidence
from ..evidence_schema import trust_level_rank

def mark_cleanup_fresh(
    base_dir: str,
    resolved_notes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Set cleanup_status=fresh, clear stale items and blockers.
    Replaces stale cleanup_notes with resolved notes.
    """
    base = Path(base_dir)
    review_path = base / ".aiwf" / "quality" / "review.json"
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
    review_path = base / ".aiwf" / "quality" / "review.json"
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
    review_path = base / ".aiwf" / "quality" / "review.json"
    evidence_path = base / ".aiwf" / "evidence" / "records.json"
    testing_path = base / ".aiwf" / "quality" / "testing.json"

    state = _read(state_path)
    review = _read(review_path)
    evidence = _read(evidence_path)
    testing = _read(testing_path)

    from ..review_contract import promote_evidence
    evidence = promote_evidence(evidence, review)
    _write(evidence_path, evidence)

    blockers = []

    # 1. Phase sequence — has the workflow progressed to a closeable state?
    phase = state.get("phase", "discussing")
    if phase in ("discussing", "planned", "closed"):
        blockers.append(
            f"phase not ready for close: {phase}. "
            "Progress through planning → implementing → testing → reviewing → closing."
        )

    # 2. Evidence exists — was any work actually done and captured?
    accepted = [r for r in evidence.get("records", []) or [] if r.get("status") == "accepted"]
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
            "Re-run record-review with --closure-allowed true."
        )

    # 5. Cleanup done — has the project been cleaned up?
    if review.get("cleanup_status") != "fresh" or review.get("stale_items"):
        blockers.append(
            "cleanup not fresh. Run aiwf state mark-cleanup-fresh."
        )

    # Finalize
    passed = len(blockers) == 0
    if passed:
        state["phase"] = "closed"
        state["close_attempt"] = False
        state["closure_allowed"] = True
        _write(state_path, state)
        try:
            from ..cross_task_quality import append_task_history_from_state, write_quality_digest
            append_task_history_from_state(base_dir)
            write_quality_digest(base_dir)
        except Exception:
            pass
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
    }


def build_close_summary(base_dir: str) -> str:
    """Build a user-facing close summary. What was done and how thoroughly."""
    base = Path(base_dir)
    state = _read(base / ".aiwf" / "state" / "state.json")
    review = _read(base / ".aiwf" / "quality" / "review.json")
    testing = _read(base / ".aiwf" / "quality" / "testing.json")
    evidence = _read(base / ".aiwf" / "evidence" / "records.json")
    goal = _read(base / ".aiwf" / "state" / "goal.json")
    lines = []
    warns = []

    records = evidence.get("records", []) or []
    accepted = [r for r in records if r.get("status") == "accepted"]
    strong = sum(1 for r in records if r.get("attribution") == "strong")

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
    reids = review.get("accepted_evidence_ids", []) or []
    advs = review.get("adversarial_observations", []) or []
    lines.append(f"  Review: {rstat}" +
                 (f", examined {len(reids)} evidence records" if reids else ", examined no evidence"))
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

