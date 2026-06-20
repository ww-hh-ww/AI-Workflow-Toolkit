"""Machine-observed evidence writer.

Per-operation evidence: changed_files = only what THIS tool call introduced,
computed by diffing current dirty files against previous evidence record.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...core.event_model import EvidenceRecord, NormalizedEvent
from ...core.evidence_schema import create_evidence_record
from ...core.state_schema import default_evidence
from ...core.state._common import _locked_json_update
from .diff_snapshot import detect_changed_files_with_baseline, filter_internal
from ...core.scope_policy import classify_file_change


def _read_json(path: Path, default: Dict) -> Dict:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, data: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _get_last_working_tree_files(evidence: Dict) -> List[str]:
    """Get the working_tree_changed_files from the most recent evidence record."""
    records = evidence.get("records", [])
    if not isinstance(records, list) or not records:
        return []
    last = records[-1]
    if isinstance(last, dict):
        return last.get("working_tree_changed_files", []) or []
    return []


def _compute_operation_files(
    current_dirty: List[str],
    previous_dirty: List[str],
) -> tuple:
    """Compute per-operation changed files.

    Returns (operation_files, working_tree_files, attribution, source).
    - operation_files: files newly appearing in this operation
    - working_tree_files: current cumulative dirty files
    - attribution: "strong" if we had previous snapshot, "weak" if first op
    - source: "snapshot_diff" or "first_operation"
    """
    prev_set = set(previous_dirty)
    curr_set = set(current_dirty)
    new_files = sorted(curr_set - prev_set)

    if previous_dirty:
        return (new_files, sorted(curr_set), "strong", "snapshot_diff")
    else:
        # First operation — attribute all current dirty files
        return (sorted(curr_set), sorted(curr_set), "weak", "first_operation")


def record_post_tool_event(
    event: NormalizedEvent,
    cwd: str = "",
    operation_changed_files: Optional[List[str]] = None,
    op_source: str = "",
    op_attribution: str = "",
) -> EvidenceRecord:
    """Create and persist a per-operation evidence record.

    Primary source: pre/post snapshot diff (true per-operation evidence).
    Fallback: dirty-set delta from previous evidence record.

    Args:
        event: Normalized Claude event.
        cwd: Project root directory.
        operation_changed_files: Pre-computed operation files (from snapshot diff).
        op_source: Source label for operation_changed_files.
        op_attribution: "strong" or "weak".
    """
    base = Path(cwd) if cwd else Path(event.cwd) if event.cwd else Path.cwd()
    evidence_path = base / ".aiwf" / "records" / "evidence.json"
    state_path = base / ".aiwf" / "state" / "state.json"

    state = _read_json(state_path, {})

    # Get working tree dirty files (cumulative, for reference)
    wt_diff = detect_changed_files_with_baseline(base)
    working_tree_files = wt_diff["files"]
    wt_source = wt_diff["source"]

    command = ""
    if event.tool_name == "Bash":
        command = event.tool_input.get("command", "") or ""

    def _append(evidence: Dict[str, Any]) -> tuple:
        # Determine operation-level changed_files while holding the evidence
        # lock; the dirty-set fallback depends on the previous record.
        if operation_changed_files is not None:
            op_files = list(operation_changed_files)
            final_source = op_source or "pre_post_snapshot"
            final_attribution = op_attribution or "strong"
        else:
            previous_wt = _get_last_working_tree_files(evidence)
            op_files, _, att, src = _compute_operation_files(
                working_tree_files, previous_wt)
            final_source = "dirty_set_delta_fallback" if previous_wt else src
            final_attribution = "weak" if not previous_wt else att

        records = evidence.get("records", [])
        if not isinstance(records, list):
            records = []
        record = create_evidence_record(
            tool_name=event.tool_name,
            tool_input=event.tool_input,
            command=command[:500] if command else "",
            exit_code=event.exit_code,
            changed_files=op_files,
            changed_files_source=final_source,
            session_id=event.session_id,
            agent_id=event.agent_id,
            agent_type=event.agent_type,
            context_id=state.get("active_context_id") or "",
            phase=state.get("phase", ""),
            existing_records=records,
        )

        project_files = [f for f in op_files if classify_file_change(f) == "project"]
        gov_files = [f for f in op_files if classify_file_change(f) == "governance"]

        if final_source == "pre_post_snapshot":
            trust_lvl = "command_observed"
        elif final_attribution == "strong":
            trust_lvl = "git_observed"
        elif command:
            trust_lvl = "command_observed"
        else:
            trust_lvl = "role_recorded"

        record_dict = {
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
            "changed_files": project_files,
            "governance_changed_files": gov_files,
            "changed_files_source": final_source,
            "working_tree_changed_files": working_tree_files,
            "working_tree_source": wt_source,
            "attribution": final_attribution,
            "stdout_summary": record.stdout_summary,
            "stderr_summary": record.stderr_summary,
            "status": record.status,
            "trust": record.trust,
            "trust_level": trust_lvl,
        }

        active_task_id = str(state.get("active_task_id") or "")
        if active_task_id:
            record_dict["task_id"] = active_task_id
            try:
                ledger_path = base / ".aiwf" / "state" / "tasks.json"
                ledger = _read_json(ledger_path, {"tasks": []}) if ledger_path.exists() else {"tasks": []}
                for task in ledger.get("tasks", []) or []:
                    if isinstance(task, dict) and task.get("id") == active_task_id:
                        record_dict["supports_plan"] = str(task.get("plan_id") or task.get("parent_plan") or "")
                        record_dict["supports_goal"] = str(task.get("goal_id") or task.get("parent_goal") or "")
                        break
            except Exception:
                pass

        records.append(record_dict)
        evidence["records"] = records
        evidence["updated_at"] = record.timestamp
        return record, final_source, gov_files, op_files

    record, final_source, gov_files, op_files = _locked_json_update(evidence_path, default_evidence(), _append)

    role_text = f"{event.agent_type} {event.agent_id}".lower()
    if "reviewer" in role_text and ".aiwf/records/review.json" in gov_files:
        state["phase"] = "reviewing"
        _write_json(state_path, state)

    # Update EvidenceRecord dataclass for return value
    record.changed_files = op_files
    record.changed_files_source = final_source

    return record


def check_and_record_scope_violations(
    changed_files: list,
    active_context: Dict,
    base: Path,
) -> list:
    """Check changed files against scope, record hard violations and soft drift.

    Only checks project files (AIWF internal paths filtered).
    Uses operation-level changed_files, not working tree.
    """
    from ...core.scope_policy import check_scope
    from ...core.review_contract import add_scope_violation_blocker

    state_path = base / ".aiwf" / "state" / "state.json"
    state = _read_json(state_path, {})
    active_task_id = str(state.get("active_task_id") or "")

    project_files = filter_internal(changed_files, cwd=base)

    violations = []
    drifts = []
    for f in project_files:
        result = check_scope(f, active_context, state=state, project_root=str(base))
        if not result.allowed:
            violations.append(f)
        elif getattr(result, "soft_drift", False):
            drifts.append({"path": f, "reason": result.reason})

    if violations:
        from datetime import datetime, timezone
        state_path = base / ".aiwf" / "state" / "state.json"
        state = _read_json(state_path, {})
        state["scope_violation"] = True
        _write_json(state_path, state)

        review_path = base / ".aiwf" / "records" / "review.json"
        from ...core.state_schema import default_review
        review = _read_json(review_path, default_review())
        for vf in violations:
            add_scope_violation_blocker(
                review, vf, active_context.get("id", "unknown")
            )
            events = review.setdefault("scope_violation_events", [])
            # allowed_write lives on the task, not the context
            task_allowed = []
            if active_task_id:
                try:
                    ledger_path = base / ".aiwf" / "state" / "tasks.json"
                    ledger = _read_json(ledger_path, {"tasks": []})
                    for t in ledger.get("tasks", []) or []:
                        if isinstance(t, dict) and t.get("id") == active_task_id:
                            task_allowed = list(t.get("allowed_write", []) or [])
                            break
                except Exception:
                    pass
            event = {
                "path": vf,
                "context_id": active_context.get("id", "unknown"),
                "allowed_write_snapshot": task_allowed,
                "forbidden_write_snapshot": list(active_context.get("forbidden_write", []) or []),
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "status": "recorded",
            }
            if not any(
                isinstance(old, dict)
                and old.get("path") == vf
                and old.get("context_id") == event["context_id"]
                for old in events
            ):
                events.append(event)
        _write_json(review_path, review)

    if drifts:
        from datetime import datetime, timezone
        review_path = base / ".aiwf" / "records" / "review.json"
        from ...core.state_schema import default_review
        review = _read_json(review_path, default_review())
        events = review.setdefault("scope_drift_events", [])
        for drift in drifts:
            event = {
                "path": drift["path"],
                "context_id": active_context.get("id", "unknown"),
                "reason": drift["reason"],
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "status": "recorded",
            }
            if not any(
                isinstance(old, dict)
                and old.get("path") == event["path"]
                and old.get("context_id") == event["context_id"]
                for old in events
            ):
                events.append(event)
        _write_json(review_path, review)

    return violations


def check_and_record_missing_active_task(changed_files: list, base: Path) -> list:
    """Post-tool safety net: log project writes without active task.

    The pre-tool Write guard blocks direct file writes without an active task.
    Bash commands that modify files (mkdir, sed, etc.) pass the Bash guard but
    are detected here. These are recorded for visibility, not permanently
    flagged as violations — the developer was working, not violating.
    """
    project_files = filter_internal(changed_files, cwd=base)
    if not project_files:
        return []
    state_path = base / ".aiwf" / "state" / "state.json"
    state = _read_json(state_path, {})
    if state.get("active_task_id"):
        return []
    # Don't set scope_violation. The pre-tool Write guard is the real gate.
    # Bash-driven file changes without an active task are normal developer activity.
    return project_files
