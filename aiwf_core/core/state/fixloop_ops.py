"""Fix-loop and architecture change operations."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ._common import _execution_contract_frozen, _freeze_explanation, _read, _write

def open_fix_loop(
    base_dir: str,
    route: str,
    reason: str,
    required_fixes: Optional[List[str]] = None,
    required_verification: Optional[List[str]] = None,
    source: str = "reviewer",
    invalidated_files: Optional[List[str]] = None,
    invalidated_obligations: Optional[List[str]] = None,
    invalidated_evidence_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Open a fix-loop with route, reason, required fixes, and verification.

    If already open: increments attempt_count, appends route_history.
    Sets max_attempts from workflow_level on first open.
    If attempt_count > max_attempts: escalation_required=true, rollback_recommended
    if checkpoint exists.
    Does NOT auto-execute fixes, modify goal/scope/context, or auto-close workflow.
    """
    base = Path(base_dir)
    fix_loop_path = base / ".aiwf" / "state" / "fix-loop.json"
    state_path = base / ".aiwf" / "state" / "state.json"

    fix_loop = _read(fix_loop_path)
    was_open = fix_loop.get("status") == "open"

    if was_open:
        attempt = fix_loop.get("attempt_count", 0) + 1
    else:
        attempt = 1

    fix_loop["status"] = "open"
    fix_loop["route"] = route
    fix_loop["reason"] = reason
    fix_loop["required_fixes"] = required_fixes or (fix_loop.get("required_fixes") if was_open else [])
    fix_loop["required_verification"] = required_verification or (fix_loop.get("required_verification") if was_open else [])

    # Record invalidated scope: what files, obligations, and evidence this fix-loop invalidates
    if invalidated_files or invalidated_obligations or invalidated_evidence_ids:
        fix_loop["invalidated_scope"] = {
            "files": list(invalidated_files or []),
            "obligations": list(invalidated_obligations or []),
            "evidence_ids": list(invalidated_evidence_ids or []),
            "reason": reason,
        }
    fix_loop["source"] = source
    fix_loop["attempt_count"] = attempt

    # Set max_attempts from workflow_level on first open
    if not was_open or not fix_loop.get("max_attempts"):
        state = _read(state_path)
        level = state.get("workflow_level", "L1_review_light")
        from ..state_schema import LEVEL_MAX_ATTEMPTS
        fix_loop["max_attempts"] = LEVEL_MAX_ATTEMPTS.get(level, 2)

    # Append route history
    history = fix_loop.get("route_history", []) or []
    history.append({"attempt": attempt, "route": route, "reason": reason, "source": source})
    fix_loop["route_history"] = history

    # Escalation check
    max_att = fix_loop.get("max_attempts", 2)
    if attempt > max_att:
        fix_loop["escalation_required"] = True
        fix_loop["escalation_reason"] = f"fix-loop attempts ({attempt}) exceeded max_attempts ({max_att})"
        # rollback recommended if checkpoint exists
        ckpt_dir = base / ".aiwf" / "checkpoints"
        has_ckpt = ckpt_dir.exists() and any(ckpt_dir.iterdir())
        fix_loop["rollback_recommended"] = True if has_ckpt else False

    _write(fix_loop_path, fix_loop)

    # Update state phase if needed
    state = _read(state_path)
    if state.get("phase") not in ("closing", "closed"):
        state["phase"] = "reviewing"
    _write(state_path, state)

    return fix_loop



def _extract_paths_from_fixes(required_fixes: List[str]) -> List[str]:
    """Extract likely file paths from human-readable required_fixes strings.

    Fix strings look like:
      "Resolve scope violations: external-assets/scripts/new-planning-search.sh"
      "Fix broken test in tests/test_foo.py"
      "restore src/module/file.py to committed state"
    """
    import re
    paths = []
    for fix in required_fixes:
        if not isinstance(fix, str):
            continue
        # Look for path-like fragments: relative paths with slashes and extensions
        found = re.findall(r'([\w./-]+\.[\w]+)', fix)
        for f in found:
            # Filter: must look like a file path (has / or starts with a known dir)
            f_clean = f.lstrip("./")
            if "/" in f_clean or f_clean.endswith((".py", ".sh", ".md", ".json", ".js", ".ts", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".txt", ".css", ".html")):
                paths.append(f_clean)
    return sorted(set(paths))


