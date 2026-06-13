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
    plan_id = getattr(args, "plan_id_pos", "") or getattr(args, "plan_id", "")
    legacy_task_id = getattr(args, "task_id", "") or ""
    if not plan_id and not legacy_task_id:
        print("plan_id or task_id is required: aiwf plan create <PLAN-ID>", file=sys.stderr)
        raise SystemExit(1)
    kwargs = {}
    list_fields = {"interfaces", "constraints"}
    str_fields = ("goal_id", "context_id", "title", "kind", "plan_kind", "target_goal_id", "active_phase",
                  "child_goal_policy", "milestone_id", "work_intent")
    for k in str_fields:
        v = getattr(args, k, "") or ""
        if v:
            kwargs[k] = v
    for k in list_fields:
        v = getattr(args, k, []) or []
        if v:
            kwargs[k] = v
    task_ids = getattr(args, "task_ids", []) or []
    if task_ids:
        kwargs["task_ids"] = task_ids
    result = create_task_plan(str(Path.cwd()), task_id=legacy_task_id, plan_id=plan_id, **kwargs)
    effective_id = result.get("plan_id") or plan_id or legacy_task_id
    print(f"Plan: {effective_id} created={result['created']}")
    print(f"  Path: {_rel(result['path'])}")
    if result.get("target_goal_id"):
        print(f"  Target Goal: {result['target_goal_id']}")
    if result.get("plan_kind"):
        print(f"  Plan Kind: {result['plan_kind']}")
    if result.get("active_phase"):
        print(f"  Active Phase: {result['active_phase']}")
    if result.get("child_goal_policy"):
        print(f"  Child Goal Policy: {result['child_goal_policy']}")
    if result.get("work_intent"):
        print(f"  Work Intent: {result['work_intent']}")
    if result.get("interfaces"):
        print(f"  Interfaces: {', '.join(result['interfaces'])}")
    if result.get("constraints"):
        print(f"  Constraints: {', '.join(result['constraints'])}")
    print("  Note: .aiwf/artifacts/plans/ is AI working memory; JSON gates remain mechanical truth.")


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


def _cmd_plan_attach(args: argparse.Namespace) -> None:
    """Attach a task to an existing Plan."""
    from ..core.state.plan_ops import attach_task_to_plan
    plan_id = getattr(args, "plan_id", "") or ""
    task_id = getattr(args, "task_id", "") or ""
    if not plan_id or not task_id:
        print("Usage: aiwf plan attach <PLAN-ID> --task <TASK-ID>")
        raise SystemExit(1)
    result = attach_task_to_plan(str(Path.cwd()), plan_id, task_id)
    if result.get("attached"):
        print(f"Task {task_id} attached to Plan {plan_id}.")
    else:
        print(f"Failed: {result.get('reason', 'unknown')}")
        raise SystemExit(1)


def _cmd_plan_detach(args: argparse.Namespace) -> None:
    """Detach a task from a Plan."""
    from ..core.state.plan_ops import detach_task_from_plan
    plan_id = getattr(args, "plan_id", "") or ""
    task_id = getattr(args, "task_id", "") or ""
    if not plan_id or not task_id:
        print("Usage: aiwf plan detach <PLAN-ID> --task <TASK-ID>")
        raise SystemExit(1)
    result = detach_task_from_plan(str(Path.cwd()), plan_id, task_id)
    if result.get("detached"):
        print(f"Task {task_id} detached from Plan {plan_id}.")
    else:
        print(f"Failed: {result.get('reason', 'unknown')}")
        raise SystemExit(1)


def _cmd_plan_help(args: argparse.Namespace) -> None:
    print("AIWF Task Plan Artifacts")
    print()
    print("Available subcommands:")
    print("  aiwf plan create     — create .aiwf/artifacts/plans/<PLAN-ID>.md")
    print("  aiwf plan update     — update one plan section")
    print("  aiwf plan show       — print a task plan")
    print("  aiwf plan attach     — attach a task to a Plan")
    print("  aiwf plan detach     — detach a task from a Plan")
    print("  aiwf plan summarize  — show compact plan metadata")
    print("  aiwf plan list       — list task plans")
    print("  aiwf plan activate   — activate a plan (set active_plan_id)")
    print("  aiwf plan deactivate — deactivate the active plan")


def _cmd_plan_activate(args: argparse.Namespace) -> None:
    from ..core.state.plan_ops import set_active_plan
    try:
        result = set_active_plan(str(Path.cwd()), args.plan_id)
    except ValueError as e:
        print(f"Plan activate blocked: {e}", file=sys.stderr)
        raise SystemExit(1)
    p = result["plan"]
    print(f"Plan activated: {p.get('plan_id', p.get('id', ''))}")
    print(f"  Title: {p.get('title', '')}")
    print(f"  Plan Kind: {p.get('plan_kind', 'implementation')}")
    print(f"  Target Goal: {p.get('target_goal_id', '')}")
    print("  Phase set to planned. Next: aiwf task plan <ID> --plan <PLAN-ID> ...")


def _cmd_plan_deactivate(args: argparse.Namespace) -> None:
    from ..core.state.plan_ops import deactivate_plan
    result = deactivate_plan(str(Path.cwd()))
    prev = result.get("previous") or "(none)"
    print(f"Plan deactivated: was {prev}")
    print("  Phase set to discussing. All plans are now inactive.")
