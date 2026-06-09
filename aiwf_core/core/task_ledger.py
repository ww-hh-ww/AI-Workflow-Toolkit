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


def _read(path: Path, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else (default or {})
    except Exception:
        return default or {}


def _write(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ledger_path(base_dir: str) -> Path:
    return Path(base_dir) / ".aiwf" / "history" / "task-ledger.json"


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
    allowed_write: Optional[List[str]] = None,
    parallel_safe: bool = False,
    notes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Create/update a task without activating execution."""
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
        if allowed_write is not None and allowed_write != (task.get("allowed_write", []) or []):
            contract_changes.append("allowed_write")
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
            "allowed_write": [],
            "parallel_safe": False,
            "notes": [],
            "created_at": _now(),
            "updated_at": _now(),
        }
        tasks.append(task)
    if title:
        task["title"] = title
    task["status"] = status
    if dependencies is not None:
        task["dependencies"] = dependencies
    if allowed_write is not None:
        task["allowed_write"] = allowed_write
    task["parallel_safe"] = bool(parallel_safe)
    if notes:
        task.setdefault("notes", []).extend(notes)
    task["updated_at"] = _now()
    _sync_active_ids(ledger)
    save_ledger(base_dir, ledger)
    return {"task": task, "ledger": ledger}


def _sync_active_ids(ledger: Dict[str, Any]) -> None:
    active = [t.get("id") for t in ledger.get("tasks", []) if t.get("status") == "active" and t.get("id")]
    ledger.setdefault("execution_window", {})["active_task_ids"] = active


def _overlap(a: List[str], b: List[str]) -> List[str]:
    return sorted(set(a or []) & set(b or []))


def _quality_activation_blockers(base_dir: str, task: Dict[str, Any]) -> List[str]:
    """Consume task_gravity() for quality-based activation blockers."""
    from .task_gravity import task_gravity
    gravity = task_gravity(base_dir, task.get("allowed_write", []))
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
    """Derive conservative routing factors from machine-readable task/project state."""
    root = Path(base_dir)
    allowed = [str(p) for p in (task.get("allowed_write", []) or []) if str(p)]
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

    factors = {
        "cross_module": len(module_roots) > 1,
        "public_api_change": bool(
            "public_api_change" in risk_flags
            or "public_api_changes" in risk_flags
        ),
        "semantic_change": bool(non_docs),
        # Historical/project pressure is surfaced separately. It should inform Planner
        # explanation and optional breadth increases, not permanently inflate every
        # small task into L3.
        "historical_deferred_risk": False,
        "security_or_data_risk": bool(
            risk_flags & {"security_sensitive", "security_or_data_risk", "data_migration"}
        ),
        "test_matrix_complexity": bool(
            "test_matrix_complexity" in risk_flags
            or (bool(non_docs) and bool(brief.get("integration_points")))
            or (bool(non_docs) and bool(brief.get("architecture_risks")))
        ),
        "user_decision_needed": bool(state.get("requires_user_decision")),
        "architecture_impact": bool(
            "architecture_impact" in risk_flags
            or bool(brief.get("integration_points") and len(module_roots) > 1)
        ),
        "prior_fix_loop": bool(
            fix_loop.get("status") == "open"
            or "prior_fix_loop" in risk_flags
        ),
        "destructive_command": "destructive_command" in risk_flags,
        "publish_or_deploy": "publish_or_deploy" in risk_flags,
        "data_migration": "data_migration" in risk_flags,
    }
    factors["_background"] = background
    return factors


def _apply_mechanical_routing(base_dir: str, task: Dict[str, Any]) -> Dict[str, Any]:
    """Compute and persist the minimum workflow level and its depth/breadth policy."""
    root = Path(base_dir)
    state_path = root / ".aiwf" / "state" / "state.json"
    state = _read(state_path, {})
    factors = _mechanical_routing_factors(base_dir, task)
    from .routing import compute_routing_score
    background = factors.pop("_background", {}) or {}
    decision = compute_routing_score(factors, file_count=max(len(task.get("allowed_write", []) or []), 1))

    recommended = decision["workflow_level"]
    try:
        from .task_gravity import task_gravity
        gravity_level = task_gravity(base_dir, task.get("allowed_write", [])).get("suggested_min_level")
        if gravity_level in WORKFLOW_LEVELS and WORKFLOW_LEVELS.index(gravity_level) > WORKFLOW_LEVELS.index(recommended):
            recommended = gravity_level
            decision["routing_factors"].append(f"gravity:{gravity_level}")
    except Exception:
        pass

    current = state.get("workflow_level", "L1_review_light")
    if current not in WORKFLOW_LEVELS:
        current = "L1_review_light"
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
    ck_dir = Path(base_dir) / ".aiwf" / "checkpoints"
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
            overlap = _overlap(task.get("allowed_write", []), other.get("allowed_write", []))
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
    if not skip_current_state_check:
        cs = current_state_freshness(base_dir)
        if cs.get("status") == "stale":
            blockers.append("current-state.md is stale; rebase or refresh summary before activating next task")
    blockers.extend(_quality_activation_blockers(base_dir, task))
    blockers.extend(_periodic_architecture_blockers(base_dir, task))
    blockers.extend(_required_contract_blockers(base_dir, task))
    blockers.extend(_user_confirmation_blockers(base_dir))
    return blockers


def activate_task(base_dir: str, task_id: str) -> Dict[str, Any]:
    """Activate a planned task if execution-window gates pass."""
    ledger = load_ledger(base_dir)
    task = _find(ledger["tasks"], task_id)
    cs = current_state_freshness(base_dir)
    if cs.get("status") == "stale":
        return {
            "activated": False,
            "task": task,
            "ledger": ledger,
            "blockers": ["current-state.md is stale; rebase or refresh summary before activating next task"],
        }
    if task:
        _apply_mechanical_routing(base_dir, task)
        _refresh_mechanical_assets(base_dir)
    blockers = activation_blockers(base_dir, task_id, skip_current_state_check=True)
    if blockers:
        return {"activated": False, "task": task, "ledger": ledger, "blockers": blockers}
    task["status"] = "active"
    task["activated_at"] = _now()
    task["updated_at"] = _now()
    _sync_active_ids(ledger)
    state_path = Path(base_dir) / ".aiwf" / "state" / "state.json"
    state = _read(state_path, {})
    if task.get("suspended_context"):
        for key, value in task["suspended_context"].items():
            state[key] = value
    state["active_task_id"] = task_id
    _write(state_path, state)
    save_ledger(base_dir, ledger)
    return {"activated": True, "task": task, "ledger": ledger, "blockers": []}


def suspend_task(base_dir: str, task_id: str, note: str = "") -> Dict[str, Any]:
    """Suspend an active task and store a lightweight state snapshot."""
    ledger = load_ledger(base_dir)
    task = _find(ledger["tasks"], task_id)
    if not task:
        return {"suspended": False, "task": None, "ledger": ledger, "blockers": [f"task not found: {task_id}"]}
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

    testing = _read(root / ".aiwf" / "quality" / "testing.json", {})
    review = _read(root / ".aiwf" / "quality" / "review.json", {})
    evidence = _read(root / ".aiwf" / "evidence" / "records.json", {"records": []})
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
            f"L2/L3 task requires accepted machine evidence from at least 3 distinct sessions; found {len(sessions)}"
        )
    missing_roles = [r for r in ("executor", "tester", "reviewer") if r not in roles]
    if missing_roles:
        blockers.append(f"L2/L3 task requires role-bound evidence; missing: {', '.join(missing_roles)}")
    if cleanup_at and reviewer_timestamps and min(reviewer_timestamps) <= cleanup_at:
        blockers.append("L2/L3 cleanup must be verified before Reviewer evidence")
    if cleanup_at and not reviewer_timestamps:
        blockers.append("L2/L3 task requires Reviewer evidence after cleanup verification")

    blockers.extend(_architecture_migration_blockers(goal, evidence, accepted_ids))

    if level == "L3_full_power":
        checkpoint_dir = root / ".aiwf" / "checkpoints"
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
    return _mode_completion_blockers(base_dir, task) + _l2_l3_completion_blockers(base_dir, task)


def close_task(base_dir: str, task_id: str, note: str = "") -> Dict[str, Any]:
    """Mark a ledger task closed. This does not close the AIWF workflow."""
    ledger = load_ledger(base_dir)
    task = _find(ledger["tasks"], task_id)
    if not task:
        return {"closed": False, "task": None, "ledger": ledger, "blockers": [f"task not found: {task_id}"]}
    if task.get("status") == "active":
        # Only block spike-mode tasks from closing as final implementation.
        # All other quality gates belong to prepare_close, not close_task.
        state = _read(Path(base_dir) / ".aiwf" / "state" / "state.json", {})
        mode = state.get("request_mode", "execution")
        pattern = state.get("workflow_pattern", "linear")
        if mode == "spike" or pattern == "spike_first":
            return {"closed": False, "task": task, "ledger": ledger,
                    "blockers": ["spike task cannot close as final implementation; record findings and switch to request_mode=execution"]}
    task["status"] = "closed"
    task["closed_at"] = _now()
    task["updated_at"] = _now()
    if note:
        task.setdefault("notes", []).append(note)
    _sync_active_ids(ledger)
    state_path = Path(base_dir) / ".aiwf" / "state" / "state.json"
    state = _read(state_path, {})
    if state.get("active_task_id") == task_id:
        state["active_task_id"] = None
        _write(state_path, state)
    save_ledger(base_dir, ledger)
    _refresh_mechanical_assets(base_dir)
    try:
        from .cross_task_quality import append_task_history_from_state, write_quality_digest
        append_task_history_from_state(base_dir, task_id=task_id, title=task.get("title", ""))
        write_quality_digest(base_dir)
    except Exception:
        pass
    try:
        from .lifecycle_cleanup import auto_cleanup
        auto_cleanup(base_dir)
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
    return {
        "tasks": tasks,
        "counts": counts,
        "active_task_ids": ledger.get("execution_window", {}).get("active_task_ids", []),
    }
