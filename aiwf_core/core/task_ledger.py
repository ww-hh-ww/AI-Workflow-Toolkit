"""Flexible task ledger and execution-window checks.

The ledger is advisory for planning shape, but mechanical for active execution:
Planner may keep many candidate/ready tasks, while activation enforces dependency
and active-window discipline.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .current_state import current_state_freshness


VALID_TASK_STATUSES = {"candidate", "ready", "active", "blocked", "suspended", "closed", "rejected"}
WORKFLOW_LEVELS = ["L0_direct", "L1_review_light", "L2_standard_team", "L3_full_power"]

# Task granularity: titles that smell like actions, not deliverables.
# Tasks must be verifiable outcome units, not single-step actions.
_ACTION_SMELL_PREFIXES = [
    "check ", "look at ", "read ", "run ", "view ", "find ", "search ",
    "open ", "test ", "debug ", "investigate ", "try ", "explore ",
]
_ACTION_SMELL_PHRASES = [
    "change one line", "fix typo", "add comment", "update readme",
    "跑一下", "看看", "检查一下", "试一下",
]


def _detect_action_smell(title: str) -> List[str]:
    """Return warnings if a task title looks like an action, not a deliverable.

    A task should describe a verifiable outcome, e.g.:
      "route CLI is reachable from entry point with smoke test"
    Not an action step, e.g.:
      "check routing.py"
      "run tests"
      "update README"
    """
    warnings = []
    tl = title.strip().lower()
    for prefix in _ACTION_SMELL_PREFIXES:
        if tl.startswith(prefix):
            warnings.append(
                f"Task title starts with '{prefix.strip()}' — tasks should describe "
                f"verifiable outcomes, not actions. Consider merging into a larger deliverable task."
            )
            break
    for phrase in _ACTION_SMELL_PHRASES:
        if phrase in tl:
            warnings.append(
                f"Task title contains '{phrase}' — this smells like an action step. "
                f"Tasks should be deliverable units with a verifiable outcome."
            )
            break
    return warnings


def _read(path: Path, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else (default or {})
    except Exception:
        return default or {}


def _write(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ledger_path(base_dir: str) -> Path:
    return Path(base_dir) / ".aiwf" / "runtime" / "history" / "task-ledger.json"


def default_ledger() -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "execution_window": {
            "default_max_active": 1,
            "active_task_ids": [],
        },
        "tasks": [],
    }


def load_ledger(base_dir: str) -> Dict[str, Any]:
    ledger = _read(ledger_path(base_dir), default_ledger())
    if not isinstance(ledger.get("tasks"), list):
        ledger["tasks"] = []
    window = ledger.setdefault("execution_window", {})
    window.setdefault("default_max_active", 1)
    window.setdefault("active_task_ids", [])
    ledger.setdefault("schema_version", 1)
    return ledger


def save_ledger(base_dir: str, ledger: Dict[str, Any]) -> None:
    _write(ledger_path(base_dir), ledger)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _find(tasks: List[Dict[str, Any]], task_id: str) -> Optional[Dict[str, Any]]:
    for task in tasks:
        if task.get("id") == task_id:
            return task
    return None


def upsert_task(
    base_dir: str,
    task_id: str,
    title: str = "",
    status: str = "candidate",
    dependencies: Optional[List[str]] = None,
    allowed_write: Optional[List[str]] = None,   # DEPRECATED: ignored; scope lives on Plan
    parallel_safe: bool = False,
    notes: Optional[List[str]] = None,
    parent_goal: str = "",
    parent_plan: str = "",
    goal_id: str = "",
    plan_id: str = "",
    milestone: str = "",
    milestone_id: str = "",
) -> Dict[str, Any]:
    """Create/update a task without activating execution.

    parent_goal/goal_id: the GOAL-ID this task serves (task is execution unit, not goal unit).
    parent_plan/plan_id: the PLAN-ID this task belongs to.
    milestone: the milestone this task advances.
    """
    if status not in VALID_TASK_STATUSES:
        raise ValueError(f"invalid task status: {status}")
    ledger = load_ledger(base_dir)
    tasks = ledger["tasks"]
    task = _find(tasks, task_id)
    if task and task.get("status") == "active":
        contract_changes = []
        if status != "active": contract_changes.append("status")
        if dependencies is not None and dependencies != (task.get("dependencies", []) or []):
            contract_changes.append("dependencies")
        if bool(parallel_safe) != bool(task.get("parallel_safe", False)):
            contract_changes.append("parallel_safe")
        if contract_changes:
            raise ValueError(
                "active task contract is frozen; cannot change " + ", ".join(contract_changes)
                + "; this prevents retrospective scope/status changes. "
                "Allowed now: add notes and complete the current contract. "
                "To change the contract: aiwf task suspend <TASK-ID>, resolve any failing gates, "
                "then plan/activate a future task"
            )
    if not task:
        task = {
            "id": task_id,
            "title": title or task_id,
            "status": status,
            "dependencies": [],
            "parallel_safe": False,
            "notes": [],
            "created_at": _now(),
            "updated_at": _now(),
            "parent_goal": "",
            "parent_plan": "",
            "goal_id": "",
            "plan_id": "",
            "milestone": "",
            "milestone_id": "",
        }
        tasks.append(task)
    if title:
        task["title"] = title
    task["status"] = status
    if dependencies is not None:
        task["dependencies"] = dependencies
    task["parallel_safe"] = bool(parallel_safe)
    if notes:
        task.setdefault("notes", []).extend(notes)
    effective_goal = goal_id or parent_goal
    effective_plan = plan_id or parent_plan
    if effective_goal:
        task["goal_id"] = effective_goal
        task["parent_goal"] = effective_goal
    if effective_plan:
        task["plan_id"] = effective_plan
        task["parent_plan"] = effective_plan
    if milestone:
        task["milestone"] = milestone
    if milestone_id:
        task["milestone_id"] = milestone_id
    task["updated_at"] = _now()
    _sync_active_ids(ledger)
    save_ledger(base_dir, ledger)
    if effective_plan:
        try:
            from .state.plan_ops import attach_task_to_plan, plan_exists
            if plan_exists(base_dir, effective_plan):
                attach_task_to_plan(base_dir, effective_plan, task_id)
        except Exception:
            pass
    granularity = _detect_action_smell(task.get("title", ""))
    return {"task": task, "ledger": ledger, "granularity_warnings": granularity}


def _sync_active_ids(ledger: Dict[str, Any]) -> None:
    active = [t.get("id") for t in ledger.get("tasks", []) if t.get("status") == "active" and t.get("id")]
    ledger.setdefault("execution_window", {})["active_task_ids"] = active


def _overlap(a: List[str], b: List[str]) -> List[str]:
    return sorted(set(a or []) & set(b or []))


def _task_plan_scope(base_dir: str, task: Dict[str, Any]) -> List[str]:
    """Read the task's scope boundary — Plan is authoritative, task is legacy fallback."""
    plan_id = str(task.get("plan_id") or task.get("parent_plan") or "")
    if plan_id:
        try:
            from .state.plan_ops import get_plan
            plan = get_plan(base_dir, plan_id, migrate=False)
            plan_scope = plan.get("allowed_write", []) or []
            if plan_scope:
                return list(plan_scope)
        except Exception:
            pass
    # Legacy fallback: task-level allowed_write (deprecated, will be removed)
    return list(task.get("allowed_write", []) or [])


