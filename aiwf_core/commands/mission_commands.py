"""Mission CLI handlers — lightweight mission statement and boundaries.

Mission is the semantic container above the Goal Tree. It is NOT in the tree —
it owns the tree and its milestones. No hard gates read from mission directly;
mechanical constraint flows through milestones.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ..core.state._common import _read_json

def _mission_path(base_dir: str) -> Path:
    return Path(base_dir) / ".aiwf" / "state" / "mission.json"

def _read_mission(base_dir: str) -> dict:
    return _read_json(_mission_path(base_dir))

def _cmd_mission_show(args: argparse.Namespace) -> None:
    base_dir = str(Path.cwd())
    try:
        from ..core.index_ops import sync_index
        sync_index(base_dir)
    except Exception:
        pass
    mission = _read_mission(base_dir)
    if not mission:
        print("Mission: not initialized")
        print("  Create or edit .aiwf/mission.md.")
        return

    print(f"Mission: {mission.get('id', '?')}")
    print(f"  Status: {mission.get('status', 'draft')}")
    print(f"  Statement: {mission.get('statement', '(not set)')}")
    boundaries = mission.get("boundaries", []) or []
    print(f"  Boundaries ({len(boundaries)}):")
    for b in boundaries:
        print(f"    - {b}")
    milestone_ids = mission.get("milestone_ids", []) or []
    print(f"  Milestones: {', '.join(milestone_ids) if milestone_ids else '(none)'}")
    goal_roots = mission.get("goal_tree_root_ids", []) or []
    print(f"  Goal Tree Roots: {', '.join(goal_roots) if goal_roots else '(none)'}")
