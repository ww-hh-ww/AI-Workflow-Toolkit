"""Review operations — record_review."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ._common import _execution_contract_frozen, _freeze_explanation, _read, _write
from ._common import BLOCKING_REVIEW_RESULTS
from .context_ops import record_role_evidence

def record_review(
    base_dir: str,
    result: str = "",
    verdict: str = "",
    quality_dimensions: Optional[Dict[str, Any]] = None,
    review_basis: Optional[Dict[str, Any]] = None,
    closure_allowed: bool = False,
    accepted_evidence_ids: Optional[List[str]] = None,
    rejected_evidence_ids: Optional[List[str]] = None,
    blockers: Optional[List[str]] = None,
    adversarial_observations: Optional[List[Dict[str, Any]]] = None,
    cleanup_status: str = "",
    structure_status: str = "",
    summary: str = "",
    context_id: str = "",
    cleanup_code: str = "",
    docs_checked: str = "",
    root_cause: str = "",
    resolution: str = "",
    resolution_evidence_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Write review.json through a command and append reviewer role evidence.

    V2: accepts verdict (PASS/PASS_WITH_RISK/REVISE/REJECT) and quality_dimensions.
    V1 backward-compat: accepts result (accepted/needs_fix/rejected/...).
    When verdict is provided, result and closure_allowed are derived from it.
    """
    from ..state_schema import (
        VALID_REVIEW_RESULTS, VALID_REVIEW_VERDICTS, VERDICT_TO_RESULT,
        VERDICT_CLOSURE, QUALITY_DIMENSIONS, REVIEW_BASIS,
    )

    # V2 path: verdict drives result and closure
    if verdict:
        if verdict not in VALID_REVIEW_VERDICTS:
            raise ValueError(f"invalid verdict: {verdict} (valid: {', '.join(sorted(VALID_REVIEW_VERDICTS))})")
        result = VERDICT_TO_RESULT.get(verdict, "unknown")
        closure_allowed = VERDICT_CLOSURE.get(verdict, False)
    elif result:
        if result not in VALID_REVIEW_RESULTS or result == "unknown":
            raise ValueError(f"invalid review result: {result}")
    else:
        raise ValueError("either verdict or result is required")

    base = Path(base_dir)
    review_path = base / ".aiwf" / "artifacts" / "quality" / "review.json"
    state = _read(base / ".aiwf" / "state" / "state.json")
    review = _read(review_path)
    previous = json.loads(json.dumps(review))
    previous_verdict = str(previous.get("verdict", "") or "")
    now = datetime.now(timezone.utc).isoformat()

    if previous_verdict in ("REVISE", "REJECT") and verdict in ("PASS", "PASS_WITH_RISK"):
        if not resolution.strip():
            raise ValueError("clearing a prior REVISE/REJECT review requires --resolution")
        testing = _read(base / ".aiwf" / "artifacts" / "quality" / "testing.json")
        previous_at = str(previous.get("recorded_at", "") or "")
        testing_at = str(testing.get("recorded_at", "") or "")
        if not testing_at or (previous_at and testing_at <= previous_at):
            raise ValueError("review blockers require testing to be rerun after the blocking review")
        if not resolution_evidence_ids:
            raise ValueError("clearing review blockers requires --resolution-evidence-id")
        evidence = _read(base / ".aiwf" / "artifacts" / "evidence" / "records.json")
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
                "review resolution evidence IDs not found: " + ", ".join(missing_evidence)
            )

    blocking_observations = [
        obs for obs in (adversarial_observations or [])
        if isinstance(obs, dict) and obs.get("severity") in ("critical", "high")
    ]
    if verdict in ("PASS", "PASS_WITH_RISK") and blocking_observations:
        raise ValueError("CRITICAL/HIGH adversarial observations cannot pass; use REVISE or REJECT")

    history = list(review.get("review_history", []) or [])
    if review.get("recorded_at"):
        history.append({k: v for k, v in previous.items() if k != "review_history"})

    review["verdict"] = verdict or "pending"
    review["result"] = result
    review["closure_allowed"] = bool(closure_allowed)
    review["accepted_evidence_ids"] = list(accepted_evidence_ids or [])
    review["rejected_evidence_ids"] = list(rejected_evidence_ids or [])
    review["blockers"] = list(blockers or [])
    review["recorded_at"] = now
    review["resolution"] = resolution.strip()
    review["resolution_evidence_ids"] = list(resolution_evidence_ids or [])
    review["review_history"] = history

    # V2 quality dimensions
    if quality_dimensions:
        dims = review.setdefault("quality_dimensions", {})
        for dim_name in QUALITY_DIMENSIONS:
            if dim_name in quality_dimensions:
                entry = quality_dimensions[dim_name]
                if isinstance(entry, dict):
                    dims[dim_name] = {
                        "score": entry.get("score", "unscored"),
                        "note": str(entry.get("note", "") or ""),
                    }

    # V2 review basis
    if review_basis:
        basis = review.setdefault("review_basis", {})
        for basis_name in REVIEW_BASIS:
            if basis_name in review_basis:
                entry = review_basis[basis_name]
                if isinstance(entry, dict):
                    basis[basis_name] = {
                        "status": entry.get("status", "missing"),
                        "note": str(entry.get("note", "") or ""),
                    }

    if adversarial_observations is not None:
        review["adversarial_observations"] = adversarial_observations
    if cleanup_status:
        review["cleanup_status"] = cleanup_status
    if structure_status:
        review["structure_status"] = structure_status
    if cleanup_code:
        review["cleanup_code"] = cleanup_code
    if docs_checked:
        review["docs_checked"] = docs_checked
    if root_cause:
        review["root_cause"] = root_cause

    summary_text = summary or f"review verdict={verdict or result}"
    ev = record_role_evidence(
        base_dir,
        "reviewer",
        summary=summary_text,
        command="aiwf state record-review",
        context_id=context_id or state.get("active_context_id") or "",
        status="pending",
        exit_code=0 if (verdict in ("PASS", "PASS_WITH_RISK") or result == "accepted") else 1,
    )
    if (verdict in ("PASS", "PASS_WITH_RISK") or result == "accepted") and ev["id"] not in review["accepted_evidence_ids"]:
        review["accepted_evidence_ids"].append(ev["id"])
    review["reviewer_evidence_id"] = ev["id"]

    if result != "accepted":
        from ..review_contract import set_review_rejected
        set_review_rejected(review, result, blockers or [], rejected_evidence_ids or [])

    # Phase-gate: check BEFORE writing review so a failed gate doesn't
    # leave a dirty PASS/closure_allowed=true state on disk.
    if state.get("phase") not in ("closing", "closed"):
        try:
            from ..phase_gates import testing_to_reviewing_gates
            gate_blockers = testing_to_reviewing_gates(base_dir)
            if gate_blockers:
                raise ValueError(
                    "Phase gate (testing→reviewing) not met:\n" +
                    "\n".join(f"  - {b}" for b in gate_blockers)
                )
        except ValueError:
            raise
        except Exception:
            pass
        state["phase"] = "reviewing"

    _write(review_path, review)
    if state.get("phase") not in ("closing", "closed"):
        _write(base / ".aiwf" / "state" / "state.json", state)
    return review


