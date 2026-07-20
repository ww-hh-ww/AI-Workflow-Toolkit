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
    BLOCKING_REVIEW_RESULTS,
)

# ── Context ──
from .state.context_ops import (
    record_implementation,
)

# ── Testing ──
from .state.testing_ops import (
    record_testing,
)

# ── Review ──
from .state.review_ops import (
    record_review,
)
# ── Adversarial ──
from .state.adversarial_ops import (
    disposition_adversarial_observation,
)

# ── Fix-loop ──
from .state.fixloop_ops import (
    continue_fix_loop,
    open_fix_loop,
    resolve_fix_loop,
)
