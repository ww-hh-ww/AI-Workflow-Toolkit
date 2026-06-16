"""Task ledger command handlers."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys


def _cmd_task_plan(args: argparse.Namespace) -> None:
    from ..core.task_ledger import upsert_task

    def _split_csv(vals):
        if not vals: return None
        out = []
        for v in vals:
            for part in str(v).split(","):
                part = part.strip()
                if part:
                    out.append(part)
        return out or None

    task_id = args.task_id or getattr(args, "task_id_pos", "") or ""
    if not task_id:
        print("Task update blocked: task id required (use positional TASK-001 or --task-id TASK-001)", file=sys.stderr)
        raise SystemExit(1)
    try:
        result = upsert_task(
        str(Path.cwd()),
        task_id=task_id,
        title=args.title or "",
        status=args.status,
        dependencies=_split_csv(args.dependencies),
        allowed_write=_split_csv(args.allowed_write),
        parallel_safe=args.parallel_safe,
        notes=args.notes or None,
        parent_goal=args.parent_goal or "",
        parent_plan=args.parent_plan or "",
        goal_id=args.goal_id or "",
        plan_id=args.plan_id or "",
        milestone=args.milestone or "",
        milestone_id=getattr(args, "milestone_id", "") or "",
        )
    except ValueError as e:
        print(f"Task update blocked: {e}", file=sys.stderr)
        raise SystemExit(1)
    task = result["task"]
    print(f"Task recorded: {task['id']} status={task['status']}")
    print(f"  Dependencies: {len(task.get('dependencies', []) or [])}")
    if task.get("plan_id") or task.get("parent_plan"):
        print(f"  Scope: inherited from Plan {task.get('plan_id') or task.get('parent_plan')}")
    else:
        print("  Scope: no Plan linked")
    if args.allowed_write:
        print("  Note: task --allowed-write is deprecated and ignored; define scope on the Plan")
    print(f"  Parallel safe: {task.get('parallel_safe', False)}")
    if task.get("parent_goal"):
        print(f"  Parent goal: {task['parent_goal']}")
    else:
        print(f"  Parent goal: (none — tasks are execution units; link to a goal with --parent-goal)")
    if task.get("parent_plan"):
        print(f"  Parent plan: {task['parent_plan']}")
    if task.get("plan_id"):
        print(f"  Plan id: {task['plan_id']}")
    if task.get("milestone"):
        print(f"  Milestone: {task['milestone']}")
    if task.get("milestone_id"):
        print(f"  Milestone id: {task['milestone_id']}")
    # Granularity: warn if task smells like an action step
    for w in result.get("granularity_warnings", []) or []:
        print(f"  ! {w}")


def _cmd_task_activate(args: argparse.Namespace) -> None:
    from ..core.task_ledger import activate_task, task_start_confirmation_blockers
    if not getattr(args, "skip_start_gate", False):
        blockers = task_start_confirmation_blockers(str(Path.cwd()), args.task_id)
        if blockers:
            print(f"Task activation: {args.task_id} activated=False")
            print("  Start confirmation required:")
            for blocker in blockers[:5]:
                print(f"    - {blocker}")
            print("  Keep it short: scope, risk, verification, then confirm.")
            raise SystemExit(1)
    result = activate_task(str(Path.cwd()), args.task_id)
    print(f"Task activation: {args.task_id} activated={result['activated']}")
    if result["blockers"]:
        print(f"  Blockers ({len(result['blockers'])}):")
        for blocker in result["blockers"][:8]:
            print(f"    - {blocker}")
        raise SystemExit(1)
    else:
        print("  Execution window updated.")


def _cmd_task_confirm_start(args: argparse.Namespace) -> None:
    from ..core.task_ledger import record_task_start_confirmation
    result = record_task_start_confirmation(
        str(Path.cwd()),
        args.task_id,
        summary=args.summary or "",
        confirmed_by=args.confirmed_by or "user",
        skip=bool(args.skip),
        reason=args.reason or "",
    )
    if not result.get("recorded"):
        print(f"Task start confirmation blocked: {args.task_id}", file=sys.stderr)
        for blocker in result.get("blockers", [])[:5]:
            print(f"  - {blocker}", file=sys.stderr)
        raise SystemExit(1)
    task = result.get("task") or {}
    conf = task.get("start_confirmation", {}) or {}
    print(f"Task start confirmation recorded: {args.task_id} status={conf.get('status')}")


def _cmd_task_close(args: argparse.Namespace) -> None:
    from ..core.task_ledger import close_task
    result = close_task(str(Path.cwd()), args.task_id, note=args.note or "")
    print(f"Task close: {args.task_id} closed={result['closed']}")
    if result["blockers"]:
        for blocker in result["blockers"][:5]:
            print(f"  - {blocker}")
        raise SystemExit(1)

    # Goal progress: a task is an execution unit, not a goal unit.
    # Every close must show where we are in the larger goal.
    gp = result.get("goal_progress", {}) or {}
    parent_goal = gp.get("parent_goal", "")
    if parent_goal:
        done = "yes" if gp.get("goal_complete") else "no"
        print(f"  Task complete: yes")
        print(f"  Goal ({parent_goal}) complete: {done}")
        print(f"  Progress: {gp.get('closed_count', 0)}/{gp.get('total_count', 0)} tasks closed")
        remaining = gp.get("remaining_tasks", []) or []
        if remaining:
            print(f"  Next: {' '.join(remaining[:3])}")
    else:
        print(f"  Task complete: yes")
        print(f"  Goal complete: unknown (no parent goal set on this task)")
        print(f"  Hint: use --parent-goal GOAL-xxx when planning tasks")

    pp = result.get("plan_progress", {}) or {}
    if pp.get("reconciled"):
        plan = pp.get("plan", {}) or {}
        print(f"  Plan ({plan.get('plan_id', '')}) progress: {pp.get('closed_count', 0)}/{pp.get('total_count', 0)} tasks closed")
        remaining = pp.get("remaining_task_ids", []) or []
        if remaining:
            print(f"  Plan remaining: {' '.join(remaining[:3])}")
        mp = pp.get("milestone_progress", {}) or {}
        if mp.get("reconciled"):
            milestone = mp.get("milestone", {}) or {}
            rollup = milestone.get("evidence_rollup", {}) or {}
            print(f"  Milestone ({milestone.get('milestone_id', '')}) progress: {rollup.get('summary', '')}")

    # Granularity warnings
    for w in result.get("granularity_warnings", []) or []:
        print(f"  ! {w}")


def _cmd_task_suspend(args: argparse.Namespace) -> None:
    from ..core.task_ledger import suspend_task
    result = suspend_task(str(Path.cwd()), args.task_id, note=args.note or "")
    print(f"Task suspend: {args.task_id} suspended={result['suspended']}")
    if result["blockers"]:
        for blocker in result["blockers"][:5]:
            print(f"  - {blocker}")
        raise SystemExit(1)


def _cmd_task_status(args: argparse.Namespace) -> None:
    from ..core.task_ledger import ledger_summary
    summary = ledger_summary(str(Path.cwd()))
    counts = summary["counts"]
    print("Task ledger:")
    print(f"  Active: {len(summary['active_task_ids'])} ({', '.join(summary['active_task_ids']) or 'none'})")
    for status in ["candidate", "ready", "active", "blocked", "suspended", "closed", "rejected"]:
        if counts.get(status):
            print(f"  {status}: {counts[status]}")


def _cmd_task_help(args: argparse.Namespace) -> None:
    print("AIWF Task Ledger")
    print()
    print("Planner may keep multiple candidate/ready tasks.")
    print("Activation is the mechanical execution-window gate.")
    print()
    print("Available subcommands:")
    print("  aiwf task plan      — create/update a candidate or ready task")
    print("  aiwf task confirm-start — record brief user-visible start confirmation")
    print("  aiwf task activate  — mark one task active if gates pass")
    print("  aiwf task suspend   — suspend an active task with state snapshot")
    print("  aiwf task close     — mark a ledger task closed")
    print("  aiwf task status    — show ledger summary")
