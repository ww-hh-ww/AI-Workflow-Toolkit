"""Backend-neutral evidence record schema and factory."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .event_model import EvidenceRecord
from .state_schema import default_evidence, EVIDENCE_KEYS

# ── Evidence Trust Levels ──
# Ascending order: each level subsumes the trust of all levels below it.
TRUST_LEVELS = [
    "claimed",           # model claims, no machine trace
    "role_recorded",     # subagent delivery record (role evidence)
    "git_observed",      # git diff corroborates the claim
    "command_observed",  # real command output captured
    "cross_checked",     # independently verified by another role (tester + reviewer)
    "user_verified",     # human confirmed the result is real/usable
]

# Minimum trust level required for L2+ closure evidence.
# Closure requires at least one record at or above this level.
MIN_TRUST_FOR_CLOSURE = {
    "L0_direct": "claimed",
    "L1_review_light": "role_recorded",
    "L2_standard_team": "command_observed",
    "L3_full_power": "command_observed",
}

# L2+ requires evidence from multiple independent sessions (executor, tester, reviewer).
MIN_INDEPENDENT_SESSIONS = {
    "L0_direct": 1,
    "L1_review_light": 2,
    "L2_standard_team": 3,
    "L3_full_power": 3,
}


def trust_level_rank(level: str) -> int:
    """Return numeric rank of a trust level (higher = more trustworthy)."""
    try:
        return TRUST_LEVELS.index(level)
    except ValueError:
        return -1


def meets_trust_threshold(level: str, minimum: str) -> bool:
    """Check if a trust level meets or exceeds a minimum threshold."""
    return trust_level_rank(level) >= trust_level_rank(minimum)


def next_ev_id(records: List[Dict]) -> str:
    """Generate the next evidence ID: EV-001, EV-002, ..."""
    nums = []
    for r in records:
        if not isinstance(r, dict):
            continue
        eid = str(r.get("id", ""))
        if eid.startswith("EV-"):
            try:
                nums.append(int(eid.split("-")[1]))
            except ValueError:
                pass
    return f"EV-{(max(nums) + 1 if nums else 1):03d}"


def create_evidence_record(
    tool_name: str = "",
    tool_input: Optional[Dict] = None,
    command: str = "",
    exit_code: Optional[int] = None,
    changed_files: Optional[List[str]] = None,
    changed_files_source: str = "unavailable",
    session_id: str = "",
    agent_id: str = "",
    agent_type: str = "",
    context_id: str = "",
    phase: str = "",
    existing_records: Optional[List[Dict]] = None,
) -> EvidenceRecord:
    """Create a new evidence record with auto-generated ID."""
    recs = existing_records or []
    ev_id = next_ev_id(recs)
    return EvidenceRecord(
        id=ev_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        context_id=context_id,
        phase=phase,
        session_id=session_id,
        agent_id=agent_id,
        agent_type=agent_type,
        tool_name=tool_name,
        tool_input=tool_input or {},
        command=command,
        exit_code=exit_code,
        changed_files=changed_files or [],
        changed_files_source=changed_files_source,
        status="pending",
        trust="machine_observed",
    )


def record_to_dict(record: EvidenceRecord) -> Dict[str, Any]:
    """Serialize an EvidenceRecord to a dict for JSON storage."""
    return {
        "id": record.id,
        "timestamp": record.timestamp,
        "context_id": record.context_id,
        "phase": record.phase,
        "session_id": record.session_id,
        "agent_id": record.agent_id,
        "agent_type": record.agent_type,
        "tool_name": record.tool_name,
        "tool_input": record.tool_input,
        "command": record.command,
        "exit_code": record.exit_code,
        "changed_files": record.changed_files,
        "changed_files_source": record.changed_files_source,
        "stdout_summary": record.stdout_summary,
        "stderr_summary": record.stderr_summary,
        "status": record.status,
        "trust": record.trust,
        "trust_level": record.trust_level,
    }


def append_evidence(evidence: Dict[str, Any], record: EvidenceRecord) -> Dict[str, Any]:
    """Append a record to evidence.json data and return it."""
    records = evidence.get("records", [])
    if not isinstance(records, list):
        records = []
    records.append(record_to_dict(record))
    evidence["records"] = records
    return evidence