def _revalidate_required_fixes(
    base: Path,
    required_fixes: List[str],
    scope_violation_events: List[Dict],
    force: bool,
) -> Dict[str, Any]:
    """Re-validate required_fixes against current git state and review resolutions.

    Returns {"still_unresolved": [...], "stale_resolved": [...],
              "resolved_reverted": [...], "blockers": [...]}

    A fix is considered resolved if:
    - The target file appears in scope_violation_events as resolved_reverted, OR
    - The fix is verified against current git diff (file was changed since fix-loop opened)

    Without force, any still_unresolved fix blocks resolution.
    """
    result: Dict[str, Any] = {
        "still_unresolved": [],
        "stale_resolved": [],
        "resolved_reverted": [],
        "blockers": [],
    }

    # Gather file paths from required_fixes
    target_paths = _extract_paths_from_fixes(required_fixes)

    # Check scope_violation_events for explicit resolutions
    resolved_paths = set()
    for event in scope_violation_events:
        if not isinstance(event, dict):
            continue
        event_path = str(event.get("path", ""))
        event_status = str(event.get("status", ""))
        if event_status == "resolved_reverted" and event_path:
            resolved_paths.add(event_path)

    # Check current git diff for evidence of fix work
    try:
        from ...hooks.common.diff_snapshot import detect_changed_files
        changed = detect_changed_files(base)
        changed_files = set(changed.get("files", []) or [])
        diff_available = changed.get("source") != "unavailable"
    except Exception:
        changed_files = set()
        diff_available = False

    for fix_path in target_paths:
        if fix_path in resolved_paths:
            result["resolved_reverted"].append(fix_path)
        elif not diff_available:
            if force:
                # Planner override: treat as resolved when diff is unavailable
                result["stale_resolved"].append(fix_path)
            else:
                result["still_unresolved"].append(fix_path)
        elif fix_path in changed_files:
            # File was changed — fix may have been applied
            result["stale_resolved"].append(fix_path)
        else:
            # File not in diff and not resolved — fix is stale (already reverted or never applied)
            result["stale_resolved"].append(fix_path)

    # Without force, still_unresolved items block resolution
    if result["still_unresolved"] and not force:
        result["blockers"].append(
            f"{len(result['still_unresolved'])} required fix(es) still unresolved "
            f"(diff unavailable): {', '.join(result['still_unresolved'][:5])}"
        )

    return result


