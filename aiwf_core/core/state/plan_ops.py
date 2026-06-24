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
                status: str = "open", milestone_id: str = "",
                **_legacy) -> Dict[str, Any]:
    """V2 minimal Plan JSON: index + status + doc binding only.

    Semantic fields (work_intent, allowed_write, purpose, etc.) live in Plan.md.
    This function accepts but ignores legacy kwargs for backward compat.
    """
    now = _now()
    ids = list(dict.fromkeys(task_ids or []))
    return {
        "id": plan_id,
        "plan_id": plan_id,
        "type": "plan",
        "title": plan_id,
        "title_cache": "",
        "summary_cache": "",
        "doc_path": "",
        "report_policy": "ask",
        "goal_id": goal_id or LEGACY_GOAL_ID,
        "milestone_id": milestone_id or None,
        "task_ids": ids,
        "task_status": {tid: "unknown" for tid in ids},
        "closed_task_ids": [],
        "remaining_task_ids": ids,
        "status": status,
        "created_at": now,
        "updated_at": now,
    }


def _find_plan(plans: Dict[str, Any], plan_id: str) -> Optional[Dict[str, Any]]:
    for plan in plans.get("plans", []) or []:
        if isinstance(plan, dict) and (plan.get("plan_id") == plan_id or plan.get("id") == plan_id):
            return plan
    return None


def _plan_id(plan: Dict[str, Any]) -> str:
    return str(plan.get("plan_id") or plan.get("id") or "")


def validate_plan_dependencies(plans: Dict[str, Any]) -> None:
    """Validate the complete Plan dependency graph."""
    entries = [p for p in plans.get("plans", []) or [] if isinstance(p, dict)]
    by_id = {_plan_id(p): p for p in entries if _plan_id(p)}
    for plan_id, plan in by_id.items():
        for dependency_id in plan.get("dependencies", []) or []:
            if dependency_id == plan_id:
                raise ValueError(f"plan cannot depend on itself: {plan_id}")
            if dependency_id not in by_id:
                raise ValueError(f"plan dependency not found: {plan_id} -> {dependency_id}")

    visiting: List[str] = []
    visited = set()

    def visit(plan_id: str) -> None:
        if plan_id in visited:
            return
        if plan_id in visiting:
            start = visiting.index(plan_id)
            cycle = visiting[start:] + [plan_id]
            raise ValueError(f"plan dependency cycle: {' -> '.join(cycle)}")
        visiting.append(plan_id)
        for dependency_id in by_id[plan_id].get("dependencies", []) or []:
            visit(str(dependency_id))
        visiting.pop()
        visited.add(plan_id)

    for plan_id in sorted(by_id):
        visit(plan_id)


def plan_dependency_blockers(base_dir: str, plan_id: str) -> List[str]:
    plans = load_plans(base_dir)
    plan = _find_plan(plans, plan_id)
    if not plan:
        return [f"plan not found: {plan_id}"]
    blockers = []
    for dependency_id in plan.get("dependencies", []) or []:
        dependency = _find_plan(plans, str(dependency_id))
        if not dependency:
            blockers.append(f"plan dependency missing: {dependency_id}")
            continue
        status = str(dependency.get("status") or "draft")
        if status != "closed":
            blockers.append(f"plan dependency not complete: {dependency_id} (status={status})")
    return blockers


def plan_readiness(base_dir: str, plan_id: str) -> Dict[str, Any]:
    plan = get_plan(base_dir, plan_id)
    blockers = plan_dependency_blockers(base_dir, plan_id)
    return {
        "plan_id": plan_id,
        "dependencies": list(plan.get("dependencies", []) or []),
        "ready": bool(plan) and not blockers,
        "blockers": blockers,
    }


