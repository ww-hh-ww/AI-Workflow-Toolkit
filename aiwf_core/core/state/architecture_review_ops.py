"""Periodic architecture review state operations.

V1: Architect is a read-only periodic reviewer, NOT a Task.
Architect does not require an active ARCH-* task.
Architect output is an advisory report; Planner decides whether to open Plan/Task.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ._common import _read, _write

VALID_STATUSES = {"intact", "issues_found"}
VALID_SEVERITIES = {"critical", "high", "medium", "low"}


def record_architecture_review(
    base_dir: str,
    *,
    status: str,
    summary: str = "",
    findings: Optional[List[Dict[str, str]]] = None,
    recommendations: Optional[List[str]] = None,
    issues: Optional[List[Dict[str, str]]] = None,
    resolution: str = "",
    resolution_evidence_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Record a periodic architecture review.

    V1: Architect is read-only. No ARCH-* task required.
    This records observations; Planner decides next steps.

    Args:
        base_dir: Project root.
        status: 'intact' or 'issues_found'.
        summary: Human-readable review summary.
        findings: List of {"severity": "...", "description": "..."} findings.
        recommendations: Optional actionable recommendations for Planner.
        issues: Deprecated alias for findings.
        resolution: Required when transitioning from issues_found to intact.
        resolution_evidence_ids: Optional evidence for resolution.
    """
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid architecture review status: {status}")

    root = Path(base_dir)

    # Normalize findings (supports both --finding and legacy --issue)
    all_findings = list(findings or []) + list(issues or [])
    normalized = []
    for f in all_findings:
        severity = str(f.get("severity", "")).lower()
        description = str(f.get("description", "")).strip()
        if severity not in VALID_SEVERITIES:
            raise ValueError(f"invalid finding severity: {severity}")
        if not description:
            raise ValueError("finding description is required")
        normalized.append({
            "severity": severity,
            "description": description,
            "disposition": "open",
        })

    if status == "intact" and normalized:
        raise ValueError("architecture review cannot be intact while findings are recorded")
    if status == "issues_found" and not normalized:
        raise ValueError("issues_found architecture review requires at least one finding")

    path = root / ".aiwf" / "records" / "architecture-review.json"
    current = _read(path)

    # Transition: issues_found → intact requires resolution
    if current.get("status") == "issues_found" and status == "intact":
        if not resolution.strip():
            raise ValueError(
                "architecture issues require a resolution summary before review can become intact"
            )
        if not resolution_evidence_ids:
            raise ValueError("architecture issue resolution requires evidence IDs")
        evidence = _read(root / ".aiwf" / "records" / "evidence.json") or {
            "records": []
        }
        known_evidence = {
            str(record.get("id", ""))
            for record in evidence.get("records", [])
            if isinstance(record, dict)
        }
        missing_evidence = [
            eid for eid in resolution_evidence_ids if eid not in known_evidence
        ]
        if missing_evidence:
            raise ValueError(
                "architecture resolution evidence IDs not found: "
                + ", ".join(missing_evidence)
            )

    history = list(current.get("review_history", []) or [])
    if current.get("recorded_at"):
        history.append({k: v for k, v in current.items() if k != "review_history"})

    result = {
        "status": status,
        "findings": normalized,
        "issues": normalized,  # backward compat
        "summary": summary,
        "recommendations": list(recommendations or []),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "resolution": resolution.strip(),
        "resolution_evidence_ids": list(resolution_evidence_ids or []),
        "review_history": history,
    }
    _write(path, result)
    return result
