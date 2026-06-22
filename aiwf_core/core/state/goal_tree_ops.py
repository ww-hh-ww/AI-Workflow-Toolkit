"""Goal Tree Registry — recursive functional skeleton for AIWF.

goals.json is a lightweight registry for the Rooted Functional Tree model.
It lives alongside (not replacing) the legacy singleton goal.json.

This module provides CRUD + validation. It does NOT integrate with task
activation, task close, or CLI — those come in later stages."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..state_schema import (
    LEGACY_GOAL_ID,
    VALID_GOAL_STATUSES,
    VALID_RELATION_TYPES,
    default_goals,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _goals_path(base_dir: str) -> Path:
    return Path(base_dir) / ".aiwf" / "state" / "goals.json"


def _read(path: Path, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else (default or {})
    except Exception:
        return default or {}


def _write(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ── goal entry ────────────────────────────────────────────────────────────

def _empty_goal(
    goal_id: str,
    title: str = "",
    parent_goal_id: Optional[str] = None,
    status: str = "open",
    intent: str = "",
    acceptance_boundary: str = "",
) -> Dict[str, Any]:
    now = _now()
    if status not in VALID_GOAL_STATUSES:
        raise ValueError(f"invalid goal status: {status}")
    return {
        "id": goal_id,
        "type": "goal",
        "title": title or goal_id,
        "title_cache": title or goal_id,
        "summary_cache": "",
        "doc_path": "",
        "doc_hash": "",
        "doc_updated_at": "",
        "report_policy": "ask",
        "parent_goal_id": parent_goal_id,
        "child_goal_ids": [],
        "children_order": [],
        "intent": intent,
        "acceptance_boundary": acceptance_boundary,
        "attached_plan_ids": [],
        "status": status,
        "visibility": "default",
        "advance_policy": "checkpoint",
        "checkpoint_level": "goal",
        "evidence_rollup": {},
        "open_gaps": [],
        "admission_trace": None,
        "created_at": now,
        "updated_at": now,
    }


# ── registry CRUD ─────────────────────────────────────────────────────────

def load_goal_tree(base_dir: str, auto_create: bool = True) -> Dict[str, Any]:
    """Load goals.json. If it doesn't exist and auto_create, seed with GOAL-001."""
    path = _goals_path(base_dir)
    data = _read(path, None)
    if data is None or not path.exists():
        data = default_goals()
        if auto_create:
            _write(path, data)
    data.setdefault("schema_version", 1)
    data.setdefault("active_goal_id", None)
    data.setdefault("roots", [])
    data.setdefault("goals", [])
    data.setdefault("relations", [])
    return data


def save_goal_tree(base_dir: str, tree: Dict[str, Any]) -> None:
    tree.setdefault("schema_version", 1)
    tree.setdefault("active_goal_id", None)
    tree.setdefault("roots", [])
    tree.setdefault("goals", [])
    tree.setdefault("relations", [])
    _write(_goals_path(base_dir), tree)


def _seed_from_legacy(base_dir: str) -> Dict[str, Any]:
    """Create initial goals.json with GOAL-001 from legacy goal.json."""
    data = default_goals()
    legacy_path = Path(base_dir) / ".aiwf" / "state" / "goal.json"
    if legacy_path.exists():
        try:
            legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
            active_goal = legacy.get("active_goal") or legacy.get("current_goal") or ""
            confirmed = legacy.get("confirmed", False)
            intent = legacy.get("original_intent") or legacy.get("current_goal") or ""
            status = "open" if confirmed else "discussion"
        except Exception:
            active_goal = ""
            intent = ""
            status = "discussion"
    else:
        active_goal = ""
        intent = ""
        status = "discussion"

    goal = _empty_goal(
        LEGACY_GOAL_ID,
        title=active_goal[:120] if active_goal else LEGACY_GOAL_ID,
        parent_goal_id=None,
        status=status,
        intent=intent,
    )
    data["goals"].append(goal)
    data["roots"].append(LEGACY_GOAL_ID)
    if status == "active":
        data["active_goal_id"] = LEGACY_GOAL_ID
    return data


