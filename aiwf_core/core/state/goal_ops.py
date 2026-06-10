"""Goal operations — quality brief, revise, decisions, meta-critique."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ._common import _execution_contract_frozen, _freeze_explanation, _read, _write

def record_quality_brief(
    base_dir: str,
    acceptance_criteria: Optional[List[str]] = None,
    test_focus: Optional[List[str]] = None,
    review_focus: Optional[List[str]] = None,
    non_goals: Optional[List[str]] = None,
    escalation_triggers: Optional[List[str]] = None,
    # ── architecture brief ──
    target_structure: str = "",
    module_boundaries: Optional[List[str]] = None,
    allowed_files: Optional[List[str]] = None,
    protected_files: Optional[List[str]] = None,
    allowed_new_files: Optional[List[str]] = None,
    public_api_changes: Optional[List[str]] = None,
    integration_points: Optional[List[str]] = None,
    architecture_invariants: Optional[List[str]] = None,
    forbidden_restructures: Optional[List[str]] = None,
    architecture_risks: Optional[List[str]] = None,
    migration_source_of_truth: str = "",
    legacy_paths: Optional[List[str]] = None,
    legacy_terms: Optional[List[str]] = None,
    default_entrypoints: Optional[List[str]] = None,
    validators: Optional[List[str]] = None,
    sample_outputs: Optional[List[str]] = None,
    surface_types: Optional[List[str]] = None,
    user_visible_outcome: str = "",
    evaluation_acceptance_criteria: Optional[List[str]] = None,
    evaluation_non_goals: Optional[List[str]] = None,
    test_obligations: Optional[List[str]] = None,
    review_obligations: Optional[List[str]] = None,
    known_risks: Optional[List[str]] = None,
    closure_question: str = "",
    system_integration_obligations: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Write task-specific quality brief; frozen cycles permit additive changes only."""
    base = Path(base_dir)
    goal_path = base / ".aiwf" / "state" / "goal.json"
    goal = _read(goal_path)
    brief = goal.get("quality_brief", {})
    ab = brief.get("architecture_brief", {})
    ec = brief.get("evaluation_contract", {})
    if _execution_contract_frozen(base):
        freeze_note = _freeze_explanation(base)
        for field, proposed in (
            ("acceptance_criteria", acceptance_criteria),
            ("test_focus", test_focus), ("review_focus", review_focus),
            ("non_goals", non_goals), ("escalation_triggers", escalation_triggers),
            ("surface_types", surface_types),
        ):
            if proposed is not None:
                _require_additive_list(brief.get(field), proposed, field, freeze_note)
        for field, proposed in (
            ("module_boundaries", module_boundaries), ("allowed_files", allowed_files),
            ("protected_files", protected_files), ("allowed_new_files", allowed_new_files),
            ("public_api_changes", public_api_changes), ("integration_points", integration_points),
            ("architecture_invariants", architecture_invariants),
            ("forbidden_restructures", forbidden_restructures),
            ("architecture_risks", architecture_risks),
            ("legacy_paths", legacy_paths), ("legacy_terms", legacy_terms),
            ("default_entrypoints", default_entrypoints), ("validators", validators),
            ("sample_outputs", sample_outputs),
        ):
            if proposed is not None:
                _require_additive_list(ab.get(field), proposed, f"architecture_brief.{field}", freeze_note)
        _require_stable_scalar(ab.get("target_structure"), target_structure, "architecture_brief.target_structure", freeze_note)
        _require_stable_scalar(ab.get("migration_source_of_truth"), migration_source_of_truth, "architecture_brief.migration_source_of_truth", freeze_note)
        for field, proposed in (
            ("acceptance_criteria", evaluation_acceptance_criteria),
            ("non_goals", evaluation_non_goals), ("test_obligations", test_obligations),
            ("review_obligations", review_obligations), ("known_risks", known_risks),
            ("system_integration_obligations", system_integration_obligations),
        ):
            if proposed is not None:
                _require_additive_list(ec.get(field), proposed, f"evaluation_contract.{field}", freeze_note)
        _require_stable_scalar(ec.get("user_visible_outcome"), user_visible_outcome, "evaluation_contract.user_visible_outcome", freeze_note)
        _require_stable_scalar(ec.get("closure_question"), closure_question, "evaluation_contract.closure_question", freeze_note)
    if acceptance_criteria is not None: brief["acceptance_criteria"] = acceptance_criteria
    if test_focus is not None: brief["test_focus"] = test_focus
    if review_focus is not None: brief["review_focus"] = review_focus
    if non_goals is not None: brief["non_goals"] = non_goals
    if escalation_triggers is not None: brief["escalation_triggers"] = escalation_triggers
    if surface_types is not None: brief["surface_types"] = surface_types
    # Architecture brief
    if target_structure: ab["target_structure"] = target_structure
    if module_boundaries is not None: ab["module_boundaries"] = module_boundaries
    if allowed_files is not None: ab["allowed_files"] = allowed_files
    if protected_files is not None: ab["protected_files"] = protected_files
    if allowed_new_files is not None: ab["allowed_new_files"] = allowed_new_files
    if public_api_changes is not None: ab["public_api_changes"] = public_api_changes
    if integration_points is not None: ab["integration_points"] = integration_points
    if architecture_invariants is not None: ab["architecture_invariants"] = architecture_invariants
    if forbidden_restructures is not None: ab["forbidden_restructures"] = forbidden_restructures
    if architecture_risks is not None: ab["architecture_risks"] = architecture_risks
    if migration_source_of_truth: ab["migration_source_of_truth"] = migration_source_of_truth
    if legacy_paths is not None: ab["legacy_paths"] = legacy_paths
    if legacy_terms is not None: ab["legacy_terms"] = legacy_terms
    if default_entrypoints is not None: ab["default_entrypoints"] = default_entrypoints
    if validators is not None: ab["validators"] = validators
    if sample_outputs is not None: ab["sample_outputs"] = sample_outputs
    brief["architecture_brief"] = ab
    if user_visible_outcome: ec["user_visible_outcome"] = user_visible_outcome
    if evaluation_acceptance_criteria is not None: ec["acceptance_criteria"] = evaluation_acceptance_criteria
    if evaluation_non_goals is not None: ec["non_goals"] = evaluation_non_goals
    if test_obligations is not None: ec["test_obligations"] = test_obligations
    if review_obligations is not None: ec["review_obligations"] = review_obligations
    if known_risks is not None: ec["known_risks"] = known_risks
    if closure_question: ec["closure_question"] = closure_question
    if system_integration_obligations is not None:
        ec["system_integration_obligations"] = system_integration_obligations
    brief["evaluation_contract"] = ec
    goal["quality_brief"] = brief
    _write(goal_path, goal)
    return goal