def add_plan_dependency(base_dir: str, plan_id: str, dependency_id: str) -> Dict[str, Any]:
    plans = load_plans(base_dir)
    plan = _find_plan(plans, plan_id)
    if not plan:
        raise ValueError(f"plan not found: {plan_id}")
    if not _find_plan(plans, dependency_id):
        raise ValueError(f"plan dependency not found: {plan_id} -> {dependency_id}")
    dependencies = list(plan.get("dependencies", []) or [])
    if dependency_id not in dependencies:
        dependencies.append(dependency_id)
    plan["dependencies"] = dependencies
    validate_plan_dependencies(plans)
    plan["updated_at"] = _now()
    save_plans(base_dir, plans)
    return {"plan": plan, "dependency_id": dependency_id, "added": True}


def remove_plan_dependency(base_dir: str, plan_id: str, dependency_id: str,
                           reason: str) -> Dict[str, Any]:
    reason = reason.strip()
    if not reason:
        raise ValueError("dependency removal reason is required")
    plans = load_plans(base_dir)
    plan = _find_plan(plans, plan_id)
    if not plan:
        raise ValueError(f"plan not found: {plan_id}")
    dependencies = list(plan.get("dependencies", []) or [])
    if dependency_id not in dependencies:
        raise ValueError(f"plan dependency not present: {plan_id} -> {dependency_id}")
    plan["dependencies"] = [item for item in dependencies if item != dependency_id]
    plan.setdefault("dependency_decisions", []).append({
        "action": "remove",
        "dependency_id": dependency_id,
        "reason": reason,
        "decided_at": _now(),
    })
    validate_plan_dependencies(plans)
    plan["updated_at"] = _now()
    save_plans(base_dir, plans)
    return {"plan": plan, "dependency_id": dependency_id, "removed": True, "reason": reason}


def _legacy_task_refs(base: Path) -> Dict[str, Dict[str, str]]:
    ledger = _read(base / ".aiwf" / "state" / "tasks.json", {})
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

    plan_dir = base / ".aiwf" / "plans"
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
                status: str = "open", milestone_id: str = "", title: str = "",
                **_legacy) -> Dict[str, Any]:
    """V2 minimal Plan upsert: index + status + doc binding only.

    Legacy semantic kwargs (plan_kind, work_intent, allowed_write, etc.)
    are accepted but ignored — they live in Plan.md now.
    """
    if milestone_id:
        from .milestone_ops import attach_plan_to_milestone, milestone_exists
        if not milestone_exists(base_dir, milestone_id):
            raise ValueError(f"milestone not found: {milestone_id}")
    effective_goal = (goal_id or "").strip()
    try:
        from .goal_tree_ops import goal_exists, load_goal_tree
        tree = load_goal_tree(base_dir, auto_create=False)
        goals = tree.get("goals", []) or []
        if goals:  # registry is non-empty — require a real goal
            if not effective_goal:
                existing = [g.get('id', '') for g in goals[:8]]
                raise ValueError(
                    f"Plan requires a target goal. "
                    f"Existing goals: {', '.join(existing) if existing else '(none)'}. "
                    f"Use: aiwf plan create {plan_id} --goal-id <GOAL-ID>"
                )
            if not goal_exists(base_dir, effective_goal):
                existing = [g.get('id', '') for g in goals[:8]]
                raise ValueError(
                    f"Goal '{effective_goal}' does not exist in goals.json. "
                    f"Existing goals: {', '.join(existing) if existing else '(none)'}. "
                    f"Create it first: aiwf goal-tree init-root {effective_goal} --title '...'"
                )
    except ImportError:
        pass

    plans = load_plans(base_dir)
    plan = _find_plan(plans, plan_id)
    if not plan:
        plan = _empty_plan(plan_id, goal_id=goal_id, task_ids=task_ids or [],
                           status=status, milestone_id=milestone_id)
        plans["plans"].append(plan)
    else:
        # V2 minimal update: only id, goal, status, milestone, task_ids, title
        plan.setdefault("id", plan_id)
        plan.setdefault("plan_id", plan_id)
        plan.setdefault("goal_id", LEGACY_GOAL_ID)
        plan.setdefault("type", "plan")
        plan.setdefault("title_cache", "")
        plan.setdefault("summary_cache", "")
        plan.setdefault("doc_path", "")
        plan.setdefault("report_policy", "ask")
        plan.setdefault("task_ids", [])
        plan.setdefault("task_status", {})
        plan.setdefault("closed_task_ids", [])
        plan.setdefault("remaining_task_ids", [])
        if goal_id:
            plan["goal_id"] = goal_id
        if milestone_id:
            plan["milestone_id"] = milestone_id
        if title:
            plan["title"] = title
        if status:
            plan["status"] = status
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
    if title:
        plan["title"] = title
    if status == "active":
        plans["active_plan_id"] = plan_id
    validate_plan_dependencies(plans)
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
    blockers = plan_dependency_blockers(base_dir, plan_id)
    if blockers:
        raise ValueError("; ".join(blockers))
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
        state["phase"] = "planning"
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
        state["phase"] = "planning"
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
        and plan.get("task_status", {}).get(tid) != "rejected"
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

    evidence = _read(Path(base_dir) / ".aiwf" / "records" / "evidence.json", {"records": []})
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
    # V1: task close updates rollup only; plan close must be explicit
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
    if plan.get("status") == "closed":
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


