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
        # V2-A routing topology dimensions
        "verification_need": "standard",
        "review_need": "optional_light_review",
        "downgrade_allowed": True,
        "substitution_allowed": False,
        "routing_reasons": [],
        "hard_constraints": [],
        "substitution_records": [],
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
    # V2-A routing topology (execution_topology derived from workflow_level)
    "verification_need", "review_need",
    "downgrade_allowed", "substitution_allowed",
    "routing_reasons", "hard_constraints", "substitution_records",
}

VALID_PHASES = {
    "discussing", "planned", "implementing", "testing",
    "reviewing", "closing", "closed",
}

VALID_REQUEST_MODES = {"discussion", "clarification", "research", "spike", "execution"}
VALID_WORKFLOW_PATTERNS = {
    "linear", "clarification_first", "research_first", "spike_first", "adversarial_early",
}
VALID_VERIFICATION_NEEDS = {"deterministic", "standard", "broad", "adversarial"}
VALID_EXECUTION_TOPOLOGIES = {
    "single_agent", "single_agent_with_machine_evidence",
    "light_review", "standard_team", "fanout_merge",
}
VALID_REVIEW_NEEDS = {"none", "optional_light_review", "required_review", "adversarial_review"}


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
        "confirmed": True,
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
                "migration_source_of_truth": "",
                "legacy_paths": [],
                "legacy_terms": [],
                "default_entrypoints": [],
                "validators": [],
                "sample_outputs": [],
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


# ── plans.json ────────────────────────────────────────────────────────

LEGACY_GOAL_ID = "GOAL-001"


def default_plans() -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "legacy_goal_id": LEGACY_GOAL_ID,
        "active_plan_id": None,
        "plans": [],
    }

PLANS_KEYS = {"schema_version", "legacy_goal_id", "active_plan_id", "plans"}

VALID_PLAN_KINDS = {"structural", "implementation", "verification", "migration", "exploration"}
DEFAULT_PLAN_KIND = "implementation"

# Plan phase loading — a structural Plan is loaded differently across the
# lifecycle of its parent Goal. Framing defines structure/interfaces/boundaries;
# integration reconciles lower-level outputs and prepares sealing.
VALID_PLAN_PHASES = {"framing", "implementation", "integration", "seal"}
DEFAULT_PLAN_PHASE = "implementation"

VALID_RELATION_TYPES = {"depends_on", "blocks", "conflicts_with", "invalidates", "supports"}


# ── goals.json ─────────────────────────────────────────────────────────

VALID_ROOT_TYPES = {"main", "temporary", "branch"}

VALID_GOAL_STATUSES = {"discussion", "active", "stable", "superseded", "archived"}


def default_goals() -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "active_goal_id": None,
        "roots": [],
        "goals": [],
        "relations": [],
    }

GOALS_KEYS = {"schema_version", "active_goal_id", "roots", "goals", "relations"}


# ── milestones.json ───────────────────────────────────────────────────

def default_milestones() -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "active_milestone_id": None,
        "mission_id": "",
        "milestones": [],
    }

MILESTONES_KEYS = {"schema_version", "active_milestone_id", "mission_id", "milestones"}

VALID_MILESTONE_STATUSES = {
    "pending", "active", "complete_candidate", "completed", "archived",
}
VALID_MILESTONE_VERDICTS = {"pending", "PASS", "PASS_WITH_RISK", "REVISE", "REJECT"}
VALID_MILESTONE_SCOPE_TYPES = {"goal_subtree", "plan_set", "task_set", "mixed"}
VALID_MILESTONE_STABILITY_CLAIMS = {"draft", "usable", "stable", "risky"}

