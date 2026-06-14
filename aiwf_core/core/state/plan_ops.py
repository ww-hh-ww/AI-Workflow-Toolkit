"""Plan registry operations — machine layer for plan/task decoupling."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..state_schema import (
    DEFAULT_PLAN_KIND, DEFAULT_PLAN_PHASE, LEGACY_GOAL_ID,
    VALID_PLAN_KINDS, VALID_PLAN_PHASES, VALID_WORK_INTENTS, default_plans,
)


def _is_valid_work_intent(intent: str) -> bool:
    return not intent or intent in VALID_WORK_INTENTS


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _plans_path(base_dir: str) -> Path:
    return Path(base_dir) / ".aiwf" / "state" / "plans.json"


def _read(path: Path, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else (default or {})
    except Exception:
        return default or {}


def _write(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _empty_plan(plan_id: str, goal_id: str = "", task_ids: Optional[List[str]] = None,
                status: str = "draft", milestone_id: str = "",
                plan_kind: str = "", target_goal_id: str = "",
                active_phase: str = "",
                interfaces: Optional[List[str]] = None,
                constraints: Optional[List[str]] = None,
                child_goal_policy: str = "",
                work_intent: str = "",
                allowed_write: Optional[List[str]] = None,
                forbidden_write: Optional[List[str]] = None,
                purpose: str = "",
                test_focus: Optional[List[str]] = None,
                review_focus: Optional[List[str]] = None,
                non_goals: Optional[List[str]] = None,
                dependencies: Optional[List[str]] = None,
                interface_contract: str = "",
                escalation_triggers: Optional[List[str]] = None,
                read_hints: Optional[List[str]] = None) -> Dict[str, Any]:
    now = _now()
    ids = list(dict.fromkeys(task_ids or []))
    kind = plan_kind or DEFAULT_PLAN_KIND
    if kind not in VALID_PLAN_KINDS:
        raise ValueError(f"invalid plan_kind: {kind}")
    phase = active_phase or DEFAULT_PLAN_PHASE
    if phase not in VALID_PLAN_PHASES:
        raise ValueError(f"invalid active_phase: {phase}")
    intent = work_intent or ""
    if intent and not _is_valid_work_intent(intent):
        raise ValueError(f"invalid work_intent: {intent}")
    return {
        "id": plan_id,
        "plan_id": plan_id,
        "title": plan_id,
        "goal_id": goal_id or LEGACY_GOAL_ID,
        "target_goal_id": target_goal_id or goal_id or LEGACY_GOAL_ID,
        "plan_kind": kind,
        "active_phase": phase,
        "work_intent": intent or None,
        "milestone_id": milestone_id or None,
        "task_ids": ids,
        "task_status": {tid: "unknown" for tid in ids},
        "closed_task_ids": [],
        "remaining_task_ids": ids,
        "interfaces": list(dict.fromkeys(interfaces or [])),
        "constraints": list(dict.fromkeys(constraints or [])),
        "child_goal_policy": child_goal_policy or "",
        "status": status,
        "admission_trace": None,  # Stage 4.4: set when Plan created via admission protocol
        "artifact_path": f".aiwf/artifacts/plans/{plan_id}.md",
        "evidence_rollup": {
            "summary": "",
            "closed_count": 0,
            "total_count": len(ids),
            "remaining_task_ids": ids,
            "changed_files": [],
        },
        # Context fields — the Plan IS the context. Tasks inherit on activation.
        "allowed_write": list(dict.fromkeys(allowed_write or [])),
        "forbidden_write": list(dict.fromkeys(forbidden_write or [])),
        "purpose": purpose or "",
        "test_focus": list(dict.fromkeys(test_focus or [])),
        "review_focus": list(dict.fromkeys(review_focus or [])),
        "non_goals": list(dict.fromkeys(non_goals or [])),
        "dependencies": list(dict.fromkeys(dependencies or [])),
        "interface_contract": interface_contract or "",
        "escalation_triggers": list(dict.fromkeys(escalation_triggers or [])),
        "read_hints": list(dict.fromkeys(read_hints or [])),
        "created_at": now,
        "updated_at": now,
    }


def _find_plan(plans: Dict[str, Any], plan_id: str) -> Optional[Dict[str, Any]]:
    for plan in plans.get("plans", []) or []:
        if isinstance(plan, dict) and (plan.get("plan_id") == plan_id or plan.get("id") == plan_id):
            return plan
    return None


def _legacy_task_refs(base: Path) -> Dict[str, Dict[str, str]]:
    ledger = _read(base / ".aiwf" / "runtime" / "history" / "task-ledger.json", {})
    refs: Dict[str, Dict[str, str]] = {}
    for task in ledger.get("tasks", []) or []:
        if not isinstance(task, dict):
            continue
        tid = str(task.get("id", "") or "")
        if not tid:
            continue
        refs[tid] = {
            "plan_id": str(task.get("plan_id") or task.get("parent_plan") or tid),
            "goal_id": str(task.get("goal_id") or task.get("parent_goal") or LEGACY_GOAL_ID),
        }
    return refs


def migrate_legacy_plans(base_dir: str, plans: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Manual/dev audit helper to identify retired markdown/task refs.

    Activation and normal load paths do not call this helper. It is additive,
    never renames retired task-named plan artifacts, and never parses markdown content.
    """
    base = Path(base_dir)
    data = plans or _read(_plans_path(base_dir), default_plans())
    data.setdefault("schema_version", 1)
    data.setdefault("legacy_goal_id", LEGACY_GOAL_ID)
    entries = data.setdefault("plans", [])
    refs = _legacy_task_refs(base)
    seen = {p.get("plan_id") for p in entries if isinstance(p, dict)}
    changed = False

    plan_dir = base / ".aiwf" / "artifacts" / "plans"
    if plan_dir.exists():
        for path in sorted(plan_dir.glob("*.md")):
            legacy_id = path.stem
            if legacy_id in seen:
                continue
            ref = refs.get(legacy_id, {})
            entries.append(_empty_plan(
                ref.get("plan_id") or legacy_id,
                goal_id=ref.get("goal_id") or LEGACY_GOAL_ID,
                task_ids=[legacy_id],
                status="active",
            ))
            seen.add(legacy_id)
            changed = True

    for tid, ref in refs.items():
        plan_id = ref.get("plan_id") or tid
        plan = _find_plan(data, plan_id)
        if not plan:
            entries.append(_empty_plan(plan_id, goal_id=ref.get("goal_id") or LEGACY_GOAL_ID,
                                       task_ids=[tid], status="active"))
            changed = True
            continue
        task_ids = plan.setdefault("task_ids", [])
        if tid not in task_ids:
            task_ids.append(tid)
            plan.setdefault("task_status", {})[tid] = "unknown"
            plan["updated_at"] = _now()
            changed = True

    if changed:
        _write(_plans_path(base_dir), data)
    return data