def _quality_activation_blockers(base_dir: str, task: Dict[str, Any]) -> List[str]:
    """Consume task_gravity() for quality-based activation blockers."""
    # Architecture review tasks are the REMEDY for gravity warnings, not
    # subject to them. Blocking ARCH- tasks with gravity constraints
    # creates a deadlock: need arch review → can't activate any task
    # including the arch review task itself.
    if _is_architecture_review_task(task):
        return []
    from .task_gravity import task_gravity
    gravity = task_gravity(base_dir, _task_plan_scope(base_dir, task))
    blockers: List[str] = []
    for c in gravity.get("hard_constraints", []):
        kind = c.get("kind", "")
        if kind == "repeated_change_hotspot":
            label = "repeated-change hotspot"
        elif kind == "fix_loop_trend":
            label = "cross-task quality escalation"
        else:
            label = kind
        blockers.append(f"[gravity] {label}: {c['message']}")
    return blockers


def _is_architecture_review_task(task: Dict[str, Any]) -> bool:
    task_id = str(task.get("id", "") or "")
    title = str(task.get("title", "") or "").strip().lower()
    return task_id.startswith("ARCH-") or title.startswith("[architect]")


def _mechanical_routing_factors(base_dir: str, task: Dict[str, Any]) -> Dict[str, bool]:
    """Derive conservative routing factors from machine-readable task/project state.

    V2-A: now produces granular prior_fix_loop, semantic_change, and
    machine_verifiable factors alongside the original coarse factors.
    """
    root = Path(base_dir)
    allowed = [str(p) for p in _task_plan_scope(base_dir, task) if str(p)]
    module_roots = {
        p.replace("\\", "/").split("/")[0]
        for p in allowed
        if "/" in p.replace("\\", "/")
    }
    goal = _read(root / ".aiwf" / "state" / "goal.json", {})
    brief = goal.get("quality_brief", {}).get("architecture_brief", {}) or {}
    state = _read(root / ".aiwf" / "state" / "state.json", {})
    fix_loop = _read(root / ".aiwf" / "state" / "fix-loop.json", {})
    risk_flags = set(state.get("risk_flags", []) or [])
    non_docs = [p for p in allowed if not p.lower().endswith((".md", ".txt", ".rst"))]
    background = {}

    if state.get("cross_task_quality_escalation_required"):
        background["historical_deferred_risk"] = True
    if fix_loop.get("attempt_count", 0) and fix_loop.get("status") != "open":
        background["prior_fix_loop_history"] = True
    if brief.get("target_structure") or brief.get("module_boundaries") or brief.get("forbidden_restructures"):
        background["architecture_brief_present"] = True

    # ── V2-A: granular fix_loop classification ──
    from .routing import classify_fix_loop
    task_id = str(task.get("id", "") or "")
    primary_fix_loop, extra_bg = classify_fix_loop(fix_loop, task_id, allowed)
    for eb in extra_bg:
        background[eb] = True

    # ── V2-A: granular semantic change classification ──
    from .routing import classify_semantic_change, detect_machine_verifiable
    semantic_type = classify_semantic_change(allowed)
    has_semantic = bool(non_docs)
    is_mechanical = semantic_type == "semantic_mechanical"
    is_contract = semantic_type == "semantic_contract"
    is_core_gate = semantic_type == "semantic_core_gate"
    is_machine_verifiable = detect_machine_verifiable(allowed, semantic_type)

    # Build factors dict with both V1 (coarse) and V2 (granular) keys.
    # When a V2 semantic type is present, suppress V1 semantic_change to avoid
    # double-counting (V2 carries the full weight).
    has_v2_semantic = is_mechanical or is_contract or is_core_gate
    factors = {
        "cross_module": len(module_roots) > 1,
        "public_api_change": bool(
            "public_api_change" in risk_flags
            or "public_api_changes" in risk_flags
        ),
        # V1 backward-compat: coarse semantic_change (suppressed when V2 is present)
        "semantic_change": has_semantic and not has_v2_semantic,
        # V2 granular semantic
        "semantic_mechanical": has_semantic and is_mechanical,
        "semantic_contract": has_semantic and is_contract,
        "semantic_core_gate": has_semantic and is_core_gate,
        "historical_deferred_risk": False,
        "security_or_data_risk": bool(
            risk_flags & {"security_sensitive", "security_or_data_risk", "data_migration"}
        ),
        "test_matrix_complexity": bool(
            "test_matrix_complexity" in risk_flags
            or (has_semantic and bool(brief.get("integration_points")))
            or (has_semantic and bool(brief.get("architecture_risks")))
        ),
        "user_decision_needed": bool(state.get("requires_user_decision")),
        "architecture_impact": bool(
            "architecture_impact" in risk_flags
            or bool(brief.get("integration_points") and len(module_roots) > 1)
        ),
        # V1 backward-compat: coarse prior_fix_loop
        "prior_fix_loop": bool(
            fix_loop.get("status") == "open"
            or "prior_fix_loop" in risk_flags
        ),
        # V2 granular fix-loop
        "prior_fix_loop_active": primary_fix_loop == "prior_fix_loop_active",
        "prior_fix_loop_same_task": primary_fix_loop == "prior_fix_loop_same_task",
        "prior_fix_loop_same_file": primary_fix_loop == "prior_fix_loop_same_file",
        "prior_fix_loop_same_module": primary_fix_loop == "prior_fix_loop_same_module",
        # V2 detection
        "machine_verifiable": is_machine_verifiable,
        "destructive_command": "destructive_command" in risk_flags,
        "publish_or_deploy": "publish_or_deploy" in risk_flags,
        "data_migration": "data_migration" in risk_flags,
    }
    factors["_background"] = background
    return factors