# ── query ─────────────────────────────────────────────────────────────────

def _find_goal(tree: Dict[str, Any], goal_id: str) -> Optional[Dict[str, Any]]:
    for goal in tree.get("goals", []) or []:
        if isinstance(goal, dict) and (goal.get("id") == goal_id):
            return goal
    return None


def list_goals(base_dir: str) -> List[Dict[str, Any]]:
    return list(load_goal_tree(base_dir).get("goals", []) or [])


def get_goal(base_dir: str, goal_id: str) -> Dict[str, Any]:
    return _find_goal(load_goal_tree(base_dir), goal_id) or {}


def goal_exists(base_dir: str, goal_id: str) -> bool:
    return bool(get_goal(base_dir, goal_id))


def list_roots(base_dir: str) -> List[Dict[str, Any]]:
    tree = load_goal_tree(base_dir)
    root_ids = set(tree.get("roots", []) or [])
    return [g for g in tree.get("goals", []) or [] if isinstance(g, dict) and g.get("id") in root_ids]


def get_active_goal(base_dir: str) -> Dict[str, Any]:
    tree = load_goal_tree(base_dir)
    active_id = tree.get("active_goal_id")
    if active_id:
        g = _find_goal(tree, active_id)
        if g:
            return g
    return {}


# ── mutation ──────────────────────────────────────────────────────────────

def upsert_goal(
    base_dir: str,
    goal_id: str,
    title: str = "",
    parent_goal_id: Optional[str] = None,
    status: str = "",
    intent: str = "",
    acceptance_boundary: str = "",
) -> Dict[str, Any]:
    if status and status not in VALID_GOAL_STATUSES:
        raise ValueError(f"invalid goal status: {status}")

    tree = load_goal_tree(base_dir)
    goal = _find_goal(tree, goal_id)

    if not goal:
        goal = _empty_goal(
            goal_id,
            title=title,
            parent_goal_id=parent_goal_id,
            status=status or "open",
            intent=intent,
            acceptance_boundary=acceptance_boundary,
        )
        tree["goals"].append(goal)
        if goal_id not in tree["roots"]:
            tree["roots"].append(goal_id)
    else:
        goal.setdefault("child_goal_ids", [])
        goal.setdefault("children_order", [])
        goal.setdefault("attached_plan_ids", [])
        goal.setdefault("open_gaps", [])
        goal.setdefault("evidence_rollup", {})
        goal.setdefault("admission_trace", None)
        if title:
            goal["title"] = title
        if status:
            goal["status"] = status
        if intent:
            goal["intent"] = intent
        if acceptance_boundary:
            goal["acceptance_boundary"] = acceptance_boundary
        goal["updated_at"] = _now()

    if goal.get("status") == "open":
        tree["active_goal_id"] = goal_id
    elif tree.get("active_goal_id") == goal_id and goal.get("status") != "open":
        tree["active_goal_id"] = None

    save_goal_tree(base_dir, tree)
    return {"goal": goal, "tree": tree}


def add_child_goal(base_dir: str, parent_id: str, child_id: str,
                   title: str = "", intent: str = "") -> Dict[str, Any]:
    tree = load_goal_tree(base_dir)
    parent = _find_goal(tree, parent_id)
    if not parent:
        raise ValueError(f"parent goal not found: {parent_id}")

    child = _find_goal(tree, child_id)
    if not child:
        child = _empty_goal(
            child_id,
            title=title or child_id,
            parent_goal_id=parent_id,
            status="open",
            intent=intent,
        )
        tree["goals"].append(child)
        if child.get("parent_goal_id") and child["parent_goal_id"] != parent_id:
            raise ValueError(
                f"goal {child_id} already has parent {child['parent_goal_id']}; "
                f"use graft to change parent"
            )
        child["parent_goal_id"] = parent_id
        child["updated_at"] = _now()

    if child_id not in parent.setdefault("child_goal_ids", []):
        parent["child_goal_ids"].append(child_id)
    if child_id not in parent.setdefault("children_order", []):
        parent["children_order"].append(child_id)
    parent["updated_at"] = _now()

    _validate_no_cycles(tree)

    save_goal_tree(base_dir, tree)
    return {"parent": parent, "child": child, "tree": tree}


