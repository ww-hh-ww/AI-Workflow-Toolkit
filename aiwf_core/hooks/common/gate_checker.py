"""Gate checker using backend-neutral core.

Evaluates closure gates from .aiwf state files.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from ...core.closure_contract import closure_conditions_met
from ...core.state_schema import default_state
from ...core.task_ledger import load_ledger, resolve_active_task_id
from ...core.task_records import load_task_record
from ...core.worktree_context import resolve_control_root


def _read_json(path: Path, default: Dict) -> Dict:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def load_all_state(cwd: Path) -> Dict[str, Any]:
    """Load all .aiwf state files from a project root."""
    control = resolve_control_root(cwd)
    task_id = resolve_active_task_id(str(cwd))
    task = next(
        (item for item in load_ledger(str(control)).get("tasks", []) if item.get("id") == task_id),
        {},
    )
    record = load_task_record(control, task_id) if task_id else {}
    state = _read_json(control / ".aiwf" / "state" / "state.json", default_state())
    state["active_task_id"] = task_id
    state["phase"] = task.get("phase", "")
    return {
        "state": state,
        "implementation": record.get("implementation", {}),
        "testing": record.get("testing", {}),
        "review": record.get("review", {}),
        "fix_loop": record.get("fix_loop", {}),
    }


def eval_closure_gates(cwd: Path) -> Dict[str, Any]:
    """Load current records and evaluate closure gates."""
    s = load_all_state(cwd)

    result = closure_conditions_met(
        s["state"], s["implementation"], s["testing"],
        s["review"], s["fix_loop"],
    )

    return result
