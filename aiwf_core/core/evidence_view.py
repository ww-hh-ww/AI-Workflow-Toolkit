"""Evidence view helpers — concise user-facing summaries from raw evidence.

Raw evidence.json is preserved intact. These helpers produce filtered,
deduplicated views for status, review, and closure reporting.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set


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


def effective_closure_evidence_ids(testing: Dict[str, Any], review: Dict[str, Any]) -> Set[str]:
    """Return evidence IDs explicitly linked by testing/review artifacts."""
    ids: set[str] = set()

    if testing.get("status") in ("adequate", "passed"):
        if testing.get("evidence_id"):
            ids.add(str(testing.get("evidence_id")))
        ids.update(str(eid) for eid in (testing.get("evidence_ids", []) or []) if str(eid))
        ids.update(str(eid) for eid in (testing.get("reused_evidence_ids", []) or []) if str(eid))
        ids.difference_update(
            str(eid) for eid in (testing.get("invalidated_evidence_ids", []) or []) if str(eid)
        )

    if review.get("result") == "accepted" or review.get("verdict") in ("PASS", "PASS_WITH_RISK"):
        ids.update(str(eid) for eid in (review.get("accepted_evidence_ids", []) or []) if str(eid))
        if review.get("reviewer_evidence_id"):
            ids.add(str(review.get("reviewer_evidence_id")))

    ids.discard("")
    return ids


def task_evidence_view(
    evidence: Dict[str, Any],
    testing: Dict[str, Any],
    review: Dict[str, Any],
    task: Dict[str, Any],
) -> Dict[str, Any]:
    """Compute evidence relevant to one task without brittle task_id dependence.

    Inclusion rules:
    - evidence with matching task_id belongs to the task
    - evidence with a different task_id never belongs to the task
    - evidence with no task_id belongs if it is explicitly linked by testing/review
      or was captured after the task activated

    This keeps old/legacy evidence usable while preventing historical pollution.
    """
    task_id = str(task.get("id") or "")
    activated_at = str(task.get("activated_at") or "")
    explicit_ids = effective_closure_evidence_ids(testing, review)
    records = evidence.get("records", []) if isinstance(evidence.get("records", []), list) else []

    relevant: list[dict] = []
    accepted: list[dict] = []
    inferred_task_ids: list[str] = []
    ignored_other_task_ids: set[str] = set()

    for record in records:
        if not isinstance(record, dict):
            continue
        rid = str(record.get("id") or "")
        record_task = str(record.get("task_id") or "")
        if record_task and task_id and record_task != task_id:
            ignored_other_task_ids.add(record_task)
            continue

        timestamp = str(record.get("timestamp") or record.get("recorded_at") or "")
        linked = bool(rid and rid in explicit_ids)
        explicit_match = bool(task_id and record_task == task_id)
        in_active_window = bool(task_id and not record_task and activated_at and timestamp and timestamp >= activated_at)
        legacy_no_window = bool(task_id and not record_task and not activated_at)

        if not (explicit_match or linked or in_active_window or legacy_no_window):
            continue

        relevant.append(record)
        if not record_task and task_id and (linked or in_active_window or legacy_no_window):
            inferred_task_ids.append(rid or "(unknown)")
        if record.get("status") == "accepted" or linked:
            accepted.append(record)

    accepted_ids = {str(r.get("id")) for r in accepted if str(r.get("id") or "")}
    accepted_ids.update(explicit_ids)
    accepted_ids.discard("")

    return {
        "task_id": task_id,
        "records": relevant,
        "accepted_records": accepted,
        "accepted_ids": accepted_ids,
        "explicit_ids": explicit_ids,
        "inferred_task_id_record_ids": inferred_task_ids,
        "ignored_other_task_ids": sorted(ignored_other_task_ids),
    }


def _compact_record(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": record.get("id", ""),
        "role": record.get("agent_type") or record.get("agent_id") or "",
        "status": record.get("status", ""),
        "trust_level": record.get("trust_level", ""),
        "command": record.get("command", ""),
        "exit_code": record.get("exit_code"),
        "stdout_summary": record.get("stdout_summary", ""),
        "stderr_summary": record.get("stderr_summary", ""),
        "changed_files": record.get("changed_files", []) or [],
        "evidence_baseline_ref": record.get("evidence_baseline_ref", ""),
        "evidence_head_ref": record.get("evidence_head_ref", ""),
    }


def build_task_review_evidence_view(
    evidence: Dict[str, Any],
    testing: Dict[str, Any],
    review: Dict[str, Any],
    task: Dict[str, Any],
) -> Dict[str, Any]:
    """Build the small evidence surface a Reviewer should read.

    This view intentionally excludes raw evidence payloads and unrelated task
    records. It gives reviewers enough to inspect diffs and proof coverage
    without burning context on the full evidence ledger.
    """
    view = task_evidence_view(evidence, testing, review, task)
    records = view.get("records", []) or []
    compact_records = [_compact_record(r) for r in records if isinstance(r, dict)]

    diff_refs = []
    for record in compact_records:
        baseline = str(record.get("evidence_baseline_ref") or "")
        head = str(record.get("evidence_head_ref") or "")
        if baseline and head:
            diff_refs.append({
                "evidence_id": record.get("id", ""),
                "role": record.get("role", ""),
                "baseline": baseline,
                "head": head,
                "command": f"git diff {baseline}..{head}",
            })

    changed_files = sorted({
        str(path)
        for record in compact_records
        for path in (record.get("changed_files", []) or [])
        if str(path)
    })

    return {
        "task_id": view.get("task_id", ""),
        "raw_record_count": len(evidence.get("records", []) or []),
        "relevant_record_count": len(compact_records),
        "accepted_ids": sorted(view.get("accepted_ids", set()) or []),
        "records": compact_records,
        "diff_refs": diff_refs,
        "changed_files": changed_files,
        "testing": {
            "status": testing.get("status", "missing"),
            "commands": testing.get("commands", []) or [],
            "verification_results": testing.get("verification_results", []) or [],
            "proof_validation": testing.get("proof_validation", {}) or {},
            "untested_risks": testing.get("untested_risks", []) or [],
            "failed_commands": testing.get("failed_commands", []) or [],
            "failure_summary": testing.get("failure_summary", ""),
        },
        "review": {
            "result": review.get("result", "unknown"),
            "verdict": review.get("verdict", "pending"),
            "blockers": review.get("blockers", []) or [],
            "accepted_evidence_ids": review.get("accepted_evidence_ids", []) or [],
        },
        "ignored_other_task_ids": view.get("ignored_other_task_ids", []) or [],
    }


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
