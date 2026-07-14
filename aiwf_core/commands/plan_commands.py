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
    plan_id = getattr(args, "plan_id", "")
    if not plan_id:
        print("plan_id is required: aiwf plan create <PLAN-ID>", file=sys.stderr)
        raise SystemExit(1)
    try:
        result = create_task_plan(
            str(Path.cwd()),
            plan_id=plan_id,
            goal_id=getattr(args, "goal_id", ""),
            title=getattr(args, "title", ""),
            task_ids=getattr(args, "task_ids", []) or [],
            milestone_id=getattr(args, "milestone_id", ""),
        )
    except ValueError as e:
        print(f"Plan create blocked: {e}", file=sys.stderr)
        raise SystemExit(1)
    effective_id = result.get("plan_id") or plan_id
    print(f"Plan: {effective_id} created={result['created']}")
    print(f"  Narrative: {_rel(result['path'])}")
    print(f"  Index: .aiwf/state/plans.json updated")
    print(f"  Goal: {result.get('goal_id', '')}")
    if result.get("task_ids"):
        print(f"  Tasks: {', '.join(result['task_ids'])}")
    from ..core.index_ops import sync_index
    sync_result = sync_index(str(Path.cwd()))
    if sync_result["changes"]:
        for c in sync_result["changes"][:5]:
            print(f"  sync: {c}")
    print("  Note: Plan.md is the semantic document; JSON indexes it.")

def _cmd_plan_show(args: argparse.Namespace) -> None:
    from ..core.task_plan import load_task_plan
    from ..core.state.plan_ops import get_plan, plan_readiness
    plan_id = getattr(args, "plan_id_pos", "") or getattr(args, "plan_id", "") or getattr(args, "task_id", "")
    text = load_task_plan(str(Path.cwd()), plan_id)
    if not text:
        print(f"Task plan not found: {plan_id}")
        raise SystemExit(1)
    print(text)
    plan = get_plan(str(Path.cwd()), plan_id)
    if plan:
        readiness = plan_readiness(str(Path.cwd()), plan_id)
        print("Plan dependency state:")
        print(f"  Dependencies: {', '.join(readiness['dependencies']) or 'none'}")
        print(f"  Readiness: {'ready' if readiness['ready'] else 'blocked'}")
        for blocker in readiness["blockers"]:
            print(f"  Blocked: {blocker}")
        if plan.get("git_branch"):
            print("Plan Git:")
            print(f"  Worktree: {plan.get('git_worktree_path') or '(current)'}")
            print(f"  Branch: {plan['git_branch']}")
            print(f"  Base: {plan.get('git_base_branch') or '(unknown)'}")
            print(f"  Head: {plan.get('git_head_ref') or '(no closed Task commit)'}")


def _cmd_plan_bind_worktree(args: argparse.Namespace) -> None:
    from ..core.git_workflow import bind_plan_worktree
    from ..core.state.plan_ops import get_plan, load_plans, save_plans

    base = str(Path.cwd())
    plans = load_plans(base)
    plan = get_plan(base, args.plan_id)
    if not plan:
        print(f"Plan worktree bind blocked: Plan not found: {args.plan_id}", file=sys.stderr)
        raise SystemExit(1)
    target = args.path or base
    try:
        binding = bind_plan_worktree(base, plan, target)
    except ValueError as exc:
        print(f"Plan worktree bind blocked: {exc}", file=sys.stderr)
        raise SystemExit(1)
    for index, item in enumerate(plans.get("plans", []) or []):
        if item.get("plan_id", item.get("id")) == args.plan_id:
            plans["plans"][index] = plan
            break
    save_plans(base, plans)
    print(f"Plan worktree bound: {args.plan_id}")
    print(f"  Worktree: {binding['worktree_path']}")
    print(f"  Branch: {binding['branch']}")
    print(f"  Base: {binding['base_branch'] or '(unknown)'}")

def _cmd_plan_list(args: argparse.Namespace) -> None:
    from ..core.task_plan import list_task_plans
    from ..core.state.plan_ops import plan_readiness
    plans = list_task_plans(str(Path.cwd()))
    if not plans:
        print("Task plans: none")
        return
    print(f"Task plans: {len(plans)}")
    for plan in plans:
        pstatus = plan.get("status", plan.get("plan_status", "open"))
        state = plan_readiness(str(Path.cwd()), plan["plan_id"]) if plan.get("registry") else None
        readiness = "unregistered"
        if state:
            if pstatus in ("cancelled", "closed"):
                readiness = pstatus
            elif state["ready"]:
                readiness = "ready"
            else:
                readiness = f"blocked: {'; '.join(state['blockers'])}"
        print(f"  {plan['task_id']} | {pstatus:10s} | {readiness} | {_rel(plan['path'])}")