def load_plans(base_dir: str, migrate: bool = False) -> Dict[str, Any]:
    path = _plans_path(base_dir)
    data = _read(path, default_plans())
    data.setdefault("schema_version", 1)
    data.setdefault("legacy_goal_id", LEGACY_GOAL_ID)
    data.setdefault("active_plan_id", None)
    data.setdefault("plans", [])
    if not path.exists():
        _write(path, data)
    return migrate_legacy_plans(base_dir, data) if migrate else data


def save_plans(base_dir: str, plans: Dict[str, Any]) -> None:
    plans.setdefault("schema_version", 1)
    plans.setdefault("legacy_goal_id", LEGACY_GOAL_ID)
    plans.setdefault("active_plan_id", None)
    plans.setdefault("plans", [])
    _write(_plans_path(base_dir), plans)


def upsert_plan(base_dir: str, plan_id: str, goal_id: str = "", task_ids: Optional[List[str]] = None,
                status: str = "active", milestone_id: str = "", title: str = "",
                plan_kind: str = "", target_goal_id: str = "",
                active_phase: str = "",
                interfaces: Optional[List[str]] = None,
                constraints: Optional[List[str]] = None,
                child_goal_policy: str = "",
                work_intent: str = "",
                allowed_write: Optional[List[str]] = None,
                forbidden_write: Optional[List[str]] = None,
                purpose: str = "",
                test_focus: Optional[List[str]] = None,
                review_focus: Optional[List[str]] = None,
                interface_contract: str = "",
                escalation_triggers: Optional[List[str]] = None) -> Dict[str, Any]:
    if milestone_id:
        from .milestone_ops import attach_plan_to_milestone, milestone_exists
        if not milestone_exists(base_dir, milestone_id):
            raise ValueError(f"milestone not found: {milestone_id}")
    if plan_kind and plan_kind not in VALID_PLAN_KINDS:
        raise ValueError(f"invalid plan_kind: {plan_kind}")
    if active_phase and active_phase not in VALID_PLAN_PHASES:
        raise ValueError(f"invalid active_phase: {active_phase}")
    if work_intent and work_intent not in VALID_WORK_INTENTS:
        raise ValueError(f"invalid work_intent: {work_intent}")

    # Stage 3.9: validate target_goal_id exists in goals.json when registry non-empty
    tgid = target_goal_id or ""
    if tgid and tgid != LEGACY_GOAL_ID:
        try:
            from .goal_tree_ops import goal_exists, load_goal_tree
            tree = load_goal_tree(base_dir, auto_create=False)
            if tree.get("goals"):  # registry is non-empty
                if not goal_exists(base_dir, tgid):
                    raise ValueError(
                        f"target_goal_id {tgid} does not exist in goals.json; "
                        f"create the goal first or use GOAL-001 as fallback"
                    )
        except ImportError:
            pass

    plans = load_plans(base_dir)
    plan = _find_plan(plans, plan_id)
    if not plan:
        plan = _empty_plan(plan_id, goal_id=goal_id, task_ids=task_ids or [], status=status,
                           milestone_id=milestone_id, plan_kind=plan_kind,
                           target_goal_id=target_goal_id, active_phase=active_phase,
                           interfaces=interfaces, constraints=constraints,
                           child_goal_policy=child_goal_policy, work_intent=work_intent,
                           allowed_write=allowed_write, forbidden_write=forbidden_write,
                           purpose=purpose, test_focus=test_focus, review_focus=review_focus,
                           interface_contract=interface_contract,
                           escalation_triggers=escalation_triggers)
        plans["plans"].append(plan)
    else:
        plan.setdefault("id", plan_id)
        plan.setdefault("plan_id", plan_id)
        plan.setdefault("goal_id", LEGACY_GOAL_ID)
        plan.setdefault("target_goal_id", plan.get("goal_id"))
        plan.setdefault("plan_kind", DEFAULT_PLAN_KIND)
        plan.setdefault("active_phase", DEFAULT_PLAN_PHASE)
        plan.setdefault("artifact_path", f".aiwf/artifacts/plans/{plan_id}.md")
        plan.setdefault("interfaces", [])
        plan.setdefault("constraints", [])
        plan.setdefault("child_goal_policy", "")
        plan.setdefault("admission_trace", None)
        plan.setdefault("work_intent", None)
        # Context fields — Plan IS the context
        plan.setdefault("allowed_write", [])
        plan.setdefault("forbidden_write", [])
        plan.setdefault("purpose", "")
        plan.setdefault("test_focus", [])
        plan.setdefault("review_focus", [])
        plan.setdefault("non_goals", [])
        plan.setdefault("dependencies", [])
        plan.setdefault("interface_contract", "")
        plan.setdefault("escalation_triggers", [])
        plan.setdefault("read_hints", [])
        if goal_id:
            plan["goal_id"] = goal_id
        if target_goal_id:
            plan["target_goal_id"] = target_goal_id
        if plan_kind:
            plan["plan_kind"] = plan_kind
        if active_phase:
            plan["active_phase"] = active_phase
        if milestone_id:
            plan["milestone_id"] = milestone_id
        if title:
            plan["title"] = title
        if status:
            plan["status"] = status
        for iface in interfaces or []:
            if iface not in plan.setdefault("interfaces", []):
                plan["interfaces"].append(iface)
        for c in constraints or []:
            if c not in plan.setdefault("constraints", []):
                plan["constraints"].append(c)
        if child_goal_policy:
            plan["child_goal_policy"] = child_goal_policy
        if work_intent:
            plan["work_intent"] = work_intent
        # Context fields
        if allowed_write is not None:
            plan["allowed_write"] = list(dict.fromkeys(allowed_write))
        if forbidden_write is not None:
            plan["forbidden_write"] = list(dict.fromkeys(forbidden_write))
        if purpose:
            plan["purpose"] = purpose
        if test_focus is not None:
            plan["test_focus"] = list(dict.fromkeys(test_focus))
        if review_focus is not None:
            plan["review_focus"] = list(dict.fromkeys(review_focus))
        if interface_contract:
            plan["interface_contract"] = interface_contract
        if escalation_triggers is not None:
            plan["escalation_triggers"] = list(dict.fromkeys(escalation_triggers))
        for tid in task_ids or []:
            if tid not in plan.setdefault("task_ids", []):
                plan["task_ids"].append(tid)
                plan.setdefault("task_status", {})[tid] = "unknown"
        plan["remaining_task_ids"] = [
            tid for tid in plan.get("task_ids", []) or []
            if tid not in set(plan.get("closed_task_ids", []) or [])
            and plan.get("task_status", {}).get(tid) != "rejected"
        ]
        plan["updated_at"] = _now()
    if not plan.get("target_goal_id"):
        plan["target_goal_id"] = plan.get("goal_id", LEGACY_GOAL_ID)
    if title:
        plan["title"] = title
    if status == "active":
        plans["active_plan_id"] = plan_id
    save_plans(base_dir, plans)
    if milestone_id:
        attach_plan_to_milestone(base_dir, milestone_id, plan_id, task_ids=plan.get("task_ids", []) or [])
    return {"plan": plan, "plans": plans}


