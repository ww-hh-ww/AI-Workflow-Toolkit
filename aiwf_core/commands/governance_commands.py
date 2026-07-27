"""CLI handlers for governance Git tracking."""
from __future__ import annotations

import sys
from pathlib import Path


def _cmd_governance_status(args) -> None:
    from ..core.governance_git import (
        governance_tracking_mode,
        pending_governance_paths,
    )

    mode = governance_tracking_mode(Path.cwd())
    pending = pending_governance_paths(Path.cwd())
    print(f"Governance Git tracking: {mode}")
    print(f"  Pending stable governance files: {len(pending)}")
    for path in pending[:8]:
        print(f"  - {path}")


def _cmd_governance_checkpoint(args) -> None:
    from ..core.governance_git import checkpoint_governance

    try:
        result = checkpoint_governance(Path.cwd(), reason="manual governance checkpoint")
    except ValueError as exc:
        print(f"Governance checkpoint blocked: {exc}", file=sys.stderr)
        raise SystemExit(1)
    if result["mode"] == "local":
        print("Governance is local; no Git checkpoint is needed.")
    elif result["committed"]:
        print(f"Governance checkpoint: {result['commit'][:12]}")
        print(f"  Files: {len(result['paths'])}")
    else:
        print("Governance checkpoint: already clean")


def _cmd_governance_tracking(args) -> None:
    from ..core.governance_git import set_governance_tracking

    try:
        result = set_governance_tracking(Path.cwd(), args.mode)
    except ValueError as exc:
        print(f"Governance tracking change blocked: {exc}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Governance Git tracking: {result['mode']}")
    if result["committed"]:
        print(f"  Commit: {result['commit'][:12]}")
    if result["mode"] == "local":
        print("  .aiwf state and documents stay on this machine; .aiwf/config remains tracked.")


def _cmd_governance_help(args) -> None:
    print("AIWF Governance Git")
    print("  aiwf governance status")
    print("  aiwf governance checkpoint")
    print("  aiwf governance tracking tracked|local  - HUMAN ONLY")
