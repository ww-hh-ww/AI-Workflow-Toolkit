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
    list_fields = {"interfaces", "constraints", "allowed_write", "forbidden_write",
                   "test_focus", "review_focus", "escalation_triggers"}
    str_fields = ("goal_id", "context_id", "title", "kind", "plan_kind", "target_goal_id", "active_phase",
                  "child_goal_policy", "milestone_id", "work_intent", "purpose", "interface_contract")
    for k in str_fields:
        v = getattr(args, k, "") or ""
        if v:
            kwargs[k] = v
    for k in list_fields:
        v = getattr(args, k, []) or []
        if v:
            # Split comma-separated values: --allowed-write "a,b,c" → ["a","b","c"]
            split = []
            for item in v:
                for part in str(item).split(","):
                    part = part.strip()
                    if part:
                        split.append(part)
            if split:
                kwargs[k] = split
    task_ids = getattr(args, "task_ids", []) or []
    if task_ids:
        kwargs["task_ids"] = task_ids
    dependencies = getattr(args, "depends_on", None)
    if dependencies is not None:
        kwargs["dependencies"] = dependencies
    result = create_task_plan(str(Path.cwd()), task_id=legacy_task_id, plan_id=plan_id, **kwargs)
    effective_id = result.get("plan_id") or plan_id or legacy_task_id
    print(f"Plan: {effective_id} created={result['created']}")
    print(f"  Narrative: {_rel(result['path'])}")
    print(f"  Index: .aiwf/state/plans.json updated")
    print(f"  Goal: {result.get('target_goal_id', result.get('goal_id', ''))}")
    if result.get("task_ids"):
        print(f"  Tasks: {', '.join(result['task_ids'])}")
    if getattr(args, "narrative", False):
        _write_plan_narrative(Path.cwd(), effective_id)
    print("  Note: Plan.md is the semantic document; JSON indexes it.")


def _cmd_plan_update(args: argparse.Namespace) -> None:
    from ..core.task_plan import update_task_plan_section
    plan_id = getattr(args, "plan_id_pos", "") or getattr(args, "plan_id", "") or getattr(args, "task_id", "")
    try:
        result = update_task_plan_section(str(Path.cwd()), plan_id, args.section, args.content)
    except ValueError as e:
        print(f"Plan update blocked: {e}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Task plan updated: {plan_id}")
    print(f"  Section: {result['section']}")
    print(f"  Path: {_rel(result['path'])}")


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


def _cmd_plan_summarize(args: argparse.Namespace) -> None:
    from ..core.task_plan import summarize_task_plan
    pid = getattr(args, "plan_id", "") or getattr(args, "task_id", "")
    summary = summarize_task_plan(str(Path.cwd()), pid)
    if not summary.get("exists"):
        print(f"Task plan not found: {pid}")
        raise SystemExit(1)
    print(f"Task plan summary: {pid}")
    print(f"  Path: {_rel(summary['path'])}")
    print(f"  Lines: {summary['line_count']}")
    print(f"  Checklist: {summary['checklist_checked']}/{summary['checklist_total']}")


def _cmd_plan_list(args: argparse.Namespace) -> None:
    from ..core.task_plan import list_task_plans
    from ..core.state.plan_ops import plan_readiness
    plans = list_task_plans(str(Path.cwd()))
    if not plans:
        print("Task plans: none")
        return
    print(f"Task plans: {len(plans)}")
    for plan in plans:
        state = plan_readiness(str(Path.cwd()), plan["plan_id"]) if plan.get("registry") else None
        readiness = "unregistered"
        if state:
            readiness = "ready" if state["ready"] else f"blocked: {'; '.join(state['blockers'])}"
        print(f"  {plan['task_id']} | {readiness} | {_rel(plan['path'])}")


def _cmd_plan_dep_add(args: argparse.Namespace) -> None:
    from ..core.state.plan_ops import add_plan_dependency
    try:
        result = add_plan_dependency(str(Path.cwd()), args.plan_id, args.dependency_id)
    except ValueError as e:
        print(f"Plan dependency add blocked: {e}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Plan dependency added: {args.plan_id} -> {result['dependency_id']}")


def _cmd_plan_dep_remove(args: argparse.Namespace) -> None:
    from ..core.state.plan_ops import remove_plan_dependency
    try:
        result = remove_plan_dependency(
            str(Path.cwd()), args.plan_id, args.dependency_id, args.reason,
        )
    except ValueError as e:
        print(f"Plan dependency remove blocked: {e}", file=sys.stderr)
        raise SystemExit(1)
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