def _apply_mechanical_routing(base_dir: str, task: Dict[str, Any]) -> Dict[str, Any]:
    """Compute and persist the minimum workflow level and its depth/breadth policy.

    V2-A: also populates topology dimensions (verification_need, execution_topology,
    review_need, downgrade_allowed, substitution_allowed, hard_constraints).
    """
    root = Path(base_dir)
    state_path = root / ".aiwf" / "state" / "state.json"
    state = _read(state_path, {})
    factors = _mechanical_routing_factors(base_dir, task)
    from .routing import compute_routing_score
    background = factors.pop("_background", {}) or {}
    decision = compute_routing_score(factors, file_count=max(len(_task_plan_scope(base_dir, task)), 1))

    recommended = decision["workflow_level"]
    try:
        from .task_gravity import task_gravity
        gravity_level = task_gravity(base_dir, _task_plan_scope(base_dir, task)).get("suggested_min_level")
        if gravity_level in WORKFLOW_LEVELS and WORKFLOW_LEVELS.index(gravity_level) > WORKFLOW_LEVELS.index(recommended):
            recommended = gravity_level
            decision["routing_factors"].append(f"gravity:{gravity_level}")
    except Exception:
        pass

    current = state.get("workflow_level", "L1_review_light")
    if current not in WORKFLOW_LEVELS:
        current = "L1_review_light"
    # If downgrade is allowed (no hard constraints like security/destructive),
    # respect the current level. Routing is advisory — the Planner may accept
    # a lower level with open eyes. Only force upgrade when downgrade is
    # FORBIDDEN (hard constraints present).
    # When recommended > current, flag for user confirmation. The Planner
    # must explain the downgrade and get user approval — cannot silently drop.
    downgrade_gap = (
        WORKFLOW_LEVELS.index(recommended) > WORKFLOW_LEVELS.index(current)
    )
    if decision.get("downgrade_allowed", True):
        final_level = current
        if downgrade_gap:
            decision["routing_factors"].append(
                f"downgrade:{current}→{recommended}"
            )
    else:
        final_level = max((current, recommended), key=WORKFLOW_LEVELS.index)
    from .quality_policy import select_quality_policy
    task_type = state.get("task_type") or "feature"
    policy = select_quality_policy(task_type, final_level, state.get("risk_flags", []) or [],
                                   "mechanical routing at task activation")
    state.update({
        "workflow_level": final_level,
        "routing_score": decision["routing_score"],
        "routing_factors": decision["routing_factors"],
        "routing_background_factors": sorted(k for k, v in background.items() if v),
        "routing_reason": "mechanical routing at task activation",
        "quality_policy_reason": "mechanical routing at task activation",
        "test_template": policy["test_template"],
        "review_template": policy["review_template"],
        "exploration_budget": policy["exploration_budget"],
        "asset_policy": policy["asset_policy"],
        "cleanup_policy": policy["cleanup_policy"],
        "git_policy": policy["git_policy"],
        "recommended_minimum_level": recommended,
        "quality_escalation_required": WORKFLOW_LEVELS.index(recommended) > WORKFLOW_LEVELS.index(current),
        "requires_user_decision": downgrade_gap,
        # V2-A topology dimensions
        "verification_need": decision.get("verification_need", "standard"),
        "review_need": decision.get("review_need", "optional_light_review"),
        "downgrade_allowed": decision.get("downgrade_allowed", True),
        "substitution_allowed": decision.get("substitution_allowed", False),
        "hard_constraints": decision.get("hard_constraints", []),
    })
    state["complexity"] = {
        "L0_direct": "simple",
        "L1_review_light": "standard",
        "L2_standard_team": "complex",
        "L3_full_power": "critical",
    }[final_level]
    _write(state_path, state)
    return {"decision": decision, "recommended": recommended, "final_level": final_level, "state": state}


def _refresh_mechanical_assets(base_dir: str) -> None:
    """Rebuild deterministic Tier 1 assets; preserve human-curated conventions."""
    try:
        from ..assets.schema import init_assets
        init_assets(base_dir)
    except Exception:
        pass


def _checkpoint_activation_blockers(base_dir: str, task: Dict[str, Any]) -> List[str]:
    """L3 tasks require a checkpoint before activation."""
    import json
    state_path = Path(base_dir) / ".aiwf" / "state" / "state.json"
    try:
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
    except Exception:
        return []
    if state.get("workflow_level") != "L3_full_power":
        return []
    ck_dir = Path(base_dir) / ".aiwf" / "runtime" / "checkpoints"
    if not ck_dir.exists() or not any(ck_dir.iterdir()):
        return ["L3 task requires a checkpoint before activation. Run aiwf checkpoint create --label 'pre-task'"]
    return []


def _user_confirmation_blockers(base_dir: str) -> List[str]:
    """Block L1+ task activation until the user confirms the goal. L0 skips."""
    import json
    state_path = Path(base_dir) / ".aiwf" / "state" / "state.json"
    try:
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
    except Exception:
        return []
    if state.get("workflow_level", "") == "L0_direct":
        return []
    goal_path = Path(base_dir) / ".aiwf" / "state" / "goal.json"
    try:
        goal = json.loads(goal_path.read_text()) if goal_path.exists() else {}
    except Exception:
        return []
    if goal.get("confirmed") is False:
        return ["Goal not confirmed by user. Present the plan and ask the user to confirm."]
    return []


def _periodic_architecture_blockers(base_dir: str, task: Dict[str, Any]) -> List[str]:
    """Block ordinary task activation while a periodic architecture review is due."""
    if _is_architecture_review_task(task):
        return []
    from .task_gravity import should_trigger_architecture_review
    trigger = should_trigger_architecture_review(base_dir)
    if not trigger.get("should_trigger"):
        return []
    reasons = "; ".join(trigger.get("reasons", [])[:3])
    return [
        "[gravity] periodic architecture review due before activating another task"
        + (f": {reasons}" if reasons else "")
    ]


