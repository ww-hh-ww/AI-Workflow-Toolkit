"""Milestone command handlers."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys


def _cmd_milestone_create(args: argparse.Namespace) -> None:
    from ..core.state.milestone_ops import upsert_milestone
    try:
        result = upsert_milestone(
            str(Path.cwd()),
            args.milestone_id,
            goal_id=args.goal_id or "",
            title=args.title or "",
            status=args.status or "pending",
            intent=args.intent or "",
            plan_ids=args.plan_ids or None,
            task_ids=args.task_ids or None,
            covered_goal_ids=getattr(args, "covered_goal_ids", None) or None,
            mission_id=getattr(args, "mission_id", "") or "",
            advance_policy=args.advance_policy or "",
            checkpoint_level=args.checkpoint_level or "",
        )
    except ValueError as e:
        print(f"Milestone create blocked: {e}", file=sys.stderr)
        raise SystemExit(1)
    m = result["milestone"]
    print(f"Milestone: {m['milestone_id']} status={m['status']}")
    print(f"  Goal: {m.get('goal_id', '')}")
    print(f"  Plans: {len(m.get('plan_ids', []) or [])}")
    print(f"  Tasks: {len(m.get('task_ids', []) or [])}")


def _cmd_milestone_list(args: argparse.Namespace) -> None:
    from ..core.state.milestone_ops import list_milestones
    milestones = list_milestones(str(Path.cwd()))
    if not milestones:
        print("Milestones: none")
        return
    print(f"Milestones: {len(milestones)}")
    for m in milestones:
        print(
            f"  {m.get('milestone_id') or m.get('id')} "
            f"[{m.get('status', 'pending')}] "
            f"goal={m.get('goal_id', '')} "
            f"plans={len(m.get('plan_ids', []) or [])} "
            f"{m.get('title', '')}"
        )


def _cmd_milestone_show(args: argparse.Namespace) -> None:
    from ..core.state.milestone_ops import get_milestone
    m = get_milestone(str(Path.cwd()), args.milestone_id)
    if not m:
        print(f"Milestone not found: {args.milestone_id}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Milestone: {m.get('milestone_id') or m.get('id')}")
    print(f"  Title: {m.get('title', '')}")
    print(f"  Status: {m.get('status', '')}")
    print(f"  Goal: {m.get('goal_id', '')}")
    print(f"  Intent: {m.get('intent', '') or '(none)'}")
    print(f"  Plans: {', '.join(m.get('plan_ids', []) or []) or '(none)'}")
    print(f"  Tasks: {', '.join(m.get('task_ids', []) or []) or '(none)'}")
    rollup = m.get("evidence_rollup", {}) or {}
    print(f"  Rollup: {rollup.get('summary', '') or '(none)'}")
    synthesis = m.get("stage_synthesis", {}) or {}
    print(f"  Stage Synthesis: {synthesis.get('status', 'pending')} verdict={synthesis.get('verdict', 'pending')}")
    if synthesis.get("summary"):
        print(f"  Summary: {synthesis['summary']}")
    if synthesis.get("coherence_check"):
        print(f"  Coherence: {synthesis['coherence_check']}")
    if synthesis.get("interface_stability"):
        print(f"  Interface Stability: {synthesis['interface_stability']}")


def _cmd_milestone_update(args: argparse.Namespace) -> None:
    from ..core.state.milestone_ops import upsert_milestone
    try:
        result = upsert_milestone(
            str(Path.cwd()),
            args.milestone_id,
            goal_id=args.goal_id or "",
            title=args.title or "",
            status=args.status or "",
            intent=args.intent or "",
            plan_ids=args.plan_ids or None,
            task_ids=args.task_ids or None,
            advance_policy=args.advance_policy or "",
            checkpoint_level=args.checkpoint_level or "",
        )
    except ValueError as e:
        print(f"Milestone update blocked: {e}", file=sys.stderr)
        raise SystemExit(1)
    m = result["milestone"]
    print(f"Milestone updated: {m['milestone_id']} status={m['status']}")


def _cmd_milestone_assess(args: argparse.Namespace) -> None:
    from ..core.state.milestone_ops import record_milestone_assessment
    try:
        result = record_milestone_assessment(
            str(Path.cwd()),
            args.milestone_id,
            verdict=args.verdict,
            summary=args.summary,
            evidence_ids=args.evidence_ids or None,
            coherence_check=args.coherence_check or "",
            open_gaps=args.open_gaps or None,
            residual_risks=args.residual_risks or None,
            next_recommendation=args.next_recommendation or "",
        )
    except ValueError as e:
        print(f"Milestone assessment blocked: {e}", file=sys.stderr)
        raise SystemExit(1)
    if not result.get("recorded"):
        print(f"Milestone assessment blocked: {result.get('reason', 'unknown')}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Milestone assessment recorded: {args.milestone_id} verdict={args.verdict}")


def _cmd_milestone_close(args: argparse.Namespace) -> None:
    from ..core.state.milestone_ops import close_milestone
    result = close_milestone(str(Path.cwd()), args.milestone_id)
    print(f"Milestone close: {args.milestone_id} closed={result['closed']}")
    for blocker in result.get("blockers", []) or []:
        print(f"  - {blocker}")
    if result.get("blockers"):
        raise SystemExit(1)


def _cmd_milestone_help(args: argparse.Namespace) -> None:
    print("AIWF Milestone Optional Node")
    print()
    print("Milestones are optional stage nodes for long or high-risk work.")
    print("They do not replace Plans and do not burden ordinary L0/L1 tasks.")
    print()
    print("Available subcommands:")
    print("  aiwf milestone create MS-001 --goal-id GOAL-001 --title '...'")
    print("  aiwf milestone list")
    print("  aiwf milestone show MS-001")
    print("  aiwf milestone update MS-001 --status active")
    print("  aiwf milestone assess MS-001 --verdict PASS --summary '...'")
    print("  aiwf milestone close MS-001")