def _cmd_plan_rebase(args: argparse.Namespace) -> None:
    from ..core.state.plan_ops import rebase_plan_registry
    try:
        result = rebase_plan_registry(str(Path.cwd()), fix=args.fix)
    except ValueError as e:
        print(f"Plan rebase blocked: {e}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Plan registry rebase: changed={result['changed']}")
    for change in result.get("changes", [])[:12]:
        if change.get("kind") == "plan_goal_rebased":
            print(f"  Plan {change['plan_id']}: goal_id {change.get('from') or '(empty)'} -> {change['to']}")
        elif change.get("kind") == "task_goal_rebased":
            print(f"  Task {change['task_id']}: goal {change.get('from') or '(empty)'} -> {change['to']}")
    if len(result.get("changes", []) or []) > 12:
        print(f"  ... {len(result['changes']) - 12} more")


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
    print("AIWF Plan — node CRUD and task linking")
    print()
    print("  aiwf plan create PLAN-001 --goal GOAL-001 --title '...'")
    print("  aiwf plan show PLAN-001")
    print("  aiwf plan list")
    print("  aiwf plan rename PLAN-001 --title '...'")
    print("  aiwf plan close PLAN-001 --summary '...'")
    print("  aiwf plan cancel PLAN-001 --reason '...'")
    print("  aiwf plan link-task PLAN-001 TASK-001")
    print("  aiwf plan unlink-task PLAN-001 TASK-001")
    print("  aiwf plan dep add/remove/show")


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


def _cmd_plan_rename(args: argparse.Namespace) -> None:
    from ..core.state.plan_ops import load_plans, save_plans
    from datetime import datetime, timezone
    plan_id = getattr(args, "plan_id", "")
    title = getattr(args, "title", "") or ""
    data = load_plans(str(Path.cwd()))
    for p in data.get("plans", []) or []:
        if p.get("plan_id") == plan_id or p.get("id") == plan_id:
            p["title"] = title
            p["title_cache"] = title
            p["updated_at"] = datetime.now(timezone.utc).isoformat()
            save_plans(str(Path.cwd()), data)
            print(f"Plan renamed: {plan_id} -> {title}")
            return
    print(f"Plan not found: {plan_id}", file=sys.stderr)
    raise SystemExit(1)


def _cmd_plan_close(args: argparse.Namespace) -> None:
    from ..core.state.plan_ops import load_plans, save_plans
    from datetime import datetime, timezone
    plan_id = getattr(args, "plan_id", "")
    summary = getattr(args, "summary", "") or ""
    data = load_plans(str(Path.cwd()))
    for p in data.get("plans", []) or []:
        if p.get("plan_id") == plan_id or p.get("id") == plan_id:
            p["status"] = "closed"
            p["closure"] = {"mode": "normal", "accepted": True, "summary": summary}
            p["updated_at"] = datetime.now(timezone.utc).isoformat()
            save_plans(str(Path.cwd()), data)
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
            p["status"] = "cancelled"
            p["cancel_reason"] = reason
            if replaced_by:
                p["replaced_by"] = replaced_by
            p["updated_at"] = datetime.now(timezone.utc).isoformat()
            save_plans(str(Path.cwd()), data)
            print(f"Plan cancelled: {plan_id}")
            if reason:
                print(f"  Reason: {reason}")
            if replaced_by:
                print(f"  Replaced by: {replaced_by}")
            return
    print(f"Plan not found: {plan_id}", file=sys.stderr)
    raise SystemExit(1)


def _cmd_plan_deactivate(args: argparse.Namespace) -> None:
    from ..core.state.plan_ops import deactivate_plan
    result = deactivate_plan(str(Path.cwd()))
    prev = result.get("previous") or "(none)"
    print(f"Plan deactivated: was {prev}")
    print("  Phase set to discussing. All plans are now inactive.")


def _write_plan_narrative(cwd: Path, plan_id: str) -> None:
    from ..core.index_ops import (
        generate_narrative_doc_path, write_narrative_doc,
    )
    from ..core.state.plan_ops import load_plans, save_plans

    doc_path_str = generate_narrative_doc_path(plan_id, "plan")
    fm = {"id": plan_id, "type": "plan"}
    body = f"""# {plan_id}

## Intent

(fill)

## Current Problems

(fill)

## Target Design

(fill)

## Key Decisions

(fill)

## Non-goals

(fill)

## Task Breakdown

(fill)

## Risks

(fill)

## Validation Strategy

(fill)

## Open Questions

(fill)
"""
    full_path = cwd / doc_path_str
    doc_hash = write_narrative_doc(full_path, fm, body)

    plans = load_plans(str(cwd))
    for p in plans.get("plans", []):
        if p.get("plan_id") == plan_id or p.get("id") == plan_id:
            p["doc_path"] = doc_path_str
            p["doc_hash"] = doc_hash
            p["doc_updated_at"] = _now_str()
            break
    save_plans(str(cwd), plans)
    print(f"  Narrative doc: {doc_path_str}")


def _now_str() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