def set_active_plan(base_dir: str, plan_id: str) -> Dict[str, Any]:
    """Explicitly activate a Plan. This is a planner-executor decision.

    Creating a Plan does NOT auto-activate it. The planner-executor must
    choose which Plan becomes active, after verifying its contracts are
    ready — preventing plan_only_drift deadlocks where the wrong plan
    is active and can't be edited.
    """
    plans = load_plans(base_dir)
    plan = _find_plan(plans, plan_id)
    if not plan:
        raise ValueError(f"plan not found: {plan_id}")
    plans["active_plan_id"] = plan_id
    save_plans(base_dir, plans)
    state_path = Path(base_dir) / ".aiwf" / "state" / "state.json"
    if state_path.exists():
        import json
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            state = {}
        state["active_plan_id"] = plan_id
        state["phase"] = "planned"
        state["active_task_id"] = None
        state["close_attempt"] = False
        state["closure_allowed"] = False
        state["close_prepared_task_id"] = ""
        state["close_prepared_at"] = ""
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"activated": True, "plan": plan, "plans": plans}


def deactivate_plan(base_dir: str) -> Dict[str, Any]:
    """Clear the active plan. Returns to discussing phase."""
    plans = load_plans(base_dir)
    prev = plans.get("active_plan_id")
    plans["active_plan_id"] = None
    save_plans(base_dir, plans)
    state_path = Path(base_dir) / ".aiwf" / "state" / "state.json"
    if state_path.exists():
        import json
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            state = {}
        state["active_plan_id"] = ""
        state["phase"] = "discussing"
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"deactivated": True, "previous": prev, "plans": plans}

