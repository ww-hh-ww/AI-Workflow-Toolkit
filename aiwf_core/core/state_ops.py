"""Deterministic state operation helpers.

Skills call these instead of hand-editing .aiwf/*.json.
All functions are backend-neutral — no Claude-specific logic.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

WORKFLOW_LEVELS = ["L0_direct", "L1_review_light", "L2_standard_team", "L3_full_power"]
BLOCKING_REVIEW_RESULTS = {
    "needs_fix", "needs_more_testing", "evidence_insufficient",
    "scope_violation", "rejected",
}


def _read(path: Path) -> Dict:
    try: return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except: return {}


def _write(path: Path, data: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def record_role_evidence(
    base_dir: str,
    role: str,
    summary: str = "",
    command: str = "",
    changed_files: Optional[List[str]] = None,
    session_id: str = "",
    agent_id: str = "",
    agent_type: str = "",
    context_id: str = "",
    status: str = "pending",
    exit_code: int = 0,
    scan_git: bool = False,
) -> Dict[str, Any]:
    """Append machine-recorded role evidence for subagent/hook coverage gaps."""
    role = role.strip().lower()
    if role not in ("executor", "tester", "reviewer", "planner"):
        raise ValueError(f"unknown role evidence role: {role}")
    if status not in ("pending", "accepted", "rejected"):
        raise ValueError(f"unknown role evidence status: {status}")

    base = Path(base_dir)
    evidence_path = base / ".aiwf" / "evidence" / "records.json"
    state = _read(base / ".aiwf" / "state" / "state.json")
    evidence = _read(evidence_path)
    records = evidence.get("records", [])
    if not isinstance(records, list):
        records = []

    from datetime import datetime, timezone
    from .evidence_schema import next_ev_id

    active_context = context_id or state.get("active_context_id") or ""
    synthetic_session = active_context or "aiwf"
    scanned_files: List[str] = []
    scanned_source = "not_scanned"
    if scan_git:
        try:
            from ..hooks.common.diff_snapshot import detect_changed_files_with_baseline
            scan = detect_changed_files_with_baseline(base)
            scanned_files = list(scan.get("files", []) or [])
            scanned_source = str(scan.get("source", "") or "git_diff")
        except Exception:
            scanned_files = []
            scanned_source = "scan_failed"
    delivered_files = list(changed_files or [])
    effective_changed = delivered_files or scanned_files
    record = {
        "id": next_ev_id(records),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "context_id": active_context,
        "phase": state.get("phase", ""),
        "session_id": session_id or synthetic_session,
        "agent_id": agent_id or role,
        "agent_type": agent_type or role,
        "tool_name": "AIWFRoleEvidence",
        "tool_input": {"role": role, "summary": summary, "scan_git": bool(scan_git)},
        "command": command[:500] if command else "",
        "exit_code": exit_code,
        "changed_files": effective_changed,
        "governance_changed_files": [],
        "changed_files_source": "role_delivery_git_scan" if scan_git else "role_delivery",
        "working_tree_changed_files": scanned_files,
        "working_tree_source": scanned_source,
        "attribution": "role_command",
        "stdout_summary": summary[:500] if summary else "",
        "stderr_summary": "",
        "status": status,
        "trust": "machine_observed",
    }
    records.append(record)
    evidence["records"] = records
    evidence["updated_at"] = record["timestamp"]
    _write(evidence_path, evidence)
    return record


def execution_contract_freeze_reasons(base_dir: str, state: Optional[Dict] = None) -> List[str]:
    """Explain why execution truth may only become stricter."""
    base = Path(base_dir)
    state = state if state is not None else _read(base / ".aiwf" / "state" / "state.json")
    testing = _read(base / ".aiwf" / "quality" / "testing.json")
    review = _read(base / ".aiwf" / "quality" / "review.json")
    fix_loop = _read(base / ".aiwf" / "state" / "fix-loop.json")
    reasons: List[str] = []
    if state.get("active_task_id"): reasons.append(f"active_task={state['active_task_id']}")
    if state.get("scope_violation"): reasons.append("scope_violation=true")
    if state.get("close_attempt"): reasons.append("close_attempt=true")
    if state.get("phase") in ("testing", "reviewing", "closing"):
        reasons.append(f"phase={state['phase']}")
    if testing.get("status") == "failed": reasons.append("testing=failed")
    if review.get("result") in BLOCKING_REVIEW_RESULTS:
        reasons.append(f"review={review['result']}")
    if fix_loop.get("status") == "open": reasons.append("fix_loop=open")
    return reasons


def _execution_contract_frozen(base: Path, state: Optional[Dict] = None) -> bool:
    return bool(execution_contract_freeze_reasons(str(base), state))


def _freeze_explanation(base: Path, state: Optional[Dict] = None) -> str:
    reasons = execution_contract_freeze_reasons(str(base), state)
    return (
        f"freeze reasons: {', '.join(reasons) or 'unknown'}; "
        "allowed now: add constraints or record evidence; "
        "unlock: finish/revert the failing work, satisfy testing/review, resolve the fix-loop, then close the cycle"
    )


def _require_additive_list(existing: Any, proposed: List[str], field: str, detail: str = "") -> None:
    missing = [item for item in (existing or []) if item not in proposed]
    if missing:
        raise ValueError(
            f"execution contract is frozen; {field} may add constraints but cannot remove existing items"
            + (f"; {detail}" if detail else "")
        )


def _require_stable_scalar(existing: Any, proposed: str, field: str, detail: str = "") -> None:
    if existing and proposed and existing != proposed:
        raise ValueError(
            f"execution contract is frozen; {field} cannot replace an existing value"
            + (f"; {detail}" if detail else "")
        )


def _ensure_critical_assets(base_dir: str) -> list:
    """Check and auto-fill critical assets. Returns notes about what was filled.

    Called by start_context on every session start. Mechanical — no Planner
    decision needed. If an asset is missing, we create it. Planner never
    sees "Environment: missing" again because it gets filled here first.
    """
    import json as _json
    base = Path(base_dir)
    aiwf = base / ".aiwf"
    notes = []
    filled = []

    # 1. Environment profile
    env_path = aiwf / "assets" / "environment.json"
    if not env_path.exists():
        try:
            from .environment import scan_environment, write_environment_profile
            env = scan_environment(base_dir)
            write_environment_profile(base_dir, env)
            filled.append("environment profile")
        except Exception:
            pass
    else:
        # Check if stale (>90d)
        try:
            env_data = _json.loads(env_path.read_text())
            gen_at = env_data.get("generated_at", "")
            if gen_at:
                from datetime import datetime, timezone
                try:
                    gen_dt = datetime.fromisoformat(gen_at)
                    age = (datetime.now(timezone.utc) - gen_dt).days
                    if age > 90:
                        from .environment import scan_environment, write_environment_profile
                        env = scan_environment(base_dir)
                        write_environment_profile(base_dir, env)
                        filled.append(f"environment profile (was {age}d old)")
                except Exception:
                    pass
        except Exception:
            pass

    # 2. Capabilities registry
    cap_path = aiwf / "assets" / "capabilities.json"
    cap_alt = aiwf / "capabilities.json"  # legacy pre-v2 flat path
    cap_exists = cap_path.exists() or cap_alt.exists()
    if not cap_exists:
        try:
            from .capabilities import discover_capabilities, write_capabilities_registry
            caps = discover_capabilities(base_dir)
            write_capabilities_registry(base_dir, caps)
            filled.append(f"capability registry ({len(caps.get('capabilities', []))} found)")
        except Exception:
            pass

    # 3. PROJECT-MAP
    pm_path = aiwf / "reports" / "项目地图.md"
    if not pm_path.exists():
        try:
            from .project_map import ensure_project_map
            ensure_project_map(base_dir)
            filled.append("PROJECT-MAP")
        except Exception:
            pass

    # 4. Idea inbox
    ideas_path = aiwf / "reports" / "ideas.md"
    if not ideas_path.exists():
        try:
            from .ideas import ensure_ideas_file
            ensure_ideas_file(base_dir)
            filled.append("ideas.md")
        except Exception:
            pass

    # 6. task-history baseline (if completely empty)
    th_path = aiwf / "history" / "task-history.json"
    if not th_path.exists():
        try:
            from .workspace_drift import auto_update_baseline
            auto_update_baseline(base_dir)
            filled.append("task-history baseline")
        except Exception:
            pass

    if filled:
        notes.append(f"[ASSET] Auto-filled: {', '.join(filled)}")
    return notes



# ── context operations ────────────────────────────────────────────────

def start_context(
    base_dir: str,
    context_id: str,
    label: str = "",
    allowed_write: Optional[List[str]] = None,
    forbidden_write: Optional[List[str]] = None,
    note: str = "",
    purpose: str = "",
    read_hints: Optional[List[str]] = None,
    non_goals: Optional[List[str]] = None,
    dependencies: Optional[List[str]] = None,
    interface_contract: str = "",
    test_focus: Optional[List[str]] = None,
    review_focus: Optional[List[str]] = None,
    escalation_triggers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Create or update a context. Sets state.active_context_id. Returns contexts dict.

    Once a task is active, its context identity and write boundaries are frozen.
    This prevents a scope violation from being retrospectively legalized by
    widening or swapping the active context.
    """
    base = Path(base_dir)
    contexts_path = base / ".aiwf" / "state" / "contexts.json"
    state_path = base / ".aiwf" / "state" / "state.json"

    contexts = _read(contexts_path)
    state = _read(state_path)
    if "contexts" not in contexts or not isinstance(contexts.get("contexts"), list):
        contexts = {"contexts": []}

    # Upsert context
    existing = None
    for ctx in contexts["contexts"]:
        if ctx.get("id") == context_id:
            existing = ctx
            break

    active_task_id = str(state.get("active_task_id", "") or "")
    active_context_id = str(state.get("active_context_id", "") or "")
    contract_frozen = _execution_contract_frozen(base, state)
    requested_boundary_change = bool(
        existing and (
            (allowed_write is not None and allowed_write != (existing.get("allowed_write", []) or []))
            or (forbidden_write is not None and forbidden_write != (existing.get("forbidden_write", []) or []))
        )
    )
    if contract_frozen and active_context_id and context_id != active_context_id:
        raise ValueError(
            f"execution cycle freezes context identity at {active_context_id}; "
            f"{_freeze_explanation(base, state)}"
        )
    if state.get("scope_violation") and requested_boundary_change:
        raise ValueError(
            "scope violation is already recorded; changing the current context cannot legalize it retrospectively"
        )
    if contract_frozen and requested_boundary_change:
        raise ValueError(
            f"execution cycle freezes allowed_write/forbidden_write for {context_id}; "
            f"scope changes apply only to a future task; {_freeze_explanation(base, state)}"
        )

    DISPATCH_MAP = [
        ("purpose", purpose, ""), ("read_hints", read_hints, []), ("non_goals", non_goals, []),
        ("dependencies", dependencies, []), ("interface_contract", interface_contract, ""),
        ("test_focus", test_focus, []), ("review_focus", review_focus, []),
        ("escalation_triggers", escalation_triggers, []),
    ]
    if existing:
        ctx = existing
        old_boundary = {
            "allowed_write": list(existing.get("allowed_write", []) or []),
            "forbidden_write": list(existing.get("forbidden_write", []) or []),
        }
        if label: existing["title"] = label
        if allowed_write is not None: existing["allowed_write"] = allowed_write
        if forbidden_write is not None: existing["forbidden_write"] = forbidden_write
        if requested_boundary_change:
            from datetime import datetime, timezone
            existing.setdefault("revision_history", []).append({
                "changed_at": datetime.now(timezone.utc).isoformat(),
                "previous_boundary": old_boundary,
                "new_boundary": {
                    "allowed_write": list(existing.get("allowed_write", []) or []),
                    "forbidden_write": list(existing.get("forbidden_write", []) or []),
                },
            })
        if note: existing.setdefault("notes", []).append(note)
        for fld, val, dfl in DISPATCH_MAP:
            if val is not None and val != dfl:
                existing[fld] = val
            elif fld not in existing:
                existing[fld] = dfl
    else:
        entry = {
            "id": context_id, "title": label or context_id,
            "allowed_write": allowed_write or [], "forbidden_write": forbidden_write or [],
            "notes": [note] if note else [],
        }
        for fld, val, dfl in DISPATCH_MAP:
            entry[fld] = val if (val is not None and val != dfl) else dfl
        contexts["contexts"].append(entry)
        ctx = entry

    # Set active context in state
    state["active_context_id"] = context_id
    if state.get("phase") in ("discussing", "planned"):
        state["phase"] = "implementing"
    # Reset per-task flags
    state["planner_inline"] = False

    # L0: Planner implements inline — no Executor subagent
    level = state.get("workflow_level", "L1_review_light")
    if level == "L0_direct":
        state["planner_inline"] = True
        if isinstance(ctx.get("notes"), list):
            ctx["notes"].append("[L0] Planner inline implementation — no executor subagent")

    # Auto-run workspace scan to update baseline on structural changes.
    # Inject a detailed drift summary into context notes so Planner sees what changed.
    try:
        from .workspace_drift import scan_workspace_drift, write_workspace_drift, auto_update_baseline
        drift = scan_workspace_drift(base_dir)
        write_workspace_drift(base_dir, drift)

        has_changes = drift.get("project_changes") or drift.get("untracked") or drift.get("deleted")
        if has_changes:
            baseline_result = auto_update_baseline(base_dir)

            # Build a human-readable drift summary for Planner
            drift_lines = [f"[DRIFT] Workspace changed: magnitude={baseline_result.get('magnitude', '?')}"]
            delta = baseline_result.get("delta", {})
            if delta.get("added"):
                drift_lines.append(f"  +{delta['added']} file(s) added")
            if delta.get("deleted"):
                drift_lines.append(f"  -{delta['deleted']} file(s) deleted")
            if delta.get("new_modules"):
                drift_lines.append(f"  New modules: {', '.join(delta['new_modules'][:5])}")
            if delta.get("removed_modules"):
                drift_lines.append(f"  Removed modules: {', '.join(delta['removed_modules'][:5])}")
            if delta.get("dep_changes"):
                drift_lines.append(f"  Dependency changes: {', '.join(delta['dep_changes'][:5])}")

            # Show specific changed files (capped at 10)
            changed_paths = []
            for e in (drift.get("project_changes", []) or [])[:10]:
                changed_paths.append(f"{e.get('path', '?')} [{e.get('status', '?')}]")
            if changed_paths:
                drift_lines.append(f"  Files: {', '.join(changed_paths)}")

            # Show what assets were auto-updated
            if baseline_result.get("updated"):
                drift_lines.append(f"  Assets refreshed: {', '.join(baseline_result['updated'][:5])}")
            if baseline_result.get("skipped"):
                drift_lines.append(f"  Skipped: {', '.join(baseline_result['skipped'][:5])}")

            drift_note = "\n".join(drift_lines)
            if isinstance(ctx.get("notes"), list):
                ctx["notes"].append(drift_note)
            else:
                ctx["notes"] = [drift_note]
        else:
            drift_note = "[DRIFT] Workspace clean -- no changes since last scan"
            if isinstance(ctx.get("notes"), list):
                ctx["notes"].append(drift_note)
    except Exception:
        pass

    # Inject emergent gravity context messages (at most 3, high-value only)
    try:
        from .task_gravity import task_gravity
        gravity = task_gravity(base_dir, allowed_write or [])
        priority_msgs = gravity.get("context_messages", [])[:3]
        for msg in priority_msgs:
            if "notes" not in ctx:
                ctx["notes"] = []
            if isinstance(ctx.get("notes"), list):
                ctx["notes"].append(f"[GRAVITY] {msg}")
    except Exception:
        pass

    # ── Ensure critical assets exist (mechanical, no Planner decision needed) ──
    # start_context is the universal entry point. If assets are missing, fill them now.
    # Planner cannot skip this — it happens automatically.
    asset_notes = _ensure_critical_assets(base_dir)
    if asset_notes:
        if isinstance(ctx.get("notes"), list):
            ctx["notes"].extend(asset_notes)
        else:
            ctx["notes"] = asset_notes

    _write(contexts_path, contexts)
    _write(state_path, state)

    return contexts


