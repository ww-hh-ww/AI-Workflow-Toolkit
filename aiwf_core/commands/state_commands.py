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


def _require_role_dispatch(base: Path, role: str) -> None:
    """Fail early when a required role has not been dispatched for this task."""
    requirement = ROLE_SUBAGENTS.get(role)
    if not requirement:
        return
    requirement_key, subagent_type, skill_name = requirement
    try:
        state = json.loads((base / ".aiwf/state/state.json").read_text(encoding="utf-8"))
        tasks = json.loads((base / ".aiwf/state/tasks.json").read_text(encoding="utf-8"))
    except Exception:
        return

    task_id = str(state.get("active_task_id") or "")
    if not task_id:
        return
    task = next(
        (
            item for item in tasks.get("tasks", []) or []
            if isinstance(item, dict) and str(item.get("id") or "") == task_id
        ),
        {},
    )
    if not bool((task.get("requirements", {}) or {}).get(requirement_key, True)):
        return

    dispatch_path = base / ".aiwf/runtime/internal/agent-dispatch.jsonl"
    if dispatch_path.exists():
        for line in dispatch_path.read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(line)
            except Exception:
                continue
            if entry.get("task_id") == task_id and entry.get("subagent_type") == subagent_type:
                return
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
        _require_role_dispatch(Path.cwd(), "tester")
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
        )
    except ValueError as exc:
        print(f"Testing record blocked: {exc}", file=sys.stderr)
        raise SystemExit(1)

    print(f"Testing recorded: status={args.status}")
    if testing.get("tested_ref"):
        print(f"  Tested ref: {testing['tested_ref']}")
    if args.commands:
        print(f"  Commands: {len(args.commands)}")
    if verification_results:
        print(f"  Verification results: {len(verification_results)}")


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
        _require_role_dispatch(Path.cwd(), "reviewer")
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


def _cmd_record_implementation(args: argparse.Namespace) -> None:
    from ..core.state_ops import record_implementation

    try:
        _require_role_dispatch(Path.cwd(), "executor")
        implementation = record_implementation(
            str(Path.cwd()),
            summary=args.summary,
            command=args.command,
            exit_code=args.exit_code,
            task_id=args.task_id,
        )
    except ValueError as exc:
        print(f"Implementation record blocked: {exc}", file=sys.stderr)
        raise SystemExit(1)

    print(f"Implementation recorded: {implementation['task_id']}")
    print(f"  Implementation ref: {implementation['implementation_ref']}")
    print(f"  Changed files: {len(implementation.get('changed_files', []) or [])}")


def _cmd_record_disposition(args: argparse.Namespace) -> None:
    from ..core.state_ops import disposition_adversarial_observation

    try:
        result = disposition_adversarial_observation(
            str(Path.cwd()),
            adv_id=args.observation_id,
            disposition=args.decision,
            reason=args.reason,
            disposed_by="planner",
        )
    except ValueError as exc:
        print(f"Disposition blocked: {exc}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Reviewer observation {result['id']}: {result['disposition']}")


def _cmd_record_help(args: argparse.Namespace) -> None:
    print("AIWF Task Records")
    print()
    print("Available subcommands:")
    print("  aiwf record implementation - record Executor handoff and Git snapshot")
    print("  aiwf record testing        - record one validation pass")
    print("  aiwf record review         - record reviewer judgment")
    print("  aiwf record disposition    - record Planner decision on a finding")