def init_root(base_dir: str, goal_id: str,
              title: str = "", intent: str = "") -> Dict[str, Any]:
    """Create a root Goal."""
    tree = load_goal_tree(base_dir)
    existing = _find_goal(tree, goal_id)
    if existing:
        existing["title"] = title or existing.get("title", goal_id)
        existing["intent"] = intent or existing.get("intent", "")
        existing["updated_at"] = _now()
        if goal_id not in tree["roots"]:
            tree["roots"].append(goal_id)
        save_goal_tree(base_dir, tree)
        return {"goal": existing, "tree": tree}

    goal = _empty_goal(
        goal_id,
        title=title or goal_id,
        parent_goal_id=None,
        status="open",
        intent=intent,
    )
    tree["goals"].append(goal)
    tree["roots"].append(goal_id)
    tree["active_goal_id"] = goal_id
    save_goal_tree(base_dir, tree)
    return {"goal": goal, "tree": tree}


# ── validation ────────────────────────────────────────────────────────────

def validate_goal_tree(base_dir: str) -> Dict[str, Any]:
    """Return {valid: bool, issues: [...]}. Does not mutate."""
    tree = load_goal_tree(base_dir, auto_create=False)
    issues = []
    goals = tree.get("goals", []) or []
    goal_ids = {g["id"] for g in goals if isinstance(g, dict) and g.get("id")}
    roots = set(tree.get("roots", []) or [])

    for g in goals:
        if not isinstance(g, dict):
            continue
        gid = g.get("id", "")

        # roots reference existing Goals
        if gid in roots:
            if g.get("parent_goal_id") is not None:
                issues.append(f"{gid}: root Goal has parent_goal_id set")
    
        # parent-child consistency
        parent = g.get("parent_goal_id")
        if parent is not None and parent not in goal_ids:
            issues.append(f"{gid}: parent_goal_id {parent} does not exist")
        if parent is not None:
            parent_goal = _find_goal(tree, parent)
            if parent_goal and gid not in (parent_goal.get("child_goal_ids", []) or []):
                issues.append(f"{gid}: parent_goal_id {parent} does not list this goal as child")

        # child IDs exist
        for cid in g.get("child_goal_ids", []) or []:
            if cid not in goal_ids:
                issues.append(f"{gid}: child_goal_id {cid} does not exist")
            else:
                child = _find_goal(tree, cid)
                if child and child.get("parent_goal_id") != gid:
                    issues.append(
                        f"{gid}: child_goal_id {cid} has parent_goal_id {child.get('parent_goal_id')}"
                    )

        # children_order only references child_ids
        child_set = set(g.get("child_goal_ids", []) or [])
        for cid in g.get("children_order", []) or []:
            if cid not in child_set:
                issues.append(f"{gid}: children_order references {cid} not in child_goal_ids")

        # missing children_order entries
        for cid in child_set:
            if cid not in set(g.get("children_order", []) or []):
                issues.append(f"{gid}: child_goal_id {cid} missing from children_order")

    # root set consistency
    for rid in roots:
        if rid not in goal_ids:
            issues.append(f"root {rid} is not a known goal")

    # no cycles
    cycle_issues = _detect_cycles(tree)
    issues.extend(cycle_issues)

    return {"valid": len(issues) == 0, "issues": issues}


def _validate_no_cycles(tree: Dict[str, Any]) -> None:
    issues = _detect_cycles(tree)
    if issues:
        raise ValueError("goal tree cycle detected: " + "; ".join(issues))