def _read_current_workflow_level(base_dir: str) -> str:
    """Read current workflow_level from state.json, default to L1_review_light."""
    try:
        data = _read(Path(base_dir) / ".aiwf" / "state" / "state.json")
        return str(data.get("workflow_level", "L1_review_light") or "L1_review_light")
    except Exception:
        return "L1_review_light"


def _severity_for_level(workflow_level: str) -> str:
    """Map workflow level to orphan severity.

    L0/L1: warning — surface but don't escalate
    L2/L3: high — architecture-sensitive, needs attention
    """
    if workflow_level.startswith("L2") or workflow_level.startswith("L3"):
        return "high"
    return "warning"


def _severity_desc(severity: str) -> str:
    return "review_attention (should not pass silently at L2+)" if severity == "high" \
        else "advisory (flag for Planner awareness)"


def check_orphan_patches(base_dir: str) -> Dict[str, Any]:
    """Stage 4: detect work that bypassed Change Admission.

    Returns warnings for:
    1. Tasks without plan_id — no structural home
    2. Plans without target_goal_id — no functional skeleton anchor
    3. Goals with parent but no graft_interface trace — silent skeleton mutation
    4. Cross-parent Relations without reason — opaque cross-branch links

    Severity is graded by workflow level:
    - L0/L1: warning (advisory)
    - L2/L3: high (review_attention, should not pass silently)

    Advisory only — does NOT block closure. Surface these warnings in review output
    so the Reviewer can flag orphan patches for Planner remediation.
    """
    workflow_level = _read_current_workflow_level(base_dir)
    severity = _severity_for_level(workflow_level)

    warnings: List[str] = []

    # 1. Tasks without plan_id
    try:
        from ..task_ledger import load_ledger
        ledger = load_ledger(base_dir)
        for task in ledger.get("tasks", []) or []:
            if not isinstance(task, dict):
                continue
            tid = task.get("id", "")
            plan_id = task.get("plan_id") or task.get("parent_plan") or ""
            if not plan_id:
                tag = "[warning]" if severity == "warning" else "[review_attention]"
                warnings.append(
                    f"Orphan {tag}: task {tid} has no plan_id — it was not admitted through a Plan. "
                    f"Use aiwf task plan {tid} --plan PLAN-XXX to attach it."
                )
    except Exception:
        pass

    # 2. Plans without target_goal_id (or only legacy GOAL-001 without registry entry)
    try:
        from .plan_ops import load_plans
        from .goal_tree_ops import goal_exists
        plans_data = load_plans(base_dir)
        for plan in plans_data.get("plans", []) or []:
            if not isinstance(plan, dict):
                continue
            pid = plan.get("plan_id") or plan.get("id", "")
            tgid = plan.get("target_goal_id") or plan.get("goal_id") or ""
            if not tgid or (tgid == "GOAL-001" and not goal_exists(base_dir, "GOAL-001")):
                tag = "[warning]" if severity == "warning" else "[review_attention]"
                warnings.append(
                    f"Orphan {tag}: plan {pid} has no valid target_goal_id — it is not anchored "
                    f"to any functional skeleton. Use aiwf plan create --target-goal GOAL-XXX."
                )
    except Exception:
        pass

    # 3. Goals with parent_goal_id but no graft_interface trace
    try:
        from .goal_tree_ops import list_goals
        goals = list_goals(base_dir)
        for g in goals:
            if not isinstance(g, dict):
                continue
            gid = g.get("id", "")
            parent = g.get("parent_goal_id")
            if parent and not g.get("graft_interface") and not g.get("graft_history"):
                tag = "[warning]" if severity == "warning" else "[review_attention]"
                warnings.append(
                    f"Orphan {tag}: goal {gid} has parent {parent} but no graft_interface or "
                    f"graft_history trace — it may have been created without an interface "
                    f"declaration. Graft goals through: aiwf goal-tree graft {gid} --target {parent} "
                    f"--interface \"...\" --provides \"...\""
                )
    except Exception:
        pass

    # 4. Cross-parent Relations without reason
    try:
        from .goal_tree_ops import load_goal_tree
        tree = load_goal_tree(base_dir, auto_create=False)
        for rel in tree.get("relations", []) or []:
            if not isinstance(rel, dict):
                continue
            if rel.get("cross_parent") and not rel.get("reason"):
                tag = "[warning]" if severity == "warning" else "[review_attention]"
                src = rel.get("source_id", "")
                tgt = rel.get("target_id", "")
                warnings.append(
                    f"Orphan {tag}: cross-parent relation {src}--[{rel.get('type', '')}]-->{tgt} "
                    f"has no reason — cross-tree links without justification obscure "
                    f"the functional skeleton. Add --reason with aiwf relation add."
                )
    except Exception:
        pass

    return {
        "orphan_patches_found": len(warnings) > 0,
        "severity": severity,
        "severity_description": _severity_desc(severity),
        "workflow_level": workflow_level,
        "warnings": warnings,
        "summary": f"{len(warnings)} orphan patch(es) detected" if warnings
                   else "No orphan patches detected",
    }


