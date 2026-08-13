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
    if sync_result.get("errors"):
        print("  sync warning: Plan.md still needs correction before Task activation")
        for error in sync_result["errors"][:8]:
            print(f"    - {error}")
    if sync_result["changes"]:
        for c in sync_result["changes"][:5]:
            print(f"  sync: {c}")
    print("  Note: Plan.md is the semantic document; JSON indexes it.")

def _cmd_plan_show(args: argparse.Namespace) -> None:
    from ..core.task_plan import load_task_plan
    from ..core.state.plan_ops import get_plan, plan_readiness
    from ..core.git_workflow import plan_integration_state
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
        integration = plan.get("integration", {}) or {}
        if integration:
            print("Plan integration:")
            print(f"  Status: {integration.get('status') or '(unknown)'}")
            if integration.get("verification_status"):
                print(f"  Verification disposition: {integration['verification_status']}")
            print(f"  Base ref: {integration.get('base_ref') or '(none)'}")
            print(f"  Candidate: {integration.get('candidate_ref') or '(none)'}")
            if integration.get("candidate_worktree"):
                print(f"  Run checks in: {integration['candidate_worktree']}")
            if integration.get("merge_commit"):
                print(f"  Merge commit: {integration['merge_commit']}")
            if integration.get("conflicts"):
                print(f"  Conflicts: {', '.join(integration['conflicts'][:8])}")
            for gap in integration.get("known_gaps", []) or []:
                print(f"  Accepted gap: {gap}")
            if integration.get("acceptance_reason"):
                print(f"  Acceptance reason: {integration['acceptance_reason']}")
        closure = plan.get("closure", {}) or {}
        if closure.get("merged_to_branch"):
            print("Plan delivery:")
            print(f"  Merged to: {closure['merged_to_branch']}")
        if closure.get("resolved_conflicts"):
            print(f"  Resolved conflicts: {', '.join(closure['resolved_conflicts'])}")
        integration_state = plan_integration_state(str(Path.cwd()), plan)
        if integration_state not in ("working", "open", "closed", "cancelled"):
            print(f"Plan closeout: {integration_state}")
            if integration_state == "held":
                print(f"  Held at: {str(plan.get('integration_hold_ref') or '')[:12]}")


def _cmd_plan_bind_worktree(args: argparse.Namespace) -> None:
    from ..core.git_workflow import bind_plan_worktree
    from ..core.plan_worktrees import create_plan_worktree
    from ..core.state.plan_ops import get_plan, load_plans, save_plans
    from ..core.worktree_context import resolve_control_root, resolve_worktree_root, same_path

    base = str(Path.cwd())
    plans = load_plans(base)
    plan = get_plan(base, args.plan_id)
    if not plan:
        print(f"Plan worktree bind blocked: Plan not found: {args.plan_id}", file=sys.stderr)
        raise SystemExit(1)
    try:
        if getattr(args, "create", False):
            binding = create_plan_worktree(base, plan, args.path or None)
        else:
            target = args.path or base
            target_path = Path(target).expanduser()
            if not target_path.exists():
                raise ValueError(
                    f"worktree does not exist: {target_path}; use --create to create it"
                )
            if same_path(resolve_worktree_root(target_path), resolve_control_root(base)):
                raise ValueError(
                    "the control root is for Planner and shared AIWF state. "
                    f"Run: aiwf plan bind-worktree {args.plan_id} --create"
                )
            binding = bind_plan_worktree(base, plan, target_path)
    except ValueError as exc:
        print(f"Plan worktree bind blocked: {exc}", file=sys.stderr)
        raise SystemExit(1)
    for index, item in enumerate(plans.get("plans", []) or []):
        if item.get("plan_id", item.get("id")) == args.plan_id:
            plans["plans"][index] = plan
            break
    save_plans(base, plans)
    checkpoint = {}
    try:
        from ..core.governance_git import checkpoint_governance

        checkpoint = checkpoint_governance(
            base, reason=f"after binding Plan worktree: {args.plan_id}",
        )
    except ValueError as exc:
        print(f"  Governance checkpoint pending: {exc}")
    print(f"Plan worktree bound: {args.plan_id}")
    if checkpoint.get("committed"):
        print(f"  Governance checkpoint: {checkpoint['commit'][:12]}")
    if getattr(args, "create", False):
        print(f"  Action: {'created' if binding.get('created') else 'reused'}")
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
                closure_mode = str((plan.get("closure", {}) or {}).get("mode") or "")
                readiness = (
                    "closed: accepted gaps"
                    if pstatus == "closed" and closure_mode == "accepted_with_gaps"
                    else pstatus
                )
            elif state["ready"]:
                readiness = "ready"
            else:
                readiness = f"blocked: {'; '.join(state['blockers'])}"
        print(f"  {plan['task_id']} | {pstatus:10s} | {readiness} | {_rel(plan['path'])}")

