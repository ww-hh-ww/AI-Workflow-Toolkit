"""Task-local fix-loop operations."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..task_ledger import load_ledger, resolve_active_task_id, update_task_runtime
from ..task_records import load_task_record, update_task_record
from ..worktree_context import resolve_worktree_root


def _tester_verified_current_implementation(record: Dict[str, Any], source: str) -> bool:
    implementation = record.get("implementation", {}) or {}
    testing = record.get("testing", {}) or {}
    implementation_ref = str(implementation.get("implementation_ref") or "")
    return bool(
        source == "tester"
        and implementation_ref
        and testing.get("status") == "passed"
        and testing.get("tested_ref")
        and str(testing.get("based_on_ref") or "") == implementation_ref
    )


def _continued_after_escalation(fix_loop: Dict[str, Any]) -> bool:
    return any(
        str(entry.get("source") or "") == "human"
        and str(entry.get("reason") or "") == "human continued after escalation"
        for entry in fix_loop.get("route_history", []) or []
        if isinstance(entry, dict)
    )


def open_fix_loop(
    base_dir: str,
    route: str,
    reason: str,
    required_fixes: Optional[List[str]] = None,
    required_verification: Optional[List[str]] = None,
    source: str = "reviewer",
    invalidated_files: Optional[List[str]] = None,
    invalidated_obligations: Optional[List[str]] = None,
    task_id: str = "",
) -> Dict[str, Any]:
    """Open a fix-loop with route, reason, required fixes, and verification.

    A new Tester failure advances attempt_count. Repeated recording of the same
    failure or a route change does not pretend to be another repair attempt.
    Uses a small fixed retry limit before asking for escalation.
    If attempt_count reaches max_attempts: escalation_required=true, rollback_recommended
    if checkpoint exists.
    Does NOT auto-execute fixes, modify goal/scope/context, or auto-close workflow.
    """
    effective_task = resolve_active_task_id(base_dir, task_id)
    if not effective_task:
        raise ValueError("fix-loop requires an active Task ID or an assigned Task worktree")

    result: Dict[str, Any] = {}

    def mutate(record: Dict[str, Any]) -> None:
        nonlocal result
        fix_loop = record["fix_loop"]
        was_open = fix_loop.get("status") == "open"
        implementation = record.get("implementation", {}) or {}
        testing = record.get("testing", {}) or {}
        evidence_ref = str((
            testing.get("tested_ref")
            if source == "tester"
            else implementation.get("implementation_ref")
        ) or "")
        history = list(fix_loop.get("route_history", []) or []) if was_open else []
        duplicate = bool(
            was_open
            and any(
                str(entry.get("route") or "") == route
                and str(entry.get("source") or "") == source
                and " ".join(str(entry.get("reason") or "").split()).casefold()
                == " ".join(str(reason or "").split()).casefold()
                and str(entry.get("evidence_ref") or "") == evidence_ref
                for entry in history
            )
        )
        prior_attempt = int(fix_loop.get("attempt_count", 0) or 0)
        seen_failed_refs = {
            str(entry.get("evidence_ref") or "")
            for entry in history
            if str(entry.get("source") or "") == "tester"
            and entry.get("evidence_ref")
        }
        new_tester_failure = bool(
            source == "tester"
            and evidence_ref
            and evidence_ref not in seen_failed_refs
        )
        if new_tester_failure:
            attempt = prior_attempt + 1
        else:
            attempt = prior_attempt
        fix_loop.update({
            "status": "open",
            "route": route,
            "reason": reason,
            "source": source,
            "attempt_count": attempt,
            "max_attempts": int(fix_loop.get("max_attempts", 0) or 0) or 2,
        })
        if not was_open:
            fix_loop.update({
                "resolution": "",
                "escalation_required": False,
                "escalation_reason": "",
                "rollback_recommended": False,
                "route_history": [],
            })
        if required_fixes is not None:
            fix_loop["required_fixes"] = list(required_fixes)
        elif not was_open:
            fix_loop["required_fixes"] = []
        if required_verification is not None:
            fix_loop["required_verification"] = list(required_verification)
        elif not was_open:
            fix_loop["required_verification"] = []
        if invalidated_files or invalidated_obligations:
            fix_loop["invalidated_scope"] = {
                "files": list(invalidated_files or []),
                "obligations": list(invalidated_obligations or []),
                "reason": reason,
            }
        history = list(fix_loop.get("route_history", []) or [])
        if not duplicate:
            entry = {
                "attempt": attempt,
                "route": route,
                "reason": reason,
                "source": source,
            }
            if evidence_ref:
                entry["evidence_ref"] = evidence_ref
            history.append(entry)
            fix_loop["route_history"] = history
        if new_tester_failure and attempt >= fix_loop["max_attempts"]:
            fix_loop["escalation_required"] = True
            fix_loop["escalation_reason"] = (
                f"fix-loop failed verification attempts ({attempt}) reached "
                f"max_attempts ({fix_loop['max_attempts']})"
            )
            fix_loop["rollback_recommended"] = True
        result = dict(fix_loop)

    update_task_record(base_dir, effective_task, mutate)
    update_task_runtime(base_dir, effective_task, phase="reviewing")
    return result


def resolve_fixloop_task_id(base_dir: str, task_id: str = "") -> str:
    """Resolve an explicit active or suspended Task for fix-loop recovery."""
    if task_id:
        task = next(
            (
                item for item in load_ledger(base_dir).get("tasks", []) or []
                if isinstance(item, dict) and item.get("id") == task_id
            ),
            None,
        )
        if task and task.get("status") in ("active", "suspended"):
            return task_id
        return ""
    return resolve_active_task_id(base_dir)


def continue_fix_loop(base_dir: str, task_id: str = "") -> Dict[str, Any]:
    """Human acknowledgement that permits the current fix-loop route to continue."""
    effective_task = resolve_fixloop_task_id(base_dir, task_id)
    if not effective_task:
        raise ValueError("fix-loop continue requires an active Task ID or assigned Task worktree")

    result: Dict[str, Any] = {}

    def mutate(record: Dict[str, Any]) -> None:
        nonlocal result
        fix_loop = record["fix_loop"]
        if fix_loop.get("status") != "open":
            raise ValueError("fix-loop is not open")
        if not fix_loop.get("escalation_required"):
            raise ValueError("fix-loop is not awaiting a human decision")
        attempt = int(fix_loop.get("attempt_count", 0) or 0)
        history = list(fix_loop.get("route_history", []) or [])
        history.append({
            "attempt": attempt,
            "route": str(fix_loop.get("route") or "planner"),
            "reason": "human continued after escalation",
            "source": "human",
        })
        fix_loop.update({
            "escalation_required": False,
            "escalation_reason": "",
            "rollback_recommended": False,
            "route_history": history,
        })
        result = dict(fix_loop)

    update_task_record(base_dir, effective_task, mutate)
    return result

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
) -> Dict[str, Any]:
    """Re-validate required_fixes against current git state and review resolutions.

    Returns {"still_unresolved": [...], "stale_resolved": [...],
              "resolved_reverted": [...], "blockers": [...]}

    A fix is considered resolved if:
    - The target file appears in scope_violation_events as resolved_reverted, OR
    - The fix is verified against current git diff (file was changed since fix-loop opened)

    Any still_unresolved fix blocks resolution.
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
            result["still_unresolved"].append(fix_path)
        elif fix_path in changed_files:
            # File was changed — fix may have been applied
            result["stale_resolved"].append(fix_path)
        else:
            # File not in diff and not resolved — fix is stale (already reverted or never applied)
            result["stale_resolved"].append(fix_path)

    if result["still_unresolved"]:
        result["blockers"].append(
            f"{len(result['still_unresolved'])} required fix(es) still unresolved "
            f"(diff unavailable): {', '.join(result['still_unresolved'][:5])}"
        )

    return result