# ── testing operations ────────────────────────────────────────────────

def record_testing(
    base_dir: str,
    context_id: str = "",
    status: str = "adequate",
    commands: Optional[List[str]] = None,
    evidence_ids: Optional[List[str]] = None,
    untested_risks: Optional[List[str]] = None,
    coverage_summary: str = "",
    failure_summary: str = "",
    failed_obligations: Optional[List[str]] = None,
    failed_commands: Optional[List[str]] = None,
    suspected_route: str = "",
    required_verification: Optional[List[str]] = None,
    acceptance_coverage: Optional[List[str]] = None,
    system_coverage: Optional[List[str]] = None,
    validation_layers: Optional[List[str]] = None,
    full_suite_status: str = "",
    full_suite_reason: str = "",
    real_usage_status: str = "",
    real_usage_reason: str = "",
    inferred_surfaces: Optional[List[str]] = None,
    missing_surface_notes: Optional[List[str]] = None,
    cross_task_risks: Optional[List[str]] = None,
    testing_debt: Optional[List[str]] = None,
    repeated_change_hotspots: Optional[List[str]] = None,
    adversarial_mode: bool = False,
) -> Dict[str, Any]:
    """Write testing.json consistently. Returns testing dict."""
    base = Path(base_dir)
    testing_path = base / ".aiwf" / "quality" / "testing.json"

    testing = _read(testing_path)
    testing["status"] = status
    testing["context_id"] = context_id
    if commands is not None: testing["commands"] = commands
    if evidence_ids is not None: testing["evidence_ids"] = evidence_ids
    if untested_risks is not None: testing["untested_risks"] = untested_risks
    if coverage_summary: testing["coverage_summary"] = coverage_summary
    if failure_summary: testing["failure_summary"] = failure_summary
    if failed_obligations is not None: testing["failed_obligations"] = failed_obligations
    if failed_commands is not None: testing["failed_commands"] = failed_commands
    if suspected_route: testing["suspected_route"] = suspected_route
    if required_verification is not None: testing["required_verification"] = required_verification
    if acceptance_coverage is not None: testing["acceptance_coverage"] = acceptance_coverage
    if system_coverage is not None: testing["system_coverage"] = system_coverage
    if validation_layers is not None: testing["validation_layers"] = validation_layers
    if full_suite_status: testing["full_suite_status"] = full_suite_status
    if full_suite_reason: testing["full_suite_reason"] = full_suite_reason
    if real_usage_status: testing["real_usage_status"] = real_usage_status
    if real_usage_reason: testing["real_usage_reason"] = real_usage_reason
    if inferred_surfaces is not None: testing["inferred_surfaces"] = inferred_surfaces
    if missing_surface_notes is not None: testing["missing_surface_notes"] = missing_surface_notes
    if cross_task_risks is not None: testing["cross_task_risks"] = cross_task_risks
    if testing_debt is not None: testing["testing_debt"] = testing_debt
    if repeated_change_hotspots is not None: testing["repeated_change_hotspots"] = repeated_change_hotspots
    testing["adversarial_mode"] = bool(adversarial_mode)

    _write(testing_path, testing)
    state_path = base / ".aiwf" / "state" / "state.json"
    state = _read(state_path)
    if state.get("phase") not in ("closing", "closed"):
        state["phase"] = "testing"
        _write(state_path, state)
    evidence_command = "; ".join(commands or [])
    evidence_summary = coverage_summary or failure_summary or f"testing status={status}"
    ev = record_role_evidence(
        base_dir,
        "tester",
        summary=evidence_summary,
        command=evidence_command,
        context_id=context_id or state.get("active_context_id") or "",
        status="pending",
        exit_code=0 if status in ("adequate", "passed") else 1 if status == "failed" else 0,
    )
    testing["evidence_id"] = ev["id"]
    _write(testing_path, testing)
    return testing