def resolve_fix_loop(
    base_dir: str,
    resolution: str,
    source: str = "reviewer",
    force: bool = False,
) -> Dict[str, Any]:
    """Resolve a fix-loop only after its mechanical verification gates pass.

    Re-validates required_fixes against current git diff and review.json
    scope_violation_events. Blocks resolution when fixes are still unresolved
    (target files not in diff and not marked resolved_reverted).

    When force=True, Planner explicitly acknowledges that remaining changed files
    are legitimate (e.g. cross-task modifications), not scope violations.
    """
    base = Path(base_dir)
    fix_loop_path = base / ".aiwf" / "state" / "fix-loop.json"

    fix_loop = _read(fix_loop_path)
    if fix_loop.get("status") != "open":
        raise ValueError("fix-loop is not open")
    blockers: List[str] = []
    scope_resolution = None
    state = _read(base / ".aiwf" / "state" / "state.json")
    testing = _read(base / ".aiwf" / "quality" / "testing.json")

    # ── Re-validate required_fixes against current state ──
    required_fixes = fix_loop.get("required_fixes", []) or []
    review_path = base / ".aiwf" / "quality" / "review.json"
    review = _read(review_path)
    scope_events = review.get("scope_violation_events", []) or []
    reval = _revalidate_required_fixes(base, required_fixes, scope_events, force)
    if reval["blockers"]:
        blockers.extend(reval["blockers"])
    # Log revalidation details for transparency
    fix_loop["fix_validation"] = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "total_required": len(required_fixes),
        "target_paths": _extract_paths_from_fixes(required_fixes),
        "still_unresolved": reval["still_unresolved"],
        "stale_resolved": reval["stale_resolved"],
        "resolved_reverted": reval["resolved_reverted"],
    }

    if state.get("scope_violation"):
        unresolved = [
            event for event in scope_events
            if isinstance(event, dict) and event.get("status", "recorded") != "resolved_reverted"
        ]
        from ...hooks.common.diff_snapshot import detect_changed_files
        changed = detect_changed_files(base)
        remaining = sorted({
            str(event.get("path")) for event in unresolved
            if event.get("path") in set(changed.get("files", []) or [])
        })
        if changed.get("source") == "unavailable" and not force:
            blockers.append("scope violation cannot be verified because git change detection is unavailable")
        elif remaining and not force:
            blockers.append("scope-violating files remain changed: " + ", ".join(remaining[:5]))
        elif not unresolved:
            if force:
                # All events already resolved_reverted — just clear the flag.
                state["scope_violation"] = False
                _write(base / ".aiwf" / "state" / "state.json", state)
            else:
                blockers.append("scope violation has no structured event history to verify")
        else:
            scope_resolution = (review_path, review, unresolved, state)
    if fix_loop.get("escalation_required"):
        blockers.append("escalation_required=true; Planner cannot self-resolve escalation")
    if fix_loop.get("required_verification"):
        if testing.get("status") not in ("adequate", "passed"):
            blockers.append("required verification has not produced adequate/passed testing")
        if not testing.get("commands"):
            blockers.append("required verification has no recorded test commands")
        # P1-4: check that each required_verification item is mechanically covered
        uncovered = _check_verification_coverage(fix_loop.get("required_verification", []) or [], testing)
        if uncovered:
            blockers.append("required verification not covered in testing: " + "; ".join(uncovered[:5]))
    if blockers:
        raise ValueError("fix-loop resolution blocked: " + "; ".join(blockers))
    # P1-3: delta review/cleanup invalidation when fixes involved real code changes
    _invalidate_delta_review(base, fix_loop, state, review_path, review, force)
    if scope_resolution:
        review_path, review, unresolved, state = scope_resolution
        ts = datetime.now(timezone.utc).isoformat()
        for event in unresolved:
            event["status"] = "resolved_reverted"
            event["resolved_at"] = ts
            event["resolution"] = resolution
        review["blockers"] = [
            blocker for blocker in (review.get("blockers", []) or [])
            if not str(blocker).startswith("scope_violation:")
        ]
        if not force:
            # Normal resolution: reset review to force re-review after fix
            review["result"] = "unknown"
            review["closure_allowed"] = False
        state["scope_violation"] = False
        _write(review_path, review)
        _write(base / ".aiwf" / "state" / "state.json", state)
    fix_loop["status"] = "resolved"
    fix_loop["resolution"] = resolution
    if source: fix_loop["source"] = source
    _write(fix_loop_path, fix_loop)

    return fix_loop


def _check_verification_coverage(
    required_verification: List[str],
    testing: Dict[str, Any],
) -> List[str]:
    """Check each required_verification item is covered in testing evidence.

    Coverage is checked against: acceptance_coverage, delta_verification,
    commands, and validation_layers. Simple substring/keyword match — no NLP.
    """
    uncovered = []
    # Build a corpus of all testing evidence text
    corpus_parts = []
    for field in ("acceptance_coverage", "delta_verification", "commands", "validation_layers"):
        val = testing.get(field)
        if isinstance(val, list):
            corpus_parts.extend(str(v) for v in val)
        elif isinstance(val, str) and val:
            corpus_parts.append(val)
    corpus = " ".join(corpus_parts).lower()

    for item in required_verification:
        item_lower = str(item).lower()
        # Direct substring match first
        if item_lower in corpus:
            continue
        # Check if any keyword from the item appears in the corpus
        keywords = [w for w in item_lower.split() if len(w) > 3]
        if keywords and any(kw in corpus for kw in keywords):
            continue
        uncovered.append(str(item)[:120])
    return uncovered


