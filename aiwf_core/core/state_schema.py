"""Backend-neutral AIWF state file schemas.

Defines default values, validation rules, and keys for each .aiwf/*.json file.
No Claude-specific logic belongs here.
"""
from __future__ import annotations

from typing import Any, Dict, List


# ── state.json ────────────────────────────────────────────────────────

def default_state() -> Dict[str, Any]:
    return {
        "phase": "discussing",
        "active_context_id": None,
        "close_attempt": False,
        "closure_allowed": False,
        "scope_violation": False,
        "complexity": "standard",
        "routing_reason": "",
        "workflow_level": "L1_review_light",
        "workflow_strength": "standard",  # DEPRECATED: use workflow_level instead
        "routing_score": 0,
        "routing_factors": [],
        "routing_background_factors": [],
        "escalation_history": [],
        "task_type": "",
        "risk_flags": [],
        "test_template": "",
        "review_template": "",
        "exploration_budget": "",
        "asset_policy": "",
        "cleanup_policy": "",
        "git_policy": "no_auto_commit",
        "quality_policy_reason": "",
        "recommended_minimum_level": "",
        "requires_user_decision": False,
        "quality_escalation_required": False,
        "quality_escalation_reason": "",
        "active_task_id": None,
        "planner_inline": False,
        "cross_task_quality_escalation_required": False,
        "cross_task_quality_escalation_reason": "",
        "adversarial_mode": False,
        "request_mode": "execution",
        "workflow_pattern": "linear",
        "pattern_reason": "",
        "external_research_required": False,
        "active_plan_id": "",
        "planned_capability_ids": [],
    }

STATE_KEYS = {
    "phase", "active_context_id", "close_attempt", "closure_allowed",
    "scope_violation", "complexity", "routing_reason",
    "workflow_strength", "workflow_level", "routing_score",
    "routing_factors", "routing_background_factors", "escalation_history",
    "task_type", "risk_flags", "test_template", "review_template",
    "exploration_budget", "asset_policy", "cleanup_policy",
    "git_policy", "quality_policy_reason",
    "recommended_minimum_level", "requires_user_decision",
    "quality_escalation_required", "quality_escalation_reason",
    "active_task_id", "planner_inline",
    "cross_task_quality_escalation_required", "cross_task_quality_escalation_reason",
    "adversarial_mode",
    "request_mode", "workflow_pattern", "pattern_reason",
    "external_research_required", "active_plan_id", "planned_capability_ids",
}

VALID_PHASES = {
    "discussing", "planned", "implementing", "testing",
    "reviewing", "closing", "closed",
}

VALID_REQUEST_MODES = {"discussion", "clarification", "research", "spike", "execution"}
VALID_WORKFLOW_PATTERNS = {
    "linear", "clarification_first", "research_first", "spike_first", "adversarial_early",
}


def validate_state(state: Dict[str, Any]) -> List[str]:
    """Return list of issues, empty if valid."""
    issues = []
    phase = state.get("phase", "")
    if phase not in VALID_PHASES:
        issues.append(f"Unknown phase: {phase}")
    request_mode = state.get("request_mode", "execution")
    if request_mode not in VALID_REQUEST_MODES:
        issues.append(f"Unknown request_mode: {request_mode}")
    workflow_pattern = state.get("workflow_pattern", "linear")
    if workflow_pattern not in VALID_WORKFLOW_PATTERNS:
        issues.append(f"Unknown workflow_pattern: {workflow_pattern}")
    if state.get("scope_violation") and state.get("closure_allowed"):
        issues.append("scope_violation=true but closure_allowed=true")
    if state.get("close_attempt") and not state.get("closure_allowed") and state.get("phase") != "closing":
        issues.append("close_attempt=true but closure_allowed=false outside closing phase")
    return issues


# ── goal.json ─────────────────────────────────────────────────────────

def default_goal() -> Dict[str, Any]:
    return {
        "goal_version": 1,
        "original_intent": "",
        "current_goal": "",
        "active_goal": "",
        "goal_status": "discussion",
        "confirmed": False,
        "last_user_intent": "",
        "intent_changes": [],
        "decisions": [],
        "meta_critique": {
            "status": "missing",
            "summary": "",
            "recorded_by": "",
            "recorded_at": "",
        },
        "open_questions": [],
        "superseded_goals": [],
        "quality_brief": {
            "acceptance_criteria": [],
            "test_focus": [],
            "review_focus": [],
            "non_goals": [],
            "escalation_triggers": [],
            "surface_types": [],
            "architecture_brief": {
                "target_structure": "",
                "module_boundaries": [],
                "allowed_files": [],
                "protected_files": [],
                "allowed_new_files": [],
                "public_api_changes": [],
                "integration_points": [],
                "architecture_invariants": [],
                "forbidden_restructures": [],
                "architecture_risks": [],
            },
            "evaluation_contract": {
                "user_visible_outcome": "",
                "acceptance_criteria": [],
                "non_goals": [],
                "test_obligations": [],
                "review_obligations": [],
                "known_risks": [],
                "closure_question": "",
                "system_integration_obligations": [],
            },
        },
    }

GOAL_KEYS = {
    "goal_version", "original_intent", "current_goal", "active_goal",
    "goal_status", "confirmed", "last_user_intent",
    "intent_changes", "decisions", "meta_critique", "open_questions", "superseded_goals",
    "quality_brief",
}


