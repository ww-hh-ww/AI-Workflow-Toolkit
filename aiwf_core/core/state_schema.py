"""Backend-neutral AIWF state file schemas.

Defines default values, validation rules, and keys for each .aiwf/*.json file.
No Claude-specific logic belongs here.
"""
from __future__ import annotations

from typing import Any, Dict, List

# ── state.json ────────────────────────────────────────────────────────

def default_state() -> Dict[str, Any]:
    """Minimal state machine core."""
    return {
        "schema_version": 1,
        "phase": "planning",
        "active_goal_id": None,
        "active_plan_id": None,
        "active_task_id": None,
        "active_milestone_id": None,
        "blocked": False,
        "blockers": [],
        "next": "",
        "updated_at": "",
    }

# V2 canonical phases: planning, executing, testing, reviewing, closing, blocked, closed
# V1 aliases kept for backward compat: discussing→planning, planned→planning, implementing→executing
VALID_PHASES = {
    "planning", "executing", "testing", "reviewing", "closing", "blocked", "closed",
    # V1 backward compat
    "discussing", "planned", "implementing",
}

# ── plans.json ────────────────────────────────────────────────────────

LEGACY_GOAL_ID = "GOAL-001"

def default_plans() -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "active_plan_id": None,
        "plans": [],
    }

VALID_RELATION_TYPES = {"depends_on", "blocks", "conflicts_with", "invalidates", "supports"}

# ── goals.json ─────────────────────────────────────────────────────────

# ── V1 Unified Status Sets ──
# Goal / Plan / Milestone: open, closed, cancelled
# Task: ready, active, suspended, closed, cancelled
VALID_GOAL_STATUSES = {"open", "closed", "cancelled"}
VALID_MILESTONE_STATUSES = {"open", "closed", "cancelled"}

# ── V2 Unified Closure ──
# Normal close:    {"status":"closed","closure":{"mode":"normal","accepted":true,"summary":"..."}}
# Force-close:     {"status":"closed","closure":{"mode":"human_force","reason":null,"unsatisfied_checks":[]}}
# Interrupt:       {"status":"suspended","interruption":{"reason":null,"unsatisfied_checks":[]}}
# Cancel:          {"status":"cancelled","cancel_reason":"...","replaced_by":null}

def default_goals() -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "active_goal_id": None,
        "roots": [],
        "goals": [],
        "relations": [],
    }

# ── milestones.json ───────────────────────────────────────────────────

def default_milestones() -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "active_milestone_id": None,
        "mission_id": "",
        "milestones": [],
    }

VALID_MILESTONE_VERDICTS = {"pending", "PASS", "PASS_WITH_RISK", "REVISE", "REJECT"}

# ── contexts.json ─────────────────────────────────────────────────────

# ── implementation.json ───────────────────────────────────────────────

def default_implementation(task_id: str = "") -> Dict[str, Any]:
    return {
        "task_id": task_id,
        "summary": "",
        "implementation_ref": "",
        "recorded_at": "",
    }

# ── testing.json ──────────────────────────────────────────────────────

def default_testing(task_id: str = "") -> Dict[str, Any]:
    return {
        "task_id": task_id,
        "status": "missing",
        "commands": [],
        "summary": "",
        "tested_ref": "",
        "recorded_at": "",
    }

VALID_TESTING_STATUSES = {"missing", "partial", "adequate", "passed", "failed"}
# ── review.json ───────────────────────────────────────────────────────

def default_review(task_id: str = "") -> Dict[str, Any]:
    return {
        "task_id": task_id,
        "result": "unknown",
        "closure_allowed": False,
        "blockers": [],
        "summary": "",
        "adversarial_observations": [],
        "reviewed_ref": "",
        "recorded_at": "",
    }

VALID_REVIEW_RESULTS = {"unknown", "accepted", "needs_fix", "needs_more_testing",
                         "evidence_insufficient", "scope_violation", "rejected"}

# ── claims.json ───────────────────────────────────────────────────────

def default_events() -> Dict[str, Any]:
    return {"events": []}

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
    }

VALID_FIX_LOOP_STATUSES = {"none", "open", "resolved"}

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

VALID_MISSION_STATUSES = {"draft", "active", "complete", "archived"}

# -- tasks.json --

def default_tasks() -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "default_max_active": 1,
        "tasks": [],
    }

# -- all mvp files --

MVP_STATE_FILES = {
    "state/state.json": default_state,
    "state/goals.json": default_goals,
    "state/plans.json": default_plans,
    "state/tasks.json": default_tasks,
    "state/milestones.json": default_milestones,
    "state/fix-loop.json": default_fix_loop,
    "records/implementation.json": default_implementation,
    "records/testing.json": default_testing,
    "records/review.json": default_review,
    "records/events.json": default_events,
}
