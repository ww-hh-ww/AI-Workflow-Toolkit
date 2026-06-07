"""Task plan artifact command handlers."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys


def _rel(path: str) -> str:
    try:
        return str(Path(path).relative_to(Path.cwd()))
    except Exception:
        return path


def _cmd_plan_create(args: argparse.Namespace) -> None:
    from ..core.task_plan import create_task_plan
    result = create_task_plan(str(Path.cwd()), args.task_id, context_id=args.context_id or "", title=args.title or "")
    print(f"Task plan: {args.task_id} created={result['created']}")
    print(f"  Path: {_rel(result['path'])}")
    print("  Note: plan.md is human-readable; AIWF JSON remains mechanical truth.")


def _cmd_plan_update(args: argparse.Namespace) -> None:
    from ..core.task_plan import update_task_plan_section
    try:
        result = update_task_plan_section(str(Path.cwd()), args.task_id, args.section, args.content)
    except ValueError as e:
        print(f"Plan update blocked: {e}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Task plan updated: {args.task_id}")
    print(f"  Section: {result['section']}")
    print(f"  Path: {_rel(result['path'])}")


def _cmd_plan_show(args: argparse.Namespace) -> None:
    from ..core.task_plan import load_task_plan
    text = load_task_plan(str(Path.cwd()), args.task_id)
    if not text:
        print(f"Task plan not found: {args.task_id}")
        raise SystemExit(1)
    print(text)


def _cmd_plan_summarize(args: argparse.Namespace) -> None:
    from ..core.task_plan import summarize_task_plan
    summary = summarize_task_plan(str(Path.cwd()), args.task_id)
    if not summary.get("exists"):
        print(f"Task plan not found: {args.task_id}")
        raise SystemExit(1)
    print(f"Task plan summary: {args.task_id}")
    print(f"  Path: {_rel(summary['path'])}")
    print(f"  Lines: {summary['line_count']}")
    print(f"  Checklist: {summary['checklist_checked']}/{summary['checklist_total']}")


def _cmd_plan_list(args: argparse.Namespace) -> None:
    from ..core.task_plan import list_task_plans
    plans = list_task_plans(str(Path.cwd()))
    if not plans:
        print("Task plans: none")
        return
    print(f"Task plans: {len(plans)}")
    for plan in plans:
        print(f"  {plan['task_id']} | {_rel(plan['path'])}")


def _cmd_plan_help(args: argparse.Namespace) -> None:
    print("AIWF Task Plan Artifacts")
    print()
    print("Available subcommands:")
    print("  aiwf plan create     — create .aiwf/plans/TASK.md")
    print("  aiwf plan update     — update one plan section")
    print("  aiwf plan show       — print a task plan")
    print("  aiwf plan summarize  — show compact plan metadata")
    print("  aiwf plan list       — list task plans")
