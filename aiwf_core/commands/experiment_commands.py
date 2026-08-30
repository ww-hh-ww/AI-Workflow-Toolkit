"""CLI handlers for disposable empirical experiments."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _blocked(label: str, exc: ValueError) -> None:
    print(f"Experiment {label} blocked: {exc}", file=sys.stderr)
    raise SystemExit(1)


def _cmd_experiment_open(args: argparse.Namespace) -> None:
    from ..core.experiment_records import open_experiment

    try:
        record = open_experiment(
            str(Path.cwd()), args.experiment_id, args.question,
            hypothesis=args.hypothesis or "", task_id=args.task_id or "",
            plan_id=args.plan_id or "", subject_ref=args.subject_ref or "",
            timing=args.timing or "",
        )
    except ValueError as exc:
        _blocked("open", exc)
    print(f"Experiment opened: {record['experiment_id']}")
    print(f"  Subject ref: {record['subject_ref']}")
    print(f"  Scope: {record['scope']['kind']} {record['scope']['id']}")


def _cmd_experiment_start(args: argparse.Namespace) -> None:
    from ..core.experiment_records import start_experiment

    try:
        record = start_experiment(str(Path.cwd()), args.experiment_id)
    except ValueError as exc:
        _blocked("start", exc)
    print(f"Experiment running: {record['experiment_id']}")
    print(f"  Worktree: {record['worktree_path']}")
    print(f"  Subject ref: {record['subject_ref']}")


def _cmd_experiment_record(args: argparse.Namespace) -> None:
    from ..core.agent_runtime import running_dispatches
    from ..core.experiment_records import record_experiment
    from ..core.worktree_context import resolve_control_root

    try:
        control = resolve_control_root(Path.cwd())
        from ..core.project_root import codex_dispatch_markers_advisory

        if not codex_dispatch_markers_advisory(control):
            matching = [
                item for item in running_dispatches(control)
                if item.get("subagent_type") == "aiwf-experimenter"
                and item.get("experiment_id") == args.experiment_id
            ]
            if len(matching) != 1:
                raise ValueError(
                    "experiment evidence requires one running aiwf-experimenter dispatch "
                    f"bound to {args.experiment_id}"
                )
        record = record_experiment(
            str(Path.cwd()), args.experiment_id, args.conclusion, args.summary,
            commands=args.commands or [], observations=args.observations or [],
            promotion_candidates=args.promotion_candidates or [],
        )
    except ValueError as exc:
        _blocked("record", exc)
    print(f"Experiment recorded: {record['experiment_id']} conclusion={record['conclusion']}")
    print(f"  Experiment ref: {record['experiment_ref']}")
    print(f"  Changed files: {len(record.get('changed_files', []) or [])}")


def _cmd_experiment_finish(args: argparse.Namespace) -> None:
    from ..core.experiment_records import finish_experiment

    try:
        record = finish_experiment(str(Path.cwd()), args.experiment_id)
    except ValueError as exc:
        _blocked("finish", exc)
    print(f"Experiment closed: {record['experiment_id']}")
    print("  Disposable worktree removed; snapshot and evidence retained.")


def _cmd_experiment_disposition(args: argparse.Namespace) -> None:
    from ..core.experiment_records import disposition_experiment

    try:
        record = disposition_experiment(
            str(Path.cwd()), args.experiment_id, args.decision, args.reason,
        )
    except ValueError as exc:
        _blocked("disposition", exc)
    print(f"Experiment disposition recorded: {record['experiment_id']}")
    print(f"  Decision: {record['disposition']['decision']}")
    print(f"  Reason: {record['disposition']['reason']}")


def _cmd_experiment_show(args: argparse.Namespace) -> None:
    from ..core.experiment_records import load_experiment

    try:
        record = load_experiment(str(Path.cwd()), args.experiment_id)
    except ValueError as exc:
        _blocked("show", exc)
    if not record:
        _blocked("show", ValueError(f"experiment not found: {args.experiment_id}"))
    print(f"Experiment: {record['experiment_id']}")
    print(f"  Status: {record.get('status')}")
    scope = record.get("scope", {}) or {}
    print(f"  Scope: {scope.get('kind')}:{scope.get('id')}")
    print(f"  Timing: {record.get('timing')}")
    print(f"  Question: {record.get('question')}")
    print(f"  Hypothesis: {record.get('hypothesis') or '(none)'}")
    print(f"  Subject ref: {record.get('subject_ref')}")
    print(f"  Worktree: {record.get('worktree_path') or '(none)'}")
    print(f"  Experiment ref: {record.get('experiment_ref') or '(none)'}")
    for command in record.get("commands", []) or []:
        print(f"  Command: {command}")
    for observation in record.get("observations", []) or []:
        print(f"  Observation: {observation}")
    if record.get("conclusion"):
        print(f"  Conclusion: {record['conclusion']}")
        print(f"  Summary: {record.get('summary')}")
    for candidate in record.get("promotion_candidates", []) or []:
        print(f"  Promotion candidate: {candidate}")
    if record.get("stale_reason"):
        print(f"  Stale reason: {record['stale_reason']}")
    disposition = record.get("disposition", {}) or {}
    print(
        "  Disposition: "
        f"{disposition.get('status') or 'not_recorded'}"
        + (f" ({disposition.get('decision')})" if disposition.get("decision") else "")
    )
    if disposition.get("reason"):
        print(f"  Disposition reason: {disposition['reason']}")


def _cmd_experiment_list(args: argparse.Namespace) -> None:
    from ..core.experiment_records import list_experiments

    if args.task_id and args.plan_id:
        _blocked("list", ValueError("use only one of --task-id or --plan-id"))
    records = list_experiments(
        str(Path.cwd()), task_id=args.task_id or "", plan_id=args.plan_id or "",
    )
    print(f"Experiments: {len(records)}")
    for record in records:
        scope = record.get("scope", {}) or {}
        print(
            f"  {record.get('experiment_id')} | {record.get('status')} | "
            f"{scope.get('kind')}:{scope.get('id')} | {record.get('question')}"
        )