def _cmd_plan_dep_add(args: argparse.Namespace) -> None:
    from ..core.state.plan_ops import add_plan_dependency
    from ..core.index_ops import parse_md, write_narrative_doc, sync_index
    try:
        result = add_plan_dependency(str(Path.cwd()), args.plan_id, args.dependency_id)
    except ValueError as e:
        print(f"Plan dependency add blocked: {e}", file=sys.stderr)
        raise SystemExit(1)
    # Update Plan.md frontmatter
    plan_doc = Path.cwd() / ".aiwf" / "plans" / f"{args.plan_id}.md"
    if plan_doc.exists():
        fm, body = parse_md(plan_doc)
        if fm is not None:
            deps = list(fm.get("dependencies") or [])
            if args.dependency_id not in deps:
                deps.append(args.dependency_id)
            fm["dependencies"] = deps
            write_narrative_doc(plan_doc, fm, body)
    sync_index(str(Path.cwd()))
    print(f"Plan dependency added: {args.plan_id} -> {result['dependency_id']}")

def _cmd_plan_dep_remove(args: argparse.Namespace) -> None:
    from ..core.state.plan_ops import remove_plan_dependency
    from ..core.index_ops import parse_md, write_narrative_doc, sync_index
    try:
        result = remove_plan_dependency(
            str(Path.cwd()), args.plan_id, args.dependency_id, args.reason,
        )
    except ValueError as e:
        print(f"Plan dependency remove blocked: {e}", file=sys.stderr)
        raise SystemExit(1)
    plan_doc = Path.cwd() / ".aiwf" / "plans" / f"{args.plan_id}.md"
    if plan_doc.exists():
        fm, body = parse_md(plan_doc)
        if fm is not None:
            deps = list(fm.get("dependencies") or [])
            if args.dependency_id in deps:
                deps.remove(args.dependency_id)
            fm["dependencies"] = deps
            write_narrative_doc(plan_doc, fm, body)
    sync_index(str(Path.cwd()))
    print(f"Plan dependency removed: {args.plan_id} -> {result['dependency_id']}")
    print(f"  Reason: {result['reason']}")

def _cmd_plan_dep_show(args: argparse.Namespace) -> None:
    from ..core.state.plan_ops import get_plan, plan_readiness
    plan = get_plan(str(Path.cwd()), args.plan_id)
    if not plan:
        print(f"Plan not found: {args.plan_id}", file=sys.stderr)
        raise SystemExit(1)
    state = plan_readiness(str(Path.cwd()), args.plan_id)
    print(f"Plan dependencies: {args.plan_id}")
    print(f"  Depends On: {', '.join(state['dependencies']) or 'none'}")
    print(f"  Readiness: {'ready' if state['ready'] else 'blocked'}")
    for blocker in state["blockers"]:
        print(f"  Blocked: {blocker}")

def _cmd_plan_attach(args: argparse.Namespace) -> None:
    """Attach a task to an existing Plan — sets Task.md frontmatter plan_id, sync derives Plan.task_ids."""
    from ..core.state.plan_ops import attach_task_to_plan
    from ..core.index_ops import parse_md, write_narrative_doc, sync_index
    plan_id = getattr(args, "plan_id", "") or ""
    task_id = getattr(args, "task_id", "") or ""
    if not plan_id or not task_id:
        print("Usage: aiwf plan attach <PLAN-ID> --task <TASK-ID>")
        raise SystemExit(1)
    try:
        result = attach_task_to_plan(str(Path.cwd()), plan_id, task_id)
    except ValueError as e:
        print(f"Plan task link blocked: {e}", file=sys.stderr)
        raise SystemExit(1)
    if result.get("attached"):
        # Update Task.md frontmatter — plan_id is the master input
        task_doc = Path.cwd() / ".aiwf" / "tasks" / f"{task_id}.md"
        if task_doc.exists():
            fm, body = parse_md(task_doc)
            if fm is not None:
                fm["plan_id"] = plan_id
                write_narrative_doc(task_doc, fm, body)
        sync_index(str(Path.cwd()))
        print(f"Task {task_id} attached to Plan {plan_id}.")
    else:
        print(f"Failed: {result.get('reason', 'unknown')}")
        raise SystemExit(1)