def _detect_cycles(tree: Dict[str, Any]) -> List[str]:
    """Simple DFS cycle detection on the goal tree."""
    issues = []
    goals = {g["id"]: g for g in tree.get("goals", []) or [] if isinstance(g, dict) and g.get("id")}
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {gid: WHITE for gid in goals}

    def dfs(gid, path):
        color[gid] = GRAY
        goal = goals.get(gid, {})
        for cid in goal.get("child_goal_ids", []) or []:
            if cid not in color:
                continue
            if color[cid] == GRAY:
                cycle = " → ".join(path + [cid])
                issues.append(f"cycle: {cycle}")
            elif color[cid] == WHITE:
                dfs(cid, path + [cid])
        color[gid] = BLACK

    for gid in goals:
        if color[gid] == WHITE:
            dfs(gid, [gid])
    return issues


# ── reconcile ──────────────────────────────────────────────────────────────

def reconcile_plan_to_goal(base_dir: str, plan: Dict[str, Any]) -> Dict[str, Any]:
    """Soft rollup: write plan progress into parent Goal's evidence_rollup.

    Read-only in effect — does NOT auto-close the Goal, does NOT block any gate.
    Called when a Plan becomes complete (all tasks closed)."""
    plan_id = str(plan.get("plan_id") or plan.get("id") or "")
    goal_id = str(plan.get("target_goal_id") or plan.get("goal_id") or "")
    if not plan_id or not goal_id:
        return {"reconciled": False, "reason": "missing plan_id or goal_id"}

    tree = load_goal_tree(base_dir, auto_create=False)
    goal = _find_goal(tree, goal_id)
    if not goal:
        return {"reconciled": False, "reason": f"goal not found: {goal_id}"}

    # Collect existing rollups
    rollups = goal.setdefault("evidence_rollup", {})
    plan_rollups = rollups.setdefault("plan_rollups", {})

    p_status = plan.get("status", "")
    er = plan.get("evidence_rollup", {}) or {}
    plan_rollups[plan_id] = {
        "plan_id": plan_id,
        "plan_kind": plan.get("plan_kind", "implementation"),
        "status": p_status,
        "closed_task_count": er.get("closed_count", 0),
        "total_task_count": er.get("total_count", 0),
        "key_files_changed": er.get("changed_files", []) or [],
        "updated_at": _now(),
    }

    # Aggregate summary
    total_closed = sum(r.get("closed_task_count", 0) for r in plan_rollups.values())
    total_tasks = sum(r.get("total_task_count", 0) for r in plan_rollups.values())
    complete_plans = sum(1 for r in plan_rollups.values() if r.get("status") in ("complete", "completed"))
    total_plans = len(plan_rollups)

    rollups["summary"] = f"{complete_plans}/{total_plans} plans complete, {total_closed}/{total_tasks} tasks closed"
    rollups["complete_plan_count"] = complete_plans
    rollups["total_plan_count"] = total_plans
    rollups["closed_task_count"] = total_closed
    rollups["total_task_count"] = total_tasks
    rollups["updated_at"] = _now()

    goal["updated_at"] = _now()

    # Also add plan to attached_plan_ids if not already there
    if plan_id not in goal.setdefault("attached_plan_ids", []):
        goal["attached_plan_ids"].append(plan_id)

    save_goal_tree(base_dir, tree)
    return {"reconciled": True, "goal_id": goal_id, "plan_id": plan_id}


# ── structural operations: graft & prune ──────────────────────────────────

