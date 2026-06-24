"""Testing operations — record_testing."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ._common import _execution_contract_frozen, _freeze_explanation, _read, _write
from .context_ops import record_role_evidence

def record_testing(
    base_dir: str,
    context_id: str = "",
    status: str = "adequate",
    commands: Optional[List[str]] = None,
    evidence_ids: Optional[List[str]] = None,
    untested_risks: Optional[List[str]] = None,
    coverage_summary: str = "",
    failure_summary: str = "",
    failed_obligations: Optional[List[str]] = None,
    failed_commands: Optional[List[str]] = None,
    verification_results: Optional[List[Dict[str, Any]]] = None,
    suspected_route: str = "",
    required_verification: Optional[List[str]] = None,
    acceptance_coverage: Optional[List[str]] = None,
    system_coverage: Optional[List[str]] = None,
    validation_layers: Optional[List[str]] = None,
    full_suite_status: str = "",
    full_suite_reason: str = "",
    real_usage_status: str = "",
    real_usage_reason: str = "",
    inferred_surfaces: Optional[List[str]] = None,
    missing_surface_notes: Optional[List[str]] = None,
    cross_task_risks: Optional[List[str]] = None,
    testing_debt: Optional[List[str]] = None,
    repeated_change_hotspots: Optional[List[str]] = None,
    adversarial_mode: bool = False,
    delta_verification: str = "",
    reused_evidence_ids: Optional[List[str]] = None,
    invalidated_evidence_ids: Optional[List[str]] = None,
    supports_plan: str = "",
    supports_goal: str = "",
    scan_git: bool = True,
) -> Dict[str, Any]:
    """Write testing.json consistently. Returns testing dict.
    scan_git: when True (default), records a git snapshot and advances
    the evidence baseline. Tester writes new tests — capture their diff."""
    base = Path(base_dir)
    testing_path = base / ".aiwf" / "records" / "testing.json"

    testing = _read(testing_path)
    testing["status"] = status
    testing["context_id"] = context_id
    if commands is not None: testing["commands"] = commands
    if evidence_ids is not None: testing["evidence_ids"] = evidence_ids
    if untested_risks is not None: testing["untested_risks"] = untested_risks
    if coverage_summary: testing["coverage_summary"] = coverage_summary
    if status in ("adequate", "passed"):
        testing["failure_summary"] = failure_summary or ""
        testing["failed_obligations"] = failed_obligations or []
        testing["failed_commands"] = failed_commands or []
    else:
        if failure_summary: testing["failure_summary"] = failure_summary
        if failed_obligations is not None: testing["failed_obligations"] = failed_obligations
        if failed_commands is not None: testing["failed_commands"] = failed_commands
    if verification_results is not None: testing["verification_results"] = verification_results
    if suspected_route: testing["suspected_route"] = suspected_route
    if required_verification is not None: testing["required_verification"] = required_verification
    if acceptance_coverage is not None: testing["acceptance_coverage"] = acceptance_coverage
    if system_coverage is not None: testing["system_coverage"] = system_coverage
    if validation_layers is not None: testing["validation_layers"] = validation_layers
    if full_suite_status: testing["full_suite_status"] = full_suite_status
    if full_suite_reason: testing["full_suite_reason"] = full_suite_reason
    if real_usage_status: testing["real_usage_status"] = real_usage_status
    if real_usage_reason: testing["real_usage_reason"] = real_usage_reason
    if inferred_surfaces is not None: testing["inferred_surfaces"] = inferred_surfaces
    if missing_surface_notes is not None: testing["missing_surface_notes"] = missing_surface_notes
    if cross_task_risks is not None: testing["cross_task_risks"] = cross_task_risks
    if testing_debt is not None: testing["testing_debt"] = testing_debt
    if repeated_change_hotspots is not None: testing["repeated_change_hotspots"] = repeated_change_hotspots
    testing["adversarial_mode"] = bool(adversarial_mode)
    if delta_verification: testing["delta_verification"] = delta_verification
    if reused_evidence_ids is not None: testing["reused_evidence_ids"] = reused_evidence_ids
    if invalidated_evidence_ids is not None: testing["invalidated_evidence_ids"] = invalidated_evidence_ids
    if supports_plan: testing["supports_plan"] = supports_plan
    if supports_goal: testing["supports_goal"] = supports_goal
    testing["recorded_at"] = datetime.now(timezone.utc).isoformat()

    try:
        state_for_task = _read(base / ".aiwf" / "state" / "state.json")
        active_task_id = str(state_for_task.get("active_task_id") or "")
        if active_task_id:
            from ..task_ledger import load_ledger
            from ..task_proof import validate_testing_against_task
            task = next(
                (
                    item for item in load_ledger(base_dir).get("tasks", []) or []
                    if isinstance(item, dict) and item.get("id") == active_task_id
                ),
                None,
            )
            if task:
                testing["proof_validation"] = validate_testing_against_task(base_dir, task, testing)
    except Exception as e:
        testing["proof_validation"] = {"error": str(e)}

    _write(testing_path, testing)

    state_path = base / ".aiwf" / "state" / "state.json"
    state = _read(state_path)
    if state.get("phase") not in ("closing", "closed"):
        state["phase"] = "reviewing"
        _write(state_path, state)
    evidence_command = "; ".join(commands or [])
    evidence_summary = coverage_summary or failure_summary or f"testing status={status}"
    ev = record_role_evidence(
        base_dir,
        "tester",
        summary=evidence_summary,
        command=evidence_command,
        context_id=context_id or state.get("active_context_id") or "",
        status="pending",
        exit_code=0 if status in ("adequate", "passed") else 1 if status == "failed" else 0,
        supports_plan=supports_plan,
        supports_goal=supports_goal,
        scan_git=scan_git,
    )
    testing["evidence_id"] = ev["id"]
    _write(testing_path, testing)
    return testing