def _cmd_plan_detach(args: argparse.Namespace) -> None:
    """Detach a task from a Plan — clears Task.md frontmatter plan_id, sync updates Plan.task_ids."""
    from ..core.state.plan_ops import detach_task_from_plan
    from ..core.index_ops import parse_md, write_narrative_doc, sync_index
    plan_id = getattr(args, "plan_id", "") or ""
    task_id = getattr(args, "task_id", "") or ""
    if not plan_id or not task_id:
        print("Usage: aiwf plan detach <PLAN-ID> --task <TASK-ID>")
        raise SystemExit(1)
    try:
        result = detach_task_from_plan(str(Path.cwd()), plan_id, task_id)
    except ValueError as e:
        print(f"Plan task unlink blocked: {e}", file=sys.stderr)
        raise SystemExit(1)
    if result.get("detached"):
        task_doc = Path.cwd() / ".aiwf" / "tasks" / f"{task_id}.md"
        if task_doc.exists():
            fm, body = parse_md(task_doc)
            if fm is not None:
                fm["plan_id"] = ""
                write_narrative_doc(task_doc, fm, body)
        sync_index(str(Path.cwd()))
        print(f"Task {task_id} detached from Plan {plan_id}.")
    else:
        print(f"Failed: {result.get('reason', 'unknown')}")
        raise SystemExit(1)

def _cmd_plan_help(args: argparse.Namespace) -> None:
    print("AIWF Plan — node CRUD and task linking")
    print()
    print("  aiwf plan create PLAN-001 --goal GOAL-001 --title '...'")
    print("  aiwf plan show PLAN-001")
    print("  aiwf plan list")
    print("  aiwf plan close PLAN-001 --summary '...'")
    print("  aiwf plan cancel PLAN-001 --reason '...'")
    print("  aiwf plan link-task PLAN-001 TASK-001")
    print("  aiwf plan unlink-task PLAN-001 TASK-001")
    print("  aiwf plan dep add/remove/show")

def _update_md_status(entity_type: str, entity_id: str, status: str,
                      summary: str = "") -> None:
    from ..core.index_ops import parse_md, write_narrative_doc, sync_index
    from pathlib import Path as _P
    dir_map = {"plan": ".aiwf/plans", "milestone": ".aiwf/milestones"}
    subdir = dir_map.get(entity_type)
    if not subdir:
        return
    doc = _P.cwd() / subdir / f"{entity_id}.md"
    if not doc.exists():
        return
    fm, body = parse_md(doc)
    if fm is None:
        return
    fm["status"] = status
    if summary:
        fm.setdefault("closure_summary", summary)
    write_narrative_doc(doc, fm, body)
    sync_index(str(_P.cwd()))

def _cmd_plan_close(args: argparse.Namespace) -> None:
    from ..core.state.plan_ops import load_plans, save_plans
    from ..core.git_workflow import plan_close_blockers, repository_info
    from datetime import datetime, timezone
    plan_id = getattr(args, "plan_id", "")
    summary = getattr(args, "summary", "") or ""
    data = load_plans(str(Path.cwd()))
    for p in data.get("plans", []) or []:
        if p.get("plan_id") == plan_id or p.get("id") == plan_id:
            if p.get("status") == "closed":
                print(f"Plan already closed: {plan_id}")
                return
            blockers = plan_close_blockers(str(Path.cwd()), p)
            if blockers:
                print(f"Plan close blocked: {plan_id}", file=sys.stderr)
                for blocker in blockers[:8]:
                    print(f"  - {blocker}", file=sys.stderr)
                raise SystemExit(1)
            p["status"] = "closed"
            p["closure"] = {
                "mode": "normal",
                "accepted": True,
                "summary": summary,
                "merged_commit": repository_info(str(Path.cwd()))["head"],
            }
            p["updated_at"] = datetime.now(timezone.utc).isoformat()
            save_plans(str(Path.cwd()), data)
            _update_md_status("plan", plan_id, "closed", summary)
            print(f"Plan closed: {plan_id}")
            return
    print(f"Plan not found: {plan_id}", file=sys.stderr)
    raise SystemExit(1)

def _cmd_plan_cancel(args: argparse.Namespace) -> None:
    from ..core.state.plan_ops import load_plans, save_plans
    from datetime import datetime, timezone
    plan_id = getattr(args, "plan_id", "")
    reason = getattr(args, "reason", "") or ""
    replaced_by = getattr(args, "replaced_by", "") or ""
    data = load_plans(str(Path.cwd()))
    for p in data.get("plans", []) or []:
        if p.get("plan_id") == plan_id or p.get("id") == plan_id:
            if p.get("status") == "closed":
                print(
                    f"Plan cancel blocked: {plan_id} is closed; create a new Plan for new work.",
                    file=sys.stderr,
                )
                raise SystemExit(1)
            p["status"] = "cancelled"
            p["cancel_reason"] = reason
            if replaced_by:
                p["replaced_by"] = replaced_by
            p["updated_at"] = datetime.now(timezone.utc).isoformat()
            save_plans(str(Path.cwd()), data)
            _update_md_status("plan", plan_id, "cancelled")
            print(f"Plan cancelled: {plan_id}")
            if reason:
                print(f"  Reason: {reason}")
            if replaced_by:
                print(f"  Replaced by: {replaced_by}")
            return
    print(f"Plan not found: {plan_id}", file=sys.stderr)
    raise SystemExit(1)
