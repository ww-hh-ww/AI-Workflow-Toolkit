"""CLI handlers for Executor construction evidence and Reviewer judgments."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..core.construction_evidence import load_construction_proof_file


ROLE_SUBAGENTS = {
    "executor": ("executor_required", "aiwf-executor", "aiwf-implement"),
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
    from ..core.project_root import has_codex_adapter, in_codex_session

    codex = in_codex_session() and has_codex_adapter(control)
    skill = ("$" if codex else "/") + skill_name
    raise ValueError(
        f"{role} record requires a task-scoped {subagent_type} dispatch. "
        f"Load {skill} and dispatch {subagent_type} before recording."
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


def _construction_verification_results(
    base: Path,
    task_id: str,
    observed_results: list[str],
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
            "recorded observations need an explicit --verdict; Executor must judge "
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
                "Task.md Verification Commands need an explicit ID column before "
                "Executor construction evidence can be recorded"
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
            raise ValueError("critical/high observations require needs_change or rejected")
        if args.result in ("needs_change", "rejected") and not args.blockers:
            raise ValueError("a blocking review requires at least one --blocker")
        if args.result == "needs_experiment" and (
            not args.experiment_id or not args.experiment_question
        ):
            raise ValueError("needs_experiment requires --experiment-id and --experiment-question")
        review = record_review(
            str(root),
            result=args.result,
            closure_allowed=args.result == "accepted" and not args.blockers,
            blockers=args.blockers or None,
            adversarial_observations=observations or None,
            cleanup_status=args.cleanup_status or "",
            structure_status=args.structure_status or "",
            summary=args.summary or "",
            experiment_request={
                "experiment_id": args.experiment_id,
                "question": args.experiment_question,
                "hypothesis": args.experiment_hypothesis or "",
            } if args.result == "needs_experiment" else None,
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
        executed_commands = list(getattr(args, "executed_commands", []) or [])
        if args.proof_file and (
            args.observed_results or args.observed_files or args.checks
            or args.verdicts or args.bases or executed_commands
        ):
            raise ValueError("--proof-file cannot be combined with inline verification arguments")
        if args.observed_results and args.observed_files:
            raise ValueError("use either --observed or --observed-file, not both")
        if args.proof_file:
            proof_entries = load_construction_proof_file(
                str(_invocation_file(args.proof_file, root))
            )
            verification_results = _construction_verification_results(
                root, task_id,
                [item["observed"] for item in proof_entries],
                checks=[item["verification_id"] for item in proof_entries],
                verdicts=[item["verdict"] for item in proof_entries],
                bases=[item.get("basis", "") for item in proof_entries],
                executed_commands=[item.get("executed_command", "") for item in proof_entries],
            )
        else:
            observed_results = list(args.observed_results or [])
            if args.observed_files:
                observed_results = []
                for observed_file in args.observed_files:
                    try:
                        observed_results.append(
                            _invocation_file(observed_file, root).read_text(encoding="utf-8")
                        )
                    except OSError as exc:
                        raise ValueError(f"cannot read observed file {observed_file}: {exc}") from exc
            verification_results = _construction_verification_results(
                root, task_id, observed_results,
                checks=args.checks, verdicts=args.verdicts or [], bases=args.bases or [],
                executed_commands=executed_commands,
            )
        implementation = record_implementation(
            str(root),
            summary=args.summary,
            verification_results=verification_results,
            task_id=task_id,
        )
    except ValueError as exc:
        print(f"Implementation record blocked: {exc}", file=sys.stderr)
        raise SystemExit(1)

    print(f"Implementation recorded: {implementation['task_id']}")
    print(f"  Implementation ref: {implementation['implementation_ref']}")
    print(f"  Changed files: {len(implementation.get('changed_files', []) or [])}")
    print(f"  V evidence: {len(implementation.get('verification_results', []) or [])}")
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
