"""Milestone command handlers."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

def _cmd_milestone_create(args: argparse.Namespace) -> None:
    from ..core.state.milestone_ops import upsert_milestone
    try:
        result = upsert_milestone(
            str(Path.cwd()),
            args.milestone_id,
            goal_id=getattr(args, "goal_id", "") or "",
            title=getattr(args, "title", "") or "",
            status=getattr(args, "status", "") or "pending",
            intent=getattr(args, "intent", "") or "",
            plan_ids=getattr(args, "plan_ids", None) or None,
            task_ids=getattr(args, "task_ids", None) or None,
            covered_goal_ids=getattr(args, "covered_goal_ids", None) or None,
            mission_id=getattr(args, "mission_id", "") or "",
            advance_policy=getattr(args, "advance_policy", "") or "",
            checkpoint_level=getattr(args, "checkpoint_level", "") or "",
        )
    except ValueError as e:
        print(f"Milestone create blocked: {e}", file=sys.stderr)
        raise SystemExit(1)
    m = result["milestone"]
    print(f"Milestone: {m['milestone_id']} status={m['status']}")
    from ..core.index_ops import create_narrative_for_entity, sync_index
    path = create_narrative_for_entity(str(Path.cwd()), args.milestone_id, "milestone",
                                       title=getattr(args, "title", "") or "",
                                       goal_id=getattr(args, "goal_id", "") or "",
                                       status=m.get("status", ""))
    print(f"  Narrative doc: {path}")
    sync_result = sync_index(str(Path.cwd()))
    if sync_result["changes"]:
        for c in sync_result["changes"][:5]:
            print(f"  sync: {c}")
    print(f"  Goal: {m.get('goal_id', '')}")
    print(f"  Plans: {len(m.get('plan_ids', []) or [])}")
    print(f"  Tasks: {len(m.get('task_ids', []) or [])}")

def _cmd_milestone_list(args: argparse.Namespace) -> None:
    from ..core.state.milestone_ops import list_milestones
    milestones = list_milestones(str(Path.cwd()))
    if not milestones:
        print("Milestones: none")
        return
    print(f"Milestones: {len(milestones)}")
    for m in milestones:
        print(
            f"  {m.get('milestone_id') or m.get('id')} "
            f"[{m.get('status', 'pending')}] "
            f"goal={m.get('goal_id', '')} "
            f"plans={len(m.get('plan_ids', []) or [])} "
            f"{m.get('title', '')}"
        )

def _cmd_milestone_show(args: argparse.Namespace) -> None:
    from ..core.state.milestone_ops import get_milestone
    m = get_milestone(str(Path.cwd()), args.milestone_id)
    if not m:
        print(f"Milestone not found: {args.milestone_id}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Milestone: {m.get('milestone_id') or m.get('id')}")
    print(f"  Title: {m.get('title', '')}")
    print(f"  Status: {m.get('status', '')}")
    print(f"  Goal: {m.get('goal_id', '')}")
    print(f"  Intent: {m.get('intent', '') or '(none)'}")
    print(f"  Plans: {', '.join(m.get('plan_ids', []) or []) or '(none)'}")
    print(f"  Tasks: {', '.join(m.get('task_ids', []) or []) or '(none)'}")
    synthesis = m.get("stage_synthesis", {}) or {}
    print(f"  Stage Synthesis: {synthesis.get('status', 'pending')} verdict={synthesis.get('verdict', 'pending')}")
    if synthesis.get("summary"):
        print(f"  Summary: {synthesis['summary']}")
    if synthesis.get("coherence_check"):
        print(f"  Coherence: {synthesis['coherence_check']}")
    if synthesis.get("interface_stability"):
        print(f"  Interface Stability: {synthesis['interface_stability']}")
    from ..core.state.milestone_ops import check_milestone_technical_readiness
    technical_blockers = check_milestone_technical_readiness(str(Path.cwd()), args.milestone_id)
    acceptance = m.get("user_acceptance", {}) or {}
    print(f"  Technical Ready: {'yes' if not technical_blockers else 'no'}")
    print(f"  User Confirmation Required: {'yes' if acceptance.get('required', True) else 'no'}")
    print(f"  User Confirmed: {'yes' if acceptance.get('status') == 'confirmed' else 'no'}")
    if acceptance.get("confirmed_by"):
        print(f"  Confirmed By: {acceptance['confirmed_by']}")

def _cmd_milestone_cancel(args: argparse.Namespace) -> None:
    from ..core.state.milestone_ops import load_milestones, save_milestones
    from datetime import datetime, timezone
    data = load_milestones(str(Path.cwd()))
    for m in data.get("milestones", []) or []:
        if m.get("milestone_id") == args.milestone_id:
            m["status"] = "cancelled"
            reason = getattr(args, "reason", "") or ""
            if reason:
                m["cancel_reason"] = reason
            replaced_by = getattr(args, "replaced_by", "") or ""
            if replaced_by:
                m["replaced_by"] = replaced_by
            m["updated_at"] = datetime.now(timezone.utc).isoformat()
            # Clear active_milestone_id if this was active
            if data.get("active_milestone_id") == args.milestone_id:
                data["active_milestone_id"] = None
            save_milestones(str(Path.cwd()), data)
            _update_milestone_md(args.milestone_id, status="cancelled")
            print(f"Milestone cancelled: {args.milestone_id}")
            if reason:
                print(f"  Reason: {reason}")
            return
    print(f"Milestone not found: {args.milestone_id}", file=sys.stderr)
    raise SystemExit(1)

def _cmd_milestone_assess(args: argparse.Namespace) -> None:
    from ..core.state.milestone_ops import record_milestone_assessment
    def _g(key, default=""):
        return getattr(args, key, default)
    def _gl(key, default=None):
        return getattr(args, key, default)
    try:
        result = record_milestone_assessment(
            str(Path.cwd()),
            _g("milestone_id"),
            verdict=_g("verdict"),
            summary=_g("summary"),
            coherence_check=_g("coherence_check"),
            open_gaps=_gl("open_gaps"),
            residual_risks=_gl("residual_risks"),
            next_recommendation=_g("next_recommendation"),
        )
    except ValueError as e:
        print(f"Milestone assessment blocked: {e}", file=sys.stderr)
        raise SystemExit(1)
    if not result.get("recorded"):
        print(f"Milestone assessment blocked: {result.get('reason', 'unknown')}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Milestone assessment recorded: {args.milestone_id} verdict={args.verdict}")

def _cmd_milestone_close(args: argparse.Namespace) -> None:
    from ..core.state.milestone_ops import close_milestone
    result = close_milestone(str(Path.cwd()), args.milestone_id)
    print(f"Milestone close: {args.milestone_id} closed={result['closed']}")
    for blocker in result.get("blockers", []) or []:
        print(f"  - {blocker}")
    if result.get("blockers"):
        raise SystemExit(1)
    _update_milestone_md(args.milestone_id, status="closed")
    print()
    print("Milestone closed.")
    print("Recommended human action:")
    print("  git status")
    print("  git add -A")
    print(f"  git commit -m \"milestone({args.milestone_id}): <title>\"")

def _cmd_milestone_confirm(args: argparse.Namespace) -> None:
    from ..core.state.milestone_ops import confirm_milestone_acceptance
    result = confirm_milestone_acceptance(
        str(Path.cwd()),
        args.milestone_id,
        confirmed_by=getattr(args, "confirmed_by", "user") or "user",
        summary=args.summary,
    )
    print(f"Milestone acceptance: {args.milestone_id} confirmed={result['confirmed']}")
    for blocker in result.get("blockers", []) or []:
        print(f"  - {blocker}")
    if not result.get("confirmed"):
        raise SystemExit(1)

def _cmd_milestone_integration_test(args: argparse.Namespace) -> None:
    from ..core.state.milestone_ops import record_milestone_integration
    def _g(key, default=""):
        return getattr(args, key, default)
    def _gl(key, default=None):
        return getattr(args, key, default)
    commands = []
    cmd_list = _gl("command") or []
    for c in cmd_list:
        cmd, _, out = c.partition(":::")
        commands.append({"command": cmd.strip(), "output_summary": out.strip()})
    function_traces = []
    for item in _gl("function_trace") or []:
        parts = item.split("::", 4)
        if len(parts) < 4:
            print(
                "Integration test blocked: --function-trace requires "
                "FILE::FUNCTION::CALLERS::STATUS[::REASON]",
                file=sys.stderr,
            )
            raise SystemExit(1)
        file_path, function, callers, status = (part.strip() for part in parts[:4])
        reason = parts[4].strip() if len(parts) > 4 else ""
        function_traces.append({
            "file": file_path,
            "function": function,
            "callers": [c.strip() for c in callers.split(",") if c.strip()],
            "status": status,
            "reason": reason,
        })
    try:
        result = record_milestone_integration(
            str(Path.cwd()),
            _g("milestone_id"),
            status=_g("status"),
            commands=commands or None,
            summary=_g("summary"),
            failed_points=_gl("failed_point"),
            coverage_mode=_g("coverage_mode"),
            main_path_status=_g("main_path_status"),
            source_files=_gl("source_file"),
            accounted_files=_gl("accounted_file"),
            function_traces=function_traces or None,
        )
    except ValueError as e:
        print(f"Integration test blocked: {e}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Integration test recorded: {_g('milestone_id')} status={_g('status')}")

def _cmd_milestone_arch_review(args: argparse.Namespace) -> None:
    from ..core.state.milestone_ops import record_milestone_arch_review
    def _g(key, default=""):
        return getattr(args, key, default)
    def _gl(key, default=None):
        return getattr(args, key, default)
    iface = []
    for i in _gl("interface") or []:
        parts = i.split("→", 1)
        from_g = parts[0].strip() if parts else ""
        to_g = parts[1].strip() if len(parts) > 1 else ""
        iface.append({"from_goal": from_g, "to_goal": to_g, "status": "intact"})
    issues = []
    for item in _gl("issue") or []:
        severity, sep, description = item.partition(":::")
        if not sep:
            print("Architecture review blocked: --issue requires SEVERITY:::DESCRIPTION", file=sys.stderr)
            raise SystemExit(1)
        issues.append({"severity": severity.strip().lower(), "description": description.strip(), "disposition": "open"})
    try:
        result = record_milestone_arch_review(
            str(Path.cwd()),
            _g("milestone_id"),
            status=_g("status"),
            interface_integrity=iface or None,
            cross_goal_issues=issues or None,
            notes=_g("notes"),
            resolution=_g("resolution"),
        )
    except ValueError as e:
        print(f"Architecture review blocked: {e}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Architecture review recorded: {_g('milestone_id')} status={_g('status')}")

def _update_milestone_md(milestone_id: str, plan_ids=None, task_ids=None,
                        status: str = "", summary: str = "") -> None:
    """Update Milestone.md frontmatter fields, then sync to JSON."""
    from ..core.index_ops import parse_md, write_narrative_doc, sync_index
    ms_doc = Path.cwd() / ".aiwf" / "milestones" / f"{milestone_id}.md"
    if not ms_doc.exists():
        return
    fm, body = parse_md(ms_doc)
    if fm is None:
        return
    if plan_ids is not None:
        fm["plan_ids"] = list(plan_ids)
    if task_ids is not None:
        fm["task_ids"] = list(task_ids)
    if status:
        fm["status"] = status
    if summary:
        fm.setdefault("closure_summary", summary)
    write_narrative_doc(ms_doc, fm, body)
    sync_index(str(Path.cwd()))

def _cmd_milestone_link_plan(args: argparse.Namespace) -> None:
    from ..core.state.milestone_ops import link_milestone_plan
    result = link_milestone_plan(str(Path.cwd()), args.milestone_id, args.plan_id)
    if result.get("linked"):
        from ..core.state.milestone_ops import get_milestone
        ms = get_milestone(str(Path.cwd()), args.milestone_id)
        _update_milestone_md(args.milestone_id, plan_ids=ms.get("plan_ids", []))
    print(f"Milestone link-plan: {args.milestone_id} <- {args.plan_id} linked={result.get('linked', False)}")

def _cmd_milestone_unlink_plan(args: argparse.Namespace) -> None:
    from ..core.state.milestone_ops import unlink_milestone_plan
    result = unlink_milestone_plan(str(Path.cwd()), args.milestone_id, args.plan_id)
    if result.get("unlinked"):
        from ..core.state.milestone_ops import get_milestone
        ms = get_milestone(str(Path.cwd()), args.milestone_id)
        _update_milestone_md(args.milestone_id, plan_ids=ms.get("plan_ids", []))
    print(f"Milestone unlink-plan: {args.milestone_id} -/-> {args.plan_id} unlinked={result.get('unlinked', False)}")

def _cmd_milestone_link_task(args: argparse.Namespace) -> None:
    from ..core.state.milestone_ops import link_milestone_task
    result = link_milestone_task(str(Path.cwd()), args.milestone_id, args.task_id)
    if result.get("linked"):
        from ..core.state.milestone_ops import get_milestone
        ms = get_milestone(str(Path.cwd()), args.milestone_id)
        _update_milestone_md(args.milestone_id, task_ids=ms.get("task_ids", []))
    print(f"Milestone link-task: {args.milestone_id} <- {args.task_id} linked={result.get('linked', False)}")

def _cmd_milestone_unlink_task(args: argparse.Namespace) -> None:
    from ..core.state.milestone_ops import unlink_milestone_task
    result = unlink_milestone_task(str(Path.cwd()), args.milestone_id, args.task_id)
    if result.get("unlinked"):
        from ..core.state.milestone_ops import get_milestone
        ms = get_milestone(str(Path.cwd()), args.milestone_id)
        _update_milestone_md(args.milestone_id, task_ids=ms.get("task_ids", []))
    print(f"Milestone unlink-task: {args.milestone_id} -/-> {args.task_id} unlinked={result.get('unlinked', False)}")

def _cmd_milestone_help(args: argparse.Namespace) -> None:
    print("AIWF Milestone — node and acceptance")
    print()
    print("Node:")
    print("  aiwf milestone create MS-001 --title '...'")
    print("  aiwf milestone show MS-001")
    print("  aiwf milestone list")
    print("  aiwf milestone cancel MS-001 --reason '...'")
    print("  aiwf milestone link-plan MS-001 PLAN-001")
    print("  aiwf milestone unlink-plan MS-001 PLAN-001")
    print("  aiwf milestone link-task MS-001 TASK-001")
    print("  aiwf milestone unlink-task MS-001 TASK-001")
    print()
    print("Acceptance (human confirm required):")
    print("  aiwf milestone integration-test MS-001 --status passed --coverage-mode end_to_end_flow --main-path-status passed --command '...'")
    print("  aiwf milestone arch-review MS-001 --status intact --notes '...'")
    print("  aiwf milestone assess MS-001 --verdict PASS --summary '...'")
    print("  aiwf milestone confirm MS-001 --summary '...'     — only after human review")
    print("  aiwf milestone close MS-001")