# ═══════════════════════════════════════════════════════════════════════════
# Stage 4.4: Admission-aware Review
# ═══════════════════════════════════════════════════════════════════════════

def check_admission_trace(base_dir: str) -> Dict[str, Any]:
    """Check that Plans and Goals created via admission have valid trace entries.

    Stage 4.4: Lightweight patches/tasks must be owned by an existing Plan.
    Every change must have a structural home — but not every change needs a new Plan.

    Returns warnings about:
    - Plans with admission_trace but missing target_goal_id
    - Goals with admission_trace that is graft_goal but missing graft_interface
    - Temporary roots without reason
    - Lightweight patches/tasks without target_plan_id or active plan
    """
    workflow_level = _read_current_workflow_level(base_dir)
    severity = _severity_for_level(workflow_level)
    tag = "[warning]" if severity == "warning" else "[review_attention]"
    warnings: List[str] = []

    # Plans: check admission_trace consistency
    try:
        from .plan_ops import load_plans
        plans_data = load_plans(base_dir)
        for plan in plans_data.get("plans", []) or []:
            if not isinstance(plan, dict):
                continue
            pid = plan.get("plan_id") or plan.get("id", "")
            trace = plan.get("admission_trace")

            if trace and isinstance(trace, dict):
                at = str(trace.get("admission_type") or "")
                granularity = str(trace.get("action_granularity") or "plan")
                trace_plan_id = str(trace.get("target_plan_id") or "")

                # Lightweight patch/task must have target_plan_id
                if granularity in ("patch", "task") and not trace_plan_id:
                    # Check if there's an active plan as fallback
                    active_plan = plans_data.get("active_plan_id", "")
                    if not active_plan:
                        warnings.append(
                            f"Admission {tag}: plan {pid} trace says {granularity} "
                            f"but has no target_plan_id and no active plan. "
                            f"Lightweight changes must be owned by an existing Plan."
                        )

                # attach_plan admission → must have target_goal_id
                if at == "attach_plan":
                    tgid = plan.get("target_goal_id") or ""
                    if not tgid or (tgid == "GOAL-001" and not _quick_goal_exists(base_dir, "GOAL-001")):
                        warnings.append(
                            f"Admission {tag}: plan {pid} has attach_plan admission_trace "
                            f"but no valid target_goal_id. Anchor it to a functional Goal."
                        )

            # Without trace: covered by check_orphan_patches
    except Exception:
        pass

    # Goals: check admission_trace and graft interface consistency
    try:
        from .goal_tree_ops import list_goals
        goals = list_goals(base_dir)
        for g in goals:
            if not isinstance(g, dict):
                continue
            gid = g.get("id", "")
            trace = g.get("admission_trace")
            parent = g.get("parent_goal_id")

            if trace and isinstance(trace, dict):
                at = str(trace.get("admission_type") or "")
                validated = trace.get("validated", False)

                if not validated:
                    warnings.append(
                        f"Admission {tag}: goal {gid} has admission_trace but "
                        f"validated=false — decision was not machine-validated."
                    )

                # graft_goal admission → must have graft_interface
                if at == "graft_goal":
                    gi = g.get("graft_interface") or {}
                    if not gi and not g.get("graft_history"):
                        warnings.append(
                            f"Admission {tag}: goal {gid} admitted as graft_goal "
                            f"but has no graft_interface or graft_history. "
                            f"Graft through: aiwf goal-tree graft {gid} —interface \"...\" --provides \"...\""
                        )
                    elif gi:
                        if not gi.get("consumed"):
                            warnings.append(
                                f"Admission {tag}: goal {gid} graft_interface missing "
                                f"interface_consumed — what interface does it consume from parent?"
                            )
                        if not gi.get("provided"):
                            warnings.append(
                                f"Admission {tag}: goal {gid} graft_interface missing "
                                f"capability_provided — what does it provide to the parent?"
                            )

                # temporary_root admission → must have root_type=temporary or reason
                if at == "temporary_root":
                    rt = g.get("root_type")
                    if rt != "temporary":
                        warnings.append(
                            f"Admission {tag}: goal {gid} admitted as temporary_root "
                            f"but root_type is '{rt}', not 'temporary'."
                        )

            # Goal with parent but no trace at all — covered by check_orphan_patches
    except Exception:
        pass

    return {
        "admission_trace_issues_found": len(warnings) > 0,
        "severity": severity,
        "warnings": warnings,
        "summary": f"{len(warnings)} admission trace issue(s) detected" if warnings
                   else "Admission traces valid",
    }