def _required_contract_blockers(base_dir: str, task: Dict[str, Any]) -> List[str]:
    """Require machine-readable planning contracts at the depth selected by routing."""
    root = Path(base_dir)
    state = _read(root / ".aiwf" / "state" / "state.json", {})
    level = state.get("workflow_level", "L1_review_light")
    if _is_architecture_review_task(task):
        return []
    goal = _read(root / ".aiwf" / "state" / "goal.json", {})
    brief = goal.get("quality_brief", {}) or {}
    evaluation = brief.get("evaluation_contract", {}) or {}
    architecture = brief.get("architecture_brief", {}) or {}
    blockers: List[str] = []
    if level in ("L2_standard_team", "L3_full_power"):
        if not evaluation.get("user_visible_outcome"):
            blockers.append("L2/L3 requires evaluation_contract.user_visible_outcome before activation")
        if not evaluation.get("acceptance_criteria"):
            blockers.append("L2/L3 requires evaluation_contract.acceptance_criteria before activation")
        if not evaluation.get("test_obligations"):
            blockers.append("L2/L3 requires evaluation_contract.test_obligations before activation")
        if not evaluation.get("review_obligations"):
            blockers.append("L2/L3 requires evaluation_contract.review_obligations before activation")
        if not any(architecture.get(k) for k in (
            "target_structure", "module_boundaries", "architecture_invariants",
            "forbidden_restructures", "integration_points",
        )):
            blockers.append("L2/L3 requires a structural Architecture Brief before activation")
    return blockers


def activation_blockers(base_dir: str, task_id: str, skip_current_state_check: bool = False) -> List[str]:
    ledger = load_ledger(base_dir)
    tasks = ledger.get("tasks", [])
    task = _find(tasks, task_id)
    blockers: List[str] = []
    if not task:
        return [f"task not found: {task_id}"]
    if task.get("status") not in ("candidate", "ready", "suspended", "blocked"):
        blockers.append(f"task status cannot activate: {task.get('status')}")

    for dep in task.get("dependencies", []) or []:
        dep_task = _find(tasks, dep)
        if not dep_task or dep_task.get("status") != "closed":
            blockers.append(f"dependency not closed: {dep}")

    active = [t for t in tasks if t.get("status") == "active" and t.get("id") != task_id]
    max_active = int(ledger.get("execution_window", {}).get("default_max_active", 1) or 1)
    if active and not task.get("parallel_safe"):
        blockers.append("active execution window occupied; mark task parallel_safe only if Planner verified independence")
    if len(active) >= max_active and not task.get("parallel_safe"):
        blockers.append(f"default active task limit reached: {max_active}")
    if task.get("parallel_safe"):
        for other in active:
            overlap = _overlap(_task_plan_scope(base_dir, task), _task_plan_scope(base_dir, other))
            if overlap:
                blockers.append(f"parallel write boundary conflict with {other.get('id')}: {', '.join(overlap[:5])}")

    state = _read(Path(base_dir) / ".aiwf" / "state" / "state.json", {})
    try:
        from .workflow_patterns import mode_activation_blocker
        mode_blocker = mode_activation_blocker(state)
        if mode_blocker:
            blockers.append(mode_blocker)
    except Exception:
        pass
    if state.get("external_research_required") and state.get("request_mode", "execution") == "execution":
        try:
            from .external_research import research_requirement_blocker
            research_blocker = research_requirement_blocker(base_dir)
            if research_blocker:
                blockers.append(research_blocker)
        except Exception:
            blockers.append("external research requirement could not be verified")
    try:
        from .capabilities import capability_use_blockers
        blockers.extend(capability_use_blockers(base_dir))
    except Exception:
        pass
    if state.get("scope_violation"):
        blockers.append(
            "scope violation remains recorded; revert the originally violating files, then run "
            "aiwf fix-loop resolve --resolution '<what was reverted>' before activating another task"
        )
    if state.get("close_attempt") or state.get("phase") == "closing":
        blockers.append("workflow close attempt in progress")
    fix_loop = _read(Path(base_dir) / ".aiwf" / "state" / "fix-loop.json", {})
    if fix_loop.get("status") == "open":
        required = fix_loop.get("required_verification", []) or []
        suffix = f"; required verification: {', '.join(map(str, required[:3]))}" if required else ""
        blockers.append(
            "fix-loop is open; complete required fixes/verification and run aiwf fix-loop resolve"
            + suffix
        )
    blockers.extend(_quality_activation_blockers(base_dir, task))
    blockers.extend(_periodic_architecture_blockers(base_dir, task))
    blockers.extend(_required_contract_blockers(base_dir, task))
    blockers.extend(_user_confirmation_blockers(base_dir))
    blockers.extend(_active_plan_blockers(base_dir, task))
    # Phase-gate field checks: Plan, Context, Contract must have key fields filled
    try:
        from .phase_gates import planned_to_implementing_gates
        blockers.extend(planned_to_implementing_gates(base_dir, task_plan_id=task.get("plan_id", "") or ""))
    except Exception:
        pass
    return blockers


