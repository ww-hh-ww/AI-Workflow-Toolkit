"""External research command handlers."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys


def _cmd_research_record(args: argparse.Namespace) -> None:
    from ..core.external_research import record_research
    rec = record_research(
        str(Path.cwd()),
        source=args.source,
        query=args.query,
        claims=args.claims or None,
        links=args.links or None,
        time_window=args.time_window or "",
        confidence=args.confidence,
    )
    print(f"External research recorded: {rec['id']}")
    print(f"  Status: {rec['status']} (low-trust until Planner promotes it)")
    print(f"  Claims: {len(rec['claims'])}")
    print(f"  Links: {len(rec['links'])}")


def _cmd_research_list(args: argparse.Namespace) -> None:
    from ..core.external_research import list_research
    records = list_research(str(Path.cwd()), include_promoted=args.include_promoted)
    if not records:
        print("External research: none")
        return
    print(f"External research: {len(records)}")
    for rec in records:
        print(f"  {rec['id']} | {rec['status']} | {rec.get('confidence','low')} | {rec.get('source','')[:20]} | {rec.get('query','')[:80]}")


def _cmd_research_promote(args: argparse.Namespace) -> None:
    from ..core.external_research import promote_research
    try:
        rec = promote_research(str(Path.cwd()), args.id, args.decision, promoted_by=args.promoted_by)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        raise SystemExit(1)
    print(f"External research promoted: {rec['id']}")
    print(f"  Decision: {rec['used_for_decision'][:160]}")
    print("  Note: promotion records a decision trace; update goal/context explicitly if needed.")


def _cmd_research_skip(args: argparse.Namespace) -> None:
    from ..core.external_research import record_research_skip
    try:
        skip = record_research_skip(str(Path.cwd()), args.reason, decided_by=args.decided_by)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        raise SystemExit(1)
    print("External research skipped by Planner decision")
    print(f"  Reason: {skip['reason'][:160]}")


def _cmd_research_help(args: argparse.Namespace) -> None:
    print("AIWF External Research")
    print()
    print("Available subcommands:")
    print("  aiwf research record   — record low-trust external research")
    print("  aiwf research list     — list research records")
    print("  aiwf research promote  — promote a record into Planner decision trace")
    print("  aiwf research skip     — explicitly skip required external research")
