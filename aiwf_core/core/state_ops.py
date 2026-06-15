"""Deterministic state operation helpers — facade module.

Skills call these instead of hand-editing .aiwf/*.json.
All functions are backend-neutral — no Claude-specific logic.

Implementation is split across state/ sub-modules; this module
re-exports the public API for backwards compatibility.
"""
from __future__ import annotations

# ── Common utilities ──
from .state._common import (
    _read, _write,
    _execution_contract_frozen, _freeze_explanation,
    _require_additive_list, _require_stable_scalar,
    execution_contract_freeze_reasons,
    WORKFLOW_LEVELS, BLOCKING_REVIEW_RESULTS,
)

# ── Context ──
from .state.context_ops import (
    record_role_evidence,
    start_context,
)

# ── Testing ──
from .state.testing_ops import (
    record_testing,
)

# ── Cleanup & Closure ──
from .state.closure_ops import (
    cancel_close,
    mark_cleanup_fresh,
    mark_cleanup_stale,
    prepare_close,
    build_close_summary,
)

# ── Review ──
from .state.review_ops import (
    record_review,
)
from .state.architecture_review_ops import (
    record_architecture_review,
)

# ── Adversarial ──
from .state.adversarial_ops import (
    disposition_adversarial_observation,
)

# ── Fix-loop ──
from .state.fixloop_ops import (
    open_fix_loop,
    resolve_fix_loop,
)

# ── Architecture change ──
from .state.fixloop_ops import (
    request_architecture_change,
    decide_architecture_change,
    list_architecture_changes,
)

# ── Goal ──
from .state.goal_ops import (
    record_quality_brief,
    revise_goal,
    record_goal_decision,
    record_meta_critique,
)

# ── Workflow mode ──
from .state.workflow_mode_ops import (
    record_quality_policy,
)

# ── Project ──
from .state.project_ops import (
    bootstrap_project,
    get_state_summary,
)
