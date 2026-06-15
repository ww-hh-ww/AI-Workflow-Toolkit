"""Periodic architecture review state operations."""
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
    task_id: str,
    status: str,
    issues: Optional[List[Dict[str, str]]] = None,
    summary: str = "",
    resolution: str = "",
    resolution_evidence_ids: Optional[List[str]] = None,
    resolved_task_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid architecture review status: {status}")
    if not task_id.startswith("ARCH-"):
        raise ValueError("periodic architecture review must be recorded by an ARCH-* task")
    root = Path(base_dir)
    ledger = _read(root / ".aiwf" / "runtime" / "history" / "task-ledger.json") or {"tasks": []}
    active = next(
        (t for t in ledger.get("tasks", []) if isinstance(t, dict) and t.get("id") == task_id),
        None,
    )
    if not active or active.get("status") != "active" or task_id.startswith("ARCH-FIX-"):
        raise ValueError("periodic architecture review must be recorded from an active ARCH-* review task")

    normalized = []
    for issue in issues or []:
        severity = str(issue.get("severity", "")).lower()
        description = str(issue.get("description", "")).strip()
        if severity not in VALID_SEVERITIES:
            raise ValueError(f"invalid architecture issue severity: {severity}")
        if not description:
            raise ValueError("architecture issue description is required")
        normalized.append({
            "severity": severity,
            "description": description,
            "disposition": "open",
        })
    if status == "intact" and normalized:
        raise ValueError("architecture review cannot be intact while issues are recorded")
    if status == "issues_found" and not normalized:
        raise ValueError("issues_found architecture review requires at least one issue")

    path = root / ".aiwf" / "artifacts" / "quality" / "architecture-review.json"
    current = _read(path)
    if current.get("status") == "issues_found" and status == "intact":
        if not resolution.strip():
            raise ValueError("architecture issues require a resolution summary before review can become intact")
        resolved_ids = list(resolved_task_ids or [])
        if not resolved_ids:
            raise ValueError("architecture issues require at least one resolved ARCH-FIX-* task")
        tasks = {t.get("id"): t for t in ledger.get("tasks", []) if isinstance(t, dict)}
        invalid = [
            tid for tid in resolved_ids
            if not tid.startswith("ARCH-FIX-") or tasks.get(tid, {}).get("status") != "closed"
        ]
        if invalid:
            raise ValueError("resolved architecture tasks must be closed ARCH-FIX-* tasks: " + ", ".join(invalid))
        if not resolution_evidence_ids:
            raise ValueError("architecture issue resolution requires evidence IDs")
        evidence = _read(root / ".aiwf" / "artifacts" / "evidence" / "records.json") or {"records": []}
        known_evidence = {
            str(record.get("id", ""))
            for record in evidence.get("records", [])
            if isinstance(record, dict)
        }
        missing_evidence = [
            evidence_id for evidence_id in resolution_evidence_ids
            if evidence_id not in known_evidence
        ]
        if missing_evidence:
            raise ValueError(
                "architecture resolution evidence IDs not found: " + ", ".join(missing_evidence)
            )

    history = list(current.get("review_history", []) or [])
    if current.get("recorded_at"):
        history.append({k: v for k, v in current.items() if k != "review_history"})
    result = {
        "status": status,
        "task_id": task_id,
        "issues": normalized,
        "summary": summary,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "resolution": resolution.strip(),
        "resolution_evidence_ids": list(resolution_evidence_ids or []),
        "resolved_task_ids": list(resolved_task_ids or []),
        "review_history": history,
    }
    _write(path, result)
    return result
