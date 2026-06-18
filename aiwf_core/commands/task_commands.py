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

    def _g(key, default=""):
        return getattr(args, key, default)

    def _gl(key, default=None):
        return getattr(args, key, default)

    task_id = _g("task_id") or _g("task_id_pos") or ""
    if not task_id:
        print("Task update blocked: task id required (use positional TASK-001 or --task-id TASK-001)", file=sys.stderr)
        raise SystemExit(1)
    try:
        result = upsert_task(
        str(Path.cwd()),
        task_id=task_id,
        title=_g("title"),
        status=_g("status", "candidate"),
        dependencies=_split_csv(_gl("dependencies")),
        allowed_write=_split_csv(_gl("allowed_write")),
        parallel_safe=bool(_g("parallel_safe")),
        notes=_gl("notes"),
        parent_goal=_g("parent_goal") or _g("goal_id"),
        parent_plan=_g("parent_plan") or _g("plan_id"),
        goal_id=_g("goal_id"),
        plan_id=_g("plan_id"),
        milestone=_g("milestone"),
        milestone_id=_g("milestone_id"),
        kind=_g("kind"),
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
    if _gl("allowed_write"):
        print("  Note: task --allowed-write is deprecated and ignored; define scope on the Plan")
    print(f"  Parallel safe: {task.get('parallel_safe', False)}")
    # V1: Task.md is the execution contract — always created on task create
    _write_task_narrative(Path.cwd(), task)
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
    from ..core.task_ledger import activate_task
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
    task_id = getattr(args, "task_id", "") or getattr(args, "task_id_pos", "") or ""
    result = close_task(str(Path.cwd()), task_id, note=args.note or "")
    print(f"Task close: {task_id or result.get('task', {}).get('id', '?')} closed={result['closed']}")
    if result["blockers"]:
        for blocker in result["blockers"][:5]:
            print(f"  - {blocker}")
        raise SystemExit(1)

    # Goal progress: a task is an execution unit, not a goal unit.
    # Every close must show where we are in the larger goal.
    gp = result.get("goal_progress", {}) or {}
    task_snapshot = result.get("task") or {}
    verification_status = task_snapshot.get("verification_status", "")
    if verification_status == "unverified":
        gaps = task_snapshot.get("verification_gaps", []) or []
        print("  Verification: unverified")
        if gaps:
            print(f"  Verification gaps: {', '.join(str(g) for g in gaps[:3])}")
        print("  Note: task code may be complete, but runtime/system validation remains open.")
    elif verification_status:
        print(f"  Verification: {verification_status}")
    task_kind = task_snapshot.get("kind", "")
    task_ms_id = task_snapshot.get("milestone_id", "")
    if task_kind == "milestone_verification" and task_ms_id:
        print(f"  Task complete: yes")
        print(f"  Milestone: {task_ms_id} — verification complete")
        print(f"  Next: aiwf milestone close {task_ms_id}")
    elif gp.get("parent_goal"):
        done = "yes" if gp.get("goal_complete") else "no"
        print(f"  Task complete: yes")
        print(f"  Goal ({gp['parent_goal']}) complete: {done}")
        print(f"  Progress: {gp.get('closed_count', 0)}/{gp.get('total_count', 0)} tasks closed")
        remaining = gp.get("remaining_tasks", []) or []
        if remaining:
            print(f"  Remaining tasks: {' '.join(remaining[:3])}")
        print(f"  Next: aiwf-planner")
    else:
        print(f"  Task complete: yes")
        print(f"  Goal complete: unknown (no parent goal set on this task)")
        print(f"  Hint: use --parent-goal GOAL-xxx when planning tasks")
        print(f"  Next: aiwf-planner")

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
    result = suspend_task(str(Path.cwd()), note=args.note or "")
    task_id = result.get("task", {}).get("id", "?") if result.get("task") else "?"
    print(f"Task suspend: {task_id} suspended={result['suspended']}")
    if result["blockers"]:
        for blocker in result["blockers"][:5]:
            print(f"  - {blocker}")
        raise SystemExit(1)


def _cmd_task_force_close(args: argparse.Namespace) -> None:
    from ..core.task_ledger import force_close_task
    reason = getattr(args, "reason", "") or ""
    result = force_close_task(str(Path.cwd()), reason=reason)
    task = result.get("task") or {}
    task_id = task.get("id", "unknown")
    print(f"Task force-close: {task_id} closed={result['closed']}")
    if result["blockers"]:
        for blocker in result["blockers"][:5]:
            print(f"  - {blocker}")
        raise SystemExit(1)
    closure = task.get("closure", {}) or {}
    if closure.get("mode") == "human_force":
        unsatisfied = closure.get("unsatisfied_checks", []) or []
        print(f"  Close mode: human_force")
        if closure.get("reason"):
            print(f"  Reason: {closure['reason']}")
        if unsatisfied:
            print(f"  Unsatisfied checks ({len(unsatisfied)}):")
            for check in unsatisfied:
                print(f"    - {check}")
        print("  WARNING: all gates were bypassed. This is a human emergency override.")


def _cmd_task_rename(args: argparse.Namespace) -> None:
    from ..core.task_ledger import load_ledger, save_ledger
    task_id = getattr(args, "task_id", "")
    title = getattr(args, "title", "") or ""
    ledger = load_ledger(str(Path.cwd()))
    for t in ledger.get("tasks", []):
        if t.get("id") == task_id:
            t["title"] = title
            t["title_cache"] = title
            save_ledger(str(Path.cwd()), ledger)
            print(f"Task renamed: {task_id} -> {title}")
            return
    print(f"Task not found: {task_id}", file=sys.stderr)
    raise SystemExit(1)


def _cmd_task_cancel(args: argparse.Namespace) -> None:
    from ..core.task_ledger import load_ledger, save_ledger
    from datetime import datetime, timezone
    task_id = getattr(args, "task_id", "")
    reason = getattr(args, "reason", "") or ""
    replaced_by = getattr(args, "replaced_by", "") or ""
    ledger = load_ledger(str(Path.cwd()))
    for t in ledger.get("tasks", []):
        if t.get("id") == task_id:
            if t.get("status") == "active":
                print(f"Cannot cancel active task: {task_id}. Use force-close instead.", file=sys.stderr)
                raise SystemExit(1)
            t["status"] = "cancelled"
            t["cancel_reason"] = reason
            if replaced_by:
                t["replaced_by"] = replaced_by
            t["updated_at"] = datetime.now(timezone.utc).isoformat()
            save_ledger(str(Path.cwd()), ledger)

            # Sync plan index: remove from remaining_task_ids, update rollup
            plan_id = t.get("plan_id") or t.get("parent_plan") or ""
            if plan_id:
                try:
                    from ..core.state.plan_ops import load_plans, save_plans
                    plans = load_plans(str(Path.cwd()))
                    for p in plans.get("plans", []) or []:
                        pid = p.get("plan_id") or p.get("id") or ""
                        if pid == plan_id:
                            p.setdefault("task_status", {})[task_id] = "cancelled"
                            rem = p.get("remaining_task_ids", []) or []
                            if task_id in rem:
                                rem.remove(task_id)
                                p["remaining_task_ids"] = rem
                            # Recompute rollup
                            ts = p.get("task_status", {}) or {}
                            closed = sum(1 for v in ts.values() if v == "closed")
                            total = len(ts)
                            p["evidence_rollup"] = {
                                "summary": f"{closed}/{total} tasks closed under this plan.",
                                "closed_task_count": closed,
                                "total_task_count": total,
                            }
                            p["updated_at"] = datetime.now(timezone.utc).isoformat()
                            save_plans(str(Path.cwd()), plans)
                            break
                except Exception:
                    pass

            print(f"Task cancelled: {task_id}")
            if reason:
                print(f"  Reason: {reason}")
            if replaced_by:
                print(f"  Replaced by: {replaced_by}")
            return
    print(f"Task not found: {task_id}", file=sys.stderr)
    raise SystemExit(1)


def _cmd_task_void(args: argparse.Namespace) -> None:
    from ..core.task_ledger import void_task
    result = void_task(
        str(Path.cwd()),
        args.task_id,
        reason=args.reason or "",
        superseded_by=getattr(args, "superseded_by", "") or "",
    )
    print(f"Task void: {args.task_id} voided={result['voided']}")
    if result["blockers"]:
        for blocker in result["blockers"][:5]:
            print(f"  - {blocker}")
        raise SystemExit(1)
    task = result.get("task") or {}
    print(f"  Reason: {task.get('state_reason', '')}")
    if task.get("superseded_by"):
        print(f"  Superseded by: {task['superseded_by']}")


def _cmd_task_show(args: argparse.Namespace) -> None:
    from ..core.task_ledger import load_ledger
    task_id = getattr(args, "task_id", "") or ""
    ledger = load_ledger(str(Path.cwd()))
    if not task_id:
        # Default to active task
        state_path = Path.cwd() / ".aiwf" / "state" / "state.json"
        import json
        if state_path.exists():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
                task_id = state.get("active_task_id", "")
            except Exception:
                pass
    if not task_id:
        print("No task ID provided and no active task.", file=sys.stderr)
        raise SystemExit(1)
    task = None
    for t in ledger.get("tasks", []):
        if t.get("id") == task_id:
            task = t
            break
    if not task:
        print(f"Task not found: {task_id}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Task: {task.get('id')}")
    print(f"  Title: {task.get('title', '')}")
    print(f"  Status: {task.get('status', '')}")
    print(f"  Kind: {task.get('kind', '') or '(none)'}")
    print(f"  Goal: {task.get('goal_id', '') or task.get('parent_goal', '') or '(none)'}")
    print(f"  Plan: {task.get('plan_id', '') or task.get('parent_plan', '') or '(none)'}")
    print(f"  Milestone: {task.get('milestone_id', '') or task.get('milestone', '') or '(none)'}")
    print(f"  Dependencies: {', '.join(task.get('dependencies', []) or []) or '(none)'}")
    print(f"  Parallel safe: {task.get('parallel_safe', False)}")
    reqs = task.get("requirements", {}) or {}
    print(f"  Requirements: executor={reqs.get('executor_required', True)}, tester={reqs.get('tester_required', True)}, reviewer={reqs.get('reviewer_required', True)}")
    if task.get("close_mode"):
        print(f"  Close mode: {task['close_mode']}")
        print(f"  Closed by: {task.get('closed_by', '')}")
    if task.get("doc_path"):
        print(f"  Doc: {task['doc_path']}")
    if task.get("notes"):
        for note in task["notes"][-3:]:
            print(f"  Note: {note}")


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
    print("AIWF Task — node CRUD and runtime")
    print()
    print("Node:")
    print("  aiwf task create TASK-001 --title '...'      — create a task")
    print("  aiwf task show [TASK-ID]                     — show task (defaults to active)")
    print("  aiwf task list                               — list all tasks")
    print("  aiwf task rename TASK-001 --title '...'      — rename a task")
    print("  aiwf task cancel TASK-001 --reason '...'     — cancel a non-active task")
    print()
    print("Runtime:")
    print("  aiwf task activate TASK-001                  — activate for execution")
    print("  aiwf task close                              — close the active task")
    print("  aiwf task suspend                            — suspend the active task")
    print("  aiwf task force-close [--reason '...']       — HUMAN ONLY emergency close")


def _write_task_narrative(cwd: Path, task: dict) -> None:
    from ..core.index_ops import (
        generate_narrative_doc_path, write_narrative_doc,
    )
    from ..core.task_ledger import load_ledger, save_ledger

    doc_path_str = generate_narrative_doc_path(task["id"], "task")
    fm = {"id": task["id"], "type": "task"}
    task_kind = task.get("kind", "")
    if task_kind == "milestone_verification":
        ms_id = task.get("milestone_id", "MS-ID")
        body = f"""# {task['id']} — {task.get('title', '')}

This task verifies {ms_id} against `.aiwf/milestones/{ms_id}.md`.
Do NOT implement feature changes here.
Run integration and architecture review sub-steps through `/aiwf-milestone`.

## Objective

Verify milestone {ms_id}.

## Milestone Reference

- Milestone: {ms_id}
- This task is: kind=milestone_verification

## Pass Standard Source

The authoritative Pass Standard is in `.aiwf/milestones/{ms_id}.md`.

## Integration Test Requirements

(fill — what must the integration tester verify?)

## Architect Review Requirements

(fill — is architecture review required? what must be checked?)

## Milestone Review Requirements

(fill — what must the final milestone reviewer verify?)

## Residual Risk Handling

(fill — which risks are acceptable? which block?)

## Human Acceptance Check

(fill — is explicit human acceptance required?)

## Done When

- [ ] Integration test passed and testing record exists (aiwf record testing)
- [ ] Architecture review intact (if required)
- [ ] Milestone review passed and review record exists (aiwf record review)
- [ ] Records in records/review.json, records/architecture-review.json
- [ ] Assessment recorded: aiwf milestone assess {ms_id} --verdict PASS

Note: This task has executor_required=false by default — no executor evidence needed.
If Planner overrides executor_required=true, executor evidence must also be recorded.
"""
    else:
        body = f"""# {task['id']} — {task.get('title', '')}

## Objective

(fill)

## Scope

(fill)

## Non-goals

(fill)

## Forbidden Write

(fill)

## Executor Requirements

(fill)

## Tester Requirements

(fill)

## Reviewer Requirements

(fill)

## Done When

(fill)

## Validation

(fill)

## Notes

(fill)
"""
    full_path = cwd / doc_path_str
    doc_hash = write_narrative_doc(full_path, fm, body)

    ledger = load_ledger(str(cwd))
    for t in ledger.get("tasks", []):
        if t.get("id") == task["id"]:
            t["doc_path"] = doc_path_str
            t["doc_hash"] = doc_hash
            t["doc_updated_at"] = _now_str()
            break
    save_ledger(str(cwd), ledger)
    print(f"  Narrative doc: {doc_path_str}")


def _now_str() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
