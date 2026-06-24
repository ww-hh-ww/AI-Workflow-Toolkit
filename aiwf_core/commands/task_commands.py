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
    from ..core.index_ops import sync_index
    sync_result = sync_index(str(Path.cwd()))
    if sync_result["changes"]:
        for c in sync_result["changes"][:5]:
            print(f"  sync: {c}")
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

    # Dispatch gate: check that required subagents were actually dispatched.
    # This catches the model running tests/review inline and recording evidence
    # without ever calling Agent() to spawn the independent role.
    import json as _json
    cwd = Path.cwd()
    try:
        state = _json.loads((cwd / ".aiwf" / "state" / "state.json").read_text())
        active_id = task_id or state.get("active_task_id", "")
        if active_id:
            task_md = cwd / ".aiwf" / "tasks" / f"{active_id}.md"
            if task_md.exists():
                text = task_md.read_text(encoding="utf-8")
                if text.startswith("---\n"):
                    end = text.find("\n---\n", 4)
                    if end != -1:
                        import yaml
                        fm = yaml.safe_load(text[4:end]) or {}
                        er = fm.get("executor_required", False)
                        tr = fm.get("tester_required", False)
                        rr = fm.get("reviewer_required", False)

                        dispatch_log = cwd / ".aiwf" / "runtime" / "internal" / "agent-dispatch.jsonl"
                        dispatched = set()
                        if dispatch_log.exists():
                            for line in dispatch_log.read_text().strip().split("\n"):
                                try:
                                    d = _json.loads(line)
                                    if d.get("task_id") == active_id:
                                        dispatched.add(d.get("subagent_type", ""))
                                except Exception:
                                    pass

                        print("Dispatch check (was Agent() called?):")
                        if er:
                            ok = "aiwf-executor" in dispatched
                            print(f"  executor_required: true → dispatched: {'✓' if ok else '✗'} (aiwf-executor)")
                            if not ok:
                                raise SystemExit(
                                    "executor_required but aiwf-executor never dispatched.\n"
                                    "  → load /aiwf-implement, dispatch aiwf-executor, record evidence."
                                )
                        if tr:
                            ok = "aiwf-tester" in dispatched
                            print(f"  tester_required:   true → dispatched: {'✓' if ok else '✗'} (aiwf-tester)")
                            if not ok:
                                raise SystemExit(
                                    "tester_required but aiwf-tester never dispatched.\n"
                                    "  → load /aiwf-test, dispatch aiwf-tester, record testing."
                                )
                        if rr:
                            ok = "aiwf-reviewer" in dispatched
                            print(f"  reviewer_required: true → dispatched: {'✓' if ok else '✗'} (aiwf-reviewer)")
                            if not ok:
                                raise SystemExit(
                                    "reviewer_required but aiwf-reviewer never dispatched.\n"
                                    "  → load /aiwf-review, dispatch aiwf-reviewer, record review."
                                )
    except SystemExit:
        raise
    except Exception:
        pass

    result = close_task(str(Path.cwd()), task_id, note=args.note or "")
    print(f"Task close: {task_id or result.get('task', {}).get('id', '?')} closed={result['closed']}")
    if result["blockers"]:
        for blocker in result["blockers"][:5]:
            print(f"  - {blocker}")
        raise SystemExit(1)
    task = result.get("task") or {}
    for w in task.get("close_warnings", []) or []:
        print(f"  Warning: {w}")

    # Write close banner to Task.md (safe: lock released, task is closed)
    doc_path = task.get("doc_path", "")
    if doc_path:
        doc = Path.cwd() / doc_path
        if doc.exists():
            text = doc.read_text(encoding="utf-8")
            first = text.find("---\n", 4)
            if first != -1:
                fm_end = first + 4
                from datetime import datetime, timezone
                ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                banner = (
                    f"\n> **CLOSED** {ts} — "
                    f"frozen contract from activation. "
                    f"evidence={len(task.get('evidence_ids', []) or [])} records.\n"
                )
                doc.write_text(text[:fm_end] + banner + text[fm_end:], encoding="utf-8")

    # report_policy: ask → report to human and wait; silent_until_done → auto-proceed
    report_policy = (task.get("report_policy") or "ask").strip()
    gp = result.get("goal_progress", {}) or {}
    task_snapshot = result.get("task") or {}
    task_kind = task_snapshot.get("kind", "")
    task_ms_id = task_snapshot.get("milestone_id", "")
    pp = result.get("plan_progress", {}) or {}

    if report_policy == "silent_until_done":
        # Auto-proceed: Planner decides next action, no human reporting
        remaining = gp.get("remaining_tasks", []) or []
        ms_id = task_ms_id or pp.get("milestone_progress", {}).get("milestone", {}).get("milestone_id", "")
        if remaining:
            print(f"  → load /aiwf-planner, pick next task from [{', '.join(remaining[:5])}], activate and continue  (silent, do not report to human)")
        elif ms_id:
            print(f"  → load /aiwf-architect with milestone-acceptance lens, assess milestone {ms_id}  (silent batch complete, report milestone result to human)")
        else:
            print(f"  → all tasks complete, load /aiwf-planner for next cycle  (silent, report summary to human)")
        return

    # ask policy: summarize what was done, current state, next step, then wait for human
    title = task_snapshot.get("title_cache") or task_snapshot.get("title") or task_id
    kind = task_snapshot.get("kind", "")
    print(f"  Task: {title}")
    print(f"  Status: closed")
    if kind == "milestone_verification":
        print(f"  Kind: milestone verification for {task_ms_id}")
    # What was accomplished
    closure = task_snapshot.get("closure", {}) or {}
    if closure.get("summary"):
        print(f"  Summary: {closure['summary']}")
    # Current phase
    phase = task_snapshot.get("phase", "")
    if not phase:
        from pathlib import Path as _P
        import json as _j
        sp = _P.cwd() / ".aiwf" / "state" / "state.json"
        if sp.exists():
            phase = _j.loads(sp.read_text()).get("phase", "")
    print(f"  Phase: {phase}")
    # Goal progress
    if gp.get("parent_goal"):
        done = "yes" if gp.get("goal_complete") else "no"
        remaining = gp.get("remaining_tasks", []) or []
        print(f"  Goal: {gp['parent_goal']} — {gp.get('closed_count', 0)}/{gp.get('total_count', 0)} tasks closed ({'complete' if done == 'yes' else f'{len(remaining)} remaining'})")
        if remaining:
            print(f"  Remaining tasks: {' '.join(remaining[:5])}")
    # Plan progress
    if pp.get("reconciled"):
        plan = pp.get("plan", {}) or {}
        print(f"  Plan: {plan.get('plan_id', '')} — {pp.get('closed_count', 0)}/{pp.get('total_count', 0)} tasks closed")
    # Milestone progress
    mp = pp.get("milestone_progress", {}) or {}
    if mp.get("reconciled"):
        ms = mp.get("milestone", {}) or {}
        print(f"  Milestone: {ms.get('milestone_id', '')}")
    # Next action
    if kind == "milestone_verification" and task_ms_id:
        print(f"  Next: aiwf milestone close {task_ms_id}")
    else:
        print(f"  Next: aiwf-planner")
    print(f"  → Report this summary to the human and wait for instructions.")

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
    from ..core.index_ops import create_narrative_for_entity
    from ..core.task_ledger import load_ledger, save_ledger

    path = create_narrative_for_entity(str(cwd), task["id"], "task",
                                       title=task.get("title", ""),
                                       goal_id=task.get("goal_id", ""),
                                       plan_id=task.get("plan_id", ""),
                                       milestone_id=task.get("milestone_id", ""),
                                       kind=task.get("kind", ""))
    # Update ledger with doc path
    ledger = load_ledger(str(cwd))
    for t in ledger.get("tasks", []):
        if t.get("id") == task["id"]:
            t["doc_path"] = path
            break
    save_ledger(str(cwd), ledger)
    print(f"  Narrative doc: {path}")


def _now_str() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
