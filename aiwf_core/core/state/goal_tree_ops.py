"""Goal Tree Registry operations."""

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

# ── structural operations: graft & prune ──────────────────────────────────

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
