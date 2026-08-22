"""CLI handlers for installation, status recovery, and doctor."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..constants import VERSION


def _parse_fixloop_verification(values: list[str]) -> list[dict]:
    obligations = []
    for raw in values:
        parts = [part.strip() for part in str(raw).split(":::", 2)]
        if len(parts) == 1 and parts[0]:
            obligations.append({
                "verification_id": parts[0],
                "source": "task",
            })
            continue
        if len(parts) == 3 and all(parts):
            obligations.append({
                "verification_id": parts[0],
                "source": "fix_loop",
                "command": parts[1],
                "expected": parts[2],
            })
            continue
        raise ValueError(
            "--verify must be V-001 or "
            "'FIX-001:::exact command:::expected observable'"
        )
    return obligations


def _cmd_fix_loop_open(args: argparse.Namespace) -> None:
    from ..core.state_ops import open_fix_loop

    try:
        obligations = _parse_fixloop_verification(
            args.verification_obligations or []
        )
        result = open_fix_loop(
            str(Path.cwd()),
            route=args.route,
            reason=args.reason,
            required_fixes=args.required_fixes or None,
            verification_obligations=obligations or None,
            source=args.source or "reviewer",
            invalidated_files=args.invalidated_files or None,
            invalidated_obligations=args.invalidated_obligations or None,
            task_id=args.task_id,
        )
    except ValueError as exc:
        print(f"Fix-loop open blocked: {exc}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Fix-loop opened: status={result['status']}")
    print(f"  Route: {args.route}")
    print(f"  Reason: {args.reason[:160]}")
    if args.required_fixes:
        print(f"  Required fixes: {len(args.required_fixes)}")
    if obligations:
        print(f"  Verification obligations: {len(obligations)}")
    print("  Next: run aiwf status --prompt and follow its route")


def _cmd_fix_loop_resolve(args: argparse.Namespace) -> None:
    from ..core.state_ops import resolve_fix_loop

    try:
        result = resolve_fix_loop(
            str(Path.cwd()),
            resolution=args.resolution,
            source=args.source or "reviewer",
            task_id=args.task_id,
        )
    except ValueError as exc:
        print(f"Fix-loop resolution blocked: {exc}", file=sys.stderr)
        print("  Next: run aiwf status --prompt and follow its route", file=sys.stderr)
        raise SystemExit(1)
    print(f"Fix-loop resolved: status={result['status']}")
    print(f"  Resolution: {args.resolution[:160]}")
    print("  Next: run aiwf status --prompt and follow its route")


def _cmd_fix_loop_continue(args: argparse.Namespace) -> None:
    from ..core.state_ops import continue_fix_loop

    try:
        result = continue_fix_loop(str(Path.cwd()), task_id=args.task_id)
    except ValueError as exc:
        print(f"Fix-loop continue blocked: {exc}", file=sys.stderr)
        raise SystemExit(1)
    print("Fix-loop continued by human decision")
    print(f"  Route: {result.get('route') or 'planner'}")
    print(f"  Attempt: {result.get('attempt_count', 0)}")
    print("  Next: run aiwf status --prompt and follow its route")


def _cmd_fix_loop_status(args: argparse.Namespace) -> None:
    from ..core.state.fixloop_ops import resolve_fixloop_task_id
    from ..core.task_records import load_task_record

    task_id = resolve_fixloop_task_id(str(Path.cwd()), args.task_id)
    if not task_id:
        print("Fix-loop status blocked: Task ID required or no Task is assigned to this worktree", file=sys.stderr)
        raise SystemExit(1)
    fix_loop = load_task_record(Path.cwd(), task_id).get("fix_loop", {}) or {}
    print("Fix-loop:")
    print(f"  Task: {task_id}")
    print(f"  Status: {fix_loop.get('status', 'none')}")
    print(f"  Route: {fix_loop.get('route') or 'none'}")
    print(f"  Attempt: {fix_loop.get('attempt_count', 0)} / {fix_loop.get('max_attempts', 2)}")
    if fix_loop.get("reason"):
        print(f"  Reason: {fix_loop['reason'][:160]}")
    for item in fix_loop.get("required_fixes", []) or []:
        print(f"  Fix: {str(item)[:160]}")
    for item in fix_loop.get("verification_obligations", []) or []:
        if not isinstance(item, dict):
            continue
        verification_id = str(item.get("verification_id") or "")
        command = str(item.get("command") or "")
        detail = f" — {command}" if command else ""
        print(f"  Verify: {verification_id}{detail}"[:170])
    if fix_loop.get("required_verification"):
        print("  Verify: legacy free-text contract; reopen with --verify")
    if fix_loop.get("escalation_required"):
        print("  Human decision required: yes")
        print(f"  Continue: aiwf fixloop continue --task-id {task_id}")
        print(f"  Pause and replan: aiwf task interrupt {task_id}")
        print(f"  Accept unmet checks and close: aiwf task force-close {task_id}")


def _cmd_install(args: argparse.Namespace) -> None:
    if args.mode == "codex":
        from ..install_codex import (
            COMMAND_NAME, ENTRY_COMMAND, PRODUCT_NAME, install_codex,
        )
        product_name = PRODUCT_NAME
        command_name = COMMAND_NAME
        entry_command = ENTRY_COMMAND
        results = install_codex(force=bool(args.force))
    elif args.mode == "opencode":
        from ..install_opencode import (
            COMMAND_NAME, ENTRY_COMMAND, PRODUCT_NAME, install_opencode,
        )
        product_name = PRODUCT_NAME
        command_name = COMMAND_NAME
        entry_command = ENTRY_COMMAND
        results = install_opencode(force=bool(args.force))
    else:
        from ..install_claude import TARGETS, install_claude, install_embedded

        target = TARGETS[args.mode]
        product_name = target.product_name
        command_name = target.command_name
        entry_command = target.entry_command
        results = (
            install_claude(force=bool(args.force))
            if args.mode == "claude"
            else install_embedded(args.mode, force=bool(args.force))
        )
    print(f"# AIWF V{VERSION} - {product_name} Integration Installed")
    if results["created"]:
        print(f"Created ({len(results['created'])}):")
        for path in results["created"]:
            print(f"  + {path}")
    if results["updated"]:
        print(f"Updated ({len(results['updated'])}):")
        for path in results["updated"]:
            print(f"  ~ {path}")
    for warning in results.get("warnings", []):
        print(f"WARNING: {warning}")
    from ..core.git_hygiene import inspect_git_hygiene

    hygiene = inspect_git_hygiene(Path.cwd())
    if not hygiene["repository"]:
        print("Git readiness: this directory is not a Git repository.")
    if not hygiene["has_head"]:
        print("Before starting AIWF work: initialize Git and create the initial commit.")
    if hygiene["tracked_residue"]:
        print(
            "WARNING: tracked local residue can invalidate testing/review snapshots: "
            + ", ".join(hygiene["tracked_residue"][:8])
        )
        print("  Review these paths and untrack them deliberately; AIWF will not modify the index.")
    print("Next:")
    print(f"  1. Start {product_name}: {command_name}")
    print(f"  2. Load Planner: {entry_command}")
    print("  3. Describe the goal or question")


def _cmd_doctor(args: argparse.Namespace) -> None:
    from ..core.project_root import (
        has_codex_adapter,
        has_opencode_adapter,
        in_codex_session,
    )

    requested_host = getattr(args, "host", None)
    if requested_host == "codex" or (
        requested_host is None
        and has_codex_adapter(Path.cwd())
        and (in_codex_session() or not (
            (Path.cwd() / ".claude" / "settings.json").exists()
            or (Path.cwd() / ".reasonix" / "settings.json").exists()
            or has_opencode_adapter(Path.cwd())
        ))
    ):
        from ..install_codex import doctor_codex
        results = doctor_codex()
    elif requested_host == "opencode" or (
        requested_host is None
        and has_opencode_adapter(Path.cwd())
        and not (
            (Path.cwd() / ".claude" / "settings.json").exists()
            or (Path.cwd() / ".reasonix" / "settings.json").exists()
        )
    ):
        from ..install_opencode import doctor_opencode
        results = doctor_opencode()
    else:
        from ..install_claude import doctor
        results = doctor(mode=requested_host)
    overall = results["overall"]
    from ..core.git_hygiene import inspect_git_hygiene

    hygiene = inspect_git_hygiene(Path.cwd())
    git_warning = bool(
        not hygiene["repository"]
        or not hygiene["has_head"]
        or hygiene["tracked_residue"]
    )
    if overall == "healthy" and git_warning:
        overall = "healthy_with_warnings"
    product = results.get("product_name", "embedded")
    config_dir = results.get("config_dir", ".claude")
    instruction_file = results.get("instruction_file", "CLAUDE.md")
    icon = lambda ok: "OK" if ok else "FAIL"

    print(f"# AIWF Doctor - {product} - {overall}")
    print(f"{icon(results['instruction_md'])} {instruction_file}")
    print(f"{icon(results['settings_json'])} {results.get('settings_label', config_dir + '/settings.json')}")
    print("Skills:")
    for name, info in results["skills"].items():
        print(f"  {icon(info['exists'] and info.get('has_frontmatter', False))} {name}")
    print("Agents:")
    for name, info in results["agents"].items():
        print(f"  {icon(info['exists'])} {name}")
    print("Hooks:")
    for name, info in results["hooks"].items():
        print(f"  {icon(info.get('valid_schema', False))} {name}")
    print("State:")
    for name, ok in results["state_files"].items():
        print(f"  {icon(ok)} .aiwf/{name}")
    print("Scripts:")
    for name, info in results["scripts"].items():
        print(f"  {icon(info['exists'] and info.get('executable', False))} scripts/{name}")

    index = results.get("index", {})
    if index and not index.get("healthy", True):
        print(f"FAIL index: {index.get('issues_count', 0)} issue(s)")
    sync = results.get("sync", {})
    if sync and not sync.get("healthy", True):
        print(f"FAIL sync: {sync.get('error_count', 0)} error(s)")
    memory = results.get("memory", {})
    if memory and memory.get("warning_count", 0):
        print(f"WARN memory: {memory.get('warning_count', 0)} structural warning(s)")
        for warning in memory.get("warnings", []):
            print(f"  WARN {warning}")
    for warning in results.get("adapter_warnings", []):
        print(f"WARN adapter: {warning}")

    if not hygiene["repository"]:
        print("WARN git: not a Git repository; initialize it and create an initial commit before Task activation")
    elif not hygiene["has_head"]:
        print("WARN git: repository has no initial commit; create one before Task activation")
    if hygiene["tracked_residue"]:
        print(
            "WARN git: tracked local residue can invalidate proof snapshots: "
            + ", ".join(hygiene["tracked_residue"][:8])
        )

    if overall not in ("healthy", "healthy_with_warnings"):
        raise SystemExit(1)
