"""Gate checker using backend-neutral core.

Evaluates closure gates from .aiwf state files.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from ...core.closure_contract import closure_conditions_met
from ...core.state_schema import (
    default_state, default_implementation,
    default_testing, default_review, default_fix_loop,
)


def _read_json(path: Path, default: Dict) -> Dict:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def load_all_state(cwd: Path) -> Dict[str, Any]:
    """Load all .aiwf state files from a project root."""
    return {
        "state": _read_json(cwd / ".aiwf" / "state" / "state.json", default_state()),
        "implementation": _read_json(cwd / ".aiwf" / "records" / "implementation.json", default_implementation()),
        "testing": _read_json(cwd / ".aiwf" / "records" / "testing.json", default_testing()),
        "review": _read_json(cwd / ".aiwf" / "records" / "review.json", default_review()),
        "fix_loop": _read_json(cwd / ".aiwf" / "state" / "fix-loop.json", default_fix_loop()),
    }


def eval_closure_gates(cwd: Path) -> Dict[str, Any]:
    """Load current records and evaluate closure gates."""
    s = load_all_state(cwd)

    result = closure_conditions_met(
        s["state"], s["implementation"], s["testing"],
        s["review"], s["fix_loop"],
    )

    return result