def graft_branch(base_dir: str, source_id: str, target_parent_id: str,
                 reason: str = "",
                 interface_consumed: str = "",
                 capability_provided: str = "",
                 relation_to_parent: str = "",
                 affected_plan_ids: Optional[List[str]] = None,
                 whether_parent_meaning_changes: bool = False) -> Dict[str, Any]:
    """Graft a Temporary Root or branch into the main Goal Tree through an interface.

    Every graft records: interface consumed from parent, capability provided by
    source, relation to parent, affected plans, and whether the graft changes
    the parent's meaning. This is "graft through interface", not just reparenting.
    """
    tree = load_goal_tree(base_dir)
    source = _find_goal(tree, source_id)
    if not source:
        raise ValueError(f"source goal not found: {source_id}")

    target = _find_goal(tree, target_parent_id)
    if not target:
        raise ValueError(f"target parent goal not found: {target_parent_id}")

    if source_id == target_parent_id:
        raise ValueError("cannot graft a goal onto itself")

    affected = list(dict.fromkeys(affected_plan_ids or []))

    # Check for cycles before grafting
    old_parent = source.get("parent_goal_id")
    source["parent_goal_id"] = target_parent_id
    try:
        _validate_no_cycles(tree)
    except ValueError:
        source["parent_goal_id"] = old_parent
        raise ValueError(f"graft would create a cycle: {source_id} → {target_parent_id}")

    # Remove from roots if it was a root
    if source_id in tree.get("roots", []):
        tree["roots"] = [r for r in tree["roots"] if r != source_id]

    if old_parent:
        old_parent_goal = _find_goal(tree, old_parent)
        if old_parent_goal:
            old_parent_goal["child_goal_ids"] = [
                c for c in old_parent_goal.get("child_goal_ids", []) or [] if c != source_id
            ]
            old_parent_goal["children_order"] = [
                c for c in old_parent_goal.get("children_order", []) or [] if c != source_id
            ]
            old_parent_goal["updated_at"] = _now()

    # Update target's children
    if source_id not in target.setdefault("child_goal_ids", []):
        target["child_goal_ids"].append(source_id)
    if source_id not in target.setdefault("children_order", []):
        target["children_order"].append(source_id)

    # Record graft through interface — the contract of the graft
    graft_record = {
        "source_id": source_id,
        "target_parent_id": target_parent_id,
        "reason": reason,
        "interface_consumed": interface_consumed,
        "capability_provided": capability_provided,
        "relation_to_parent": relation_to_parent,
        "affected_plan_ids": affected,
        "whether_parent_meaning_changes": whether_parent_meaning_changes,
        "previous_parent": old_parent,
        "grafted_at": _now(),
    }
    source.setdefault("graft_history", []).append(graft_record)

    # Record interface trace on the source for later inspection
    if interface_consumed:
        source.setdefault("graft_interface", {})["consumed"] = interface_consumed
    if capability_provided:
        source.setdefault("graft_interface", {})["provided"] = capability_provided
    if relation_to_parent:
        source.setdefault("graft_interface", {})["relation_to_parent"] = relation_to_parent
    if whether_parent_meaning_changes:
        source.setdefault("graft_interface", {})["parent_meaning_changes"] = True

    source["visibility"] = "default"  # Entering main tree — becomes visible
    source["updated_at"] = _now()
    target["updated_at"] = _now()

    save_goal_tree(base_dir, tree)
    return {
        "grafted": True,
        "source": source,
        "target_parent": target,
        "graft_record": graft_record,
        "affected_plan_ids": affected,
    }