def attach_task_to_plan(base_dir: str, plan_id: str, task_id: str) -> Dict[str, Any]:
    plans = load_plans(base_dir)
    plan = _find_plan(plans, plan_id)
    if not plan:
        return {"attached": False, "plan": None, "plans": plans, "reason": f"plan not found: {plan_id}"}
    try:
        from ..task_ledger import load_ledger, save_ledger

        ledger = load_ledger(base_dir)
        for task in ledger.get("tasks", []) or []:
            if not isinstance(task, dict) or task.get("id") != task_id:
                continue
            existing = str(task.get("plan_id") or task.get("parent_plan") or "")
            if existing and existing != plan_id:
                return {
                    "attached": False,
                    "plan": plan,
                    "plans": plans,
                    "reason": f"task {task_id} already belongs to plan {existing}",
                }
            task["plan_id"] = plan_id
            task["parent_plan"] = plan_id
            goal_id = str(plan.get("target_goal_id") or plan.get("goal_id") or "")
            if goal_id:
                task["goal_id"] = goal_id
                task["parent_goal"] = goal_id
            task["updated_at"] = _now()
            save_ledger(base_dir, ledger)
            break
    except Exception:
        pass
    task_ids = plan.setdefault("task_ids", [])
    if task_id not in task_ids:
        task_ids.append(task_id)
    status = plan.setdefault("task_status", {}).get(task_id, "unknown")
    try:
        from ..task_ledger import load_ledger

        for task in load_ledger(base_dir).get("tasks", []) or []:
            if isinstance(task, dict) and task.get("id") == task_id:
                status = str(task.get("status", status) or status)
                break
    except Exception:
        pass
    plan.setdefault("task_status", {})[task_id] = status
    plan["remaining_task_ids"] = [
        tid for tid in plan.get("task_ids", []) or []
        if tid not in set(plan.get("closed_task_ids", []) or [])
    ]
    plan["updated_at"] = _now()
    save_plans(base_dir, plans)
    if plan.get("milestone_id"):
        try:
            from .milestone_ops import attach_plan_to_milestone
            attach_plan_to_milestone(base_dir, plan["milestone_id"], plan_id, task_ids=[task_id])
        except Exception:
            pass
    return {"attached": True, "plan": plan, "plans": plans}


