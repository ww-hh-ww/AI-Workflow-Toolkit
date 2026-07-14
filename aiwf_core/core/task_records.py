"""Per-Task implementation, testing, review, and fix-loop records."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict

from .state._common import _exclusive_operation_lock, _read_json, _atomic_write
from .state_schema import (
    default_fix_loop,
    default_implementation,
    default_review,
    default_testing,
)
from .worktree_context import resolve_control_root


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_task_id(task_id: str) -> str:
    value = str(task_id or "").strip()
    if not value or not re.fullmatch(r"[A-Za-z0-9._-]+", value):
        raise ValueError(f"invalid Task ID for record path: {task_id!r}")
    return value


def default_task_record(task_id: str) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "task_id": task_id,
        "implementation": default_implementation(task_id),
        "testing": default_testing(task_id),
        "review": default_review(task_id),
        "fix_loop": default_fix_loop(),
        "updated_at": "",
    }


def task_record_path(base_dir: str | Path, task_id: str) -> Path:
    control = resolve_control_root(base_dir)
    return control / ".aiwf" / "records" / "tasks" / f"{_safe_task_id(task_id)}.json"


def _legacy_record(control: Path, task_id: str) -> Dict[str, Any]:
    record = default_task_record(task_id)
    matched = False
    for section, relative in (
        ("implementation", "records/implementation.json"),
        ("testing", "records/testing.json"),
        ("review", "records/review.json"),
    ):
        value = _read_json(control / ".aiwf" / relative, {})
        if value.get("task_id") == task_id:
            record[section] = value
            matched = True
    fix_loop = _read_json(control / ".aiwf" / "state" / "fix-loop.json", {})
    state = _read_json(control / ".aiwf" / "state" / "state.json", {})
    if fix_loop.get("status") == "open" and state.get("active_task_id") == task_id:
        record["fix_loop"] = fix_loop
        matched = True
    if matched:
        record["updated_at"] = _now()
    return record


def load_task_record(base_dir: str | Path, task_id: str) -> Dict[str, Any]:
    path = task_record_path(base_dir, task_id)
    record = _read_json(path, {})
    if not record:
        control = resolve_control_root(base_dir)
        record = _legacy_record(control, task_id)
    defaults = default_task_record(task_id)
    for key in ("implementation", "testing", "review", "fix_loop"):
        if not isinstance(record.get(key), dict):
            record[key] = defaults[key]
    record["schema_version"] = 1
    record["task_id"] = task_id
    record.setdefault("updated_at", "")
    return record


def save_task_record(base_dir: str | Path, record: Dict[str, Any]) -> None:
    task_id = _safe_task_id(str(record.get("task_id") or ""))
    record["updated_at"] = _now()
    _atomic_write(task_record_path(base_dir, task_id), record)


def update_task_record(
    base_dir: str | Path,
    task_id: str,
    mutator: Callable[[Dict[str, Any]], Any],
) -> Any:
    control = resolve_control_root(base_dir)
    safe_id = _safe_task_id(task_id)
    with _exclusive_operation_lock(str(control), f"task-record-{safe_id}"):
        record = load_task_record(base_dir, safe_id)
        result = mutator(record)
        save_task_record(base_dir, record)
        return result


def task_record_section(base_dir: str | Path, task_id: str, section: str) -> Dict[str, Any]:
    value = load_task_record(base_dir, task_id).get(section, {})
    return value if isinstance(value, dict) else {}
