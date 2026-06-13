"""Canonical .aiwf/ path definitions — single source of truth.

Stage 4.7.3: Five-zone workspace layout. Runtime code uses v2 paths only.
Old path mappings are retained for explicit migration/audit commands, not as normal
read/write fallback.
"""

import os
from pathlib import Path
from typing import Optional

# ═══════════════════════════════════════════════════════════════════════════
# Zone roots
# ═══════════════════════════════════════════════════════════════════════════

AIWF_DIR = ".aiwf"

STATE_DIR = ".aiwf/state"
ARTIFACTS_DIR = ".aiwf/artifacts"
RUNTIME_DIR_V2 = ".aiwf/runtime"
ASSETS_DIR = ".aiwf/assets"
ARCHIVE_DIR = ".aiwf/archive"

# ═══════════════════════════════════════════════════════════════════════════
# State machine — unchanged, state/ is stable
# ═══════════════════════════════════════════════════════════════════════════

STATE_JSON = ".aiwf/state/state.json"
GOAL_JSON = ".aiwf/state/goal.json"
CONTEXTS_JSON = ".aiwf/state/contexts.json"
FIX_LOOP_JSON = ".aiwf/state/fix-loop.json"
PLANS_JSON = ".aiwf/state/plans.json"
MILESTONES_JSON = ".aiwf/state/milestones.json"
GOALS_JSON = ".aiwf/state/goals.json"

# ═══════════════════════════════════════════════════════════════════════════
# Artifacts zone
# ═══════════════════════════════════════════════════════════════════════════

EVIDENCE_JSON = ".aiwf/artifacts/evidence/records.json"
TESTING_JSON = ".aiwf/artifacts/quality/testing.json"
REVIEW_JSON = ".aiwf/artifacts/quality/review.json"
QUALITY_DIGEST_MD = ".aiwf/artifacts/reports/质量摘要.md"
PROJECT_MAP_MD = ".aiwf/artifacts/reports/项目地图.md"
IDEAS_MD = ".aiwf/artifacts/reports/ideas.md"
TASK_PLANS_DIR = ".aiwf/artifacts/plans"
EXTERNAL_RESEARCH_JSON = ".aiwf/artifacts/research/external.json"

EVIDENCE_DIR = ".aiwf/artifacts/evidence"
QUALITY_DIR = ".aiwf/artifacts/quality"
REPORTS_DIR = ".aiwf/artifacts/reports"
RESEARCH_DIR = ".aiwf/artifacts/research"
PLAN_ARTIFACTS_DIR = ".aiwf/artifacts/plans"

# ═══════════════════════════════════════════════════════════════════════════
# Runtime zone
# ═══════════════════════════════════════════════════════════════════════════

TASK_HISTORY_JSON = ".aiwf/runtime/history/task-history.json"
TASK_LEDGER_JSON = ".aiwf/runtime/history/task-ledger.json"
WORKSPACE_DRIFT_JSON = ".aiwf/runtime/internal/workspace-drift.json"
BASELINE_JSON = ".aiwf/runtime/internal/baseline.json"

HISTORY_DIR = ".aiwf/runtime/history"
CHECKPOINTS_DIR = ".aiwf/runtime/checkpoints"
INTERNAL_DIR = ".aiwf/runtime/internal"

# ═══════════════════════════════════════════════════════════════════════════
# Assets zone
# ═══════════════════════════════════════════════════════════════════════════

CAPABILITIES_JSON = ".aiwf/assets/capabilities.json"
CAPABILITY_DECISIONS_JSON = ".aiwf/assets/capability-decisions.json"

# ═══════════════════════════════════════════════════════════════════════════
# Old path mapping — old → new (explicit migration/audit only)
# ═══════════════════════════════════════════════════════════════════════════

LEGACY_TO_NEW = {
    ".aiwf/plans": PLAN_ARTIFACTS_DIR,
    ".aiwf/evidence": EVIDENCE_DIR,
    ".aiwf/reports": REPORTS_DIR,
    ".aiwf/research": RESEARCH_DIR,
    ".aiwf/quality": QUALITY_DIR,
    ".aiwf/checkpoints": CHECKPOINTS_DIR,
    ".aiwf/history": HISTORY_DIR,
    ".aiwf/internal": INTERNAL_DIR,
}

LEGACY_FILE_TO_NEW = {
    ".aiwf/evidence/records.json": EVIDENCE_JSON,
    ".aiwf/quality/testing.json": TESTING_JSON,
    ".aiwf/quality/review.json": REVIEW_JSON,
    ".aiwf/history/task-history.json": TASK_HISTORY_JSON,
    ".aiwf/history/task-ledger.json": TASK_LEDGER_JSON,
    ".aiwf/reports/质量摘要.md": QUALITY_DIGEST_MD,
    ".aiwf/reports/项目地图.md": PROJECT_MAP_MD,
    ".aiwf/reports/ideas.md": IDEAS_MD,
    ".aiwf/plans": TASK_PLANS_DIR,
    ".aiwf/research/external.json": EXTERNAL_RESEARCH_JSON,
    ".aiwf/internal/workspace-drift.json": WORKSPACE_DRIFT_JSON,
    ".aiwf/internal/baseline.json": BASELINE_JSON,
}

