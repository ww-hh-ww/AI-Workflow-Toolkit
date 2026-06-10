"""Context operations — start_context, critical asset bootstrapping, role evidence."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ._common import _execution_contract_frozen, _freeze_explanation, _read, _write

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
    from ..evidence_schema import next_ev_id

    active_context = context_id or state.get("active_context_id") or ""
    synthetic_session = active_context or "aiwf"
    scanned_files: List[str] = []
    scanned_source = "not_scanned"
    if scan_git:
        try:
            from ...hooks.common.diff_snapshot import detect_changed_files_with_baseline
            scan = detect_changed_files_with_baseline(base)
            scanned_files = list(scan.get("files", []) or [])
            scanned_source = str(scan.get("source", "") or "git_diff")
        except Exception:
            scanned_files = []
            scanned_source = "scan_failed"
    delivered_files = list(changed_files or [])
    effective_changed = delivered_files or scanned_files
    # Determine trust level from capture method
    trust_lvl = "role_recorded"
    if command and scan_git:
        trust_lvl = "command_observed"
    elif scan_git:
        trust_lvl = "git_observed"
    elif command:
        trust_lvl = "command_observed"

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
        "trust_level": trust_lvl,
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
            from ..environment import scan_environment, write_environment_profile
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
                        from ..environment import scan_environment, write_environment_profile
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
            from ..capabilities import discover_capabilities, write_capabilities_registry
            caps = discover_capabilities(base_dir)
            write_capabilities_registry(base_dir, caps)
            filled.append(f"capability registry ({len(caps.get('capabilities', []))} found)")
        except Exception:
            pass

    # 3. PROJECT-MAP
    pm_path = aiwf / "reports" / "项目地图.md"
    if not pm_path.exists():
        try:
            from ..project_map import ensure_project_map
            ensure_project_map(base_dir)
            filled.append("PROJECT-MAP")
        except Exception:
            pass

    # 4. Idea inbox
    ideas_path = aiwf / "reports" / "ideas.md"
    if not ideas_path.exists():
        try:
            from ..ideas import ensure_ideas_file
            ensure_ideas_file(base_dir)
            filled.append("ideas.md")
        except Exception:
            pass

    # 6. task-history baseline (if completely empty)
    th_path = aiwf / "history" / "task-history.json"
    if not th_path.exists():
        try:
            from ..workspace_drift import auto_update_baseline
            auto_update_baseline(base_dir)
            filled.append("task-history baseline")
        except Exception:
            pass

    if filled:
        notes.append(f"[ASSET] Auto-filled: {', '.join(filled)}")
    return notes

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
        from ..workspace_drift import scan_workspace_drift, write_workspace_drift, auto_update_baseline
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
        from ..task_gravity import task_gravity
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

