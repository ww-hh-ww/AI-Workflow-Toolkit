"""Mission CLI handlers — lightweight mission statement and boundaries.

Mission is the semantic container above the Goal Tree. It is NOT in the tree —
it owns the tree and its milestones. No hard gates read from mission directly;
mechanical constraint flows through milestones.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mission_path(base_dir: str) -> Path:
    return Path(base_dir) / ".aiwf" / "state" / "mission.json"


def _read_mission(base_dir: str) -> dict:
    path = _mission_path(base_dir)
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        return {}


def _write_mission(base_dir: str, data: dict) -> None:
    path = _mission_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _cmd_mission_help(args: argparse.Namespace) -> None:
    print("AIWF Mission — project-level 'why' and boundaries")
    print()
    print("Mission sits above the Goal Tree. It declares what the project is for")
    print("and what it explicitly does NOT do. Mechanical gates read from Mission")
    print("indirectly — through the Milestones it owns.")
    print()
    print("Available subcommands:")
    print("  aiwf mission show               — show current mission")
    print("  aiwf mission update             — update mission statement or boundaries")
    print()


def _cmd_mission_show(args: argparse.Namespace) -> None:
    mission = _read_mission(str(Path.cwd()))
    if not mission:
        print("Mission: not initialized")
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


def _cmd_mission_update(args: argparse.Namespace) -> None:
    base_dir = str(Path.cwd())
    mission = _read_mission(base_dir)

    if not mission:
        from ..core.state_schema import default_mission
        mission = default_mission()
        mission["created_at"] = _now()

    if args.statement is not None:
        mission["statement"] = args.statement
    if args.boundary is not None:
        # Use a list from repeated --boundary args; add to existing, don't replace
        mission.setdefault("boundaries", [])
        for b in args.boundary:
            if b not in mission["boundaries"]:
                mission["boundaries"].append(b)
    if args.status:
        from ..core.state_schema import VALID_MISSION_STATUSES
        if args.status not in VALID_MISSION_STATUSES:
            print(f"Error: invalid mission status '{args.status}'. Valid: {', '.join(sorted(VALID_MISSION_STATUSES))}", file=sys.stderr)
            raise SystemExit(1)
        mission["status"] = args.status
    if getattr(args, "add_milestone", ""):
        mission.setdefault("milestone_ids", [])
        mid = args.add_milestone
        if mid not in mission["milestone_ids"]:
            mission["milestone_ids"].append(mid)
    if getattr(args, "add_goal_root", ""):
        mission.setdefault("goal_tree_root_ids", [])
        gid = args.add_goal_root
        if gid not in mission["goal_tree_root_ids"]:
            mission["goal_tree_root_ids"].append(gid)

    mission["updated_at"] = _now()
    _write_mission(base_dir, mission)

    print(f"Mission updated: {mission.get('id', '?')}")
    if args.statement is not None:
        print(f"  Statement: {args.statement[:120]}")
    if args.boundary is not None:
        print(f"  Boundaries: {len(mission.get('boundaries', []))} items")
    if args.status:
        print(f"  Status: {args.status}")
