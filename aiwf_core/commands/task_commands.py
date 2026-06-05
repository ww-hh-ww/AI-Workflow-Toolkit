"""Task ledger command handlers."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys


def _cmd_task_plan(args: argparse.Namespace) -> None:
    from ..core.task_ledger import upsert_task
    try:
        result = upsert_task(
        str(Path.cwd()),
        task_id=args.task_id,
        title=args.title or "",
        status=args.status,
        dependencies=args.dependencies or None,
        allowed_write=args.allowed_write or None,
        parallel_safe=args.parallel_safe,
        notes=args.notes or None,
        )
    except ValueError as e:
        print(f"Task update blocked: {e}", file=sys.stderr)
        raise SystemExit(1)
    task = result["task"]
    print(f"Task recorded: {task['id']} status={task['status']}")
    print(f"  Dependencies: {len(task.get('dependencies', []) or [])}")
    print(f"  Allowed write: {len(task.get('allowed_write', []) or [])}")
    print(f"  Parallel safe: {task.get('parallel_safe', False)}")


def _cmd_task_activate(args: argparse.Namespace) -> None:
    from ..core.task_ledger import activate_task
    result = activate_task(str(Path.cwd()), args.task_id)
    print(f"Task activation: {args.task_id} activated={result['activated']}")
    if result["blockers"]:
        print(f"  Blockers ({len(result['blockers'])}):")
        for blocker in result["blockers"][:8]:
            print(f"    - {blocker}")
    else:
        print("  Execution window updated.")


def _cmd_task_close(args: argparse.Namespace) -> None:
    from ..core.task_ledger import close_task
    result = close_task(str(Path.cwd()), args.task_id, note=args.note or "")
    print(f"Task close: {args.task_id} closed={result['closed']}")
    if result["blockers"]:
        for blocker in result["blockers"][:5]:
            print(f"  - {blocker}")


def _cmd_task_suspend(args: argparse.Namespace) -> None:
    from ..core.task_ledger import suspend_task
    result = suspend_task(str(Path.cwd()), args.task_id, note=args.note or "")
    print(f"Task suspend: {args.task_id} suspended={result['suspended']}")
    if result["blockers"]:
        for blocker in result["blockers"][:5]:
            print(f"  - {blocker}")


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
    print("  aiwf task activate  — mark one task active if gates pass")
    print("  aiwf task suspend   — suspend an active task with state snapshot")
    print("  aiwf task close     — mark a ledger task closed")
    print("  aiwf task status    — show ledger summary")
