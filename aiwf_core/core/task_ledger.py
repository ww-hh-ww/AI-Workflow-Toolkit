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
from .state.goal_ops import get_active_goal


VALID_TASK_STATUSES = {"candidate", "ready", "active", "blocked", "suspended", "closed", "rejected"}
# LEGACY/DEBUG-ONLY: workflow levels are not V1 runtime control paths.
# Task.requirements controls subagent dispatch. These strings exist only for
# legacy routing-debug.json compatibility and debug display.
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
    return Path(base_dir) / ".aiwf" / "state" / "tasks.json"


def _migrate_ledger_if_needed(base_dir: str) -> None:
    new_path = ledger_path(base_dir)
    old_path = Path(base_dir) / ".aiwf" / "runtime" / "history" / "task-ledger.json"
    if old_path.exists() and not new_path.exists():
        new_path.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.move(str(old_path), str(new_path))


def default_ledger() -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "default_max_active": 1,
        "tasks": [],
    }


def load_ledger(base_dir: str) -> Dict[str, Any]:
    _migrate_ledger_if_needed(base_dir)
    ledger = _read(ledger_path(base_dir), default_ledger())
    if not isinstance(ledger.get("tasks"), list):
        ledger["tasks"] = []
    ledger.setdefault("default_max_active", 1)
    ledger.setdefault("schema_version", 1)
    return ledger


def save_ledger(base_dir: str, ledger: Dict[str, Any]) -> None:
    _write(ledger_path(base_dir), ledger)


def load_routing_state(base_dir: str) -> Dict[str, Any]:
    """LEGACY/DEBUG-ONLY: Read routing/quality debug state. Returns defaults when absent.

    V2: routing fields live in runtime/internal/routing-debug.json.
    state.json is the clean V2 core — NO routing fields.
    When the debug file is absent, all readers default to L1_review_light.

    V1: Task.requirements controls dispatch. workflow_level is NOT a runtime control path.
    This function exists only for debug/status display. Do NOT use for gating decisions.
    """
    routing_path = Path(base_dir) / ".aiwf" / "runtime" / "internal" / "routing-debug.json"
    if routing_path.exists():
        return _read(routing_path, {})
    return {
        "workflow_level": "L1_review_light",
        "test_template": "",
        "review_template": "",
        "verification_need": "standard",
        "review_need": "optional_light_review",
        "routing_factors": [],
        "routing_score": 0,
        "exploration_budget": "",
        "cleanup_policy": "",
        "git_policy": "no_auto_commit",
        "recommended_minimum_level": "",
        "downgrade_allowed": True,
        "hard_constraints": [],
    }


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
    kind: str = "",
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
            "type": "task",
            "title": title or task_id,
            "status": status,
            "title_cache": title or task_id,
            "summary_cache": "",
            "doc_path": "",
            "doc_hash": "",
            "doc_updated_at": "",
            "frozen_doc_hash": None,
            "requirements": {
                "executor_required": False if kind == "milestone_verification" else True,
                "tester_required": True,
                "reviewer_required": True,
            },
            "report_policy": "ask",
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
            "kind": "",
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
    if effective_plan:
        task["plan_id"] = effective_plan
    if milestone:
        task["milestone"] = milestone
    if milestone_id:
        task["milestone_id"] = milestone_id
    if kind:
        task["kind"] = kind
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
    """No-op in V2. state.json.active_task_id is the single active pointer."""
    pass


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
        if _active_override_allows_gravity_constraint(base_dir, task, kind):
            continue
        if kind == "repeated_change_hotspot":
            label = "repeated-change hotspot"
        elif kind == "fix_loop_trend":
            label = "cross-task quality escalation"
        else:
            label = kind
        blockers.append(f"[gravity] {label}: {c['message']}")
    return blockers