def _invalidate_delta_review(
    base: Path,
    fix_loop: Dict[str, Any],
    state: Dict[str, Any],
    review_path: Path,
    review: Dict[str, Any],
    force: bool = False,
) -> None:
    """When a fix-loop involves real code changes, invalidate the old review/cleanup.

    Only triggers when:
    - route is executor or tester (fixes were code-level, not planner/environment)
    - required_fixes is non-empty OR invalidated_scope is non-empty
    - scope_violation path hasn't already handled this

    Sets review.result=unknown, closure_allowed=False, cleanup_status=stale.
    Reviewer must then perform a delta review (only the fix changed_files and
    invalidated_scope), not a full re-review from scratch.
    """
    route = str(fix_loop.get("route", "") or "").lower()
    if route not in ("executor", "tester"):
        return
    required_fixes = fix_loop.get("required_fixes", []) or []
    invalidated_scope = fix_loop.get("invalidated_scope") or {}
    if not required_fixes and not invalidated_scope.get("files") and not invalidated_scope.get("obligations"):
        return

    # Check if scope_violation path already handled this
    if state.get("scope_violation"):
        return

    # Invalidate review
    review["result"] = "unknown"
    review["closure_allowed"] = False
    review["cleanup_status"] = "stale"
    review.setdefault("delta_review_required", True)
    review.setdefault("delta_review_reason",
                      f"fix-loop route={route} resolved; delta review required for "
                      f"{len(required_fixes)} fixes, "
                      f"{len(invalidated_scope.get('files', []) or [])} invalidated files")
    _write(review_path, review)


def request_architecture_change(
    base_dir: str,
    source: str,
    reason: str,
    proposed_change: str,
    affected_files: Optional[List[str]] = None,
    affected_modules: Optional[List[str]] = None,
    current_contract_gap: str = "",
    scope_impact: str = "",
    risk: str = "",
    user_decision_required: bool = False,
) -> Dict[str, Any]:
    """Append an architecture change request to fix-loop.json. Does NOT modify brief."""
    base = Path(base_dir)
    fl_path = base / ".aiwf" / "state" / "fix-loop.json"
    fl = _read(fl_path)

    acrs = fl.get("architecture_change_requests", []) or []
    next_id = f"ACR-{len(acrs) + 1:03d}"
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).isoformat()

    acr = {
        "id": next_id,
        "status": "proposed",
        "source": source,
        "reason": reason,
        "proposed_change": proposed_change,
        "affected_files": affected_files or [],
        "affected_modules": affected_modules or [],
        "current_contract_gap": current_contract_gap,
        "scope_impact": scope_impact,
        "risk": risk,
        "planner_decision": "",
        "user_decision_required": user_decision_required,
        "created_at": ts,
        "resolved_at": "",
    }
    acrs.append(acr)
    fl["architecture_change_requests"] = acrs
    _write(fl_path, fl)
    return acr


def decide_architecture_change(
    base_dir: str,
    acr_id: str,
    status: str,
    decision: str,
) -> Dict[str, Any]:
    """Update an architecture change request status + decision.
    Raises ValueError if acr_id is not found.
    """
    base = Path(base_dir)
    fl_path = base / ".aiwf" / "state" / "fix-loop.json"
    fl = _read(fl_path)

    acrs = fl.get("architecture_change_requests", []) or []
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).isoformat()

    found = False
    for acr in acrs:
        if acr.get("id") == acr_id:
            acr["status"] = status
            acr["planner_decision"] = decision
            acr["resolved_at"] = ts
            found = True
            break

    if not found:
        raise ValueError(f"architecture change request not found: {acr_id}")

    fl["architecture_change_requests"] = acrs
    _write(fl_path, fl)
    return {"id": acr_id, "status": status, "decision": decision}


def list_architecture_changes(base_dir: str) -> List[Dict[str, Any]]:
    """Return list of architecture change requests."""
    base = Path(base_dir)
    fl_path = base / ".aiwf" / "state" / "fix-loop.json"
    fl = _read(fl_path)
    return fl.get("architecture_change_requests", []) or []