def _active_plan_blockers(base_dir: str, task: Dict[str, Any]) -> List[str]:
    """L1+ execution requires task.plan_id to reference plans.json authority."""
    root = Path(base_dir)
    state = _read(root / ".aiwf" / "state" / "state.json", {})
    level = state.get("workflow_level", "L1_review_light")
    request_mode = state.get("request_mode", "execution")
    plan_id = str(task.get("plan_id") or "")

    # Plan dependency ordering applies at every workflow level. L0 may omit a
    # Plan, but it may not bypass dependencies when a Plan is attached.
    if plan_id:
        try:
            from .state.plan_ops import get_plan, plan_dependency_blockers
            if get_plan(base_dir, plan_id, migrate=False):
                dependency_blockers = plan_dependency_blockers(base_dir, plan_id)
                if dependency_blockers:
                    return dependency_blockers
        except Exception as e:
            return [f"Plan dependency check failed: {e}"]

    if level == "L0_direct":
        return []
    if request_mode not in ("execution", ""):
        return []

    task_id = task.get("id", "")
    legacy_plan_path = root / ".aiwf" / "artifacts" / "plans" / f"{task_id}.md"
    if not plan_id:
        if legacy_plan_path.exists() or task.get("parent_plan"):
            return [
                "Legacy task-bound plan detected. This development version uses "
                "plans.json as the Plan machine authority. Create a registry-backed plan with: "
                f"aiwf plan create PLAN-001 --goal-id GOAL-001 && aiwf plan attach PLAN-001 {task_id}"
            ]
        return [
            f"Task {task_id} has no plan_id. Create and attach a plan:\n"
            f"  aiwf plan create PLAN-001 --goal-id GOAL-001\n"
            f"  aiwf plan attach PLAN-001 {task_id}\n"
            f"  aiwf task plan {task_id} --status ready\n"
            f"(plan attach automatically links this task to the plan and its goal)"
        ]

    try:
        from .state.plan_ops import get_plan
        plan = get_plan(base_dir, plan_id, migrate=False)
    except Exception as e:
        return [f"Plan registry check failed: {e}"]
    if not plan:
        if legacy_plan_path.exists():
            return [
                "Legacy task-bound plan detected. This development version uses "
                "plans.json as the Plan machine authority. Create a registry-backed plan with: "
                f"aiwf plan create PLAN-001 --goal-id GOAL-001 && aiwf plan attach PLAN-001 {task_id}"
            ]
        return [f"task.plan_id references missing plan registry entry: {plan_id}"]
    if not plan.get("goal_id"):
        return [f"Plan {plan_id} is missing goal_id"]
    task_goal = task.get("goal_id") or ""
    if task_goal and task_goal != plan.get("goal_id"):
        return [f"task.goal_id {task_goal} does not match plan.goal_id {plan.get('goal_id')}"]
    plan_milestone = str(plan.get("milestone_id") or "")
    task_milestone = str(task.get("milestone_id") or "")
    if plan_milestone or task_milestone:
        milestone_id = plan_milestone or task_milestone
        try:
            from .state.milestone_ops import milestone_exists
            if not milestone_exists(base_dir, milestone_id):
                return [f"milestone_id references missing milestone registry entry: {milestone_id}"]
        except Exception as e:
            return [f"Milestone registry check failed: {e}"]
        if plan_milestone and task_milestone and task_milestone != plan_milestone:
            return [
                f"task.milestone_id {task_milestone} does not match plan.milestone_id {plan_milestone}"
            ]

    from .task_plan import validate_plan_impact, _resolve_plan_artifact_id
    artifact_id = _resolve_plan_artifact_id(base_dir, plan_id)
    plan_path = root / ".aiwf" / "artifacts" / "plans" / f"{artifact_id}.md"
    if plan_path.exists():
        impact_issues = validate_plan_impact(base_dir, artifact_id)
        if impact_issues:
            suffix = f"; ... {len(impact_issues) - 3} more" if len(impact_issues) > 3 else ""
            return [f"Plan Impact incomplete: {'; '.join(impact_issues[:3])}{suffix}"]
        return []
    return [f"Plan artifact missing for registry plan {plan_id}: .aiwf/artifacts/plans/{artifact_id}.md"]


def activate_task(base_dir: str, task_id: str) -> Dict[str, Any]:
    """Activate a planned task if execution-window gates pass."""
    ledger = load_ledger(base_dir)
    task = _find(ledger["tasks"], task_id)
    if task:
        _apply_mechanical_routing(base_dir, task)
        _refresh_mechanical_assets(base_dir)
    blockers = activation_blockers(base_dir, task_id, skip_current_state_check=True)
    if blockers:
        return {"activated": False, "task": task, "ledger": ledger, "blockers": blockers}
    task["status"] = "active"
    task["activated_at"] = _now()
    task["updated_at"] = _now()
    # Sync plan task_status so plans.json doesn't drift from task-ledger
    if task.get("plan_id"):
        try:
            from .state.plan_ops import load_plans, save_plans
            plans = load_plans(base_dir)
            for p in plans.get("plans", []) or []:
                if p.get("plan_id", p.get("id")) == task["plan_id"]:
                    p.setdefault("task_status", {})[task_id] = "active"
                    save_plans(base_dir, plans)
                    break
        except Exception:
            pass
    if task.get("plan_id"):
        try:
            from .state.plan_ops import get_plan
            plan = get_plan(base_dir, task["plan_id"], migrate=False)
            if plan.get("goal_id") and not task.get("goal_id"):
                task["goal_id"] = plan["goal_id"]
                task["parent_goal"] = plan["goal_id"]
            if plan.get("milestone_id") and not task.get("milestone_id"):
                task["milestone_id"] = plan["milestone_id"]
        except Exception:
            pass
    _sync_active_ids(ledger)
    state_path = Path(base_dir) / ".aiwf" / "state" / "state.json"
    state = _read(state_path, {})
    if task.get("suspended_context"):
        for key, value in task["suspended_context"].items():
            state[key] = value
    state["active_task_id"] = task_id
    if task.get("plan_id"):
        state["active_plan_id"] = task["plan_id"]
    if state.get("phase") not in ("testing", "reviewing", "closing", "closed"):
        state["phase"] = "implementing"
    _write(state_path, state)
    save_ledger(base_dir, ledger)
    return {"activated": True, "task": task, "ledger": ledger, "blockers": []}


def suspend_task(base_dir: str, task_id: str, note: str = "") -> Dict[str, Any]:
    """Suspend an active task and store a lightweight state snapshot."""
    ledger = load_ledger(base_dir)
    task = _find(ledger["tasks"], task_id)
    if not task:
        return {"suspended": False, "task": None, "ledger": ledger, "blockers": [f"task not found: {task_id}"]}
    if task.get("status") in ("closed", "rejected"):
        return {"suspended": False, "task": task, "ledger": ledger,
                "blockers": [f"cannot suspend task with terminal status: {task['status']}"]}
    state_path = Path(base_dir) / ".aiwf" / "state" / "state.json"
    state = _read(state_path, {})
    snapshot_keys = [
        "phase", "active_context_id", "active_task_id", "workflow_level",
        "task_type", "test_template", "review_template", "exploration_budget",
        "cleanup_policy", "git_policy", "request_mode", "workflow_pattern",
        "pattern_reason", "external_research_required", "active_plan_id",
        "planned_capability_ids",
    ]
    task["status"] = "suspended"
    task["suspended_at"] = _now()
    task["updated_at"] = _now()
    task["suspended_context"] = {k: state.get(k) for k in snapshot_keys if k in state}
    if note:
        task.setdefault("notes", []).append(note)
    if state.get("active_task_id") == task_id:
        state["active_task_id"] = None
        _write(state_path, state)
    _sync_active_ids(ledger)
    save_ledger(base_dir, ledger)
    return {"suspended": True, "task": task, "ledger": ledger, "blockers": []}