# ═══════════════════════════════════════════════════════════════════════════
# Directory lists
# ═══════════════════════════════════════════════════════════════════════════

ALL_DIRS_V2 = [
    "state",
    "artifacts",
    "artifacts/plans",
    "artifacts/evidence",
    "artifacts/reports",
    "artifacts/research",
    "artifacts/quality",
    "runtime",
    "runtime/checkpoints",
    "runtime/history",
    "runtime/internal",
    "assets",
    "archive",
]

# Current directory list alias.
ALL_DIRS = [
    "state",
    "artifacts", "artifacts/plans", "artifacts/evidence", "artifacts/reports",
    "artifacts/research", "artifacts/quality",
    "runtime", "runtime/checkpoints", "runtime/history", "runtime/internal",
    "assets", "archive",
]

# ═══════════════════════════════════════════════════════════════════════════
# Short-name path mapping for current v2 paths.
# ═══════════════════════════════════════════════════════════════════════════

LEGACY_MAP = {
    "state.json": STATE_JSON,
    "goal.json": GOAL_JSON,
    "contexts.json": CONTEXTS_JSON,
    "fix-loop.json": FIX_LOOP_JSON,
    "evidence.json": EVIDENCE_JSON,
    "testing.json": TESTING_JSON,
    "review.json": REVIEW_JSON,
    "task-history.json": TASK_HISTORY_JSON,
    "task-ledger.json": TASK_LEDGER_JSON,
    "quality-digest.md": QUALITY_DIGEST_MD,
    "PROJECT-MAP.md": PROJECT_MAP_MD,
    "baseline.json": BASELINE_JSON,
    "ideas.md": IDEAS_MD,
    "external-research.json": EXTERNAL_RESEARCH_JSON,
    "capability-decisions.json": CAPABILITY_DECISIONS_JSON,
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


def artifacts_dir(base_dir: str) -> str:
    return _resolve(base_dir, ARTIFACTS_DIR)


def runtime_dir(base_dir: str) -> str:
    return _resolve(base_dir, RUNTIME_DIR_V2)


def assets_dir(base_dir: str) -> str:
    return _resolve(base_dir, ASSETS_DIR)


def archive_dir(base_dir: str) -> str:
    return _resolve(base_dir, ARCHIVE_DIR)


def plan_artifacts_dir(base_dir: str) -> str:
    return _resolve(base_dir, PLAN_ARTIFACTS_DIR)


def evidence_artifacts_dir(base_dir: str) -> str:
    return _resolve(base_dir, EVIDENCE_DIR)


def reports_dir(base_dir: str) -> str:
    return _resolve(base_dir, REPORTS_DIR)


def quality_artifacts_dir(base_dir: str) -> str:
    return _resolve(base_dir, QUALITY_DIR)


def checkpoints_dir(base_dir: str) -> str:
    return _resolve(base_dir, CHECKPOINTS_DIR)


def history_dir(base_dir: str) -> str:
    return _resolve(base_dir, HISTORY_DIR)


def internal_runtime_dir(base_dir: str) -> str:
    return _resolve(base_dir, INTERNAL_DIR)


def research_artifacts_dir(base_dir: str) -> str:
    return _resolve(base_dir, RESEARCH_DIR)


# ═══════════════════════════════════════════════════════════════════════════
# Read/write helpers
# ═══════════════════════════════════════════════════════════════════════════

def read_file_with_fallback(base_dir: str, new_rel_path: str,
                             old_rel_path: Optional[str] = None) -> Optional[str]:
    """Read the current path only.

    ``old_rel_path`` is accepted for old callers but intentionally ignored. Normal
    runtime must not silently treat retired paths as machine truth.
    """
    new_full = _resolve(base_dir, new_rel_path)
    if os.path.isfile(new_full):
        return Path(new_full).read_text(encoding="utf-8")
    return None


def write_file_new_path(base_dir: str, new_rel_path: str, content: str) -> str:
    new_full = _resolve(base_dir, new_rel_path)
    Path(new_full).parent.mkdir(parents=True, exist_ok=True)
    Path(new_full).write_text(content, encoding="utf-8")
    return new_full


def resolve_existing_path(base_dir: str, new_rel_path: str,
                           old_rel_path: Optional[str] = None) -> str:
    """Return the current v2 path.

    ``old_rel_path`` is accepted for old callers but intentionally ignored. Use the
    migration/audit APIs to inspect retired paths.
    """
    new_full = _resolve(base_dir, new_rel_path)
    return new_full


def is_layout_v2(base_dir: str) -> bool:
    artifacts_full = _resolve(base_dir, ARTIFACTS_DIR)
    runtime_full = _resolve(base_dir, RUNTIME_DIR_V2)
    return os.path.isdir(artifacts_full) and os.path.isdir(runtime_full)


def needs_migration(base_dir: str) -> bool:
    if is_layout_v2(base_dir):
        return False
    for old_dir in ["plans", "evidence", "reports", "checkpoints", "history", "internal"]:
        if os.path.isdir(_resolve(base_dir, f".aiwf/{old_dir}")):
            return True
    return False


def list_old_dirs_present(base_dir: str) -> list:
    found = []
    for old_dir, new_dir in LEGACY_TO_NEW.items():
        full_old = _resolve(base_dir, old_dir)
        if os.path.isdir(full_old):
            found.append((old_dir, new_dir))
    return found