def _cmd_plan_dep_add(args: argparse.Namespace) -> None:
    from ..core.state.plan_ops import add_plan_dependency
    from ..core.index_ops import parse_md, write_narrative_doc, sync_index
    from ..core.worktree_context import resolve_control_root
    try:
        result = add_plan_dependency(str(Path.cwd()), args.plan_id, args.dependency_id)
    except ValueError as e:
        print(f"Plan dependency add blocked: {e}", file=sys.stderr)
        raise SystemExit(1)
    # Update Plan.md frontmatter
    plan_doc = resolve_control_root(Path.cwd()) / ".aiwf" / "plans" / f"{args.plan_id}.md"
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
    from ..core.worktree_context import resolve_control_root
    try:
        result = remove_plan_dependency(
            str(Path.cwd()), args.plan_id, args.dependency_id, args.reason,
        )
    except ValueError as e:
        print(f"Plan dependency remove blocked: {e}", file=sys.stderr)
        raise SystemExit(1)
    plan_doc = resolve_control_root(Path.cwd()) / ".aiwf" / "plans" / f"{args.plan_id}.md"
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
    from ..core.worktree_context import resolve_control_root
    plan_id = getattr(args, "plan_id", "") or ""
    task_id = getattr(args, "task_id", "") or ""
    if not plan_id or not task_id:
        print("Usage: aiwf plan link-task <PLAN-ID> <TASK-ID>")
        raise SystemExit(1)
    try:
        result = attach_task_to_plan(str(Path.cwd()), plan_id, task_id)
    except ValueError as e:
        print(f"Plan task link blocked: {e}", file=sys.stderr)
        raise SystemExit(1)
    if result.get("attached"):
        # Update Task.md frontmatter — plan_id is the master input
        task_doc = resolve_control_root(Path.cwd()) / ".aiwf" / "tasks" / f"{task_id}.md"
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
    from ..core.worktree_context import resolve_control_root
    plan_id = getattr(args, "plan_id", "") or ""
    task_id = getattr(args, "task_id", "") or ""
    if not plan_id or not task_id:
        print("Usage: aiwf plan unlink-task <PLAN-ID> <TASK-ID>")
        raise SystemExit(1)
    try:
        result = detach_task_from_plan(str(Path.cwd()), plan_id, task_id)
    except ValueError as e:
        print(f"Plan task unlink blocked: {e}", file=sys.stderr)
        raise SystemExit(1)
    if result.get("detached"):
        task_doc = resolve_control_root(Path.cwd()) / ".aiwf" / "tasks" / f"{task_id}.md"
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

def _cmd_plan_hold(args: argparse.Namespace) -> None:
    from ..core.state.plan_ops import hold_plan_integration

    try:
        result = hold_plan_integration(str(Path.cwd()), args.plan_id)
    except ValueError as exc:
        print(f"Plan hold blocked: {exc}", file=sys.stderr)
        raise SystemExit(1)
    action = "held" if result["changed"] else "already held"
    print(f"Plan integration {action}: {args.plan_id}")
    print(f"  Head: {str(result['hold_ref'])[:12]}")
    print("  The Plan remains open and will not prompt for merge until its result changes.")


