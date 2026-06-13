"""Impact Cone — read-only structural impact analysis (Stage 3.8).

Advisory only. Does not gate any operation. Computes affected nodes from
tree position and sibling relations, not from stored weights."""

from __future__ import annotations

from typing import Any, Dict, List

from .goal_tree_ops import get_goal, get_relations, list_goals, load_goal_tree


def compute_impact_cone(base_dir: str, goal_id: str) -> Dict[str, Any]:
    """Return the Impact Cone for a given Goal node.

    Includes: ancestors, children, sibling relations, attached Plans,
    related Milestones. Read-only advisory output.
    """
    goal = get_goal(base_dir, goal_id)
    if not goal:
        return {"found": False, "goal_id": goal_id}

    # Ancestors — walk up parent_goal_id chain
    ancestors = _walk_ancestors(base_dir, goal_id)

    # Children — direct child Goals
    children = [_summary(g) for g in _get_children(base_dir, goal)]

    # Sibling relations from the tree
    relations = get_relations(base_dir, goal_id)

    # Attached Plans
    plan_ids = goal.get("attached_plan_ids", []) or []
    try:
        from .plan_ops import get_plan
        plans = [p for pid in plan_ids if (p := get_plan(base_dir, pid))]
    except Exception:
        plans = []

    # Active Tasks under attached Plans
    active_tasks: List[str] = []
    try:
        from ..task_ledger import load_ledger
        ledger = load_ledger(base_dir)
        plan_id_set = set(plan_ids)
        for task in ledger.get("tasks", []) or []:
            if not isinstance(task, dict):
                continue
            tid = task.get("id", "")
            tpid = task.get("plan_id") or task.get("parent_plan") or ""
            if tpid in plan_id_set and task.get("status") == "active":
                active_tasks.append(tid)
    except Exception:
        pass

    # Related Milestones
    related_milestones: List[str] = []
    try:
        from .milestone_ops import list_milestones
        for m in list_milestones(base_dir):
            if isinstance(m, dict):
                covered = (m.get("covered_goal_ids") or []) + [m.get("goal_id") or ""]
                if goal_id in covered:
                    related_milestones.append(m.get("milestone_id") or m.get("id", ""))
    except Exception:
        pass

    # Notes
    notes = []
    if goal.get("root_type") == "temporary":
        notes.append("Temporary root — not yet grafted into main tree")
    if goal.get("status") == "archived":
        notes.append("Archived — this node is no longer active")

    return {
        "found": True,
        "goal_id": goal_id,
        "ancestors": ancestors,
        "children": children,
        "relations": relations,
        "attached_plans": [p.get("plan_id") or p.get("id", "") for p in plans],
        "active_tasks": active_tasks,
        "related_milestones": related_milestones,
        "notes": notes,
    }


def _walk_ancestors(base_dir: str, goal_id: str) -> List[str]:
    ancestors = []
    current = goal_id
    while True:
        g = get_goal(base_dir, current)
        parent = g.get("parent_goal_id") if g else None
        if not parent:
            break
        if parent in ancestors:
            break  # safety: cycle detected
        ancestors.append(parent)
        current = parent
    return ancestors


def _get_children(base_dir: str, goal: Dict[str, Any]) -> List[Dict[str, Any]]:
    result = []
    for cid in goal.get("child_goal_ids", []) or []:
        child = get_goal(base_dir, cid)
        if child:
            result.append(child)
    return result


def _summary(goal: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": goal.get("id", ""),
        "title": goal.get("title", ""),
        "status": goal.get("status", ""),
        "root_type": goal.get("root_type"),
    }