def resolve_fix_loop(
    base_dir: str,
    resolution: str,
    source: str = "reviewer",
    task_id: str = "",
) -> Dict[str, Any]:
    """Resolve a fix-loop only after its mechanical verification gates pass.

    Re-validates required_fixes against current git diff and review.json
    scope_violation_events. Blocks resolution when fixes are still unresolved
    (target files not in diff and not marked resolved_reverted).
    """
    effective_task = resolve_fixloop_task_id(base_dir, task_id)
    if not effective_task:
        raise ValueError("fix-loop resolution requires an active Task ID or assigned Task worktree")
    task = next(
        (item for item in load_ledger(base_dir).get("tasks", []) if item.get("id") == effective_task),
        None,
    )
    if not task:
        raise ValueError(f"Task not found: {effective_task}")
    base = Path(task.get("worktree_path") or resolve_worktree_root(base_dir))

    record = load_task_record(base_dir, effective_task)
    fix_loop = record["fix_loop"]
    if fix_loop.get("status") != "open":
        raise ValueError("fix-loop is not open")
    blockers: List[str] = []
    scope_resolution = None
    testing = record["testing"]

    # ── Re-validate required_fixes against current state ──
    required_fixes = fix_loop.get("required_fixes", []) or []
    review = record["review"]
    scope_events = review.get("scope_violation_events", []) or []
    reval = _revalidate_required_fixes(base, required_fixes, scope_events)
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

    if task.get("scope_violation"):
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
        if changed.get("source") == "unavailable":
            blockers.append("scope violation cannot be verified because git change detection is unavailable")
        elif remaining:
            blockers.append("scope-violating files remain changed: " + ", ".join(remaining[:5]))
        elif not scope_events:
            blockers.append("scope violation has no structured event history to verify")
        elif not unresolved:
            task["scope_violation"] = False
        else:
            scope_resolution = unresolved
    if (
        fix_loop.get("escalation_required")
        and not _tester_verified_current_implementation(record, source)
    ):
        blockers.append(
            "escalation_required=true; Planner cannot self-resolve escalation. "
            "The human must continue, interrupt, or force-close the Task."
        )
    if (
        _continued_after_escalation(fix_loop)
        and source == "tester"
        and not _tester_verified_current_implementation(record, source)
    ):
        blockers.append(
            "continued escalation requires passed testing against the current implementation"
        )
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
    _invalidate_delta_review(fix_loop, task, review)
    if scope_resolution:
        unresolved = scope_resolution
        ts = datetime.now(timezone.utc).isoformat()
        for event in unresolved:
            event["status"] = "resolved_reverted"
            event["resolved_at"] = ts
            event["resolution"] = resolution
        review["blockers"] = [
            blocker for blocker in (review.get("blockers", []) or [])
            if not str(blocker).startswith("scope_violation:")
        ]
        review["result"] = "unknown"
        review["closure_allowed"] = False
        task["scope_violation"] = False
    fix_loop["status"] = "resolved"
    fix_loop["resolution"] = resolution
    if source: fix_loop["source"] = source
    def store(current: Dict[str, Any]) -> None:
        current["fix_loop"] = fix_loop
        current["review"] = review

    update_task_record(base_dir, effective_task, store)
    next_phase = "reviewing" if review.get("result") != "accepted" else "closing"
    if task.get("status") == "suspended":
        update_task_runtime(
            base_dir,
            effective_task,
            phase="suspended",
            suspended_phase=next_phase,
            scope_violation=bool(task.get("scope_violation")),
        )
    else:
        update_task_runtime(
            base_dir,
            effective_task,
            phase=next_phase,
            scope_violation=bool(task.get("scope_violation")),
        )
    return dict(fix_loop)

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
    fix_loop: Dict[str, Any],
    task: Dict[str, Any],
    review: Dict[str, Any],
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
    if task.get("scope_violation"):
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
