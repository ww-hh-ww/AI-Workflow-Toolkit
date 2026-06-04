"""Canonical .aiwf/ path definitions — single source of truth."""

# State machine (JSON)
STATE_JSON = ".aiwf/state/state.json"
GOAL_JSON = ".aiwf/state/goal.json"
CONTEXTS_JSON = ".aiwf/state/contexts.json"
FIX_LOOP_JSON = ".aiwf/state/fix-loop.json"

# Evidence (JSON)
EVIDENCE_JSON = ".aiwf/evidence/records.json"

# Quality gates (JSON)
TESTING_JSON = ".aiwf/quality/testing.json"
REVIEW_JSON = ".aiwf/quality/review.json"

# History (JSON)
TASK_HISTORY_JSON = ".aiwf/history/task-history.json"
TASK_LEDGER_JSON = ".aiwf/history/task-ledger.json"

# Human-readable reports (Chinese MD)
CURRENT_STATE_MD = ".aiwf/reports/当前状态.md"
REPORT_MD = ".aiwf/reports/闭合报告.md"
QUALITY_DIGEST_MD = ".aiwf/reports/质量摘要.md"
PROJECT_MAP_MD = ".aiwf/reports/项目地图.md"
IDEAS_MD = ".aiwf/reports/ideas.md"

# Root-level (flat)
CAPABILITIES_JSON = ".aiwf/assets/capabilities.json"
WORKSPACE_DRIFT_JSON = ".aiwf/internal/workspace-drift.json"
BASELINE_JSON = ".aiwf/internal/baseline.json"

# Directories
STATE_DIR = ".aiwf/state"
EVIDENCE_DIR = ".aiwf/evidence"
QUALITY_DIR = ".aiwf/quality"
HISTORY_DIR = ".aiwf/history"
REPORTS_DIR = ".aiwf/reports"
ASSETS_DIR = ".aiwf/assets"
CHECKPOINTS_DIR = ".aiwf/checkpoints"
INTERNAL_DIR = ".aiwf/internal"

# All directories that must exist
ALL_DIRS = ["state", "evidence", "quality", "history", "reports", "assets", "checkpoints", "internal"]

# Legacy path mapping for migration
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
    "current-state.md": CURRENT_STATE_MD,
    "report.md": REPORT_MD,
    "quality-digest.md": QUALITY_DIGEST_MD,
    "PROJECT-MAP.md": PROJECT_MAP_MD,
    "baseline.json": BASELINE_JSON,
    "ideas.md": IDEAS_MD,
}
