"""CLI handlers for implementation, testing, and review records."""
from __future__ import annotations

import argparse
import json
import re
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


def _parse_paired_verification_results(
    commands: list[str], raw_results: list[str],
) -> list[dict]:
    if not raw_results:
        return []
    if len(commands) != len(raw_results):
        raise ValueError("--result must appear once for each --command")
    results = []
    for command, raw in zip(commands, raw_results):
        parts = [part.strip() for part in str(raw).split(":::", 2)]
        if len(parts) != 3:
            raise ValueError(
                "--result must be 'expected:::observed:::matched|mismatched'"
            )
        match_token = parts[2].lower()
        if match_token not in ("matched", "mismatched"):
            raise ValueError("--result must end with matched or mismatched")
        results.append({
            "command": command,
            "expected": parts[0],
            "observed": parts[1],
            "matched": match_token == "matched",
        })
    return results


def _task_verification_results(
    base: Path,
    task_id: str,
    commands: list[str],
    observed_results: list[str],
    status: str,
) -> list[dict]:
    """Build ordinary verification results from the Task contract.

    The Task already owns expected observables. Repeating them in a four-part
    shell argument adds noise without adding evidence.
    """
    if not observed_results:
        return []
    if len(observed_results) != len(commands):
        raise ValueError("--observed must appear once for each --command")
    if status != "passed":
        raise ValueError(
            "--observed is available only with --status passed; use "
            "--verification-result for failed or mixed results"
        )

    from ..core.task_ledger import load_ledger
    from ..core.task_proof import read_task_proof_contract

    task = next(
        (
            item for item in load_ledger(str(base)).get("tasks", []) or []
            if isinstance(item, dict) and str(item.get("id") or "") == task_id
        ),
        None,
    )
    if not task:
        raise ValueError(f"active Task not found: {task_id}")
    contract = read_task_proof_contract(str(base), task)
    if not contract or not contract.schema_recognized:
        raise ValueError("--observed requires a recognized Task.md proof contract")

    def normalize(command: str) -> str:
        return re.sub(r"\s+", " ", command.strip()).strip("` ")

    expected_by_command = {
        normalize(item.command): item
        for item in contract.verification_commands
    }
    results = []
    positional = len(commands) == len(contract.verification_commands)
    for index, (command, observed) in enumerate(zip(commands, observed_results)):
        contract_item = expected_by_command.get(normalize(command))
        if contract_item is None and positional:
            contract_item = contract.verification_commands[index]
        if contract_item is None:
            raise ValueError(
                "--observed only records a Task.md Verification Command; "
                "use --verification-result for an extra probe"
            )
        if not str(observed).strip():
            raise ValueError("--observed must not be empty")
        results.append({
            "command": contract_item.command,
            "expected": contract_item.expected,
            "observed": observed,
            "matched": True,
        })
    return results


def _cmd_record_testing(args: argparse.Namespace) -> None:
    from ..core.state_ops import record_testing

    try:
        task_id = _require_role_dispatch(Path.cwd(), "tester", args.task_id)
        if args.observed_results and args.verification_results:
            raise ValueError("use either --observed or --verification-result, not both")
        verification_results = _parse_verification_results(args.verification_results or [])
        verification_results = verification_results or _task_verification_results(
            Path.cwd(), task_id, args.commands or [], args.observed_results or [], args.status,
        )
        recorded_commands = (
            [item["command"] for item in verification_results]
            if args.observed_results
            else (args.commands or [])
        )
        if args.status == "passed" and not args.commands:
            raise ValueError("passed testing requires at least one exact --command")
        if args.status == "failed" and not args.summary:
            raise ValueError("failed testing requires a concise --summary")
        testing = record_testing(
            str(Path.cwd()),
            status=args.status,
            commands=recorded_commands or None,
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