def _l2_l3_completion_blockers(base_dir: str, task: Dict[str, Any]) -> List[str]:
    """Require the independent quality chain before an active L2/L3 task closes."""
    root = Path(base_dir)
    state = _read(root / ".aiwf" / "state" / "state.json", {})
    level = state.get("workflow_level", "L1_review_light")
    if level not in ("L2_standard_team", "L3_full_power") or _is_architecture_review_task(task):
        return []

    testing = _read(root / ".aiwf" / "artifacts" / "quality" / "testing.json", {})
    review = _read(root / ".aiwf" / "artifacts" / "quality" / "review.json", {})
    evidence = _read(root / ".aiwf" / "artifacts" / "evidence" / "records.json", {"records": []})
    goal = _read(root / ".aiwf" / "state" / "goal.json", {})
    blockers: List[str] = []

    if testing.get("status") not in ("adequate", "passed"):
        blockers.append("L2/L3 task requires adequate independent testing before close")
    if not testing.get("commands"):
        blockers.append("L2/L3 task requires recorded test commands before close")
    layers = set(testing.get("validation_layers", []) or [])
    if "targeted" not in layers:
        blockers.append("L2/L3 Tester must record a targeted validation layer")
    if testing.get("full_suite_status", "not_run") == "not_run":
        blockers.append(
            "L2/L3 Tester must run the full project suite or explicitly record not_available/not_feasible with a reason"
        )
    if (
        testing.get("full_suite_status") in ("not_available", "not_feasible")
        and not testing.get("full_suite_reason")
    ):
        blockers.append("L2/L3 full-suite deferral requires full_suite_reason")
    if testing.get("full_suite_status") == "passed" and "full_regression" not in layers:
        blockers.append("L2/L3 passed full suite must record validation_layer=full_regression")
    if testing.get("real_usage_status", "not_run") == "not_run":
        blockers.append(
            "L2/L3 Tester must exercise a real user-facing entrypoint or explicitly record not_available/not_feasible with a reason"
        )
    if (
        testing.get("real_usage_status") in ("not_available", "not_feasible")
        and not testing.get("real_usage_reason")
    ):
        blockers.append("L2/L3 real-usage deferral requires real_usage_reason")
    if testing.get("real_usage_status") == "passed" and "real_usage" not in layers:
        blockers.append("L2/L3 passed real usage must record validation_layer=real_usage")
    if (
        testing.get("full_suite_status") in ("not_available", "not_feasible")
        or testing.get("real_usage_status") in ("not_available", "not_feasible")
    ) and not testing.get("untested_risks"):
        blockers.append("L2/L3 validation deferral requires an explicit untested_risk")
    if testing.get("full_suite_status") == "failed":
        blockers.append("L2/L3 full project suite failed")
    if testing.get("real_usage_status") == "failed":
        blockers.append("L2/L3 real user-facing validation failed")
    if review.get("result") != "accepted" or not review.get("closure_allowed", False):
        blockers.append("L2/L3 task requires accepted independent review before close")
    if review.get("cleanup_status") != "fresh" or review.get("stale_items") or review.get("cleanup_blockers"):
        blockers.append("L2/L3 task requires fresh cleanup before close")
    if review.get("structure_status") != "accepted" or review.get("structure_blockers"):
        blockers.append("L2/L3 task requires accepted structure review before close")
    cleanup_at = str(review.get("cleanup_verified_at", "") or "")
    if not cleanup_at:
        blockers.append("L2/L3 task requires a mechanical cleanup verification before review")

    from .review_contract import has_pending_adversarial_observations
    if has_pending_adversarial_observations(review):
        blockers.append("L2/L3 task has pending adversarial observations")

    decisions = goal.get("decisions", []) or []
    structured_meta = goal.get("meta_critique", {}) or {}
    has_meta_critique = (
        structured_meta.get("status") == "completed"
        and str(structured_meta.get("recorded_by", "")).lower() == "planner"
        and bool(str(structured_meta.get("summary", "")).strip())
    ) or any(
        isinstance(d, dict)
        and str(d.get("source", "")).lower() == "planner"
        and "meta" in str(d.get("decision", "")).lower()
        and "critique" in str(d.get("decision", "")).lower()
        for d in decisions
    )
    if not has_meta_critique:
        blockers.append("L2/L3 task requires Planner meta-critique before close")

    accepted_ids = {
        str(eid) for eid in (review.get("accepted_evidence_ids", []) or []) if str(eid)
    }
    sessions = set()
    roles = set()
    reviewer_timestamps: List[str] = []
    for record in evidence.get("records", []) or []:
        if not isinstance(record, dict) or str(record.get("id", "")) not in accepted_ids:
            continue
        if record.get("trust") != "machine_observed":
            continue
        session_id = str(record.get("session_id", "") or "").strip()
        agent_id = str(record.get("agent_id", "") or "").strip()
        if session_id:
            sessions.add(f"{session_id}::{agent_id}" if agent_id else session_id)
        role_text = " ".join([
            str(record.get("agent_type", "")),
            agent_id,
            session_id,
        ]).lower()
        for role in ("executor", "tester", "reviewer"):
            if role in role_text:
                roles.add(role)
                if role == "reviewer" and record.get("timestamp"):
                    reviewer_timestamps.append(str(record["timestamp"]))
    if len(sessions) < 3:
        blockers.append(
            f"L2/L3 task requires accepted machine evidence from at least 3 distinct sessions; found {len(sessions)}. "
            "Fix: spawn aiwf-executor, aiwf-tester, and aiwf-reviewer as separate Agent tool subagents. "
            "Each subagent's Write/Edit/Bash calls generate hook evidence with a distinct session_id. "
            "Running record-role-evidence from the main session does NOT count."
        )
    missing_roles = [r for r in ("executor", "tester", "reviewer") if r not in roles]
    if missing_roles:
        blockers.append(
            f"L2/L3 task requires role-bound evidence; missing: {', '.join(missing_roles)}. "
            f"Fix: for each missing role, spawn a subagent via Agent tool "
            f"(subagent_type=aiwf-<role>) and have it do real work (Write/Edit/Bash)."
        )
    if cleanup_at and reviewer_timestamps and min(reviewer_timestamps) <= cleanup_at:
        blockers.append("L2/L3 cleanup must be verified before Reviewer evidence")
    if cleanup_at and not reviewer_timestamps:
        blockers.append("L2/L3 task requires Reviewer evidence after cleanup verification")

    blockers.extend(_architecture_migration_blockers(goal, evidence, accepted_ids))

    if level == "L3_full_power":
        checkpoint_dir = root / ".aiwf" / "runtime" / "checkpoints"
        goal_decisions = goal.get("decisions", []) or []
        explicit_skip = any(
            isinstance(d, dict)
            and "checkpoint" in str(d.get("decision", "")).lower()
            and "skip" in str(d.get("decision", "")).lower()
            for d in goal_decisions
        )
        if not (checkpoint_dir.exists() and any(checkpoint_dir.iterdir())) and not explicit_skip:
            blockers.append("L3 task requires checkpoint or explicit checkpoint skip decision")
    return blockers


