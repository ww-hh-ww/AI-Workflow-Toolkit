"""Architecture documentation command handlers."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _cmd_architecture_doc_require(args: argparse.Namespace) -> None:
    from ..core.architecture_doc import require_architecture_doc
    try:
        state = require_architecture_doc(str(Path.cwd()), args.reason, path=args.path)
    except ValueError as e:
        print(f"Architecture doc require blocked: {e}", file=sys.stderr)
        raise SystemExit(1)
    print("Architecture snapshot required")
    print(f"  Path:   {state.get('path')}")
    print(f"  Reason: {state.get('reason')}")


def _cmd_architecture_doc_status(args: argparse.Namespace) -> None:
    from ..core.architecture_doc import load_architecture_doc_state
    state = load_architecture_doc_state(str(Path.cwd()))
    validation = state.get("validation", {}) or {}
    print("Architecture snapshot:")
    print(f"  Status:   {state.get('status', 'not_required')}")
    print(f"  Required: {'yes' if state.get('required') else 'no'}")
    print(f"  Path:     {state.get('path')}")
    if state.get("reason"):
        print(f"  Reason:   {state['reason']}")
    if state.get("waive_reason"):
        print(f"  Waived:   {state['waive_reason']}")
    if validation.get("checked_at"):
        print(f"  Valid:    {'yes' if validation.get('valid') else 'no'}")
        for issue in validation.get("issues", []) or []:
            print(f"  Issue:    {issue}")
        for warning in validation.get("warnings", []) or []:
            print(f"  Warning:  {warning}")


def _cmd_architecture_doc_validate(args: argparse.Namespace) -> None:
    from ..core.architecture_doc import validate_architecture_doc
    result = validate_architecture_doc(str(Path.cwd()), path=args.path)
    print(f"Architecture snapshot: {'valid' if result['valid'] else 'invalid'}")
    print(f"  Path: {result['path']}")
    for issue in result.get("issues", []) or []:
        print(f"  Error: {issue}")
    for warning in result.get("warnings", []) or []:
        print(f"  Warning: {warning}")
    if not result["valid"]:
        raise SystemExit(1)


def _cmd_architecture_doc_satisfy(args: argparse.Namespace) -> None:
    from ..core.architecture_doc import satisfy_architecture_doc
    try:
        state = satisfy_architecture_doc(str(Path.cwd()), path=args.path)
    except ValueError as e:
        print(f"Architecture doc satisfy blocked: {e}", file=sys.stderr)
        raise SystemExit(1)
    print("Architecture snapshot satisfied")
    print(f"  Path: {state.get('path')}")


def _cmd_architecture_doc_waive(args: argparse.Namespace) -> None:
    from ..core.architecture_doc import waive_architecture_doc
    try:
        state = waive_architecture_doc(str(Path.cwd()), args.reason)
    except ValueError as e:
        print(f"Architecture doc waive blocked: {e}", file=sys.stderr)
        raise SystemExit(1)
    print("Architecture snapshot waived")
    print(f"  Reason: {state.get('waive_reason')}")


def _cmd_architecture_doc_help(args: argparse.Namespace) -> None:
    print("AIWF Architecture Snapshot")
    print()
    print("Available subcommands:")
    print("  aiwf architecture-doc require --reason 'milestone handoff'")
    print("  aiwf architecture-doc status")
    print("  aiwf architecture-doc validate")
    print("  aiwf architecture-doc satisfy")
    print("  aiwf architecture-doc waive --reason 'not stable enough yet'")

