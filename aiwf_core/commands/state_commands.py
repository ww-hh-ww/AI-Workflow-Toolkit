"""CLI handlers for implementation, testing, and review records."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROLE_SUBAGENTS = {
    "executor": ("executor_required", "aiwf-executor", "aiwf-implement"),
    "tester": ("tester_required", "aiwf-tester", "aiwf-test"),
    "reviewer": ("reviewer_required", "aiwf-reviewer", "aiwf-review"),
}


def _print_record_handoff() -> None:
    print(
        "  Next: return the report you already prepared to the main session. "
        "Do not rerun successful work. The main session runs aiwf status --prompt"
    )


def _require_role_dispatch(base: Path, role: str, task_id: str = "") -> str:
    """Fail early when a required role has not been dispatched for this task."""
    requirement = ROLE_SUBAGENTS.get(role)
    if not requirement:
        return task_id
    requirement_key, subagent_type, skill_name = requirement
    try:
        from ..core.task_ledger import load_ledger, resolve_active_task_id
        from ..core.worktree_context import resolve_control_root
        effective_task = resolve_active_task_id(str(base), task_id)
        tasks = load_ledger(str(base))
        control = resolve_control_root(base)
    except Exception:
        return task_id

    if not effective_task:
        raise ValueError("record requires an active Task ID or an assigned Task worktree")
    task = next(
        (
            item for item in tasks.get("tasks", []) or []
            if isinstance(item, dict) and str(item.get("id") or "") == effective_task
        ),
        {},
    )
    if not bool((task.get("requirements", {}) or {}).get(requirement_key, True)):
        return effective_task

    dispatch_path = control / ".aiwf/runtime/internal/agent-dispatch.jsonl"
    if dispatch_path.exists():
        for line in dispatch_path.read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(line)
            except Exception:
                continue
            if (
                entry.get("task_id") == effective_task
                and entry.get("subagent_type") == subagent_type
            ):
                return effective_task
    raise ValueError(
        f"{role} record requires a task-scoped {subagent_type} dispatch. "
        f"Load /{skill_name} and dispatch {subagent_type} before recording."
    )


def _parse_verification_results(raw_results: list[str]) -> list[dict]:
    results = []
    for raw in raw_results:
        parts = [part.strip() for part in str(raw).split(":::", 3)]
        if len(parts) != 4:
            raise ValueError(
                "--verification-result must be "
                "'command:::expected:::observed:::matched|mismatched'"
            )
        match_token = parts[3].lower()
        if match_token not in ("matched", "mismatched"):
            raise ValueError("verification result must end with matched or mismatched")
        results.append({
            "command": parts[0],
            "expected": parts[1],
            "observed": parts[2],
            "matched": match_token == "matched",
        })
    return results


def _cmd_record_testing(args: argparse.Namespace) -> None:
    from ..core.state_ops import record_testing

    try:
        task_id = _require_role_dispatch(Path.cwd(), "tester", args.task_id)
        verification_results = _parse_verification_results(args.verification_results or [])
        if args.status == "passed" and not args.commands:
            raise ValueError("passed testing requires at least one exact --command")
        if args.status == "failed" and not args.summary:
            raise ValueError("failed testing requires a concise --summary")
        testing = record_testing(
            str(Path.cwd()),
            status=args.status,
            commands=args.commands or None,
            coverage_summary=args.summary or "",
            failure_summary=args.summary if args.status == "failed" else "",
            failed_commands=args.commands if args.status == "failed" else None,
            verification_results=verification_results or None,
            task_id=task_id,
        )
    except ValueError as exc:
        print(f"Testing record blocked: {exc}", file=sys.stderr)
        raise SystemExit(1)

    print(f"Testing recorded: status={testing.get('status', args.status)}")
    if testing.get("tested_ref"):
        print(f"  Tested ref: {testing['tested_ref']}")
    if args.commands:
        print(f"  Commands: {len(args.commands)}")
    if verification_results:
        print(f"  Verification results: {len(verification_results)}")
    if testing.get("fix_loop_resolved"):
        print("  Fix-loop: resolved by this verification")
    elif testing.get("fix_loop_pending_reason"):
        print(f"  Fix-loop remains open: {testing['fix_loop_pending_reason'][:240]}")
    if testing.get("status") == "partial":
        from ..core.task_proof import testing_proof_gaps

        missing = testing_proof_gaps(testing.get("proof_validation", {}) or {})
        if missing:
            print(f"  Missing proof: {', '.join(missing[:5])}")
    _print_record_handoff()


def _parse_observations(raw_observations: list[str]) -> list[dict]:
    observations = []
    valid_severities = {"critical", "high", "warn", "low"}
    for index, raw in enumerate(raw_observations, start=1):
        parts = [part.strip() for part in raw.split(":::", 2)]
        if len(parts) != 3:
            raise ValueError(
                "--adversarial-observations must be 'severity:::kind:::message'"
            )
        severity, kind, message = parts
        if severity not in valid_severities:
            raise ValueError(f"invalid adversarial severity: {severity}")
        observations.append({
            "id": f"ADV-{index:03d}",
            "severity": severity,
            "kind": kind or "review_observation",
            "message": message,
            "disposition": "pending",
        })
    return observations


def _cmd_record_review(args: argparse.Namespace) -> None:
    from ..core.state_ops import record_review

    try:
        task_id = _require_role_dispatch(Path.cwd(), "reviewer", args.task_id)
        observations = _parse_observations(args.adversarial_observations or [])
        if args.result == "accepted" and any(
            item["severity"] in ("critical", "high") for item in observations
        ):
            raise ValueError("critical/high observations require needs_fix or rejected")
        if args.result in ("needs_fix", "rejected") and not args.blockers:
            raise ValueError("a blocking review requires at least one --blocker")
        review = record_review(
            str(Path.cwd()),
            result=args.result,
            closure_allowed=args.result == "accepted" and not args.blockers,
            blockers=args.blockers or None,
            adversarial_observations=observations or None,
            cleanup_status=args.cleanup_status or "",
            structure_status=args.structure_status or "",
            summary=args.summary or "",
            task_id=task_id,
        )
    except ValueError as exc:
        print(f"Review record blocked: {exc}", file=sys.stderr)
        raise SystemExit(1)

    print(f"Review recorded: result={review.get('result')}")
    print(f"  Closure allowed: {review.get('closure_allowed', False)}")
    if review.get("reviewed_ref"):
        print(f"  Reviewed ref: {review['reviewed_ref']}")
    if review.get("blockers"):
        print(f"  Blockers: {len(review['blockers'])}")
    _print_record_handoff()


def _cmd_record_implementation(args: argparse.Namespace) -> None:
    from ..core.state_ops import record_implementation

    try:
        task_id = _require_role_dispatch(Path.cwd(), "executor", args.task_id)
        implementation = record_implementation(
            str(Path.cwd()),
            summary=args.summary,
            command=args.command,
            exit_code=args.exit_code,
            task_id=task_id,
        )
    except ValueError as exc:
        print(f"Implementation record blocked: {exc}", file=sys.stderr)
        raise SystemExit(1)

    print(f"Implementation recorded: {implementation['task_id']}")
    print(f"  Implementation ref: {implementation['implementation_ref']}")
    print(f"  Changed files: {len(implementation.get('changed_files', []) or [])}")
    _print_record_handoff()


def _cmd_record_disposition(args: argparse.Namespace) -> None:
    from ..core.state_ops import disposition_adversarial_observation

    try:
        result = disposition_adversarial_observation(
            str(Path.cwd()),
            adv_id=args.observation_id,
            disposition=args.decision,
            reason=args.reason,
            disposed_by="planner",
            task_id=args.task_id,
        )
    except ValueError as exc:
        print(f"Disposition blocked: {exc}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Reviewer observation {result['id']}: {result['disposition']}")
    print("  Next: run aiwf status --prompt and follow its route")


def _cmd_record_help(args: argparse.Namespace) -> None:
    print("AIWF Task Records")
    print()
    print("Available subcommands:")
    print("  aiwf record implementation - record Executor handoff and Git snapshot")
    print("  aiwf record testing        - record one validation pass")
    print("  aiwf record review         - record reviewer judgment")
    print("  aiwf record disposition    - record Planner decision on a finding")