def rebase_plan_registry(base_dir: str, fix: str = "legacy-goal-id") -> Dict[str, Any]:
    """Repair mechanical Plan registry drift without hand-editing plans.json."""
    if fix != "legacy-goal-id":
        raise ValueError(f"unknown plan rebase fix: {fix}")

    plans = load_plans(base_dir)
    ledger_path = Path(base_dir) / ".aiwf" / "state" / "tasks.json"
    ledger = _read(ledger_path, {"tasks": [], "execution_window": {"active_task_ids": []}})
    task_by_id = {
        str(t.get("id", "")): t
        for t in ledger.get("tasks", []) or []
        if isinstance(t, dict) and t.get("id")
    }
    changes: List[Dict[str, Any]] = []

    for plan in plans.get("plans", []) or []:
        if not isinstance(plan, dict):
            continue
        plan_id = str(plan.get("plan_id") or plan.get("id") or "")
        target_goal = str(plan.get("target_goal_id") or "")
        old_goal = str(plan.get("goal_id") or "")
        if target_goal and old_goal != target_goal:
            plan["goal_id"] = target_goal
            changes.append({
                "kind": "plan_goal_rebased",
                "plan_id": plan_id,
                "from": old_goal,
                "to": target_goal,
            })
        task_status = plan.setdefault("task_status", {})
        task_ids = list(dict.fromkeys(plan.get("task_ids", []) or []))
        for task_id in task_ids:
            task = task_by_id.get(str(task_id))
            if not task:
                continue
            if target_goal and (task.get("goal_id") != target_goal or task.get("parent_goal") != target_goal):
                before = task.get("goal_id") or task.get("parent_goal") or ""
                task["goal_id"] = target_goal
                task["parent_goal"] = target_goal
                changes.append({
                    "kind": "task_goal_rebased",
                    "task_id": task_id,
                    "plan_id": plan_id,
                    "from": before,
                    "to": target_goal,
                })
            task["plan_id"] = plan_id
            task["parent_plan"] = plan_id
            task_status[str(task_id)] = str(task.get("status", "unknown") or "unknown")
        closed = [tid for tid in task_ids if task_status.get(tid) == "closed"]
        remaining = [
            tid for tid in task_ids
            if task_status.get(tid) not in ("closed", "rejected")
        ]
        plan["closed_task_ids"] = closed
        plan["remaining_task_ids"] = remaining
        plan["updated_at"] = _now()

    save_plans(base_dir, plans)
    if ledger_path.exists():
        _write(ledger_path, ledger)
    return {"changed": bool(changes), "changes": changes, "plans": plans, "ledger": ledger}
