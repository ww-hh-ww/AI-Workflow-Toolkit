"""Claim-Evidence Alignment CLI commands.

aiwf claim record  — record a claim linked to evidence
aiwf claim verify  — auto-verify claim-evidence alignment
aiwf claim list    — list claims for a task
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _cmd_claim_record(args: argparse.Namespace) -> None:
    from ..core.state.claims_ops import record_claim
    claim = record_claim(
        str(Path.cwd()),
        text=args.text,
        task_id=args.task_id or "",
        evidence_ids=args.evidence_ids or [],
        claim_id=args.claim_id or "",
    )
    print(f"Claim recorded: {claim['id']}")
    print(f"  Text: {claim['text'][:120]}")
    print(f"  Evidence: {len(claim['evidence_ids'])} linked")
    print(f"  Status: {claim['status']}")


def _cmd_claim_verify(args: argparse.Namespace) -> None:
    from ..core.state.claims_ops import verify_claims
    result = verify_claims(
        str(Path.cwd()),
        task_id=args.task_id or "",
    )
    print(f"Claims verified: {result['total']} checked")
    print(f"  Supported:   {result['total'] - result['unsupported_count'] - result['overclaimed_count']}")
    print(f"  Unsupported: {result['unsupported_count']}")
    print(f"  Overclaimed: {result['overclaimed_count']}")
    print(f"  All supported: {'yes' if result['all_supported'] else 'no'}")
    for r in result["results"]:
        print(f"  {r['claim_id']}: {r['status']} — {r['reason'][:100]}")


def _cmd_claim_list(args: argparse.Namespace) -> None:
    from ..core.state.claims_ops import load_claims
    claims_data = load_claims(str(Path.cwd()))
    all_claims = claims_data.get("claims", [])
    task_id = args.task_id or ""
    if task_id:
        all_claims = [c for c in all_claims if c.get("task_id") == task_id]

    if not all_claims:
        print("No claims recorded." + (f" (task: {task_id})" if task_id else ""))
        return

    print(f"Claims: {len(all_claims)}")
    for c in all_claims[-20:]:
        status_mark = {"supported": "+", "unsupported": "-", "overclaimed": "~", "pending": "?", "disputed": "!"}
        mark = status_mark.get(c.get("status", "pending"), "?")
        print(f"  [{mark}] {c['id']} | {c.get('status', 'pending'):12s} | {c.get('text', '')[:100]}")


def _cmd_claim_help(args: argparse.Namespace) -> None:
    print("AIWF Claim-Evidence Alignment")
    print()
    print("Every claim about task completion must be traceable to evidence.")
    print()
    print("Available subcommands:")
    print("  aiwf claim record  — record a claim linked to evidence IDs")
    print("  aiwf claim verify  — auto-verify claim-evidence alignment")
    print("  aiwf claim list    — list claims for a task")
    print()
    print("Claim statuses:")
    print("  pending      — not yet verified")
    print("  supported    — all evidence exists, accepted, machine-observed")
    print("  unsupported  — no evidence or evidence rejected")
    print("  overclaimed  — claim broader than evidence (weak sourcing)")
    print("  disputed     — reviewer flagged the claim")