def detach_task_from_plan(base_dir: str, plan_id: str, task_id: str) -> Dict[str, Any]:
    plans = load_plans(base_dir)
    plan = _find_plan(plans, plan_id)
    if not plan:
        return {"detached": False, "plan": None, "plans": plans}
    plan["task_ids"] = [tid for tid in plan.get("task_ids", []) or [] if tid != task_id]
    plan.setdefault("task_status", {}).pop(task_id, None)
    plan["closed_task_ids"] = [tid for tid in plan.get("closed_task_ids", []) or [] if tid != task_id]
    plan["updated_at"] = _now()
    save_plans(base_dir, plans)
    return {"detached": True, "plan": plan, "plans": plans}


def get_plan(base_dir: str, plan_id: str, migrate: bool = False) -> Dict[str, Any]:
    return _find_plan(load_plans(base_dir, migrate=migrate), plan_id) or {}


def plan_exists(base_dir: str, plan_id: str) -> bool:
    return bool(get_plan(base_dir, plan_id, migrate=False))


def reconcile_task_to_plan(base_dir: str, task: Dict[str, Any]) -> Dict[str, Any]:
    """Roll closed task progress into its parent plan registry entry."""
    task_id = str(task.get("id", "") or "")
    plan_id = str(task.get("plan_id") or task.get("parent_plan") or "")
    if not task_id or not plan_id:
        return {"reconciled": False, "reason": "missing plan_id"}

    plans = load_plans(base_dir)
    plan = _find_plan(plans, plan_id)
    if not plan:
        return {"reconciled": False, "reason": f"plan not found: {plan_id}"}

    task_ids = plan.setdefault("task_ids", [])
    if task_id not in task_ids:
        task_ids.append(task_id)
    task_status = plan.setdefault("task_status", {})
    task_status[task_id] = str(task.get("status", "unknown") or "unknown")
    closed = [tid for tid in task_ids if task_status.get(tid) == "closed"]
    remaining = [tid for tid in task_ids if task_status.get(tid) not in ("closed", "rejected")]

    evidence = _read(Path(base_dir) / ".aiwf" / "artifacts" / "evidence" / "records.json", {"records": []})
    changed = sorted({
        f for rec in evidence.get("records", []) or []
        if isinstance(rec, dict)
        for f in (rec.get("changed_files") or [])
        if f
    })
    plan["closed_task_ids"] = closed
    plan["remaining_task_ids"] = remaining
    plan["evidence_rollup"] = {
        "summary": f"{len(closed)}/{len(task_ids)} plan tasks closed",
        "closed_count": len(closed),
        "total_count": len(task_ids),
        "remaining_task_ids": remaining,
        "changed_files": changed,
    }
    if task_ids and not remaining:
        plan["status"] = "complete"
    plan["updated_at"] = _now()
    save_plans(base_dir, plans)

    milestone_progress = {}
    if plan.get("milestone_id"):
        try:
            from .milestone_ops import reconcile_plan_to_milestone
            milestone_progress = reconcile_plan_to_milestone(base_dir, plan)
        except Exception:
            milestone_progress = {"reconciled": False, "reason": "milestone reconcile failed"}

    # Stage 3.4: soft rollup to parent Goal (read-only, no auto-close)
    goal_progress = {}
    if plan.get("status") == "complete":
        try:
            from .goal_tree_ops import reconcile_plan_to_goal
            goal_progress = reconcile_plan_to_goal(base_dir, plan)
        except Exception:
            goal_progress = {"reconciled": False, "reason": "goal reconcile failed"}

    return {
        "reconciled": True,
        "plan": plan,
        "remaining_task_ids": remaining,
        "closed_count": len(closed),
        "total_count": len(task_ids),
        "milestone_progress": milestone_progress,
        "goal_progress": goal_progress,
    }
