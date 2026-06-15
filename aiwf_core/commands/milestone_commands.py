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
            goal_id=args.goal_id or "",
            title=args.title or "",
            status=args.status or "pending",
            intent=args.intent or "",
            plan_ids=args.plan_ids or None,
            task_ids=args.task_ids or None,
            covered_goal_ids=getattr(args, "covered_goal_ids", None) or None,
            mission_id=getattr(args, "mission_id", "") or "",
            advance_policy=args.advance_policy or "",
            checkpoint_level=args.checkpoint_level or "",
        )
    except ValueError as e:
        print(f"Milestone create blocked: {e}", file=sys.stderr)
        raise SystemExit(1)
    m = result["milestone"]
    print(f"Milestone: {m['milestone_id']} status={m['status']}")
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
    rollup = m.get("evidence_rollup", {}) or {}
    print(f"  Rollup: {rollup.get('summary', '') or '(none)'}")
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


def _cmd_milestone_update(args: argparse.Namespace) -> None:
    from ..core.state.milestone_ops import upsert_milestone
    try:
        result = upsert_milestone(
            str(Path.cwd()),
            args.milestone_id,
            goal_id=args.goal_id or "",
            title=args.title or "",
            status=args.status or "",
            intent=args.intent or "",
            plan_ids=args.plan_ids or None,
            task_ids=args.task_ids or None,
            advance_policy=args.advance_policy or "",
            checkpoint_level=args.checkpoint_level or "",
        )
    except ValueError as e:
        print(f"Milestone update blocked: {e}", file=sys.stderr)
        raise SystemExit(1)
    m = result["milestone"]
    print(f"Milestone updated: {m['milestone_id']} status={m['status']}")


def _cmd_milestone_assess(args: argparse.Namespace) -> None:
    from ..core.state.milestone_ops import record_milestone_assessment
    try:
        result = record_milestone_assessment(
            str(Path.cwd()),
            args.milestone_id,
            verdict=args.verdict,
            summary=args.summary,
            evidence_ids=args.evidence_ids or None,
            coherence_check=args.coherence_check or "",
            open_gaps=args.open_gaps or None,
            residual_risks=args.residual_risks or None,
            next_recommendation=args.next_recommendation or "",
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


def _cmd_milestone_confirm(args: argparse.Namespace) -> None:
    from ..core.state.milestone_ops import confirm_milestone_acceptance
    result = confirm_milestone_acceptance(
        str(Path.cwd()),
        args.milestone_id,
        confirmed_by=args.confirmed_by,
        summary=args.summary,
    )
    print(f"Milestone acceptance: {args.milestone_id} confirmed={result['confirmed']}")
    for blocker in result.get("blockers", []) or []:
        print(f"  - {blocker}")
    if not result.get("confirmed"):
        raise SystemExit(1)


def _cmd_milestone_integration_test(args: argparse.Namespace) -> None:
    from ..core.state.milestone_ops import record_milestone_integration
    commands = []
    if args.command:
        for c in args.command:
            cmd, _, out = c.partition(":::")
            commands.append({"command": cmd.strip(), "output_summary": out.strip()})
    function_traces = []
    for item in args.function_trace or []:
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
            args.milestone_id,
            status=args.status,
            commands=commands or None,
            summary=args.summary or "",
            failed_points=args.failed_point or None,
            coverage_mode=args.coverage_mode or "",
            main_path_status=args.main_path_status or "",
            source_files=args.source_file or None,
            accounted_files=args.accounted_file or None,
            function_traces=function_traces or None,
        )
    except ValueError as e:
        print(f"Integration test blocked: {e}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Integration test recorded: {args.milestone_id} status={args.status}")

def _cmd_milestone_arch_review(args: argparse.Namespace) -> None:
    from ..core.state.milestone_ops import record_milestone_arch_review
    iface = []
    if args.interface:
        for i in args.interface:
            parts = i.split("→", 1)
            from_g = parts[0].strip() if parts else ""
            to_g = parts[1].strip() if len(parts) > 1 else ""
            iface.append({"from_goal": from_g, "to_goal": to_g, "status": "intact"})
    issues = []
    for item in args.issue or []:
        severity, sep, description = item.partition(":::")
        if not sep:
            print(
                "Architecture review blocked: --issue requires SEVERITY:::DESCRIPTION",
                file=sys.stderr,
            )
            raise SystemExit(1)
        issues.append({
            "severity": severity.strip().lower(),
            "description": description.strip(),
            "disposition": "open",
        })
    try:
        result = record_milestone_arch_review(
            str(Path.cwd()),
            args.milestone_id,
            status=args.status,
            interface_integrity=iface or None,
            cross_goal_issues=issues or None,
            notes=args.notes or "",
            resolution=args.resolution or "",
            resolution_evidence_ids=args.resolution_evidence_id or None,
        )
    except ValueError as e:
        print(f"Architecture review blocked: {e}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Architecture review recorded: {args.milestone_id} status={args.status}")

def _cmd_milestone_help(args: argparse.Namespace) -> None:
    print("AIWF Milestone Optional Node")
    print()
    print("Milestones are stable version checkpoints — cross-Goal integration")
    print("verification + architecture integrity review + snapshot + git tag.")
    print()
    print("Available subcommands:")
    print("  aiwf milestone create MS-001 --goal-id GOAL-001 --title '...'")
    print("  aiwf milestone list")
    print("  aiwf milestone show MS-001")
    print("  aiwf milestone update MS-001 --status active")
    print("  aiwf milestone assess MS-001 --verdict PASS --summary '...'")
    print("  aiwf milestone integration-test MS-001 --status passed --command '...'")
    print("  aiwf milestone arch-review MS-001 --status intact --interface 'AUTH→BACKEND'")
    print("  aiwf milestone confirm MS-001 --summary 'User accepted stage delivery'")
    print("  aiwf milestone close MS-001")
