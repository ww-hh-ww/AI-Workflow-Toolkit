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


def _invocation_root() -> Path:
    from ..core.project_root import resolve_invocation_root

    return resolve_invocation_root()


def _invocation_file(raw_path: str, root: Path) -> Path:
    path = Path(raw_path).expanduser()
    return path if path.is_absolute() else root / path


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
        if match_token not in ("matched", "mismatched", "blocked"):
            raise ValueError("verification result must end with matched, mismatched, or blocked")
        results.append({
            "command": parts[0],
            "expected": parts[1],
            "observed": parts[2],
            "matched": match_token == "matched",
            "verdict": match_token,
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
        if match_token not in ("matched", "mismatched", "blocked"):
            raise ValueError("--result must end with matched, mismatched, or blocked")
        results.append({
            "command": command,
            "expected": parts[0],
            "observed": parts[1],
            "matched": match_token == "matched",
            "verdict": match_token,
        })
    return results


def _load_testing_proof_file(path: str) -> list[dict]:
    proof_path = Path(path).expanduser()
    try:
        payload = json.loads(proof_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read proof file {proof_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"proof file is not valid JSON: {proof_path}: {exc}") from exc
    if isinstance(payload, dict):
        payload = payload.get("results", [])
    if not isinstance(payload, list) or not payload:
        raise ValueError("proof file must contain a non-empty JSON array or {\"results\": [...]}")
    results = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"proof file result {index} must be an object")
        verification_id = str(
            item.get("verification_id") or item.get("check") or item.get("id") or ""
        ).strip()
        if not verification_id:
            raise ValueError(f"proof file result {index} is missing verification_id/check")
        observed = item.get("observed", "")
        observed_file = str(item.get("observed_file") or "").strip()
        if observed_file:
            try:
                observed = Path(observed_file).expanduser().read_text(encoding="utf-8")
            except OSError as exc:
                raise ValueError(f"cannot read observed_file for {verification_id}: {exc}") from exc
        verdict = str(item.get("verdict") or "").strip().lower()
        if verdict not in {"matched", "mismatched", "blocked"}:
            raise ValueError(f"proof file result {verification_id} has invalid verdict")
        if verdict != "blocked" and not str(observed).strip():
            raise ValueError(f"proof file result {verification_id} has empty observed output")
        if verdict == "blocked" and not str(item.get("basis") or item.get("reason") or "").strip():
            raise ValueError(f"blocked proof result {verification_id} requires basis/reason")
        results.append({
            "verification_id": verification_id,
            "observed": str(observed),
            "verdict": verdict,
            "basis": str(item.get("basis") or item.get("reason") or "").strip(),
            "executed_command": str(item.get("executed_command") or "").strip(),
        })
    return results


def _task_verification_results(
    base: Path,
    task_id: str,
    observed_results: list[str],
    status: str,
    checks: list[str] | None = None,
    verdicts: list[str] | None = None,
    bases: list[str] | None = None,
    executed_commands: list[str] | None = None,
) -> list[dict]:
    """Build ordinary verification results from the Task contract.

    The Task already owns expected observables. Repeating them in a four-part
    shell argument adds noise without adding evidence.
    """
    if not observed_results and not checks and not executed_commands:
        return []
    checks = list(checks or [])
    verdicts = list(verdicts or [])
    bases = list(bases or [])
    executed_commands = list(executed_commands or [])
    if not checks:
        raise ValueError("Task proof recording requires at least one --check ID")
    if len(set(checks)) != len(checks):
        raise ValueError("each Task proof --check ID may appear only once per record")
    if len(observed_results) != len(checks):
        raise ValueError("--observed/--observed-file must appear once for each --check")
    if executed_commands and len(executed_commands) != len(checks):
        raise ValueError("--executed-command must appear once for each --check")
    if not verdicts:
        raise ValueError(
            "recorded observations need an explicit --verdict; Tester must judge "
            "matched, mismatched, or blocked"
        )
    if len(verdicts) != len(checks):
        raise ValueError("--verdict must appear once for each --check")
    if bases and len(bases) != len(verdicts):
        raise ValueError("--basis must appear once for each --check")

    from ..core.task_ledger import load_ledger
    from ..core.task_proof import (
        fix_loop_verification_commands,
        read_task_proof_contract,
    )

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
        raise ValueError("--check requires a recognized Task.md proof contract")

    expected_by_id = {
        item.verification_id: item for item in contract.verification_commands
    }
    expected_by_id.update({
        item.verification_id: item
        for item in fix_loop_verification_commands(str(base), task_id)
    })
    results = []
    for index, (identity, observed, verdict) in enumerate(
        zip(checks, observed_results, verdicts)
    ):
        contract_item = expected_by_id.get(identity)
        if contract_item is None:
            raise ValueError(
                f"unknown proof check: {identity}. Use a Task V-* or declared FIX-* ID."
            )
        if not contract_item.explicit_id:
            raise ValueError(
                "Task.md Verification Commands need an explicit ID column before testing "
                "can be recorded"
            )
        verdict = str(verdict).strip().lower()
        if verdict not in {"matched", "mismatched", "blocked"}:
            raise ValueError("--verdict must be matched, mismatched, or blocked")
        basis = bases[index] if bases else ""
        if verdict != "blocked" and not str(observed).strip():
            raise ValueError("--observed must not be empty")
        if verdict == "blocked" and not str(basis).strip():
            raise ValueError("blocked verification requires --basis explaining the environment limit")
        result = {
            "verification_id": contract_item.verification_id,
            "command": contract_item.command,
            "expected": contract_item.expected,
            "observed": observed,
            "matched": verdict == "matched",
            "verdict": verdict,
        }
        executed_command = executed_commands[index].strip() if executed_commands else ""
        if executed_command:
            result["executed_command"] = executed_command
        if str(basis).strip():
            result["basis"] = str(basis).strip()
        results.append(result)
    return results


def _cmd_record_testing(args: argparse.Namespace) -> None:
    from ..core.state_ops import record_testing

    try:
        root = _invocation_root()
        executed_commands = list(getattr(args, "executed_commands", []) or [])
        task_id = _require_role_dispatch(root, "tester", args.task_id)
        if args.proof_file and (
            args.observed_results or args.observed_files or args.checks
            or args.verdicts or args.bases or executed_commands
        ):
            raise ValueError("--proof-file cannot be combined with inline verification arguments")
        if args.observed_results and args.observed_files:
            raise ValueError("use either --observed or --observed-file, not both")
        if args.proof_file:
            proof_entries = _load_testing_proof_file(
                str(_invocation_file(args.proof_file, root))
            )
            verification_results = _task_verification_results(
                root, task_id,
                [item["observed"] for item in proof_entries], args.status,
                checks=[item["verification_id"] for item in proof_entries],
                verdicts=[item["verdict"] for item in proof_entries],
                bases=[item.get("basis", "") for item in proof_entries],
                executed_commands=[item.get("executed_command", "") for item in proof_entries],
            )
        else:
            if not args.checks:
                raise ValueError(
                    "record testing requires declared --check IDs; update Task.md's "
                    "Verification Commands table before recording"
                )
            observed_results = list(args.observed_results or [])
            if args.observed_files:
                observed_results = []
                for observed_file in args.observed_files:
                    try:
                        observed_results.append(_invocation_file(observed_file, root).read_text(encoding="utf-8"))
                    except OSError as exc:
                        raise ValueError(f"cannot read observed file {observed_file}: {exc}") from exc
            verification_results = _task_verification_results(
                root, task_id, observed_results, args.status,
                checks=args.checks, verdicts=args.verdicts or [], bases=args.bases or [],
                executed_commands=executed_commands,
            )
        recorded_commands = [item["command"] for item in verification_results]
        if args.status == "passed" and not recorded_commands:
            raise ValueError(
                "passed testing requires at least one --check with observed output"
            )
        if args.status == "failed" and not args.summary:
            raise ValueError("failed testing requires a concise --summary")
        testing = record_testing(
            str(root),
            status=args.status,
            commands=recorded_commands or None,
            coverage_summary=args.summary or "",
            failure_summary=args.summary if args.status == "failed" else "",
            failed_commands=recorded_commands if args.status == "failed" else None,
            verification_results=verification_results or None,
            task_id=task_id,
        )
    except ValueError as exc:
        print(f"Testing record blocked: {exc}", file=sys.stderr)
        raise SystemExit(1)

    print(f"Testing recorded: status={testing.get('status', args.status)}")
    if testing.get("tested_ref"):
        print(f"  Tested ref: {testing['tested_ref']}")
    if getattr(args, "checks", None):
        print(f"  Checks: {len(args.checks)}")
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
        root = _invocation_root()
        task_id = _require_role_dispatch(root, "reviewer", args.task_id)
        observations = _parse_observations(args.adversarial_observations or [])
        if args.result == "accepted" and any(
            item["severity"] in ("critical", "high") for item in observations
        ):
            raise ValueError("critical/high observations require needs_fix or rejected")
        if args.result in ("needs_fix", "rejected") and not args.blockers:
            raise ValueError("a blocking review requires at least one --blocker")
        review = record_review(
            str(root),
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
        root = _invocation_root()
        task_id = _require_role_dispatch(root, "executor", args.task_id)
        implementation = record_implementation(
            str(root),
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
