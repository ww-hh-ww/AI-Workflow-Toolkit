"""Task ledger command handlers."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import re

def _task_doc_has_section(cwd: Path, task_id: str, heading: str) -> bool:
    from ..core.worktree_context import resolve_control_root
    doc = resolve_control_root(cwd) / ".aiwf" / "tasks" / f"{task_id}.md"
    if not doc.exists():
        return False
    try:
        text = doc.read_text(encoding="utf-8")
    except Exception:
        return False
    return bool(re.search(rf"^## {re.escape(heading)}\s*$", text, flags=re.MULTILINE))

def _cmd_task_plan(args: argparse.Namespace) -> None:
    from ..core.task_ledger import upsert_task
    from ..core.index_ops import sync_index

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
        print(f"  Plan: {task.get('plan_id') or task.get('parent_plan')}")
    else:
        print("  Plan: none linked")
    if _gl("allowed_write"):
        print("  Note: task --allowed-write is deprecated and ignored; use Task.md Contract Responsibility and Forbidden Write.")
    # V1: Task.md is the execution contract — always created on task create
    _write_task_narrative(Path.cwd(), task)
    sync_result = sync_index(str(Path.cwd()))
    if sync_result["changes"]:
        for c in sync_result["changes"][:5]:
            print(f"  sync: {c}")
    linked_goal = task.get("goal_id") or task.get("parent_goal")
    if linked_goal:
        print(f"  Goal: {linked_goal}")
    else:
        print("  Goal: none linked")
    if task.get("milestone"):
        print(f"  Milestone: {task['milestone']}")
    if task.get("milestone_id"):
        print(f"  Milestone id: {task['milestone_id']}")
    # Granularity: warn if task smells like an action step
    for w in result.get("granularity_warnings", []) or []:
        print(f"  ! {w}")

def _cmd_task_activate(args: argparse.Namespace) -> None:
    from ..core.task_ledger import activate_task, task_activation_critique_blockers
    critique_blockers = task_activation_critique_blockers(str(Path.cwd()), args.task_id)
    if critique_blockers:
        print(f"Task activation: {args.task_id} activated=False")
        print(f"  Blockers ({len(critique_blockers)}):")
        for blocker in critique_blockers[:8]:
            print(f"    - {blocker}")
        raise SystemExit(1)
    result = activate_task(
        str(Path.cwd()), args.task_id,
        accept_head_change=bool(getattr(args, "accept_head_change", False)),
    )
    print(f"Task activation: {args.task_id} activated={result['activated']}")
    if result["blockers"]:
        print(f"  Blockers ({len(result['blockers'])}):")
        for blocker in result["blockers"][:8]:
            print(f"    - {blocker}")
        raise SystemExit(1)
    else:
        print("  Execution window updated.")
        if result.get("adopted_head_ref"):
            print(
                "  Current Git HEAD adopted as the resumed Task baseline; "
                "old implementation/testing/review proof was invalidated."
            )
            print("  The open fix-loop and Reviewer observations were preserved.")
        print("  Next: aiwf status --prompt")

def _cmd_task_critique(args: argparse.Namespace) -> None:
    from ..core.task_ledger import record_task_activation_critique
    result = record_task_activation_critique(str(Path.cwd()), args.task_id)
    if not result.get("recorded"):
        print(f"Task activation critique blocked: {args.task_id}", file=sys.stderr)
        for blocker in result.get("blockers", [])[:5]:
            print(f"  - {blocker}", file=sys.stderr)
        raise SystemExit(1)
    count = result.get("count", 0)
    required = result.get("required", 2)
    print(f"Activation critique recorded: {args.task_id} count={count}/{required}")
    if result.get("ready"):
        print("  Task can now be activated.")
    else:
        print("  Run Planner activation critique again before activation.")

def _cmd_task_calibrate(args: argparse.Namespace) -> None:
    from ..core.index_ops import (
        parse_md, replace_markdown_section, sync_index, write_narrative_doc,
    )
    from ..core.task_ledger import resolve_active_task_id
    from ..core.worktree_context import resolve_control_root

    cwd = Path.cwd()
    task_id = resolve_active_task_id(str(cwd), getattr(args, "task_id", "") or "")
    if not task_id:
        print("Task calibration blocked: task id required or active task missing", file=sys.stderr)
        raise SystemExit(1)
    summary = (getattr(args, "summary", "") or "").strip()
    if not summary:
        print("Task calibration blocked: --summary is required", file=sys.stderr)
        raise SystemExit(1)

    control = resolve_control_root(cwd)
    task_doc = control / ".aiwf" / "tasks" / f"{task_id}.md"
    if not task_doc.exists():
        print(f"Task calibration blocked: Task.md not found: {task_doc}", file=sys.stderr)
        raise SystemExit(1)
    fm, body = parse_md(task_doc)
    if fm is None:
        print("Task calibration blocked: Task.md must have frontmatter", file=sys.stderr)
        raise SystemExit(1)
    body = replace_markdown_section(body, "Closure Calibration", summary)
    write_narrative_doc(task_doc, fm, body)
    sync = sync_index(str(control))
    if sync.get("errors"):
        print("Task calibration sync failed:", file=sys.stderr)
        for err in sync["errors"][:5]:
            print(f"  - {err}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Task calibration written: {task_id}")
    print("  Section: Closure Calibration")
    print("  Next: aiwf status --prompt")

def _cmd_task_close(args: argparse.Namespace) -> None:
    from ..core.task_ledger import close_task, resolve_active_task_id
    from ..core.worktree_context import resolve_control_root

    task_id = getattr(args, "task_id", "") or ""
    effective_task_id = resolve_active_task_id(str(Path.cwd()), task_id)
    if effective_task_id and not _task_doc_has_section(Path.cwd(), effective_task_id, "Closure Calibration"):
        print(
            "  Warning: Task.md has no Closure Calibration. "
            "Planner should record what actually completed before close with "
            "`aiwf task calibrate --summary \"...\"`."
        )

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
        doc = resolve_control_root(Path.cwd()) / doc_path
        if doc.exists():
            text = doc.read_text(encoding="utf-8")
            first = text.find("---\n", 4)
            if first != -1:
                fm_end = first + 4
                from datetime import datetime, timezone
                ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                banner = (
                    f"\n> **CLOSED** {ts} — "
                    f"contract_status=closed. "
                    f"commit={((task.get('closure', {}) or {}).get('git_commit') or '')[:12]}.\n"
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
        print("  Next: aiwf status --prompt")
    print(f"  → Report this summary to the human and wait for instructions.")

    # Granularity warnings
    for w in result.get("granularity_warnings", []) or []:
        print(f"  ! {w}")

def _cmd_task_interrupt(args: argparse.Namespace) -> None:
    from ..core.task_ledger import interrupt_task
    reason = getattr(args, "reason", "") or ""
    result = interrupt_task(
        str(Path.cwd()), reason=reason, task_id=getattr(args, "task_id", "") or ""
    )
    task = result.get("task") or {}
    task_id = task.get("id", "unknown")
    print(f"Task interrupt: {task_id} interrupted={result['interrupted']}")
    if result["blockers"]:
        for blocker in result["blockers"][:5]:
            print(f"  - {blocker}")
        raise SystemExit(1)
    interruption = task.get("interruption", {}) or {}
    unsatisfied = interruption.get("unsatisfied_checks", []) or []
    if interruption.get("reason"):
        print(f"  Reason: {interruption['reason']}")
    if unsatisfied:
        print(f"  Unsatisfied checks ({len(unsatisfied)}):")
        for check in unsatisfied:
            print(f"    - {check}")
    print("  Status: suspended")
    print("  Next: planner may revise, reactivate, or cancel this task.")

def _cmd_task_force_close(args: argparse.Namespace) -> None:
    from ..core.task_ledger import force_close_task
    reason = getattr(args, "reason", "") or ""
    result = force_close_task(
        str(Path.cwd()), reason=reason, task_id=getattr(args, "task_id", "") or ""
    )
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
    from ..core.task_ledger import _mark_task_doc_contract_status
    from datetime import datetime, timezone
    task_id = getattr(args, "task_id", "")
    reason = getattr(args, "reason", "") or ""
    replaced_by = getattr(args, "replaced_by", "") or ""
    ledger = load_ledger(str(Path.cwd()))
    for t in ledger.get("tasks", []):
        if t.get("id") == task_id:
            if t.get("status") == "active":
                print(f"Cannot cancel active task: {task_id}. Use interrupt first, then cancel if the task is no longer wanted.", file=sys.stderr)
                raise SystemExit(1)
            t["status"] = "cancelled"
            t["cancel_reason"] = reason
            if replaced_by:
                t["replaced_by"] = replaced_by
            t["updated_at"] = datetime.now(timezone.utc).isoformat()
            warning = _mark_task_doc_contract_status(str(Path.cwd()), t, "cancelled")
            if warning:
                t.setdefault("close_warnings", []).append(warning)
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
                            # Recompute Task progress without replacing Git commits.
                            ts = p.get("task_status", {}) or {}
                            closed = sum(1 for v in ts.values() if v == "closed")
                            total = len(ts)
                            rollup = p.get("task_rollup", {}) or {}
                            rollup.update({
                                "summary": f"{closed}/{total} tasks closed under this plan.",
                                "closed_count": closed,
                                "total_count": total,
                            })
                            p["task_rollup"] = rollup
                            p.pop("evidence_rollup", None)
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

def _cmd_task_show(args: argparse.Namespace) -> None:
    from ..core.task_ledger import load_ledger, resolve_active_task_id
    task_id = getattr(args, "task_id", "") or ""
    ledger = load_ledger(str(Path.cwd()))
    if not task_id:
        task_id = resolve_active_task_id(str(Path.cwd()))
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
    print(f"  Phase: {task.get('phase', '') or '(none)'}")
    print(f"  Worktree: {task.get('worktree_path', '') or '(none)'}")
    print(f"  Kind: {task.get('kind', '') or '(none)'}")
    print(f"  Goal: {task.get('goal_id', '') or task.get('parent_goal', '') or '(none)'}")
    print(f"  Plan: {task.get('plan_id', '') or task.get('parent_plan', '') or '(none)'}")
    print(f"  Milestone: {task.get('milestone_id', '') or task.get('milestone', '') or '(none)'}")
    print(f"  Dependencies: {', '.join(task.get('dependencies', []) or []) or '(none)'}")
    reqs = task.get("requirements", {}) or {}
    print(f"  Requirements: executor={reqs.get('executor_required', True)}, tester={reqs.get('tester_required', True)}, reviewer={reqs.get('reviewer_required', True)}")
    if task.get("close_mode"):
        print(f"  Close mode: {task['close_mode']}")
        print(f"  Closed by: {task.get('closed_by', '')}")
    if task.get("doc_path"):
        print(f"  Doc: {task['doc_path']}")
    if task.get("git_origin_ref"):
        print(f"  Git origin: {task['git_origin_ref']}")
    if (task.get("closure", {}) or {}).get("git_commit"):
        print(f"  Git commit: {task['closure']['git_commit']}")
    if task.get("notes"):
        for note in task["notes"][-3:]:
            print(f"  Note: {note}")

def _cmd_task_proof(args: argparse.Namespace) -> None:
    import json
    from ..core.task_ledger import load_ledger, resolve_active_task_id
    from ..core.task_proof import build_task_proof

    cwd = Path.cwd()
    task_id = getattr(args, "task_id", "") or ""
    if not task_id:
        task_id = resolve_active_task_id(str(cwd))
    task = next(
        (item for item in load_ledger(str(cwd)).get("tasks", []) or [] if item.get("id") == task_id),
        None,
    )
    if not task:
        print(f"Task proof blocked: task not found: {task_id or '(none)'}", file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps(build_task_proof(str(cwd), task), ensure_ascii=False, indent=2))

def _cmd_task_status(args: argparse.Namespace) -> None:
    from ..core.task_ledger import ledger_summary
    summary = ledger_summary(str(Path.cwd()))
    counts = summary["counts"]
    print("Task ledger:")
    active_ids = summary.get("active_task_ids", []) or []
    print(f"  Active: {len(active_ids)}")
    for task in summary.get("active_tasks", []) or []:
        print(
            f"    {task.get('id')}  plan={task.get('plan_id') or task.get('parent_plan') or '-'} "
            f"phase={task.get('phase') or '-'}  worktree={task.get('worktree_path') or '-'}"
        )
    for status in ["candidate", "ready", "active", "blocked", "suspended", "closed", "cancelled"]:
        if counts.get(status):
            print(f"  {status}: {counts[status]}")

def _cmd_task_help(args: argparse.Namespace) -> None:
    print("AIWF Task — node CRUD and runtime")
    print()
    print("Node:")
    print("  aiwf task create TASK-001 --title '...'      — create a task")
    print("  aiwf task show [TASK-ID]                     — show task (defaults to active)")
    print("  aiwf task proof [TASK-ID]                    — show Git, implementation, test, and review truth")
    print("  aiwf task list                               — list all tasks")
    print("  aiwf task cancel TASK-001 --reason '...'     — cancel a non-active task")
    print()
    print("Runtime:")
    print("  aiwf task activate TASK-001                  — activate for execution")
    print("  aiwf task critique TASK-001                  — record one activation critique pass")
    print("  aiwf task calibrate [TASK-001] --summary '...' — write Closure Calibration")
    print("  aiwf task close                              — close the active task")
    print("  aiwf task interrupt [--reason '...']         — HUMAN ONLY interrupt active task")
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