def check_operation_alignment(base_dir: str) -> Dict[str, Any]:
    """Check that actual structures align with their admission decisions.

    - If a Plan's admission_trace says graft_goal, there should be a corresponding Goal graft
    - Structural Plans should have --kind structural in plan_kind
    """
    workflow_level = _read_current_workflow_level(base_dir)
    severity = _severity_for_level(workflow_level)
    tag = "[warning]" if severity == "warning" else "[review_attention]"
    warnings: List[str] = []

    try:
        from .plan_ops import load_plans
        from .goal_tree_ops import list_goals
        plans_data = load_plans(base_dir)
        goals = list_goals(base_dir)
        goal_ids = {g.get("id") for g in goals if isinstance(g, dict) and g.get("id")}

        for plan in plans_data.get("plans", []) or []:
            if not isinstance(plan, dict):
                continue
            pid = plan.get("plan_id") or plan.get("id", "")
            trace = plan.get("admission_trace")

            if not trace or not isinstance(trace, dict):
                continue

            at = str(trace.get("admission_type") or "")
            pk = str(plan.get("plan_kind") or "")
            tgid = str(plan.get("target_goal_id") or "")

            # Structural admission → plan_kind should be structural
            if at == "graft_goal" and pk != "structural":
                warnings.append(
                    f"Alignment {tag}: plan {pid} has graft_goal admission_trace "
                    f"but plan_kind is '{pk}', not 'structural'. "
                    f"Grafts require a structural Plan to frame the new Goal."
                )

            # attach_plan admission → target_goal should exist in tree
            if at == "attach_plan" and tgid:
                if tgid not in goal_ids and not (tgid == "GOAL-001" and _quick_goal_exists(base_dir, "GOAL-001")):
                    warnings.append(
                        f"Alignment {tag}: plan {pid} targets {tgid} "
                        f"but this Goal does not exist in the tree."
                    )

    except Exception:
        pass

    return {
        "alignment_issues_found": len(warnings) > 0,
        "severity": severity,
        "warnings": warnings,
        "summary": f"{len(warnings)} alignment issue(s) detected" if warnings
                   else "Operation alignment valid",
    }