def _active_override_allows_gravity_constraint(base_dir: str, task: Dict[str, Any], kind: str) -> bool:
    """Return true when a user-confirmed routing override may absorb a gravity warning.

    Historical trends are real and must remain visible, but they are not the
    same as active hazards. A task-scoped, user-confirmed downgrade can accept
    the residual risk for `fix_loop_trend`; active fix-loops, same-task
    recurrence, security/data risks, and core-gate changes are still handled by
    routing hard constraints and cannot be softened here.
    """
    if kind != "fix_loop_trend":
        return False
    state = _read(Path(base_dir) / ".aiwf" / "state" / "state.json", {})
    override = state.get("active_routing_override", {}) or {}
    if not isinstance(override, dict) or not override.get("user_confirmed"):
        return False
    override_task = str(override.get("task_id") or "")
    if override_task and override_task != str(task.get("id") or ""):
        return False
    reason = str(override.get("reason") or "").strip()
    return bool(reason)


def _is_architecture_review_task(task: Dict[str, Any]) -> bool:
    task_id = str(task.get("id", "") or "")
    title = str(task.get("title", "") or "").strip().lower()
    return (
        (task_id.startswith("ARCH-") and not task_id.startswith("ARCH-FIX-"))
        or title.startswith("[architect]")
    )