def revise_goal(
    base_dir: str,
    new_goal: str,
    reason: str,
    decision: str = "",
    source: str = "user",
) -> Dict[str, Any]:
    """Revise current goal with intent change tracking. Does NOT modify scope/context."""
    base = Path(base_dir)
    goal_path = base / ".aiwf" / "state" / "goal.json"
    goal = _read(goal_path)
    old_goal = goal.get("current_goal") or goal.get("active_goal", "")
    goal["goal_version"] = goal.get("goal_version", 1) + 1
    if not goal.get("original_intent"): goal["original_intent"] = old_goal or new_goal
    goal["current_goal"] = new_goal
    goal["active_goal"] = new_goal
    goal["last_user_intent"] = new_goal
    goal.setdefault("intent_changes", []).append({
        "version": goal["goal_version"], "from": old_goal, "to": new_goal,
        "reason": reason, "decision": decision, "source": source,
    })
    _write(goal_path, goal)
    return goal

def record_goal_decision(
    base_dir: str,
    decision: str,
    source: str = "user",
) -> Dict[str, Any]:
    """Record a goal-level decision without changing the goal text."""
    base = Path(base_dir)
    goal_path = base / ".aiwf" / "state" / "goal.json"
    goal = _read(goal_path)
    goal.setdefault("decisions", []).append({"decision": decision, "source": source})
    _write(goal_path, goal)
    return goal

def record_meta_critique(base_dir: str, summary: str, recorded_by: str = "planner") -> Dict[str, Any]:
    """Record structured Planner meta-critique after review."""
    from datetime import datetime, timezone
    base = Path(base_dir)
    goal_path = base / ".aiwf" / "state" / "goal.json"
    goal = _read(goal_path)
    goal["meta_critique"] = {
        "status": "completed",
        "summary": summary,
        "recorded_by": recorded_by,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    _write(goal_path, goal)
    return goal

