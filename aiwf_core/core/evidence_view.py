"""Evidence view helpers — concise user-facing summaries from raw evidence.

Raw evidence.json is preserved intact. These helpers produce filtered,
deduplicated views for status, review, and closure reporting.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def get_accepted_evidence(
    evidence: Dict[str, Any],
    review: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Return evidence records that are accepted by review.

    A record is accepted if:
    - Its id is in review.accepted_evidence_ids, OR
    - Its status is "accepted"
    """
    accepted_ids = set(review.get("accepted_evidence_ids", []) or [])
    records = evidence.get("records", [])
    if not isinstance(records, list):
        return []

    return [
        r for r in records
        if isinstance(r, dict) and (
            r.get("id") in accepted_ids or r.get("status") == "accepted"
        )
    ]


def summarize_evidence(
    records: List[Dict[str, Any]],
    raw_total: int = 0,
) -> Dict[str, Any]:
    """Produce a compact summary from evidence records.

    Returns dict with:
      - accepted_ids: list of accepted evidence IDs
      - changed_files: deduplicated list of changed file paths
      - commands: list of {command, exit_code} for Bash tool records
      - test_commands: subset of commands that look like test runners
      - scope_violations: any scope violation mentions in review blockers
      - raw_count: total raw records (passed in or computed)
      - accepted_count: number of accepted records
    """
    accepted_ids = []
    changed_files = set()
    commands = []
    test_commands = []

    TEST_PATTERNS = {"test", "pytest", "npm test", "npm run test", "jest",
                     "mocha", "node", "python -m pytest", "python -m unittest"}

    for r in records:
        if not isinstance(r, dict):
            continue
        rid = r.get("id", "")
        if rid:
            accepted_ids.append(rid)

        # Collect changed files
        for f in (r.get("changed_files") or []):
            if f:
                changed_files.add(f)

        # Collect commands
        cmd = r.get("command", "")
        if cmd:
            ec = r.get("exit_code")
            commands.append({"command": cmd[:120], "exit_code": ec})
            # Detect test commands
            if any(p in cmd for p in TEST_PATTERNS):
                test_commands.append({"command": cmd[:120], "exit_code": ec})

    return {
        "accepted_ids": accepted_ids,
        "changed_files": sorted(changed_files),
        "commands": commands,
        "test_commands": test_commands,
        "raw_count": raw_total or len(records),
        "accepted_count": len(accepted_ids),
    }


def build_closure_evidence_summary(
    evidence: Dict[str, Any],
    review: Dict[str, Any],
    testing: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a closure-focused evidence summary from state files.

    Combines accepted evidence, testing, and review into one concise dict
    suitable for status display, export-report, and close skill use.
    """
    recs = evidence.get("records", [])
    if not isinstance(recs, list):
        recs = []
    raw_total = len(recs)

    accepted = get_accepted_evidence(evidence, review)
    summary = summarize_evidence(accepted, raw_total=raw_total)

    # Add review + testing context
    summary["review_result"] = review.get("result", "unknown")
    summary["review_verdict"] = review.get("verdict", "pending")
    basis = review.get("review_basis", {}) or {}
    basis_counts = {"covered": 0, "gap": 0, "not_applicable": 0, "missing": 0}
    if isinstance(basis, dict):
        from .state_schema import REVIEW_BASIS
        for name in REVIEW_BASIS:
            entry = basis.get(name, {})
            status = entry.get("status") if isinstance(entry, dict) else "missing"
            if status not in basis_counts:
                status = "missing"
            basis_counts[status] += 1
    summary["review_basis"] = basis_counts
    summary["closure_allowed"] = review.get("closure_allowed", False)
    summary["review_blockers"] = review.get("blockers", []) or []
    summary["testing_status"] = testing.get("status", "missing")
    summary["testing_commands"] = testing.get("commands", []) or []
    summary["untested_risks"] = testing.get("untested_risks", []) or []
    summary["deferred_out_of_scope"] = testing.get("deferred_out_of_scope", []) or []

    return summary


def format_evidence_for_status(summary: Dict[str, Any]) -> List[str]:
    """Format an evidence summary into lines for `aiwf status` display."""
    lines = []
    lines.append(f"Evidence:")
    lines.append(f"  raw records: {summary.get('raw_count', 0)}")
    lines.append(f"  accepted: {summary.get('accepted_count', 0)}")
    if summary.get("accepted_ids"):
        ids = ", ".join(summary["accepted_ids"][:8])
        if len(summary["accepted_ids"]) > 8:
            ids += f" (+{len(summary['accepted_ids']) - 8})"
        lines.append(f"  accepted ids: {ids}")
    if summary.get("changed_files"):
        lines.append("  changed files:")
        for f in summary["changed_files"][:10]:
            lines.append(f"    - {f}")
    if summary.get("test_commands"):
        lines.append("  test commands:")
        for tc in summary["test_commands"][:5]:
            ec_str = f" → {tc['exit_code']}" if tc.get("exit_code") is not None else ""
            lines.append(f"    - {tc['command']}{ec_str}")
    if summary.get("untested_risks"):
        lines.append("  untested risks:")
        for r in summary["untested_risks"][:5]:
            lines.append(f"    - {r}")
    return lines