# Stage 4.7.4: Work Intent Discipline
VALID_WORK_INTENTS = {
    "feature", "bugfix", "refactor", "cleanup", "migration",
    "verification", "exploration", "documentation", "integration", "release",
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
        "supports_plan": "",
        "supports_goal": "",
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
TESTING_KEYS.update({"supports_plan", "supports_goal"})

VALID_TESTING_STATUSES = {"missing", "partial", "adequate", "passed", "failed"}
VALID_LAYER_STATUSES = {"not_run", "passed", "failed", "not_available", "not_feasible"}

VALID_SUSPECTED_ROUTES = {"executor", "tester", "planner", "environment", ""}


# ── review.json ───────────────────────────────────────────────────────

def default_review() -> Dict[str, Any]:
    return {
        # V2 verdict — quality outcome, not just process check
        "verdict": "pending",  # pending | PASS | PASS_WITH_RISK | REVISE | REJECT
        "result": "unknown",   # V1 backward-compat (derived from verdict)
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
        # V2 quality dimensions — reviewer scores each axis
        "quality_dimensions": {
            "requirement_fit": {"score": "unscored", "note": ""},
            "architecture_fit": {"score": "unscored", "note": ""},
            "minimality": {"score": "unscored", "note": ""},
            "correctness": {"score": "unscored", "note": ""},
            "test_adequacy": {"score": "unscored", "note": ""},
            "maintainability": {"score": "unscored", "note": ""},
            "risk_debt": {"score": "unscored", "note": ""},
            "human_trust": {"score": "unscored", "note": ""},
        },
        # V2 review basis — reviewer states which closure sources were evaluated.
        "review_basis": {
            "goal": {"status": "missing", "note": ""},
            "plan": {"status": "missing", "note": ""},
            "scope": {"status": "missing", "note": ""},
            "evidence": {"status": "missing", "note": ""},
            "testing": {"status": "missing", "note": ""},
            "impact": {"status": "missing", "note": ""},
        },
    }

REVIEW_KEYS = {
    "verdict", "result", "closure_allowed", "accepted_evidence_ids", "rejected_evidence_ids",
    "blockers", "cleanup_status", "cleanup_notes", "stale_items", "cleanup_blockers",
    "cleanup_verified_at",
    "structure_status", "structure_blockers", "technical_debt_notes",
    "overengineering_risks", "architecture_impact",
    "cross_task_risks", "architecture_drift", "testing_debt",
    "repeated_change_hotspots", "adversarial_observations",
    "scope_violation_events",
    "lessons", "negative_patterns", "followups",
    "reviewer_evidence_id", "quality_dimensions", "review_basis",
}

VALID_REVIEW_VERDICTS = {"pending", "PASS", "PASS_WITH_RISK", "REVISE", "REJECT"}

# V1 backward-compat: old result values still accepted, mapped from verdict
VALID_REVIEW_RESULTS = {"unknown", "accepted", "needs_fix", "needs_more_testing",
                         "evidence_insufficient", "scope_violation", "rejected"}

VALID_DIMENSION_SCORES = {"unscored", "PASS", "RISK", "FAIL"}
VALID_BASIS_STATUSES = {"missing", "covered", "gap", "not_applicable"}

QUALITY_DIMENSIONS = [
    "requirement_fit",
    "architecture_fit",
    "minimality",
    "correctness",
    "test_adequacy",
    "maintainability",
    "risk_debt",
    "human_trust",
]

REVIEW_BASIS = [
    "goal",
    "plan",
    "scope",
    "evidence",
    "testing",
    "impact",
]

# Verdict → V1 result mapping (for backward compat)
VERDICT_TO_RESULT = {
    "pending": "unknown",
    "PASS": "accepted",
    "PASS_WITH_RISK": "accepted",
    "REVISE": "needs_fix",
    "REJECT": "rejected",
}

# Verdict → closure_allowed
VERDICT_CLOSURE = {
    "pending": False,
    "PASS": True,
    "PASS_WITH_RISK": True,
    "REVISE": False,
    "REJECT": False,
}


# ── claims.json ───────────────────────────────────────────────────────

def default_claims() -> Dict[str, Any]:
    return {"claims": []}

CLAIMS_KEYS = {"claims"}

VALID_CLAIM_STATUSES = {"pending", "supported", "unsupported", "overclaimed", "disputed"}

# Strength: strong (machine-observed, reproducible), weak (prose-only, single source)
VALID_CLAIM_STRENGTHS = {"strong", "weak", "none"}


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


def default_mission() -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "id": "MISSION-001",
        "type": "mission",
        "status": "draft",
        "version": 1,
        "statement": "",
        "boundaries": [],
        "milestone_ids": [],
        "goal_tree_root_ids": [],
        "created_at": "",
        "updated_at": "",
    }

MISSION_KEYS = {
    "schema_version", "id", "type", "status", "version",
    "statement", "boundaries", "milestone_ids", "goal_tree_root_ids",
    "created_at", "updated_at",
}

VALID_MISSION_STATUSES = {"draft", "active", "complete", "archived"}


# ── all mvp files ─────────────────────────────────────────────────────

MVP_STATE_FILES = {
    "state/state.json": default_state,
    "state/goal.json": default_goal,
    "state/mission.json": default_mission,
    "state/goals.json": default_goals,
    "state/plans.json": default_plans,
    "state/milestones.json": default_milestones,
    "state/contexts.json": default_contexts,
    "artifacts/evidence/records.json": default_evidence,
    "artifacts/quality/testing.json": default_testing,
    "artifacts/quality/review.json": default_review,
    "state/fix-loop.json": default_fix_loop,
}
