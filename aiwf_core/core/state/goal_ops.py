"""Read active Goal machine state."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from ._common import _read


def get_active_goal(base_dir: str) -> Dict[str, Any]:
    goals = _read(Path(base_dir) / ".aiwf/state/goals.json") or {
        "goals": [],
        "active_goal_id": None,
    }
    active_id = goals.get("active_goal_id") or "GOAL-001"
    for goal in goals.get("goals", []) or []:
        if isinstance(goal, dict) and goal.get("id") == active_id:
            return goal
    return {"id": active_id, "title": active_id, "status": "open"}