def _architecture_migration_blockers(
    goal: Dict[str, Any],
    evidence: Dict[str, Any],
    accepted_ids: set[str],
) -> List[str]:
    """Require behavior evidence when a task declares an architecture migration."""
    brief = goal.get("quality_brief", {}) or {}
    architecture = brief.get("architecture_brief", {}) or {}
    migration_fields = {
        "migration_source_of_truth": architecture.get("migration_source_of_truth", ""),
        "legacy_paths": architecture.get("legacy_paths", []) or [],
        "legacy_terms": architecture.get("legacy_terms", []) or [],
        "default_entrypoints": architecture.get("default_entrypoints", []) or [],
        "validators": architecture.get("validators", []) or [],
        "sample_outputs": architecture.get("sample_outputs", []) or [],
    }
    migration_active = any(bool(v) for v in migration_fields.values())
    if not migration_active:
        return []

    blockers: List[str] = []
    if not str(migration_fields["migration_source_of_truth"]).strip():
        blockers.append("architecture migration requires migration_source_of_truth")
    if not (migration_fields["legacy_paths"] or migration_fields["legacy_terms"]):
        blockers.append("architecture migration requires legacy_paths or legacy_terms to sweep")
    if not migration_fields["default_entrypoints"]:
        blockers.append("architecture migration requires default_entrypoints to prove the new mainline")
    if not migration_fields["validators"]:
        blockers.append("architecture migration requires validators/CI to prove the new structure")

    accepted_records = [
        r for r in (evidence.get("records", []) or [])
        if isinstance(r, dict)
        and str(r.get("id", "")) in accepted_ids
        and r.get("trust") == "machine_observed"
    ]
    commands = [
        " ".join([
            str(r.get("command", "")),
            str(r.get("stdout_summary", "")),
            str(r.get("tool_input", "")),
        ]).lower()
        for r in accepted_records
    ]

    legacy_tokens = [
        str(token).strip().lower()
        for token in (migration_fields["legacy_paths"] + migration_fields["legacy_terms"])
        if str(token).strip()
    ]
    if legacy_tokens:
        has_sweep = any(
            ("rg " in cmd or cmd.startswith("rg") or "grep " in cmd)
            and any(token in cmd for token in legacy_tokens)
            for cmd in commands
        )
        if not has_sweep:
            blockers.append("architecture migration requires accepted legacy sweep evidence (rg/grep over legacy paths or terms)")

    for entrypoint in migration_fields["default_entrypoints"]:
        ep = str(entrypoint).strip().lower()
        if not ep:
            continue
        found = any(ep in cmd and ("dry-run" in cmd or "dry run" in cmd or "--check" in cmd) for cmd in commands)
        if not found:
            blockers.append(f"architecture migration requires accepted dry-run/check evidence for default entrypoint: {entrypoint}")

    for validator in migration_fields["validators"]:
        val = str(validator).strip().lower()
        if not val:
            continue
        found = any(val in cmd for cmd in commands)
        if not found:
            blockers.append(f"architecture migration requires accepted validator evidence: {validator}")

    for sample in migration_fields["sample_outputs"]:
        smp = str(sample).strip().lower()
        if not smp:
            continue
        found = any(smp in cmd for cmd in commands)
        if not found:
            blockers.append(f"architecture migration requires accepted sample-output alignment evidence: {sample}")

    return blockers


def _mode_completion_blockers(base_dir: str, task: Dict[str, Any]) -> List[str]:
    """Block closing advisory/exploratory modes as final implementation work."""
    state = _read(Path(base_dir) / ".aiwf" / "state" / "state.json", {})
    mode = state.get("request_mode", "execution")
    pattern = state.get("workflow_pattern", "linear")
    if mode == "spike" or pattern == "spike_first":
        return [
            "spike task cannot close as final implementation; record findings and switch to request_mode=execution for the formal task"
        ]
    return []


def active_task_completion_blockers(base_dir: str) -> List[str]:
    """Return completion blockers for the active task, if one exists."""
    state = _read(Path(base_dir) / ".aiwf" / "state" / "state.json", {})
    task_id = str(state.get("active_task_id", "") or "")
    if not task_id:
        return []
    task = _find(load_ledger(base_dir).get("tasks", []), task_id)
    if not task:
        return [f"active task is missing from task ledger: {task_id}"]
    blockers = _mode_completion_blockers(base_dir, task) + _l2_l3_completion_blockers(base_dir, task)
    blockers.extend(_claim_evidence_blockers(base_dir, task_id))
    return blockers


def _claim_evidence_blockers(base_dir: str, task_id: str) -> List[str]:
    """L1+: unsupported or overclaimed claims block task close.

    Every claim about task completion must be traceable to machine-observed evidence.
    """
    state = _read(Path(base_dir) / ".aiwf" / "state" / "state.json", {})
    level = state.get("workflow_level", "L1_review_light")
    if level == "L0_direct":
        return []

    try:
        from .state.claims_ops import unsupported_claims_blockers
        return unsupported_claims_blockers(base_dir, task_id=task_id)
    except Exception:
        return []


