"""Context operations — start_context, critical asset bootstrapping, role evidence."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ._common import _execution_contract_frozen, _freeze_explanation, _locked_json_update, _read, _write
from .goal_ops import get_active_goal


def _resolve_tree_inheritance(
    base_dir: str,
    plan_id: str = "",
    goal_id: str = "",
) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
    """Walk the Goal Tree to collect inherited boundaries.

    Returns (inherited_defaults, parent_info, warnings).
    - inherited_defaults: fields to use as defaults when Planner doesn't override
    - parent_info: debug info about which parents were found
    - warnings: potential conflicts (e.g. non_goals in allowed_write)
    """
    base = Path(base_dir)
    inherited: Dict[str, Any] = {}
    parent_info: Dict[str, Any] = {}
    warnings: List[str] = []

    # ── Resolve Plan ──
    plan = None
    if plan_id:
        plans_data = _read(base / ".aiwf" / "state" / "plans.json", {"plans": []})
        for p in plans_data.get("plans", []) or []:
            if isinstance(p, dict) and p.get("id") == plan_id:
                plan = p
                break
        if not plan:
            # Also check active_plan_id in state
            state = _read(base / ".aiwf" / "state" / "state.json", {})
            active_plan = state.get("active_plan_id", "")
            if active_plan:
                for p in plans_data.get("plans", []) or []:
                    if isinstance(p, dict) and p.get("id") == active_plan:
                        plan = p
                        break

    # ── Resolve Goal ──
    goal = None
    if goal_id or (plan and plan.get("target_goal_id")):
        gid = goal_id or plan.get("target_goal_id", "")
        goals_data = _read(base / ".aiwf" / "state" / "goals.json", {"goals": []})
        for g in goals_data.get("goals", []) or []:
            if isinstance(g, dict) and g.get("id") == gid:
                goal = g
                break

    # -- Also read goals.json quality_brief for Architecture Brief inheritance --
    goal_json = get_active_goal(base_dir)
    quality_brief = goal_json.get("quality_brief", {}) or {}
    arch_brief = quality_brief.get("architecture_brief", {}) or {}

    # ── Inherit from Goal ──
    if goal:
        parent_info["goal_id"] = goal.get("id", "")
        parent_info["goal_title"] = goal.get("title", "")[:80]

        # surface_types → default test_focus
        goal_surfaces = goal.get("surface_types", []) or []
        if goal_surfaces:
            inherited.setdefault("test_focus", [])
            for s in goal_surfaces:
                if s not in inherited["test_focus"]:
                    inherited["test_focus"].append(f"surface:{s}")

        # architecture_invariants → default review_focus
        goal_invariants = goal.get("architecture_invariants", []) or []
        if goal_invariants:
            inherited.setdefault("review_focus", [])
            for inv in goal_invariants:
                entry = f"invariant:{inv}" if isinstance(inv, str) else str(inv)
                if entry not in inherited["review_focus"]:
                    inherited["review_focus"].append(entry)

        # non_goals from Goal
        goal_non_goals = goal.get("non_goals", []) or []
        if goal_non_goals:
            inherited.setdefault("non_goals", [])
            for ng in goal_non_goals:
                if ng not in inherited["non_goals"]:
                    inherited["non_goals"].append(ng)

        # module_boundaries → hint for allowed_write
        goal_modules = goal.get("module_boundaries", []) or []
        if goal_modules:
            inherited["_suggested_modules"] = list(goal_modules)

        # Temporary Root → require isolation
        if goal.get("type") == "temporary":
            inherited.setdefault("non_goals", [])
            isolation_msg = f"temporary_root:{goal.get('id', '?')} — isolate from stable structure"
            if isolation_msg not in inherited["non_goals"]:
                inherited["non_goals"].append(isolation_msg)
            warnings.append(
                f"Parent Goal '{goal.get('id')}' is a Temporary Root — "
                "exploration must be isolated from stable structure"
            )

    # -- Inherit from Architecture Brief (goals.json) --
    if arch_brief:
        parent_info["arch_brief"] = "present"

        # protected_files → should appear in forbidden_write
        arch_protected = arch_brief.get("protected_files", []) or []
        if arch_protected:
            inherited.setdefault("_suggested_forbidden", [])
            for pf in arch_protected:
                if pf not in inherited["_suggested_forbidden"]:
                    inherited["_suggested_forbidden"].append(pf)

        # forbidden_restructures → escalation triggers
        arch_forbidden = arch_brief.get("forbidden_restructures", []) or []
        if arch_forbidden:
            inherited.setdefault("escalation_triggers", [])
            for fr in arch_forbidden:
                trigger = f"forbidden_restructure:{fr}"
                if trigger not in inherited["escalation_triggers"]:
                    inherited["escalation_triggers"].append(trigger)

    # ── Inherit from Plan ──
    if plan:
        parent_info["plan_id"] = plan.get("id", "")
        parent_info["plan_kind"] = plan.get("plan_kind", "")
        parent_info["work_intent"] = plan.get("work_intent", "")

        # Plan interfaces → interface_contract
        plan_interfaces = plan.get("interfaces", []) or []
        if plan_interfaces:
            inherited.setdefault("interface_contract", "")
            if not inherited["interface_contract"]:
                inherited["interface_contract"] = "; ".join(str(i) for i in plan_interfaces)

        # Plan constraints → context constraints
        plan_constraints = plan.get("constraints", []) or []
        if plan_constraints:
            inherited.setdefault("_plan_constraints", [])
            for c in plan_constraints:
                if c not in inherited["_plan_constraints"]:
                    inherited["_plan_constraints"].append(str(c))

        # work_intent → derived forbidden_changes
        intent = plan.get("work_intent", "")
        if intent:
            forbids = _intent_forbidden_changes(intent)
            if forbids:
                inherited.setdefault("_intent_forbidden", [])
                for f in forbids:
                    if f not in inherited["_intent_forbidden"]:
                        inherited["_intent_forbidden"].append(f)

    # ── Validate: non_goals should not overlap with allowed_write ──
    inherited_non_goals = inherited.get("non_goals", []) or []
    inherited_suggested = inherited.get("_suggested_modules", []) or []
    for ng in inherited_non_goals:
        for mod in inherited_suggested:
            if ng.lower() in mod.lower() or mod.lower() in ng.lower():
                warnings.append(
                    f"Potential conflict: non_goal '{ng}' overlaps with suggested module '{mod}'"
                )

    return inherited, parent_info, warnings


_INTENT_FORBIDDEN_MAP = {
    "feature": [],
    "bugfix": ["refactor_unrelated", "new_feature", "api_change"],
    "refactor": ["new_feature", "api_change", "behavior_change"],
    "cleanup": ["new_feature", "refactor", "semantic_change", "delete_machine_truth"],
    "migration": ["delete_old_path", "break_compatibility"],
    "verification": ["change_implementation", "new_feature"],
    "exploration": ["commit_to_stable_structure", "modify_goal_tree"],
    "documentation": ["change_machine_semantics", "change_behavior"],
    "integration": ["change_interfaces", "new_feature"],
    "release": ["change_behavior", "new_feature", "refactor"],
}


def _intent_forbidden_changes(intent: str) -> List[str]:
    """Return derived forbidden_changes for a given work_intent."""
    return _INTENT_FORBIDDEN_MAP.get(intent, [])

def _git_diff_baseline(base: Path, baseline_ref: str) -> Dict[str, Any]:
    """Get files changed since the evidence baseline ref.

    Returns dict with files, source, and evidence_head_ref.
    evidence_head_ref is a git stash create snapshot — a lightweight
    commit object capturing the working tree at evidence time. Store it
    to enable `git diff baseline_ref..evidence_head_ref` later.
    """
    import subprocess
    result: Dict[str, Any] = {"files": [], "source": "baseline_diff", "evidence_head_ref": ""}
    try:
        r = subprocess.run(
            ["git", "diff", "--name-only", baseline_ref, "HEAD"],
            capture_output=True, text=True, cwd=str(base), timeout=10,
        )
        committed = [f.strip() for f in r.stdout.split("\n") if f.strip()] if r.returncode == 0 else []

        r2 = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, cwd=str(base), timeout=10,
        )
        dirty = [f.strip() for f in r2.stdout.split("\n") if f.strip()] if r2.returncode == 0 else []

        r3 = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            capture_output=True, text=True, cwd=str(base), timeout=10,
        )
        untracked = [f.strip() for f in r3.stdout.split("\n") if f.strip()] if r3.returncode == 0 else []

        from ...hooks.common.diff_snapshot import filter_internal
        all_files = list(set(committed + dirty + untracked))
        result["files"] = sorted(filter_internal(all_files, cwd=base))

        # Capture working tree snapshot for later diff backtracking.
        # git stash create returns a commit hash without touching the stash stack.
        r4 = subprocess.run(
            ["git", "stash", "create"],
            capture_output=True, text=True, cwd=str(base), timeout=10,
        )
        if r4.returncode == 0 and r4.stdout.strip():
            result["evidence_head_ref"] = r4.stdout.strip()
    except Exception:
        result["source"] = "baseline_diff_failed"
    return result


def _check_forbidden_write_violations(
    changed_files: List[str],
    forbidden_patterns: List[str],
    base: Path,
    task_id: str,
) -> List[str]:
    """Check changed files against Task.md forbidden_write patterns.

    Returns list of violating file paths. Records violations in review.json
    and opens fix-loop when violations found.
    """
    from ...hooks.common.diff_snapshot import filter_internal
    from ...core.scope_policy import _matches

    project_files = filter_internal(changed_files, cwd=base)
    violations = []
    for f in project_files:
        for pattern in forbidden_patterns:
            if _matches(f, pattern):
                violations.append(f)
                break

    if violations:
        state_path = base / ".aiwf" / "state" / "state.json"
        state = _read(state_path, {})
        state["scope_violation"] = True
        _write(state_path, state)

        fix_path = base / ".aiwf" / "state" / "fix-loop.json"
        from ...core.state_schema import default_fix_loop
        fix_loop = _read(fix_path, default_fix_loop())
        if fix_loop.get("status") != "open":
            fix_loop["status"] = "open"
            fix_loop["required_fixes"] = [
                f"Revert: {vf} — matched Forbidden Write pattern from {task_id}.md" for vf in violations
            ]
            fix_loop["route"] = "planner"
            _write(fix_path, fix_loop)

        review_path = base / ".aiwf" / "records" / "review.json"
        from ...core.state_schema import default_review
        from ...core.review_contract import add_scope_violation_blocker
        review = _read(review_path, default_review())
        for vf in violations:
            add_scope_violation_blocker(review, vf, task_id)
        _write(review_path, review)

    return violations


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
    supports_plan: str = "",
    supports_goal: str = "",
    task_id: str = "",
) -> Dict[str, Any]:
    """Append one role-scoped evidence record per phase (not per tool call).

    When scan_git=True, diffs against the evidence_baseline_ref recorded at
    task activation time — capturing all changes the executor made in one shot.
    """
    role = role.strip().lower()
    if role not in ("executor", "tester", "reviewer", "planner"):
        raise ValueError(f"unknown role evidence role: {role}")
    if status not in ("pending", "accepted", "rejected"):
        raise ValueError(f"unknown role evidence status: {status}")

    base = Path(base_dir)
    evidence_path = base / ".aiwf" / "records" / "evidence.json"
    state = _read(base / ".aiwf" / "state" / "state.json")
    active_context = context_id or state.get("active_context_id") or ""
    active_task_id = str(task_id or state.get("active_task_id") or "")
    inferred_plan = ""
    inferred_goal = ""
    if active_task_id:
        try:
            from ..task_ledger import load_ledger
            ledger = load_ledger(base_dir)
            for task in ledger.get("tasks", []) or []:
                if isinstance(task, dict) and task.get("id") == active_task_id:
                    inferred_plan = str(task.get("plan_id") or task.get("parent_plan") or "")
                    inferred_goal = str(task.get("goal_id") or task.get("parent_goal") or "")
                    break
        except Exception:
            pass
    effective_plan = supports_plan or inferred_plan
    effective_goal = supports_goal or inferred_goal
    synthetic_session = session_id or active_context or "aiwf"

    scanned_files: List[str] = []
    scanned_source = "not_scanned"
    evidence_origin_ref = state.get("evidence_origin_ref", "")
    evidence_baseline_ref = ""
    evidence_head_ref = ""

    if scan_git:
        baseline_ref = state.get("evidence_baseline_ref", "")
        if baseline_ref:
            evidence_baseline_ref = baseline_ref
            try:
                scan = _git_diff_baseline(base, baseline_ref)
                scanned_files = list(scan.get("files", []) or [])
                scanned_source = str(scan.get("source", "") or "baseline_diff")
                evidence_head_ref = str(scan.get("evidence_head_ref", "") or "")
                # Pin the snapshot ref so git gc won't collect it.
                # refs/aiwf/evidence/* is local-only, never pushed.
                if evidence_head_ref and active_task_id:
                    import subprocess
                    subprocess.run(
                        ["git", "update-ref", f"refs/aiwf/evidence/{active_task_id}", evidence_head_ref],
                        capture_output=True, cwd=str(base), timeout=10,
                    )
            except Exception:
                scanned_files = []
                scanned_source = "baseline_diff_failed"
        else:
            # Fallback: no baseline recorded (pre-existing active task)
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

    # Scope violation check for executor: verify no changed file matches
    # forbidden_write from active Task.md. This is the safety net behind
    # the pre-tool Write gate.
    if role == "executor" and effective_changed and active_task_id:
        try:
            from ...hooks.common.scope_checker import _get_task_forbidden_write
            forbidden = _get_task_forbidden_write(base, active_task_id)
            if forbidden:
                _check_forbidden_write_violations(
                    effective_changed, forbidden, base, active_task_id)
        except Exception:
            pass

    trust_lvl = "role_recorded"
    if command and scan_git:
        trust_lvl = "command_observed"
    elif scan_git:
        trust_lvl = "git_observed"
    elif command:
        trust_lvl = "command_observed"

    from ..evidence_schema import next_ev_id

    def _append(evidence: Dict[str, Any]) -> Dict[str, Any]:
        records = evidence.get("records", [])
        if not isinstance(records, list):
            records = []
        record = {
            "id": next_ev_id(records),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "context_id": active_context,
            "phase": state.get("phase", ""),
            "session_id": session_id or synthetic_session,
            "agent_id": agent_id or role,
            "agent_type": agent_type or role,
            "tool_name": "AIWFRoleEvidence",
            "tool_input": {
                "role": role,
                "summary": summary,
                "scan_git": bool(scan_git),
                "supports_plan": effective_plan,
                "supports_goal": effective_goal,
            },
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
            "task_id": active_task_id,
            "supports_plan": effective_plan,
            "supports_goal": effective_goal,
            "evidence_origin_ref": evidence_origin_ref,
            "evidence_baseline_ref": evidence_baseline_ref,
            "evidence_head_ref": evidence_head_ref,
        }
        records.append(record)
        evidence["records"] = records
        evidence["updated_at"] = record["timestamp"]
        return record

    record = _locked_json_update(evidence_path, {"records": []}, _append)

    # Advance baseline so the next role's diff is incremental.
    # Each role's evidence captures only what THEY added.
    if evidence_head_ref and scan_git:
        state["evidence_baseline_ref"] = evidence_head_ref
        _write(base / ".aiwf" / "state" / "state.json", state)

    # Advance phase after executor evidence
    if role == "executor" and state.get("phase") not in ("closing", "closed"):
        state["phase"] = "testing"
        _write(base / ".aiwf" / "state" / "state.json", state)

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
    env_path = aiwf / "records" / "events.json"
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
    cap_path = aiwf / "records" / "events.json"
    if not cap_path.exists():
        try:
            from ..capabilities import discover_capabilities, write_capabilities_registry
            caps = discover_capabilities(base_dir)
            write_capabilities_registry(base_dir, caps)
            filled.append(f"capability registry ({len(caps.get('capabilities', []))} found)")
        except Exception:
            pass

    # 3. PROJECT-MAP
    pm_path = aiwf / "records" / "events.json"
    if not pm_path.exists():
        try:
            from ..project_map import ensure_project_map
            ensure_project_map(base_dir)
            filled.append("PROJECT-MAP")
        except Exception:
            pass

    # 4. Idea inbox
    ideas_path = aiwf / "records" / "events.json"
    if not ideas_path.exists():
        try:
            from ..ideas import ensure_ideas_file
            ensure_ideas_file(base_dir)
            filled.append("ideas.md")
        except Exception:
            pass

    # 6. task-history baseline (if completely empty)
    th_path = aiwf / "state" / "tasks.json"
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
    contexts_path = base / ".aiwf" / "state" / "state.json"
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

    # ── Tree-driven contract inheritance ──
    # When creating a NEW context, pull defaults from parent Goal/Plan.
    # Planner's explicit arguments override inherited values.
    if not existing:
        active_plan = state.get("active_plan_id", "")
        plan_id_hint = active_plan
        # Try to resolve plan from task ledger if we have an active task
        if active_task_id:
            try:
                from ..task_ledger import load_ledger
                ledger = load_ledger(base_dir)
                for t in ledger.get("tasks", []) or []:
                    if isinstance(t, dict) and t.get("id") == active_task_id:
                        plan_id_hint = t.get("plan_id") or t.get("parent_plan") or plan_id_hint
                        break
            except Exception:
                pass

        if plan_id_hint:
            try:
                inherited, parent_info, tree_warnings = _resolve_tree_inheritance(
                    base_dir, plan_id=plan_id_hint
                )
                # Apply inherited defaults — only when Planner didn't provide an explicit value
                if inherited.get("test_focus") and test_focus is None:
                    test_focus = inherited["test_focus"]
                if inherited.get("review_focus") and review_focus is None:
                    review_focus = inherited["review_focus"]
                if inherited.get("non_goals") and non_goals is None:
                    non_goals = inherited["non_goals"]
                if inherited.get("interface_contract") and not interface_contract:
                    interface_contract = inherited["interface_contract"]
                if inherited.get("escalation_triggers") and escalation_triggers is None:
                    escalation_triggers = inherited["escalation_triggers"]
                # Suggested forbidden_write from Architecture Brief protected_files
                if inherited.get("_suggested_forbidden") and forbidden_write is None:
                    forbidden_write = inherited["_suggested_forbidden"]
                # Work Intent derived forbidden changes → inject into context notes
                intent_forbidden = inherited.get("_intent_forbidden", []) or []
                # Suggested modules from Goal module_boundaries
                if inherited.get("_suggested_modules") and allowed_write is None:
                    allowed_write = inherited["_suggested_modules"]

                # Inject parent info + warnings as context notes
                if parent_info:
                    tree_note = (
                        f"[TREE] Inherited from "
                        + (f"Goal:{parent_info.get('goal_id', '?')} " if parent_info.get("goal_id") else "")
                        + (f"Plan:{parent_info.get('plan_id', '?')} " if parent_info.get("plan_id") else "")
                        + (f"kind={parent_info.get('plan_kind', '')} " if parent_info.get("plan_kind") else "")
                        + (f"intent={parent_info.get('work_intent', '')}" if parent_info.get("work_intent") else "")
                    ).strip()
                    if not note:
                        note = tree_note
                    else:
                        note = tree_note + "\n" + note

                if intent_forbidden:
                    intent_note = f"[INTENT] Derived forbidden: {', '.join(intent_forbidden)}"
                    if not note:
                        note = intent_note
                    else:
                        note = intent_note + "\n" + note

                if tree_warnings:
                    for w in tree_warnings:
                        warn_note = f"[WARN] {w}"
                        if not note:
                            note = warn_note
                        else:
                            note = warn_note + "\n" + note
            except Exception:
                pass
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
    if state.get("phase") in ("discussing", "planned", "planning"):
        state["phase"] = "executing"
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

    # ── Mission context (soft) — inject the project's "why" as a constant reference ──
    # Mission does NOT block activation; it provides semantic anchoring. If present,
    # Planner and all agents see it on every context start.
    try:
        mission_path = base / ".aiwf" / "state" / "mission.json"
        if mission_path.exists():
            import json as _json
            mission = _json.loads(mission_path.read_text(encoding="utf-8"))
            statement = str(mission.get("statement", "") or "").strip()
            boundaries = mission.get("boundaries", []) or []
            if statement or boundaries:
                mission_lines = ["[MISSION]"]
                if statement:
                    mission_lines.append(f"  Why: {statement}")
                if boundaries:
                    mission_lines.append(f"  Boundaries: {', '.join(str(b) for b in boundaries)}")
                mission_note = "\n".join(mission_lines)
                if isinstance(ctx.get("notes"), list):
                    ctx["notes"].append(mission_note)
                else:
                    ctx["notes"] = [mission_note]
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