# ── cleanup operations ────────────────────────────────────────────────

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
    from .state_schema import VALID_REVIEW_RESULTS
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
        from .review_contract import set_review_rejected
        set_review_rejected(review, blockers or [])

    _write(review_path, review)
    if state.get("phase") not in ("closing", "closed"):
        state["phase"] = "reviewing"
        _write(base / ".aiwf" / "state" / "state.json", state)
    return review


# ── close preparation ─────────────────────────────────────────────────

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

    from .review_contract import promote_evidence
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

    # 3. Testing recorded — did the Tester run?
    if testing.get("status", "missing") == "missing":
        blockers.append(
            "testing not recorded. Run aiwf state record-testing --status passed."
        )

    # 4. Review recorded — did the Reviewer run?
    if review.get("result", "unknown") == "unknown":
        blockers.append(
            "review not recorded. Run aiwf state record-review --result accepted."
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
            from .cross_task_quality import append_task_history_from_state, write_quality_digest
            append_task_history_from_state(base_dir)
            write_quality_digest(base_dir)
        except Exception:
            pass
        try:
            from .lifecycle_cleanup import auto_cleanup
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
        from .current_state import current_state_freshness
        cs = current_state_freshness(base_dir)
        cs_stat = cs.get("status", "?")
        lines.append(f"  Project docs: {'up to date' if cs_stat == 'fresh' else 'stale'}")
        if cs_stat != "fresh":
            warns.append("Project documentation is stale — run aiwf state rebuild-current-state")
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


# ── adversarial observation disposition ─────────────────────────────────

def disposition_adversarial_observation(
    base_dir: str,
    adv_id: str,
    disposition: str,
    reason: str = "",
    disposed_by: str = "planner",
) -> Dict[str, Any]:
    """Update disposition on a single adversarial observation. Prefer this over direct edit."""
    valid_dispositions = {"ignored", "accepted", "deferred", "brief_updated"}
    if disposition not in valid_dispositions:
        raise ValueError(f"invalid disposition: {disposition}. Valid: {', '.join(sorted(valid_dispositions))}")
    if not reason or not reason.strip():
        raise ValueError("disposition reason is required")
    base = Path(base_dir)
    review_path = base / ".aiwf" / "quality" / "review.json"
    review = _read(review_path)
    obs_list = review.get("adversarial_observations", [])
    if not isinstance(obs_list, list):
        obs_list = []
    found = False
    for obs in obs_list:
        if isinstance(obs, dict) and obs.get("id") == adv_id:
            obs["disposition"] = disposition
            obs["disposition_reason"] = reason.strip()
            obs["disposed_by"] = disposed_by
            found = True
            break
    if not found:
        raise ValueError(f"adversarial observation not found: {adv_id}")
    review["adversarial_observations"] = obs_list
    _write(review_path, review)
    return {"id": adv_id, "disposition": disposition, "found": True}


# ── fix-loop operations ──────────────────────────────────────────────────

def open_fix_loop(
    base_dir: str,
    route: str,
    reason: str,
    required_fixes: Optional[List[str]] = None,
    required_verification: Optional[List[str]] = None,
    source: str = "reviewer",
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
    fix_loop["source"] = source
    fix_loop["attempt_count"] = attempt

    # Set max_attempts from workflow_level on first open
    if not was_open or not fix_loop.get("max_attempts"):
        state = _read(state_path)
        level = state.get("workflow_level", "L1_review_light")
        from .state_schema import LEVEL_MAX_ATTEMPTS
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


def resolve_fix_loop(
    base_dir: str,
    resolution: str,
    source: str = "reviewer",
    force: bool = False,
) -> Dict[str, Any]:
    """Resolve a fix-loop only after its mechanical verification gates pass.

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
    if state.get("scope_violation"):
        review_path = base / ".aiwf" / "quality" / "review.json"
        review = _read(review_path)
        unresolved = [
            event for event in (review.get("scope_violation_events", []) or [])
            if isinstance(event, dict) and event.get("status", "recorded") != "resolved_reverted"
        ]
        from ..hooks.common.diff_snapshot import detect_changed_files
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
    if blockers:
        raise ValueError("fix-loop resolution blocked: " + "; ".join(blockers))
    if scope_resolution:
        from datetime import datetime, timezone
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


# ── architecture change request operations ──────────────────────────────

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


def record_quality_brief(
    base_dir: str,
    acceptance_criteria: Optional[List[str]] = None,
    test_focus: Optional[List[str]] = None,
    review_focus: Optional[List[str]] = None,
    non_goals: Optional[List[str]] = None,
    escalation_triggers: Optional[List[str]] = None,
    # ── architecture brief ──
    target_structure: str = "",
    module_boundaries: Optional[List[str]] = None,
    allowed_files: Optional[List[str]] = None,
    protected_files: Optional[List[str]] = None,
    allowed_new_files: Optional[List[str]] = None,
    public_api_changes: Optional[List[str]] = None,
    integration_points: Optional[List[str]] = None,
    architecture_invariants: Optional[List[str]] = None,
    forbidden_restructures: Optional[List[str]] = None,
    architecture_risks: Optional[List[str]] = None,
    migration_source_of_truth: str = "",
    legacy_paths: Optional[List[str]] = None,
    legacy_terms: Optional[List[str]] = None,
    default_entrypoints: Optional[List[str]] = None,
    validators: Optional[List[str]] = None,
    sample_outputs: Optional[List[str]] = None,
    surface_types: Optional[List[str]] = None,
    user_visible_outcome: str = "",
    evaluation_acceptance_criteria: Optional[List[str]] = None,
    evaluation_non_goals: Optional[List[str]] = None,
    test_obligations: Optional[List[str]] = None,
    review_obligations: Optional[List[str]] = None,
    known_risks: Optional[List[str]] = None,
    closure_question: str = "",
    system_integration_obligations: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Write task-specific quality brief; frozen cycles permit additive changes only."""
    base = Path(base_dir)
    goal_path = base / ".aiwf" / "state" / "goal.json"
    goal = _read(goal_path)
    brief = goal.get("quality_brief", {})
    ab = brief.get("architecture_brief", {})
    ec = brief.get("evaluation_contract", {})
    if _execution_contract_frozen(base):
        freeze_note = _freeze_explanation(base)
        for field, proposed in (
            ("acceptance_criteria", acceptance_criteria),
            ("test_focus", test_focus), ("review_focus", review_focus),
            ("non_goals", non_goals), ("escalation_triggers", escalation_triggers),
            ("surface_types", surface_types),
        ):
            if proposed is not None:
                _require_additive_list(brief.get(field), proposed, field, freeze_note)
        for field, proposed in (
            ("module_boundaries", module_boundaries), ("allowed_files", allowed_files),
            ("protected_files", protected_files), ("allowed_new_files", allowed_new_files),
            ("public_api_changes", public_api_changes), ("integration_points", integration_points),
            ("architecture_invariants", architecture_invariants),
            ("forbidden_restructures", forbidden_restructures),
            ("architecture_risks", architecture_risks),
            ("legacy_paths", legacy_paths), ("legacy_terms", legacy_terms),
            ("default_entrypoints", default_entrypoints), ("validators", validators),
            ("sample_outputs", sample_outputs),
        ):
            if proposed is not None:
                _require_additive_list(ab.get(field), proposed, f"architecture_brief.{field}", freeze_note)
        _require_stable_scalar(ab.get("target_structure"), target_structure, "architecture_brief.target_structure", freeze_note)
        _require_stable_scalar(ab.get("migration_source_of_truth"), migration_source_of_truth, "architecture_brief.migration_source_of_truth", freeze_note)
        for field, proposed in (
            ("acceptance_criteria", evaluation_acceptance_criteria),
            ("non_goals", evaluation_non_goals), ("test_obligations", test_obligations),
            ("review_obligations", review_obligations), ("known_risks", known_risks),
            ("system_integration_obligations", system_integration_obligations),
        ):
            if proposed is not None:
                _require_additive_list(ec.get(field), proposed, f"evaluation_contract.{field}", freeze_note)
        _require_stable_scalar(ec.get("user_visible_outcome"), user_visible_outcome, "evaluation_contract.user_visible_outcome", freeze_note)
        _require_stable_scalar(ec.get("closure_question"), closure_question, "evaluation_contract.closure_question", freeze_note)
    if acceptance_criteria is not None: brief["acceptance_criteria"] = acceptance_criteria
    if test_focus is not None: brief["test_focus"] = test_focus
    if review_focus is not None: brief["review_focus"] = review_focus
    if non_goals is not None: brief["non_goals"] = non_goals
    if escalation_triggers is not None: brief["escalation_triggers"] = escalation_triggers
    if surface_types is not None: brief["surface_types"] = surface_types
    # Architecture brief
    if target_structure: ab["target_structure"] = target_structure
    if module_boundaries is not None: ab["module_boundaries"] = module_boundaries
    if allowed_files is not None: ab["allowed_files"] = allowed_files
    if protected_files is not None: ab["protected_files"] = protected_files
    if allowed_new_files is not None: ab["allowed_new_files"] = allowed_new_files
    if public_api_changes is not None: ab["public_api_changes"] = public_api_changes
    if integration_points is not None: ab["integration_points"] = integration_points
    if architecture_invariants is not None: ab["architecture_invariants"] = architecture_invariants
    if forbidden_restructures is not None: ab["forbidden_restructures"] = forbidden_restructures
    if architecture_risks is not None: ab["architecture_risks"] = architecture_risks
    if migration_source_of_truth: ab["migration_source_of_truth"] = migration_source_of_truth
    if legacy_paths is not None: ab["legacy_paths"] = legacy_paths
    if legacy_terms is not None: ab["legacy_terms"] = legacy_terms
    if default_entrypoints is not None: ab["default_entrypoints"] = default_entrypoints
    if validators is not None: ab["validators"] = validators
    if sample_outputs is not None: ab["sample_outputs"] = sample_outputs
    brief["architecture_brief"] = ab
    if user_visible_outcome: ec["user_visible_outcome"] = user_visible_outcome
    if evaluation_acceptance_criteria is not None: ec["acceptance_criteria"] = evaluation_acceptance_criteria
    if evaluation_non_goals is not None: ec["non_goals"] = evaluation_non_goals
    if test_obligations is not None: ec["test_obligations"] = test_obligations
    if review_obligations is not None: ec["review_obligations"] = review_obligations
    if known_risks is not None: ec["known_risks"] = known_risks
    if closure_question: ec["closure_question"] = closure_question
    if system_integration_obligations is not None:
        ec["system_integration_obligations"] = system_integration_obligations
    brief["evaluation_contract"] = ec
    goal["quality_brief"] = brief
    _write(goal_path, goal)
    return goal

# ── goal operations ──────────────────────────────────────────────────

def revise_goal(
    base_dir: str,
    new_goal: str,
    reason: str,
    decision: str = "",
    source: str = "user",
) -> Dict[str, Any]:
    """Revise current goal with intent change tracking. Does NOT modify scope/context."""
    base = Path(base_dir)
    goal_path = base / ".aiwf" / "state" / "goal.json"
    goal = _read(goal_path)
    old_goal = goal.get("current_goal") or goal.get("active_goal", "")
    goal["goal_version"] = goal.get("goal_version", 1) + 1
    if not goal.get("original_intent"): goal["original_intent"] = old_goal or new_goal
    goal["current_goal"] = new_goal
    goal["active_goal"] = new_goal
    goal["last_user_intent"] = new_goal
    goal.setdefault("intent_changes", []).append({
        "version": goal["goal_version"], "from": old_goal, "to": new_goal,
        "reason": reason, "decision": decision, "source": source,
    })
    _write(goal_path, goal)
    return goal


def record_goal_decision(
    base_dir: str,
    decision: str,
    source: str = "user",
) -> Dict[str, Any]:
    """Record a goal-level decision without changing the goal text."""
    base = Path(base_dir)
    goal_path = base / ".aiwf" / "state" / "goal.json"
    goal = _read(goal_path)
    goal.setdefault("decisions", []).append({"decision": decision, "source": source})
    _write(goal_path, goal)
    return goal


def record_meta_critique(base_dir: str, summary: str, recorded_by: str = "planner") -> Dict[str, Any]:
    """Record structured Planner meta-critique after review."""
    from datetime import datetime, timezone
    base = Path(base_dir)
    goal_path = base / ".aiwf" / "state" / "goal.json"
    goal = _read(goal_path)
    goal["meta_critique"] = {
        "status": "completed",
        "summary": summary,
        "recorded_by": recorded_by,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    _write(goal_path, goal)
    return goal

# ── quality policy operations ─────────────────────────────────────────

def record_quality_policy(
    base_dir: str,
    task_type: str,
    workflow_level: str,
    risk_flags: Optional[List[str]] = None,
    routing_reason: str = "",
) -> Dict[str, Any]:
    """Select quality policy and write short keys to state.json. No template fulltext."""
    base = Path(base_dir)
    state_path = base / ".aiwf" / "state" / "state.json"

    state = _read(state_path)
    current_level = state.get("workflow_level", "L1_review_light")
    protected_cycle = _execution_contract_frozen(base, state)
    if (
        protected_cycle
        and current_level in WORKFLOW_LEVELS
        and workflow_level in WORKFLOW_LEVELS
        and WORKFLOW_LEVELS.index(workflow_level) < WORKFLOW_LEVELS.index(current_level)
    ):
        raise ValueError(
            f"cannot lower workflow level from {current_level} to {workflow_level}; "
            f"{_freeze_explanation(base, state)}"
        )

    from .quality_policy import select_quality_policy
    policy = select_quality_policy(task_type, workflow_level, risk_flags, routing_reason)

    state["task_type"] = task_type
    state["workflow_level"] = workflow_level
    state["risk_flags"] = risk_flags or []
    state["test_template"] = policy["test_template"]
    state["review_template"] = policy["review_template"]
    state["exploration_budget"] = policy["exploration_budget"]
    state["asset_policy"] = policy["asset_policy"]
    state["cleanup_policy"] = policy["cleanup_policy"]
    state["git_policy"] = policy["git_policy"]
    state["quality_policy_reason"] = routing_reason
    state["recommended_minimum_level"] = policy.get("recommended_minimum_level", "")
    state["requires_user_decision"] = policy.get("requires_user_decision", False)
    # Detect escalation: recommended level higher than current
    levels = ["L0_direct", "L1_review_light", "L2_standard_team", "L3_full_power"]
    rec_idx = levels.index(policy["recommended_minimum_level"]) if policy.get("recommended_minimum_level") in levels else -1
    cur_idx = levels.index(workflow_level) if workflow_level in levels else 0
    esc_required = (rec_idx > cur_idx)
    # Hard safety net: destructive/migration/deploy tasks cannot stay below L3.
    # security_sensitive -> adversarial review forced, but does NOT force L3.
    if task_type == "security_sensitive" or "security_sensitive" in (risk_flags or []):
        state["adversarial_mode"] = True
        if state.get("review_template") in ("review_lite", "reviewer_light", ""):
            state["review_template"] = "standard_review"
    hard_l3_types = {"data_migration", "destructive_command", "publish_or_deploy"}
    hard_l3_flags = set(risk_flags or []) & hard_l3_types
    # Auto-detect destructive intent from goal text (crude but effective)
    goal_data = _read(base / ".aiwf" / "state" / "goal.json")
    goal_text = (goal_data.get("current_goal") or goal_data.get("active_goal") or "").lower()
    destructive_keywords = [
        "purge", "delete all", "wipe", "clear all", "drop all",
        "remove all", "truncate", "destroy", "nuke"
    ]
    # Auto-detect crypto from goal text (must be after goal_text is read)
    crypto_keywords = ["encrypt", "decrypt", "crypto", "cipher", "AES", "password manager", "key derivation", "Argon2", "Fernet"]
    if any(kw.lower() in goal_text for kw in crypto_keywords):
        state["adversarial_mode"] = True
        if state.get("review_template") in ("review_lite", "reviewer_light", ""):
            state["review_template"] = "standard_review"
    if any(kw in goal_text for kw in destructive_keywords):
        hard_l3_flags.add("destructive_command")
    if (task_type in hard_l3_types or hard_l3_flags) and workflow_level != "L3_full_power":
        esc_required = True
        trigger = task_type if task_type in hard_l3_types else ", ".join(hard_l3_flags)
        state["quality_escalation_required"] = True
        state["quality_escalation_reason"] = f"safety net: {trigger} requires L3_full_power"
        state["recommended_minimum_level"] = "L3_full_power"
        rec_idx = levels.index("L3_full_power")

    # L0 guard: multi-file or complex task types require at least L1
    if workflow_level == "L0_direct" and not esc_required:
        l0_escalations = []
        if task_type in ("refactor", "api_endpoint", "bug_fix", "numeric_semantics"):
            l0_escalations.append(f"task_type '{task_type}' requires at least L1_review_light")
        if risk_flags:
            l0_escalations.append(f"risk flags present: {risk_flags}")
        if l0_escalations:
            esc_required = True
            state["quality_escalation_required"] = True
            state["quality_escalation_reason"] = "; ".join(l0_escalations)
            state["recommended_minimum_level"] = "L1_review_light"
    state["quality_escalation_required"] = esc_required
    policy_reason = "; ".join(policy.get("level_escalations_applied", [])[:3])
    if policy_reason and not state.get("quality_escalation_reason"):
        state["quality_escalation_reason"] = policy_reason
    if policy.get("level_escalations_applied"):
        hist = state.get("escalation_history", []) or []
        for e in policy["level_escalations_applied"]:
            if e not in hist: hist.append(e)
        state["escalation_history"] = hist

    # Gravity escalation: pure read + explicit state mutation at this write boundary.
    try:
        from .task_gravity import apply_gravity_to_state
        state = apply_gravity_to_state(base_dir, state)
    except Exception:
        pass

    _write(state_path, state)
    return policy



def bootstrap_project(base_dir: str) -> Dict[str, Any]:
    """Bootstrap AIWF assets for an existing project. Scans code, creates baseline."""
    root = Path(base_dir)
    aiwf = root / ".aiwf"

    results = {"tasks": [], "files": 0, "modules": []}

    # 1. Scan project structure
    code_files = []
    exclude = {".git", ".aiwf", ".claude", ".reasonix", "__pycache__", "node_modules", ".venv", "venv",
               ".pytest_cache", ".mypy_cache", "dist", "build", ".DS_Store"}
    for f in root.rglob("*"):
        if f.is_file() and not any(e in f.parts for e in exclude):
            if f.suffix in (".py", ".js", ".ts", ".go", ".rs", ".java", ".rb", ".sh", ".md", ".toml", ".yaml", ".json"):
                rel = str(f.relative_to(root))
                code_files.append(rel)

    if not code_files:
        return {"bootstrapped": False, "reason": "no code files found"}

    results["files"] = len(code_files)

    # 2. Identify modules from directory structure
    modules = {}
    for f in code_files:
        parts = f.split("/")
        if len(parts) > 1:
            mod = parts[0]
        else:
            mod = "root"
        modules.setdefault(mod, []).append(f)
    results["modules"] = sorted(modules.keys())

    # 3. Write baseline task-history entry
    from datetime import datetime, timezone
    history_path = aiwf / "history" / "task-history.json"
    history = {"tasks": [], "archived_hotspots": {}}
    if history_path.exists():
        try:
            import json
            history = json.loads(history_path.read_text())
        except Exception:
            pass
    baseline_task = {
        "id": "BASELINE-001",
        "title": "[Bootstrap] Existing codebase baseline",
        "goal": "Project bootstrapped from existing code",
        "workflow_level": "baseline",
        "task_type": "bootstrap",
        "changed_files": code_files[:50],
        "testing_status": "n/a",
        "review_result": "n/a",
        "fix_loop_attempt_count": 0,
        "untested_risk_count": 0,
        "closed_at": datetime.now(timezone.utc).isoformat(),
        "bootstrap": True,
    }
    tasks = history.get("tasks", [])
    tasks = [t for t in tasks if not t.get("bootstrap")]
    tasks.insert(0, baseline_task)
    history["tasks"] = tasks
    import json
    (aiwf / "history" / "task-history.json").write_text(json.dumps(history, indent=2))
    results["tasks"].append("task-history baseline written")

    # 4. Ensure human project map exists, but do not mechanically fill it.
    from .project_map import ensure_project_map
    ensure_project_map(base_dir)
    results["tasks"].append("PROJECT-MAP scaffold ready for Planner curation")

    # 4b. Ensure idea inbox exists for volatile planning inputs.
    from .ideas import ensure_ideas_file
    ensure_ideas_file(base_dir)
    results["tasks"].append("ideas.md initialized")

    # 5. Run env scan if possible
    try:
        from .environment import scan_environment, write_environment_profile
        env = scan_environment(base_dir)
        write_environment_profile(base_dir, env)
        results["tasks"].append("environment profile written")
    except Exception:
        pass

    # 6. Run capability scan
    try:
        from .capabilities import discover_capabilities, write_capabilities_registry
        caps = discover_capabilities(base_dir)
        write_capabilities_registry(base_dir, caps)
        results["tasks"].append(f"capability scan: {len(caps.get('capabilities',[]))} found")
    except Exception:
        pass

    # 7. Create initial workspace-drift snapshot
    try:
        from .workspace_drift import scan_workspace_drift, write_workspace_drift
        drift = scan_workspace_drift(base_dir)
        write_workspace_drift(base_dir, drift)
        results["tasks"].append("workspace drift baseline captured")
    except Exception:
        pass

    return {"bootstrapped": True, **results}

# ── state summary for skills ──────────────────────────────────────────

# ── state summary for skills ──────────────────────────────────────────

def get_state_summary(base_dir: str) -> Dict[str, Any]:
    """Return a concise summary of current AIWF state for skills."""
    base = Path(base_dir)

    def rj(name, default=None):
        return _read(base / ".aiwf" / name) if (base / ".aiwf" / name).exists() else (default or {})

    state = rj("state/state.json", {"phase": "unknown"})
    goal = rj("state/goal.json", {})
    review = rj("quality/review.json", {})
    fix_loop = rj("state/fix-loop.json", {"status": "none"})

    return {
        "phase": state.get("phase", "unknown"),
        "complexity": state.get("complexity", "standard"),
        "workflow_level": state.get("workflow_level", state.get("workflow_strength", "L1_review_light")),
        "task_type": state.get("task_type", ""),
        "test_template": state.get("test_template", ""),
        "review_template": state.get("review_template", ""),
        "exploration_budget": state.get("exploration_budget", ""),
        "git_policy": state.get("git_policy", "no_auto_commit"),
        "recommended_minimum_level": state.get("recommended_minimum_level", ""),
        "requires_user_decision": state.get("requires_user_decision", False),
        "quality_escalation_required": state.get("quality_escalation_required", False),
        "quality_escalation_reason": state.get("quality_escalation_reason", ""),
        "active_goal": goal.get("active_goal", ""),
        "active_context_id": state.get("active_context_id", ""),
        "close_attempt": state.get("close_attempt", False),
        "scope_violation": state.get("scope_violation", False),
        "review_result": review.get("result", "unknown"),
        "closure_allowed": review.get("closure_allowed", False),
        "cleanup_status": review.get("cleanup_status", "unknown"),
        "structure_status": review.get("structure_status", "unknown"),
        "fix_loop_status": fix_loop.get("status", "none"),
    }