def close_task(base_dir: str, task_id: str, note: str = "") -> Dict[str, Any]:
    """Mark a ledger task closed. This does not close the AIWF workflow.

    Returns goal progress: task is an execution unit, not a goal unit.
    Close output must show: task closed, goal complete status, next task.
    """
    ledger = load_ledger(base_dir)
    task = _find(ledger["tasks"], task_id)
    if not task:
        return {"closed": False, "task": None, "ledger": ledger, "blockers": [f"task not found: {task_id}"]}
    if task.get("status") == "closed":
        return {"closed": True, "task": task, "ledger": ledger, "blockers": []}
    if task.get("status") != "active":
        return {
            "closed": False,
            "task": task,
            "ledger": ledger,
            "blockers": [f"task status is '{task.get('status')}', not active; activate the task before close"],
        }
    if task.get("status") == "active":
        fix_loop = _read(Path(base_dir) / ".aiwf" / "state" / "fix-loop.json", {})
        if fix_loop.get("status") == "open":
            return {
                "closed": False,
                "task": task,
                "ledger": ledger,
                "blockers": [
                    "open fix-loop blocks task close; resolve it and re-run prepare-close"
                ],
            }
        state = _read(Path(base_dir) / ".aiwf" / "state" / "state.json", {})
        if not (state.get("phase") in ("closing", "closed") and state.get("closure_allowed")):
            return {
                "closed": False,
                "task": task,
                "ledger": ledger,
                "blockers": [
                    "active task cannot close before prepare-close passes; run aiwf state prepare-close first"
                ],
            }
        mode = state.get("request_mode", "execution")
        pattern = state.get("workflow_pattern", "linear")
        if mode == "spike" or pattern == "spike_first":
            return {"closed": False, "task": task, "ledger": ledger,
                    "blockers": ["spike task cannot close as final implementation; record findings and switch to request_mode=execution"]}
        # L2/L3 quality gates: independent testing, review, cleanup must complete first.
        # active_task_completion_blockers enforces the full quality chain.
        quality_blockers = active_task_completion_blockers(base_dir)
        if quality_blockers:
            return {"closed": False, "task": task, "ledger": ledger, "blockers": quality_blockers}
        # Lightweight re-check: ensure this is the task that passed prepare-close
        prepared_task = state.get("close_prepared_task_id", "") or ""
        prepared_at = state.get("close_prepared_at", "") or ""
        if prepared_task and prepared_task != task_id:
            return {"closed": False, "task": task, "ledger": ledger,
                    "blockers": [f"task {task_id} does not match close_prepared_task_id {prepared_task}; re-run prepare-close"]}
        if prepared_at:
            evidence = _read(Path(base_dir) / ".aiwf" / "artifacts" / "evidence" / "records.json", {"records": []})
            for r in evidence.get("records", []) or []:
                if isinstance(r, dict) and r.get("recorded_at", "") > prepared_at:
                    return {"closed": False, "task": task, "ledger": ledger,
                            "blockers": ["new evidence recorded after prepare-close; re-run prepare-close to revalidate"]}
    task["status"] = "closed"
    task["closed_at"] = _now()
    task["updated_at"] = _now()
    if note:
        task.setdefault("notes", []).append(note)
    _sync_active_ids(ledger)

    # Goal progress: find sibling tasks under the same parent goal
    parent_goal = task.get("goal_id") or task.get("parent_goal", "") or ""
    parent_plan = task.get("plan_id") or task.get("parent_plan", "") or ""
    goal_tasks = []
    if parent_goal:
        goal_tasks = [
            t for t in ledger.get("tasks", [])
            if (t.get("goal_id") or t.get("parent_goal")) == parent_goal and t.get("id") != task_id
        ]
    elif parent_plan:
        goal_tasks = [
            t for t in ledger.get("tasks", [])
            if (t.get("plan_id") or t.get("parent_plan")) == parent_plan and t.get("id") != task_id
        ]

    closed_count = sum(1 for t in goal_tasks if t.get("status") == "closed") + 1  # +1 for this task
    total_count = len(goal_tasks) + 1
    remaining = [t.get("id", "") for t in goal_tasks if t.get("status") not in ("closed", "rejected")]
    goal_complete = len(remaining) == 0

    state_path = Path(base_dir) / ".aiwf" / "state" / "state.json"
    state = _read(state_path, {})
    if state.get("active_task_id") == task_id:
        state["active_task_id"] = None
    if state.get("phase") == "closing":
        state["phase"] = "closed"
    _write(state_path, state)
    # When a Plan completes without README: force next Plan to fix it
    if task.get("plan_id") and not (Path(base_dir) / "README.md").exists():
        try:
            from .state.plan_ops import get_plan
            plan = get_plan(base_dir, task["plan_id"], migrate=False)
            remaining = plan.get("remaining_task_ids", []) or []
            if not remaining:
                state_path = Path(base_dir) / ".aiwf" / "state" / "state.json"
                state = _read(state_path, {})
                state["next_plan_docs_required"] = True
                _write(state_path, state)
                print("Plan complete but README.md missing. Next Plan will require Impact.docs=yes.")
        except Exception:
            pass
    save_ledger(base_dir, ledger)
    _refresh_mechanical_assets(base_dir)
    # Machine-only history and escalation state: always update
    try:
        from .cross_task_quality import append_task_history_from_state, sync_quality_escalation_state
        append_task_history_from_state(base_dir, task_id=task_id, title=task.get("title", ""))
        sync_quality_escalation_state(base_dir)
    except Exception:
        pass
    # Quality digest markdown is NOT auto-written here — it's controlled by
    # Impact.quality_summary and only written when explicitly requested
    # (milestone/retro/release).
    try:
        from .lifecycle_cleanup import auto_cleanup
        auto_cleanup(base_dir)
    except Exception:
        pass
    plan_progress = {}
    try:
        from .state.plan_ops import reconcile_task_to_plan
        plan_progress = reconcile_task_to_plan(base_dir, task)
    except Exception:
        plan_progress = {"reconciled": False, "reason": "plan reconcile failed"}
    # Granularity: task without parent goal is an orphan.
    # Tasks are execution units, not goal units.
    granularity_warnings = []
    if not parent_goal and not parent_plan:
        granularity_warnings.append(
            "No parent_goal set — task was not linked to a larger goal. "
            "Use --parent-goal GOAL-xxx when planning tasks to prevent goal drift."
        )

    return {
        "closed": True,
        "task": task,
        "ledger": ledger,
        "blockers": [],
        "goal_progress": {
            "parent_goal": parent_goal,
            "parent_plan": parent_plan,
            "closed_count": closed_count,
            "total_count": total_count,
            "goal_complete": goal_complete,
            "remaining_tasks": remaining,
        },
        "plan_progress": plan_progress,
        "granularity_warnings": granularity_warnings,
    }


def ledger_summary(base_dir: str) -> Dict[str, Any]:
    ledger = load_ledger(base_dir)
    tasks = ledger.get("tasks", [])
    counts: Dict[str, int] = {}
    for task in tasks:
        status = task.get("status", "unknown")
        counts[status] = counts.get(status, 0) + 1
    return {
        "tasks": tasks,
        "counts": counts,
        "active_task_ids": ledger.get("execution_window", {}).get("active_task_ids", []),
    }