def admission_review(base_dir: str) -> Dict[str, Any]:
    """Stage 4.4: Combined admission-aware review.

    Aggregates: orphan patches, admission trace issues, operation alignment.
    Returns a structured summary suitable for review output.

    Does NOT mutate state. Does NOT block closure.
    """
    orphan = check_orphan_patches(base_dir)
    trace = check_admission_trace(base_dir)
    alignment = check_operation_alignment(base_dir)

    workflow_level = _read_current_workflow_level(base_dir)
    severity = _severity_for_level(workflow_level)

    all_warnings = (
        list(orphan.get("warnings", []) or []) +
        list(trace.get("warnings", []) or []) +
        list(alignment.get("warnings", []) or [])
    )

    total_issues = (
        (1 if orphan.get("orphan_patches_found") else 0) +
        (1 if trace.get("admission_trace_issues_found") else 0) +
        (1 if alignment.get("alignment_issues_found") else 0)
    )

    # Determine if any admission trace exists at all
    has_any_trace = False
    try:
        from .plan_ops import load_plans
        plans_data = load_plans(base_dir)
        for plan in plans_data.get("plans", []) or []:
            if isinstance(plan, dict) and plan.get("admission_trace"):
                has_any_trace = True
                break
    except Exception:
        pass

    return {
        "admission_review_complete": True,
        "total_issues": total_issues,
        "severity": severity,
        "has_admission_trace": has_any_trace,
        "orphan_patches": {
            "found": orphan.get("orphan_patches_found", False),
            "count": len(orphan.get("warnings", []) or []),
        },
        "admission_trace_issues": {
            "found": trace.get("admission_trace_issues_found", False),
            "count": len(trace.get("warnings", []) or []),
        },
        "operation_alignment": {
            "found": alignment.get("alignment_issues_found", False),
            "count": len(alignment.get("warnings", []) or []),
        },
        "warnings": all_warnings,
        "summary": (
            f"Admission review: {total_issues} issue(s) at {severity} severity. "
            f"Orphan patches: {'yes' if orphan.get('orphan_patches_found') else 'no'}. "
            f"Trace issues: {'yes' if trace.get('admission_trace_issues_found') else 'no'}. "
            f"Alignment issues: {'yes' if alignment.get('alignment_issues_found') else 'no'}."
        ),
        "next_review_focus": _admission_review_focus(orphan, trace, alignment, severity),
    }


def _quick_goal_exists(base_dir: str, goal_id: str) -> bool:
    """Lightweight goal existence check without loading full tree."""
    try:
        from .goal_tree_ops import goal_exists
        return goal_exists(base_dir, goal_id)
    except Exception:
        return False


def _admission_review_focus(orphan: Dict, trace: Dict, alignment: Dict,
                            severity: str) -> str:
    """Generate a human-readable review focus from admission review results."""
    foci = []
    if orphan.get("orphan_patches_found"):
        foci.append("orphan patches present")
    if trace.get("admission_trace_issues_found"):
        foci.append("admission trace incomplete")
    if alignment.get("alignment_issues_found"):
        foci.append("operation alignment mismatched")
    if not foci:
        return "Admission protocol followed — no structural issues detected."
    return (
        f"{', '.join(foci)} at {severity} severity. "
        f"Review the admission decision and verify structural integrity."
    )
