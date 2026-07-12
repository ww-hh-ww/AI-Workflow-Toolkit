"""Canonical .aiwf/ path definitions — single source of truth.

V1: Six-zone workspace layout.
  state/   — machine truth (JSON)
  records/ — implementation, testing, review, events
  goals/ plans/ tasks/ milestones/ — narrative docs (Markdown)
  memory/  — planner's small long-term project memory
  config/  — skill-map, command-policy
  runtime/internal/ — toolkit-path, drift, hook and agent logs
"""

import os
from pathlib import Path
from typing import Optional

# ═══════════════════════════════════════════════════════════════════════════
# Zone roots
# ═══════════════════════════════════════════════════════════════════════════

AIWF_DIR = ".aiwf"

STATE_DIR = ".aiwf/state"
RECORDS_DIR = ".aiwf/records"
RUNTIME_DIR = ".aiwf/runtime"

# ═══════════════════════════════════════════════════════════════════════════
# State machine — state/ is stable
# ═══════════════════════════════════════════════════════════════════════════

STATE_JSON = ".aiwf/state/state.json"
GOALS_JSON = ".aiwf/state/goals.json"
PLANS_JSON = ".aiwf/state/plans.json"
TASKS_JSON = ".aiwf/state/tasks.json"
TASK_LEDGER_JSON = ".aiwf/state/tasks.json"
MILESTONES_JSON = ".aiwf/state/milestones.json"
FIX_LOOP_JSON = ".aiwf/state/fix-loop.json"

# ═══════════════════════════════════════════════════════════════════════════
# Records zone — implementation, testing, review, events
# ═══════════════════════════════════════════════════════════════════════════

RECORDS_IMPLEMENTATION = ".aiwf/records/implementation.json"
RECORDS_TESTING = ".aiwf/records/testing.json"
RECORDS_REVIEW = ".aiwf/records/review.json"
RECORDS_EVENTS = ".aiwf/records/events.json"

# ═══════════════════════════════════════════════════════════════════════════
# Narrative dirs — Markdown semantic contracts
# ═══════════════════════════════════════════════════════════════════════════

NARRATIVE_GOALS_DIR = ".aiwf/goals"
NARRATIVE_PLANS_DIR = ".aiwf/plans"
NARRATIVE_TASKS_DIR = ".aiwf/tasks"
NARRATIVE_MILESTONES_DIR = ".aiwf/milestones"

# ═══════════════════════════════════════════════════════════════════════════
# Config zone
# ═══════════════════════════════════════════════════════════════════════════

CONFIG_DIR = ".aiwf/config"

# ═══════════════════════════════════════════════════════════════════════════
# Runtime zone — internal only
# ═══════════════════════════════════════════════════════════════════════════

INTERNAL_DIR = ".aiwf/runtime/internal"
WORKSPACE_DRIFT_JSON = ".aiwf/runtime/internal/workspace-drift.json"

# ═══════════════════════════════════════════════════════════════════════════
# Directory lists — created by install, checked by doctor
# ═══════════════════════════════════════════════════════════════════════════

ALL_DIRS = [
    "state",
    "records",
    "goals", "plans", "tasks", "milestones",
    "memory", "memory/notes",
    "config",
    "runtime", "runtime/internal",
]

# ═══════════════════════════════════════════════════════════════════════════
# Legacy map — old path → new path (for migration/doctor only)
# ═══════════════════════════════════════════════════════════════════════════

LEGACY_MAP = {
    # Flat → state/
    "state.json": STATE_JSON,
    "fix-loop.json": FIX_LOOP_JSON,
    "goals.json": GOALS_JSON,
    "plans.json": PLANS_JSON,
    "tasks.json": TASKS_JSON,
    "task-ledger.json": TASKS_JSON,
    "milestones.json": MILESTONES_JSON,
    # artifacts/ → records/
    "evidence.json": None,
    "testing.json": RECORDS_TESTING,
    "review.json": RECORDS_REVIEW,
    "architecture-review.json": None,
    # Old full paths → records/
    ".aiwf/artifacts/evidence/records.json": None,
    ".aiwf/artifacts/quality/testing.json": RECORDS_TESTING,
    ".aiwf/artifacts/quality/review.json": RECORDS_REVIEW,
    ".aiwf/artifacts/quality/architecture-review.json": None,
    # Old runtime paths
    ".aiwf/runtime/history/task-history.json": None,  # deleted, not migrated
    ".aiwf/runtime/history/task-ledger.json": TASKS_JSON,
}

# ═══════════════════════════════════════════════════════════════════════════
# Path resolver functions
# ═══════════════════════════════════════════════════════════════════════════

def _resolve(base: str, rel: str) -> str:
    return os.path.join(base, rel)


def aiwf_dir(base_dir: str) -> str:
    return _resolve(base_dir, AIWF_DIR)


def state_dir(base_dir: str) -> str:
    return _resolve(base_dir, STATE_DIR)


def records_dir(base_dir: str) -> str:
    return _resolve(base_dir, RECORDS_DIR)


def runtime_dir(base_dir: str) -> str:
    return _resolve(base_dir, RUNTIME_DIR)


def internal_runtime_dir(base_dir: str) -> str:
    return _resolve(base_dir, INTERNAL_DIR)


def plan_narrative_dir(base_dir: str) -> str:
    return _resolve(base_dir, NARRATIVE_PLANS_DIR)
