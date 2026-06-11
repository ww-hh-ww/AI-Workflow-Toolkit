"""Gate checker using backend-neutral core.

Evaluates closure gates from .aiwf state files.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from ...core.closure_contract import closure_conditions_met
from ...core.gate_engine import build_status_context
from ...core.review_contract import promote_evidence
from ...core.state_schema import (
    default_state, default_goal, default_evidence,
    default_testing, default_review, default_fix_loop,
)


def _read_json(path: Path, default: Dict) -> Dict:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def load_all_state(cwd: Path) -> Dict[str, Any]:
    """Load all .aiwf state files from a project root."""
    return {
        "state": _read_json(cwd / ".aiwf" / "state" / "state.json", default_state()),
        "goal": _read_json(cwd / ".aiwf" / "state" / "goal.json", default_goal()),
        "contexts": _read_json(cwd / ".aiwf" / "state" / "contexts.json", {"contexts": []}),
        "evidence": _read_json(cwd / ".aiwf" / "evidence" / "records.json", default_evidence()),
        "testing": _read_json(cwd / ".aiwf" / "quality" / "testing.json", default_testing()),
        "review": _read_json(cwd / ".aiwf" / "quality" / "review.json", default_review()),
        "fix_loop": _read_json(cwd / ".aiwf" / "state" / "fix-loop.json", default_fix_loop()),
    }


def eval_closure_gates(cwd: Path) -> Dict[str, Any]:
    """Load state, promote evidence from review, then evaluate closure gates.

    Evidence promotion is mechanical state normalization: records listed in
    review.accepted_evidence_ids get status="accepted", rejected get status="rejected".
    This happens deterministically before every gate check so the user/Claude
    does not need to manually edit evidence.json statuses.
    """
    s = load_all_state(cwd)

    # Promote evidence before gate check (mechanical, not semantic)
    # Always save so evidence.json on disk reflects promoted status
    evidence_path = cwd / ".aiwf" / "evidence" / "records.json"
    import json
    promoted = promote_evidence(s["evidence"], s["review"])
    evidence_path.write_text(
        json.dumps(promoted, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    s["evidence"] = promoted

    result = closure_conditions_met(
        s["state"], s["evidence"], s["testing"],
        s["review"], s["fix_loop"],
    )

    # Impact review check: verify Impact declarations against actual changes
    # Only runs when there's an active close attempt with an active task
    active_task_id = s["state"].get("active_task_id", "") or ""
    if active_task_id and s["state"].get("close_attempt"):
        try:
            from aiwf_core.core.task_plan import validate_plan_impact, impact_review_check

            # Re-validate Impact completeness at close time
            impact_issues = validate_plan_impact(str(cwd), active_task_id)
            if impact_issues:
                result["blockers"].append(
                    f"Active plan Impact incomplete: {'; '.join(impact_issues[:3])}"
                )
                result["missing"].append("impact")
                result["passed"] = False

            # Collect changed files from accepted evidence
            accepted_records = [
                r for r in s["evidence"].get("records", []) or []
                if isinstance(r, dict) and r.get("status") == "accepted"
            ]
            changed_files = []
            for r in accepted_records:
                changed_files.extend(r.get("changed_files", []) or [])

            if changed_files:
                impact = impact_review_check(str(cwd), active_task_id, changed_files)
                if impact["blockers"]:
                    result["blockers"].extend(impact["blockers"])
                    result["missing"].append("impact")
                    result["passed"] = False
                if impact["warnings"]:
                    result.setdefault("warnings", []).extend(impact["warnings"])
        except Exception as e:
            result["blockers"].append(f"Impact consistency check failed: {e}")
            result["missing"].append("impact")
            result["passed"] = False

    return result


def get_status_context(cwd: Path) -> Dict[str, Any]:
    """Load state and build a status context for UserPromptSubmit."""
    s = load_all_state(cwd)
    ctx = build_status_context(s["state"], s["goal"], s["review"], s["fix_loop"])
    return {
        "phase": ctx.phase,
        "active_goal": ctx.active_goal,
        "active_context_id": ctx.active_context_id,
        "close_attempt": ctx.close_attempt,
        "scope_violation": ctx.scope_violation,
        "review_result": ctx.review_result,
        "fix_loop_status": ctx.fix_loop_status,
        "fix_loop_route": ctx.fix_loop_route,
        "next_gate": ctx.next_gate,
        "messages": ctx.messages,
    }