def prune_branch(base_dir: str, branch_id: str, reason: str = "") -> Dict[str, Any]:
    """Archive a failed, obsolete, or superseded branch.

    Archives by default — does NOT delete files or evidence.
    Returns info about abandoned Plans/Tasks for human review.
    """
    tree = load_goal_tree(base_dir)
    branch = _find_goal(tree, branch_id)
    if not branch:
        raise ValueError(f"branch not found: {branch_id}")

    # Cannot prune the active root
    if (branch_id in tree.get("roots", []) and
            tree.get("active_goal_id") == branch_id and
            branch.get("status") == "open"):
        raise ValueError(f"cannot prune the active root: {branch_id}")

    # Collect info about what's being abandoned
    abandoned_plans = list(branch.get("attached_plan_ids", []) or [])
    abandoned_children = list(branch.get("child_goal_ids", []) or [])

    # Remove from roots if present
    if branch_id in tree.get("roots", []):
        tree["roots"] = [r for r in tree["roots"] if r != branch_id]

    # Remove from parent's children
    parent_id = branch.get("parent_goal_id")
    if parent_id:
        parent = _find_goal(tree, parent_id)
        if parent:
            parent["child_goal_ids"] = [c for c in parent.get("child_goal_ids", []) or [] if c != branch_id]
            parent["children_order"] = [c for c in parent.get("children_order", []) or [] if c != branch_id]
            parent["updated_at"] = _now()

    # Archive, don't delete
    branch["status"] = "archived"
    branch["visibility"] = "archived_only"
    branch["prune_reason"] = reason
    branch["pruned_at"] = _now()
    branch["abandoned_plans"] = abandoned_plans
    branch["abandoned_child_goals"] = abandoned_children
    branch["updated_at"] = _now()

    # Clear active_goal_id if this was it
    if tree.get("active_goal_id") == branch_id:
        tree["active_goal_id"] = None

    save_goal_tree(base_dir, tree)
    return {
        "pruned": True,
        "branch": branch,
        "abandoned_plans": abandoned_plans,
        "abandoned_child_goals": abandoned_children,
    }


# ── sibling relations ──────────────────────────────────────────────────────

def add_relation(base_dir: str, source_id: str, target_id: str,
                 rel_type: str = "depends_on", reason: str = "",
                 allow_cross: bool = False) -> Dict[str, Any]:
    """Add a sibling relation between two goals in the tree.

    By default, source and target must share the same parent (sibling relation).
    Cross-parent relations require allow_cross=True to prevent accidental graph
    expansion into a full cross-tree graph.
    """
    if rel_type not in VALID_RELATION_TYPES:
        raise ValueError(f"invalid relation type: {rel_type}")
    tree = load_goal_tree(base_dir)
    source = _find_goal(tree, source_id)
    if not source:
        raise ValueError(f"source goal not found: {source_id}")
    target = _find_goal(tree, target_id)
    if not target:
        raise ValueError(f"target goal not found: {target_id}")
    if source_id == target_id:
        raise ValueError("cannot relate a goal to itself")

    # Sibling constraint: same parent required unless cross is allowed
    if not allow_cross:
        source_parent = source.get("parent_goal_id")
        target_parent = target.get("parent_goal_id")
        if source_parent != target_parent:
            raise ValueError(
                f"sibling relation requires same parent; "
                f"source parent={source_parent or '(none — root)'}, "
                f"target parent={target_parent or '(none — root)'}. "
                f"Use --cross for cross-parent relations."
            )

    # Remove any existing relation between these two
    relations = tree.setdefault("relations", [])
    relations[:] = [r for r in relations
                    if not (r.get("source_id") == source_id and r.get("target_id") == target_id)]

    rel = {
        "source_id": source_id,
        "target_id": target_id,
        "type": rel_type,
        "reason": reason,
        "cross_parent": allow_cross,
        "created_at": _now(),
    }
    relations.append(rel)
    save_goal_tree(base_dir, tree)
    return {"added": True, "relation": rel}


def remove_relation(base_dir: str, source_id: str, target_id: str) -> Dict[str, Any]:
    """Remove a sibling relation."""
    tree = load_goal_tree(base_dir)
    relations = tree.setdefault("relations", [])
    before = len(relations)
    relations[:] = [r for r in relations
                    if not (r.get("source_id") == source_id and r.get("target_id") == target_id)]
    save_goal_tree(base_dir, tree)
    return {"removed": len(relations) < before}


def get_relations(base_dir: str, node_id: str) -> List[Dict[str, Any]]:
    """Get all relations involving a node (as source or target)."""
    tree = load_goal_tree(base_dir)
    return [r for r in tree.get("relations", []) or []
            if r.get("source_id") == node_id or r.get("target_id") == node_id]