def _is_architecture_remediation_task(task: Dict[str, Any]) -> bool:
    task_id = str(task.get("id", "") or "").upper()
    title = str(task.get("title", "") or "").lower()
    return task_id.startswith("ARCH-FIX-") or title.startswith("[architecture fix]")


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
    goal = get_active_goal(base_dir)
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
    """LEGACY/DEBUG-ONLY: Compute and persist routing factors to routing-debug.json.

    V1: Task.requirements controls subagent dispatch. workflow_level is NOT a runtime
    control path. This function writes debug info only — it does NOT gate activation,
    writes, review, testing, or close. The routing-debug.json file is informational.
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
    # Mechanical routing is a floor, not a suggestion. Earlier versions allowed
    # the current lower workflow level to remain active when downgrade_allowed
    # was true, which meant an L2 recommendation could still execute as L1 and
    # bypass independent Tester/Reviewer gates. Always raise to the recommended
    # minimum; explicit topology substitutions must be recorded separately and
    # must not silently defeat this activation boundary.
    downgrade_gap = (
        WORKFLOW_LEVELS.index(recommended) > WORKFLOW_LEVELS.index(current)
    )
    final_level = max((current, recommended), key=WORKFLOW_LEVELS.index)
    if downgrade_gap:
        decision["routing_factors"].append(
            f"escalated:{current}→{recommended}"
        )
    from .quality_policy import select_quality_policy
    task_type = state.get("task_type") or "feature"
    policy = select_quality_policy(task_type, final_level, state.get("risk_flags", []) or [],
                                   "mechanical routing at task activation")
    policy_recommended = policy.get("recommended_minimum_level", "")
    if (
        policy_recommended in WORKFLOW_LEVELS
        and WORKFLOW_LEVELS.index(policy_recommended) > WORKFLOW_LEVELS.index(final_level)
    ):
        previous_level = final_level
        recommended = policy_recommended
        final_level = policy_recommended
        decision["routing_factors"].append(
            f"policy_escalated:{previous_level}→{policy_recommended}"
        )
        policy = select_quality_policy(task_type, final_level, state.get("risk_flags", []) or [],
                                       "mechanical routing at task activation")
    override = _find_confirmed_routing_override(
        state=state,
        task=task,
        recommended_level=recommended,
        decision=decision,
    )
    if override.get("allowed"):
        previous_level = final_level
        final_level = override["level"]
        decision["routing_factors"].append(
            f"explicit_downgrade:{previous_level}→{final_level}"
        )
        _apply_level_dimensions(decision, final_level)
        policy = select_quality_policy(task_type, final_level, state.get("risk_flags", []) or [],
                                       "explicit user-confirmed routing override")
    # Routing state is debug-only — NOT written to state.json.
    # All routing/quality/template fields go to runtime/internal/routing-debug.json.
    # Readers default to "L1_review_light" when the file is absent.
    routing_debug = {
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
        "quality_escalation_required": False,
        "requires_user_decision": False,
        "verification_need": decision.get("verification_need", "standard"),
        "review_need": decision.get("review_need", "optional_light_review"),
        "downgrade_allowed": decision.get("downgrade_allowed", True),
        "substitution_allowed": decision.get("substitution_allowed", False),
        "hard_constraints": decision.get("hard_constraints", []),
        "active_routing_override": override.get("record", {}) if override.get("allowed") else {},
        "updated_at": _now(),
    }
    routing_path = root / ".aiwf" / "runtime" / "internal" / "routing-debug.json"
    _write(routing_path, routing_debug)

    return {"decision": decision, "recommended": recommended, "final_level": final_level, "state": state}


def _apply_level_dimensions(decision: Dict[str, Any], level: str) -> None:
    from .routing import LEVEL_TO_TOPOLOGY

    decision["execution_topology"] = LEVEL_TO_TOPOLOGY.get(level, "light_review")
    decision["verification_need"] = {
        "L0_direct": "deterministic",
        "L1_review_light": "standard",
        "L2_standard_team": "broad",
        "L3_full_power": "adversarial",
    }.get(level, "standard")
    decision["review_need"] = {
        "L0_direct": "none",
        "L1_review_light": "optional_light_review",
        "L2_standard_team": "required_review",
        "L3_full_power": "adversarial_review",
    }.get(level, "optional_light_review")


def _find_confirmed_routing_override(
    state: Dict[str, Any],
    task: Dict[str, Any],
    recommended_level: str,
    decision: Dict[str, Any],
) -> Dict[str, Any]:
    """Return the latest valid, user-confirmed routing override for a task.

    Mechanical routing remains the default floor. This helper only recognizes
    explicit downgrade/substitution records that are tied to the current task
    (or intentionally global), carry a reason, and were user-confirmed.
    """
    if recommended_level not in WORKFLOW_LEVELS:
        return {"allowed": False}
    try:
        from .routing import DOWNGRADE_FORBIDDEN_FACTORS
        forbidden_hard = [
            str(item)
            for item in (decision.get("hard_constraints", []) or [])
            if str(item) in DOWNGRADE_FORBIDDEN_FACTORS
        ]
        if forbidden_hard:
            return {"allowed": False}
    except Exception:
        if decision.get("hard_constraints"):
            return {"allowed": False}
    if not decision.get("downgrade_allowed", True):
        return {"allowed": False}
    task_id = str(task.get("id") or "")
    records = state.get("substitution_records", []) or []
    from .routing import TOPOLOGY_TO_LEVEL

    for record in reversed(records):
        if not isinstance(record, dict):
            continue
        if record.get("type") not in ("downgrade", "substitution"):
            continue
        if not record.get("user_confirmed"):
            continue
        record_task_id = str(record.get("task_id") or "")
        if record_task_id and record_task_id != task_id:
            continue
        if not str(record.get("reason") or "").strip():
            continue
        level = str(record.get("to_level") or "") or TOPOLOGY_TO_LEVEL.get(str(record.get("to_topology") or ""), "")
        if level not in WORKFLOW_LEVELS:
            continue
        if WORKFLOW_LEVELS.index(level) >= WORKFLOW_LEVELS.index(recommended_level):
            continue
        return {"allowed": True, "level": level, "record": record}
    return {"allowed": False}


def _task_start_confirmation(task: Dict[str, Any]) -> Dict[str, Any]:
    conf = task.get("start_confirmation") or {}
    return conf if isinstance(conf, dict) else {}


def task_start_confirmation_blockers(base_dir: str, task_id: str) -> List[str]:
    """CLI-facing start gate: explain work before activation unless skipped."""
    task = _find(load_ledger(base_dir).get("tasks", []), task_id)
    if not task:
        return [f"task not found: {task_id}"]
    conf = _task_start_confirmation(task)
    status = conf.get("status")
    if status == "confirmed":
        return []
    if status == "skipped" and str(conf.get("reason") or "").strip():
        return []
    return [
        "Task start not confirmed. Briefly explain scope/risk/verification to the user, then run "
        f"aiwf task confirm-start {task_id} --summary '<one-line plan>'"
    ]


def record_task_start_confirmation(
    base_dir: str,
    task_id: str,
    summary: str = "",
    confirmed_by: str = "user",
    skip: bool = False,
    reason: str = "",
) -> Dict[str, Any]:
    ledger = load_ledger(base_dir)
    task = _find(ledger.get("tasks", []), task_id)
    if not task:
        return {"recorded": False, "blockers": [f"task not found: {task_id}"], "task": None}
    if skip:
        if not str(reason or "").strip():
            return {"recorded": False, "blockers": ["skip reason is required"], "task": task}
        task["start_confirmation"] = {
            "status": "skipped",
            "reason": str(reason).strip(),
            "confirmed_by": str(confirmed_by or "user").strip() or "user",
            "confirmed_at": _now(),
        }
    else:
        if not str(summary or "").strip():
            return {"recorded": False, "blockers": ["summary is required"], "task": task}
        task["start_confirmation"] = {
            "status": "confirmed",
            "summary": str(summary).strip(),
            "confirmed_by": str(confirmed_by or "user").strip() or "user",
            "confirmed_at": _now(),
        }
    task["updated_at"] = _now()
    save_ledger(base_dir, ledger)
    return {"recorded": True, "blockers": [], "task": task}


def _refresh_mechanical_assets(base_dir: str) -> None:
    """V1: Mechanical assets are no longer auto-created. Records zone replaces them."""
    pass


def _periodic_architecture_blockers(base_dir: str, task: Dict[str, Any]) -> List[str]:
    """LEGACY: V1 does not block ordinary task activation for architecture review.

    Architect is a read-only periodic reviewer — not a Task, not a gate.
    This function always returns no blockers. Status/prompt shows "Architect due"
    as a reminder. The old ARCH-* task / ARCH-FIX-* task mechanism is retired.
    """
    return []


def activation_blockers(base_dir: str, task_id: str, skip_current_state_check: bool = False) -> List[str]:
    """Task activation minimal gates.

    Task.md is the execution contract. Plan is not a gate.
    Only checks: task exists, status valid, deps closed, no other active,
    no fix_loop, no scope_violation, no close_attempt, start confirmed.
    """
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
    max_active = int(ledger.get("default_max_active", 1) or 1)
    if active and not task.get("parallel_safe"):
        blockers.append("active execution window occupied")
    if len(active) >= max_active and not task.get("parallel_safe"):
        blockers.append(f"default active task limit reached: {max_active}")
    if task.get("parallel_safe"):
        for other in active:
            overlap = _overlap(_task_plan_scope(base_dir, task), _task_plan_scope(base_dir, other))
            if overlap:
                blockers.append(f"parallel write boundary conflict with {other.get('id')}: {', '.join(overlap[:5])}")

    state = _read(Path(base_dir) / ".aiwf" / "state" / "state.json", {})
    if state.get("scope_violation"):
        blockers.append(
            "scope violation remains recorded; revert the violating files, then run "
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
    # V1: Periodic architecture review is advisory — it does NOT block ordinary task activation.
    # Architect is a read-only reviewer. Status/prompt shows "Architect due" as a reminder.
    blockers.extend(_active_plan_blockers(base_dir, task))
    return blockers


def _active_plan_blockers(base_dir: str, task: Dict[str, Any]) -> List[str]:
    """Plan is optional. Task.md is the execution contract.

    When a Plan is attached, only verify it exists and its index binding is healthy.
    Semantic fields (allowed_write, purpose, work_intent, etc.) live in Plan.md and
    are checked by Reviewer — NOT by the activation gate.
    """
    plan_id = str(task.get("plan_id") or "")
    if not plan_id:
        return []

    blockers: List[str] = []
    try:
        from .state.plan_ops import get_plan, plan_exists
        if not plan_exists(base_dir, plan_id):
            blockers.append(f"[plan] Plan '{plan_id}' not found in plans.json")
            return blockers
        plan = get_plan(base_dir, plan_id, migrate=False)
        if not plan:
            blockers.append(f"[plan] Plan '{plan_id}' entry is empty")
            return blockers
        # Check Plan.md exists if doc_path is set
        doc_path = plan.get("doc_path", "")
        if doc_path:
            from pathlib import Path as _Path
            if not (_Path(base_dir) / doc_path).exists():
                blockers.append(
                    f"[plan] Plan.md missing at {doc_path} — "
                    f"create it with: aiwf plan create {plan_id} --narrative"
                )
        # Check dependencies if plan has them
        from .state.plan_ops import plan_dependency_blockers
        dep_blockers = plan_dependency_blockers(base_dir, plan_id)
        if dep_blockers:
            blockers.extend(dep_blockers)
    except Exception as e:
        blockers.append(f"[plan] Plan check failed: {e}")

    return blockers


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
    # Freeze contract hash on activation (frontmatter + body)
    if task.get("doc_path"):
        from pathlib import Path as _Path
        doc = _Path(base_dir) / task["doc_path"]
        if doc.exists():
            from .index_ops import parse_md, compute_contract_hash
            fm, body = parse_md(doc)
            if body:
                task["frozen_contract_hash"] = compute_contract_hash(fm or {}, body)
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
            plan_goal = plan.get("target_goal_id") or plan.get("goal_id")
            if plan_goal and not task.get("goal_id"):
                task["goal_id"] = plan_goal
                task["parent_goal"] = plan_goal
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
        state["phase"] = "executing"
    _write(state_path, state)
    save_ledger(base_dir, ledger)
    return {"activated": True, "task": task, "ledger": ledger, "blockers": []}


def suspend_task(base_dir: str, task_id: str = "", note: str = "") -> Dict[str, Any]:
    """Suspend the active task and store a lightweight state snapshot."""
    if not task_id:
        state_path = Path(base_dir) / ".aiwf" / "state" / "state.json"
        state = _read(state_path, {})
        task_id = state.get("active_task_id", "")
    if not task_id:
        return {"suspended": False, "task": None, "ledger": load_ledger(base_dir),
                "blockers": ["no active task to suspend"]}
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
        "phase", "active_task_id", "active_plan_id",
    ]
    task["status"] = "suspended"
    task["suspended_at"] = _now()
    task["updated_at"] = _now()
    task["suspended_context"] = {k: state.get(k) for k in snapshot_keys if k in state}
    if note:
        task.setdefault("notes", []).append(note)
    if state.get("active_task_id") == task_id:
        state["active_task_id"] = None
        state["phase"] = "planning"
        _write(state_path, state)
    _sync_active_ids(ledger)
    save_ledger(base_dir, ledger)
    return {"suspended": True, "task": task, "ledger": ledger, "blockers": []}


def void_task(base_dir: str, task_id: str, reason: str, superseded_by: str = "") -> Dict[str, Any]:
    """Mark a non-active duplicate/obsolete task rejected without closure gates."""
    if not reason.strip():
        return {"voided": False, "task": None, "ledger": load_ledger(base_dir), "blockers": ["reason is required"]}
    ledger = load_ledger(base_dir)
    task = _find(ledger["tasks"], task_id)
    if not task:
        return {"voided": False, "task": None, "ledger": ledger, "blockers": [f"task not found: {task_id}"]}
    if task.get("status") == "active":
        return {
            "voided": False,
            "task": task,
            "ledger": ledger,
            "blockers": ["active task cannot be voided; suspend or close it through normal gates"],
        }
    if task.get("status") == "closed":
        return {
            "voided": False,
            "task": task,
            "ledger": ledger,
            "blockers": ["closed task cannot be voided"],
        }
    task["status"] = "rejected"
    task["state_reason"] = "superseded" if superseded_by else "not_planned"
    task["voided_at"] = _now()
    task["updated_at"] = _now()
    task.setdefault("notes", []).append(f"voided: {reason.strip()}")
    if superseded_by:
        task["superseded_by"] = superseded_by
    _sync_active_ids(ledger)
    save_ledger(base_dir, ledger)
    if task.get("plan_id") or task.get("parent_plan"):
        try:
            from .state.plan_ops import reconcile_task_to_plan
            reconcile_task_to_plan(base_dir, task)
        except Exception:
            pass
    return {"voided": True, "task": task, "ledger": ledger, "blockers": []}


def close_task(base_dir: str, task_id: str = "", note: str = "") -> Dict[str, Any]:
    """Mark the active task closed. Defaults to state.json's active_task_id.

    Returns goal progress: task is an execution unit, not a goal unit.
    Close output must show: task closed, goal complete status, next task.
    """
    if not task_id:
        state_path = Path(base_dir) / ".aiwf" / "state" / "state.json"
        state = _read(state_path, {})
        task_id = state.get("active_task_id", "")
    if not task_id:
        return {"closed": False, "task": None, "ledger": load_ledger(base_dir),
                "blockers": ["no active task to close"]}
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
        # 1. Fix-loop must not be open
        fix_loop = _read(Path(base_dir) / ".aiwf" / "state" / "fix-loop.json", {})
        if fix_loop.get("status") == "open":
            return {"closed": False, "task": task, "ledger": ledger,
                    "blockers": ["open fix-loop blocks task close"]}

        # 2. Active Task.md dirty check — warning only, does not block close
        frozen = task.get("frozen_contract_hash", "")
        if frozen and task.get("doc_path"):
            from pathlib import Path as _Path
            doc = _Path(base_dir) / task["doc_path"]
            if doc.exists():
                from .index_ops import parse_md, compute_contract_hash
                fm, body = parse_md(doc)
                if body:
                    current_hash = compute_contract_hash(fm or {}, body)
                    if current_hash != frozen:
                        warnings = task.setdefault("close_warnings", [])
                        warnings.append(
                            "active Task.md changed after activation. "
                            "This close uses the frozen JSON contract from activation. "
                            "Post-activation MD edits were ignored."
                        )

        # 3. Requirements gates: executor, tester, reviewer
        reqs = task.get("requirements", {})
        if reqs.get("executor_required"):
            evidence = _read(Path(base_dir) / ".aiwf" / "records" / "evidence.json", {"records": []})
            if not evidence.get("records"):
                return {"closed": False, "task": task, "ledger": ledger,
                        "blockers": ["executor_required but no evidence recorded"]}
        if reqs.get("tester_required"):
            testing = _read(Path(base_dir) / ".aiwf" / "records" / "testing.json", {"status": "missing"})
            if testing.get("status") not in ("adequate", "passed"):
                return {"closed": False, "task": task, "ledger": ledger,
                        "blockers": ["tester_required but testing status is not adequate/passed"]}
        if reqs.get("reviewer_required"):
            review = _read(Path(base_dir) / ".aiwf" / "records" / "review.json", {"result": "unknown"})
            if review.get("result") != "accepted":
                return {"closed": False, "task": task, "ledger": ledger,
                        "blockers": ["reviewer_required but review not accepted"]}
            if review.get("blockers"):
                return {"closed": False, "task": task, "ledger": ledger,
                        "blockers": [f"review has blockers: {review['blockers']}"]}
    task["status"] = "closed"
    task["closed_at"] = _now()
    task["updated_at"] = _now()
    task["closure"] = {"mode": "normal", "accepted": True, "summary": note or ""}
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
    if state.get("phase") in ("executing", "testing", "reviewing", "closing"):
        state["phase"] = "planning"
    _write(state_path, state)
    # When a Plan completes without README: force next Plan to fix it
    if task.get("plan_id") and not (Path(base_dir) / "README.md").exists():
        try:
            from .state.plan_ops import get_plan
            plan = get_plan(base_dir, task["plan_id"], migrate=False)
            plan_remaining = plan.get("remaining_task_ids", []) or []
            if not plan_remaining:
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
    # Milestone verification tasks bind to milestone_id, not parent_goal.
    task_kind = task.get("kind", "")
    task_milestone_id = task.get("milestone_id", "")
    granularity_warnings = []
    if not parent_goal and not parent_plan:
        if task_kind == "milestone_verification" and task_milestone_id:
            pass  # milestone verification tasks bind to milestone_id, not parent_goal
        else:
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


def force_close_task(base_dir: str, reason: str = "") -> Dict[str, Any]:
    """Human-only emergency close of the current active task.
    Bypasses ALL gates — no hash check, no evidence, no testing, no review.

    AI is mechanically blocked from calling this by command-policy.json.
    Operates on active_task_id from state.json — no TASK-ID parameter.
    """
    state_path = Path(base_dir) / ".aiwf" / "state" / "state.json"
    state = _read(state_path, {})
    task_id = state.get("active_task_id", "")
    if not task_id:
        return {"closed": False, "task": None, "ledger": load_ledger(base_dir),
                "blockers": ["no active task to force-close"]}

    ledger = load_ledger(base_dir)
    task = _find(ledger.get("tasks", []), task_id)
    if not task:
        return {"closed": False, "task": None, "ledger": ledger,
                "blockers": [f"active task not found in ledger: {task_id}"]}
    if task.get("status") == "closed":
        return {"closed": True, "task": task, "ledger": ledger, "blockers": []}

    # Collect unsatisfied checks before closing
    unsatisfied: List[str] = []
    reqs = task.get("requirements", {})
    if reqs.get("executor_required"):
        evidence = _read(Path(base_dir) / ".aiwf" / "records" / "evidence.json", {"records": []})
        if not evidence.get("records"):
            unsatisfied.append("executor_required but no evidence recorded")
    if reqs.get("tester_required"):
        testing = _read(Path(base_dir) / ".aiwf" / "records" / "testing.json", {"status": "missing"})
        if testing.get("status") not in ("adequate", "passed"):
            unsatisfied.append(f"tester_required but testing status={testing.get('status', 'missing')}")
    if reqs.get("reviewer_required"):
        review = _read(Path(base_dir) / ".aiwf" / "records" / "review.json", {"result": "unknown"})
        if review.get("result") != "accepted":
            unsatisfied.append(f"reviewer_required but review result={review.get('result', 'unknown')}")
        if review.get("blockers"):
            unsatisfied.append(f"review blockers: {review['blockers']}")

    task["status"] = "closed"
    task["closed_at"] = _now()
    task["updated_at"] = _now()
    task["closure"] = {
        "mode": "human_force",
        "accepted": False,
        "reason": reason.strip() or None,
        "unsatisfied_checks": unsatisfied,
    }
    if reason.strip():
        task.setdefault("notes", []).append(f"FORCE-CLOSED by human: {reason.strip()}")

    state["active_task_id"] = None
    if state.get("phase") in ("executing", "testing", "reviewing", "closing"):
        state["phase"] = "planning"
    _write(state_path, state)

    save_ledger(base_dir, ledger)
    _refresh_mechanical_assets(base_dir)

    try:
        from .state.plan_ops import reconcile_task_to_plan
        reconcile_task_to_plan(base_dir, task)
    except Exception:
        pass

    return {"closed": True, "task": task, "ledger": ledger, "blockers": []}


def ledger_summary(base_dir: str) -> Dict[str, Any]:
    ledger = load_ledger(base_dir)
    tasks = ledger.get("tasks", [])
    counts: Dict[str, int] = {}
    for task in tasks:
        status = task.get("status", "unknown")
        counts[status] = counts.get(status, 0) + 1
    active_ids = [t.get("id") for t in tasks if t.get("status") == "active" and t.get("id")]
    return {
        "tasks": tasks,
        "counts": counts,
        "active_task_ids": active_ids,
    }
