"""CLI handlers for installation, status recovery, and doctor."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..constants import VERSION


def _cmd_fix_loop_open(args: argparse.Namespace) -> None:
    from ..core.state_ops import open_fix_loop

    result = open_fix_loop(
        str(Path.cwd()),
        route=args.route,
        reason=args.reason,
        required_fixes=args.required_fixes or None,
        required_verification=args.required_verification or None,
        source=args.source or "reviewer",
        invalidated_files=args.invalidated_files or None,
        invalidated_obligations=args.invalidated_obligations or None,
    )
    print(f"Fix-loop opened: status={result['status']}")
    print(f"  Route: {args.route}")
    print(f"  Reason: {args.reason[:160]}")
    if args.required_fixes:
        print(f"  Required fixes: {len(args.required_fixes)}")
    if args.required_verification:
        print(f"  Required verification: {len(args.required_verification)}")


def _cmd_fix_loop_resolve(args: argparse.Namespace) -> None:
    from ..core.state_ops import resolve_fix_loop

    try:
        result = resolve_fix_loop(
            str(Path.cwd()),
            resolution=args.resolution,
            source=args.source or "reviewer",
            force=bool(args.force),
        )
    except ValueError as exc:
        print(f"Fix-loop resolution blocked: {exc}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Fix-loop resolved: status={result['status']}")
    print(f"  Resolution: {args.resolution[:160]}")


def _cmd_fix_loop_status(args: argparse.Namespace) -> None:
    from ..core.state_ops import _read

    fix_loop = _read(Path.cwd() / ".aiwf/state/fix-loop.json")
    print("Fix-loop:")
    print(f"  Status: {fix_loop.get('status', 'none')}")
    print(f"  Route: {fix_loop.get('route') or 'none'}")
    print(f"  Attempt: {fix_loop.get('attempt_count', 0)} / {fix_loop.get('max_attempts', 2)}")
    if fix_loop.get("reason"):
        print(f"  Reason: {fix_loop['reason'][:160]}")
    for item in fix_loop.get("required_fixes", []) or []:
        print(f"  Fix: {str(item)[:160]}")
    for item in fix_loop.get("required_verification", []) or []:
        print(f"  Verify: {str(item)[:160]}")
    if fix_loop.get("escalation_required"):
        print("  Human decision required: yes")


def _cmd_fix_loop_help(args: argparse.Namespace) -> None:
    print("AIWF Fix-Loop")
    print("  aiwf fixloop open")
    print("  aiwf fixloop status")
    print("  aiwf fixloop resolve")


def _cmd_install(args: argparse.Namespace) -> None:
    from ..install_claude import TARGETS, install_embedded

    target = TARGETS[args.mode]
    results = install_embedded(args.mode, force=bool(args.force))
    print(f"# AIWF V{VERSION} - {target.product_name} Integration Installed")
    if results["created"]:
        print(f"Created ({len(results['created'])}):")
        for path in results["created"]:
            print(f"  + {path}")
    if results["updated"]:
        print(f"Updated ({len(results['updated'])}):")
        for path in results["updated"]:
            print(f"  ~ {path}")
    print("Next:")
    print(f"  1. Start {target.product_name}: {target.command_name}")
    print(f"  2. Load Planner: {target.entry_command}")
    print("  3. Describe the goal or question")


def _cmd_doctor(args: argparse.Namespace) -> None:
    from ..install_claude import doctor

    results = doctor()
    overall = results["overall"]
    product = results.get("product_name", "embedded")
    config_dir = results.get("config_dir", ".claude")
    instruction_file = results.get("instruction_file", "CLAUDE.md")
    icon = lambda ok: "OK" if ok else "FAIL"

    print(f"# AIWF Doctor - {product} - {overall}")
    print(f"{icon(results['instruction_md'])} {instruction_file}")
    print(f"{icon(results['settings_json'])} {config_dir}/settings.json")
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

    if overall not in ("healthy", "healthy_with_warnings"):
        raise SystemExit(1)