def _cmd_plan_integrate(args: argparse.Namespace) -> None:
    from .state_commands import (
        _parse_paired_verification_results,
        _parse_verification_results,
    )
    from ..core.plan_integration_audit import audit_lines
    from ..core.plan_integration import finish_plan_integration, prepare_plan_integration

    try:
        if not getattr(args, "status", ""):
            result = prepare_plan_integration(
                str(Path.cwd()),
                args.plan_id,
            )
            checkpoint = result.get("governance_checkpoint", {}) or {}
            if checkpoint.get("committed"):
                print(f"Governance checkpoint: {checkpoint['commit'][:12]}")
            if result.get("audit_required"):
                print(f"Plan integration audit: {args.plan_id}")
                print("  No candidate was prepared and nothing was merged.")
                for line in audit_lines(result.get("audit", {}) or {}):
                    print(f"  {line}")
                print(
                    "  Planner: classify these as local residue, deliverable assets, "
                    "reproducible output, or unknown risk. Resolve them with normal editing "
                    "and Git, then rerun this same command. No repair workflow is required."
                )
                return
            if result.get("conflict"):
                task_id = str(result.get("integration_task_id") or "")
                print(f"Plan integration stage 1/2: conflict found for {args.plan_id}")
                print("  Planner: inspect the diff and choose the lightest honest path.")
                if task_id:
                    print(
                        f"  Existing integration Task: {task_id}. Continue it only if the "
                        "resolution is still semantic. If it was created unnecessarily and has "
                        "not produced governed work, explain that and ask the user before cancelling it."
                    )
                if result.get("conflicts"):
                    print("  Conflicts: " + ", ".join(result["conflicts"][:8]))
                print(
                    "  A small Git, generated-file, or environment conflict may be resolved "
                    "directly in the Plan worktree with normal Git; no Task or role dispatch "
                    "is needed. Then rerun this same command."
                )
                print(
                    "  If resolution changes project behavior, interfaces, dependencies, or "
                    "product meaning, create or continue one kind=integration Task instead."
                )
                if result.get("critique_reset_task_ids"):
                    print(
                        "  Preflight inputs changed. Recheck Task.md and run both "
                        "activation critique passes again before activation."
                    )
                print("  Record any meaningful resolution and remaining consequence in Plan Closure Calibration.")
                return
            print(f"Plan integration stage 1/2 prepared: {args.plan_id}")
            print("  Nothing has been merged into the base branch yet.")
            print(f"  Base ref: {result['base_ref'][:12]}")
            print(f"  Candidate ref: {result['candidate_ref'][:12]}")
            print(f"  Run checks in: {result['candidate_worktree']}")
            advisory = audit_lines(result.get("audit", {}) or {})
            if advisory:
                print("  Environment advisory (not an automatic blocker):")
                for line in advisory:
                    print(f"    {line}")
            if result.get("already_merged"):
                print("  Existing merged result adopted as the candidate; verify it to finish the Plan.")
            if result.get("integration_task_no_longer_needed"):
                print(
                    "  The refreshed preflight has no project conflict. Integration Task "
                    f"{result.get('integration_task_id')} is no longer needed; ask the "
                    "user before cancelling it."
                )
            print("  Run the Plan's integration checks against this exact candidate.")
            print(
                "  Before merge, ask whether the user wants /aiwf-architect on this exact "
                "candidate. The user chooses the review slice. If a finding changes the "
                "candidate, resolve environment, generated, or non-semantic work directly; "
                "create a Task only for semantic project work. Then prepare again."
            )
            print("  Stage 2/2 runs only after the user chooses to merge this verified candidate.")
            print(
                "  First write a concise '## Closure Calibration' in Plan.md with the actual "
                "outcome. Add only a difference or remaining gap that matters. Do not "
                "checkpoint it separately; the passing command checkpoints it after merge."
            )
            print(
                f"  Stage 2/2, verify + merge + close: aiwf plan integrate {args.plan_id} --status passed "
                "--command '<exact command>' --result "
                "'<expected>:::<observed>:::matched'"
            )
            print(
                "  If the user explicitly accepts unmet Plan outcomes, use "
                f"aiwf plan integrate {args.plan_id} --status accepted_with_gaps "
                "--command '<exact command>' --result "
                "'<expected>:::<observed>:::<matched|mismatched>' "
                "--known-gap '<unmet outcome and consequence>' "
                "--acceptance-reason '<why the user accepts it now>'. "
                "Do not call an unmet outcome passed."
            )
            print(f"  Keep open instead: aiwf plan hold {args.plan_id}")
            return

        raw_results = getattr(args, "verification_results", []) or []
        paired_results = getattr(args, "paired_results", []) or []
        if raw_results and paired_results:
            raise ValueError("use either --result or --verification-result, not both")
        verification_results = _parse_verification_results(raw_results)
        verification_results = verification_results or _parse_paired_verification_results(
            getattr(args, "commands", []) or [], paired_results,
        )
        result = finish_plan_integration(
            str(Path.cwd()),
            args.plan_id,
            status=args.status,
            commands=getattr(args, "commands", []) or [],
            verification_results=verification_results,
            summary=getattr(args, "summary", "") or "",
            known_gaps=getattr(args, "known_gaps", []) or [],
            acceptance_reason=getattr(args, "acceptance_reason", "") or "",
        )
    except ValueError as exc:
        print(f"Plan integration blocked: {exc}", file=sys.stderr)
        raise SystemExit(1)

    if not result.get("merged"):
        print(f"Plan integration recorded failed: {args.plan_id}")
        print("  Keep the Plan open, inspect the failure, and add or repair a Task.")
        return
    integration = result.get("integration", {}) or {}
    checkpoint = result.get("governance_checkpoint", {}) or {}
    if args.status == "accepted_with_gaps":
        print(f"Plan merged and closed with accepted gaps: {args.plan_id}")
    else:
        print(f"Plan merged and closed: {args.plan_id}")
    print(f"  Verified candidate: {str(integration.get('candidate_ref') or '')[:12]}")
    print(f"  Merge commit: {str(integration.get('merge_commit') or '')[:12]}")
    closure = result.get("plan", {}).get("closure", {}) or {}
    if closure.get("merged_to_branch"):
        print(f"  Merged to user-selected base: {closure.get('merged_to_branch')}")
    for gap in integration.get("known_gaps", []) or []:
        print(f"  Accepted gap: {gap}")
    if integration.get("acceptance_reason"):
        print(f"  Acceptance reason: {integration['acceptance_reason']}")
    if checkpoint.get("committed"):
        print(f"  Governance checkpoint: {str(checkpoint.get('commit') or '')[:12]}")
    elif checkpoint.get("warning"):
        print(f"  Governance checkpoint pending: {checkpoint['warning']}")
    milestone_id = str((result.get("plan") or {}).get("milestone_id") or "")
    if milestone_id:
        from .flow import _milestones_at_acceptance
        from ..core.worktree_context import resolve_control_root

        ready_ids = {
            str(item.get("milestone_id") or item.get("id") or "")
            for item in _milestones_at_acceptance(resolve_control_root(Path.cwd()))
        }
        if milestone_id in ready_ids:
            print(
                f"  Milestone acceptance frontier reached: {milestone_id}. "
                "Run aiwf status --prompt for the verification Task and Architect route; "
                "AIWF does not dispatch or confirm automatically."
            )

def _update_md_status(entity_type: str, entity_id: str, status: str,
                      summary: str = "") -> None:
    from ..core.index_ops import parse_md, write_narrative_doc, sync_index
    from ..core.worktree_context import resolve_control_root
    from pathlib import Path as _P
    dir_map = {"plan": ".aiwf/plans", "milestone": ".aiwf/milestones"}
    subdir = dir_map.get(entity_type)
    if not subdir:
        return
    doc = resolve_control_root(_P.cwd()) / subdir / f"{entity_id}.md"
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
            p.pop("integration_hold_ref", None)
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