# ── contexts.json ─────────────────────────────────────────────────────

def default_contexts() -> Dict[str, Any]:
    return {"contexts": []}

CONTEXTS_KEYS = {"contexts"}


def active_context(contexts: Dict[str, Any], context_id: str) -> Dict[str, Any]:
    """Get the active context entry by id."""
    for ctx in contexts.get("contexts", []):
        if ctx.get("id") == context_id:
            return ctx
    return {}


# ── evidence.json ─────────────────────────────────────────────────────

def default_evidence() -> Dict[str, Any]:
    return {"records": []}

EVIDENCE_KEYS = {"records"}


# ── testing.json ──────────────────────────────────────────────────────

def default_testing() -> Dict[str, Any]:
    return {
        "status": "missing",
        "commands": [],
        "untested_risks": [],
        "failure_summary": "",
        "failed_obligations": [],
        "failed_commands": [],
        "suspected_route": "",
        "required_verification": [],
        "acceptance_coverage": [],
        "system_coverage": [],
        "validation_layers": [],
        "full_suite_status": "not_run",
        "full_suite_reason": "",
        "real_usage_status": "not_run",
        "real_usage_reason": "",
        "inferred_surfaces": [],
        "missing_surface_notes": [],
        "cross_task_risks": [],
        "testing_debt": [],
        "repeated_change_hotspots": [],
        "adversarial_mode": False,
        "evidence_id": "",
    }

TESTING_KEYS = {"status", "commands", "untested_risks",
                "failure_summary", "failed_obligations", "failed_commands",
                "suspected_route", "required_verification",
                "acceptance_coverage", "system_coverage",
                "validation_layers", "full_suite_status", "full_suite_reason",
                "real_usage_status", "real_usage_reason",
                "inferred_surfaces", "missing_surface_notes"}
TESTING_KEYS.update({"cross_task_risks", "testing_debt", "repeated_change_hotspots", "adversarial_mode"})
TESTING_KEYS.add("evidence_id")

VALID_TESTING_STATUSES = {"missing", "partial", "adequate", "passed", "failed"}
VALID_LAYER_STATUSES = {"not_run", "passed", "failed", "not_available", "not_feasible"}

VALID_SUSPECTED_ROUTES = {"executor", "tester", "planner", "environment", ""}


# ── review.json ───────────────────────────────────────────────────────

def default_review() -> Dict[str, Any]:
    return {
        "result": "unknown",
        "closure_allowed": False,
        "accepted_evidence_ids": [],
        "rejected_evidence_ids": [],
        "blockers": [],
        "cleanup_status": "unknown",
        "cleanup_verified_at": "",
        "cleanup_notes": [],
        "stale_items": [],
        "cleanup_blockers": [],
        "structure_status": "unknown",
        "structure_blockers": [],
        "technical_debt_notes": [],
        "overengineering_risks": [],
        "architecture_impact": "none",
        "cross_task_risks": [],
        "architecture_drift": [],
        "testing_debt": [],
        "repeated_change_hotspots": [],
        "adversarial_observations": [],
        "scope_violation_events": [],
        "lessons": [],
        "negative_patterns": [],
        "followups": [],
        "reviewer_evidence_id": "",
    }

REVIEW_KEYS = {
    "result", "closure_allowed", "accepted_evidence_ids", "rejected_evidence_ids",
    "blockers", "cleanup_status", "cleanup_notes", "stale_items", "cleanup_blockers",
    "cleanup_verified_at",
    "structure_status", "structure_blockers", "technical_debt_notes",
    "overengineering_risks", "architecture_impact",
    "cross_task_risks", "architecture_drift", "testing_debt",
    "repeated_change_hotspots", "adversarial_observations",
    "scope_violation_events",
    "lessons", "negative_patterns", "followups",
    "reviewer_evidence_id",
}

VALID_REVIEW_RESULTS = {"unknown", "accepted", "needs_fix", "needs_more_testing",
                         "evidence_insufficient", "scope_violation", "rejected"}


# ── fix-loop.json ─────────────────────────────────────────────────────

def default_fix_loop() -> Dict[str, Any]:
    return {
        "status": "none",
        "route": None,
        "required_fixes": [],
        "required_verification": [],
        "reason": "",
        "source": "",
        "resolution": "",
        "attempt_count": 0,
        "max_attempts": 0,
        "route_history": [],
        "escalation_required": False,
        "escalation_reason": "",
        "rollback_recommended": False,
        "architecture_change_requests": [],
    }

FIX_LOOP_KEYS = {"status", "route", "required_fixes",
                  "required_verification", "reason", "source", "resolution",
                  "attempt_count", "max_attempts", "route_history",
                  "escalation_required", "escalation_reason", "rollback_recommended",
                  "architecture_change_requests"}

VALID_FIX_LOOP_STATUSES = {"none", "open", "resolved"}

# max_attempts per workflow level
LEVEL_MAX_ATTEMPTS = {"L0_direct": 1, "L1_review_light": 1,
                       "L2_standard_team": 2, "L3_full_power": 3}


# ── all mvp files ─────────────────────────────────────────────────────

MVP_STATE_FILES = {
    "state/state.json": default_state,
    "state/goal.json": default_goal,
    "state/contexts.json": default_contexts,
    "evidence/records.json": default_evidence,
    "quality/testing.json": default_testing,
    "quality/review.json": default_review,
    "state/fix-loop.json": default_fix_loop,
}
