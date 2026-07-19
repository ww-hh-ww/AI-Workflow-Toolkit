"""Small runtime helpers for task-role Agent dispatch lifecycle."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from .state._common import _exclusive_operation_lock
from .worktree_context import resolve_control_root


WORKFLOW_ROLES = frozenset({"aiwf-executor", "aiwf-tester", "aiwf-reviewer"})
TRACKED_ROLES = WORKFLOW_ROLES | {"aiwf-architect"}
TERMINAL = frozenset({"completed", "cancelled"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def dispatch_path(base_dir: str | Path) -> Path:
    return resolve_control_root(base_dir) / ".aiwf/runtime/internal/agent-dispatch.jsonl"


def _entries(base_dir: str | Path) -> List[Dict[str, Any]]:
    path = dispatch_path(base_dir)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    entries = []
    for line in lines:
        try:
            value = json.loads(line)
        except Exception:
            continue
        if isinstance(value, dict):
            entries.append(value)
    return entries


def running_dispatches(
    base_dir: str | Path,
    task_id: str = "",
    session_id: str = "",
) -> List[Dict[str, str]]:
    """Return open tracked dispatches while accepting historical log entries."""
    counts: Dict[tuple[str, str, str], int] = {}
    latest: Dict[tuple[str, str, str], Dict[str, str]] = {}
    for entry in _entries(base_dir):
        role = str(entry.get("subagent_type") or "")
        current_task = str(entry.get("task_id") or "")
        current_session = str(entry.get("session_id") or "")
        if role not in TRACKED_ROLES or not current_task:
            continue
        key = (current_task, role, current_session)
        status = str(entry.get("status") or "")
        if status in ("started", "running"):
            counts[key] = counts.get(key, 0) + 1
            latest[key] = {
                "task_id": current_task,
                "subagent_type": role,
                "session_id": current_session,
                "started_at": str(entry.get("timestamp") or ""),
            }
        elif status in TERMINAL:
            if current_session:
                counts[key] = max(0, counts.get(key, 0) - 1)
            else:
                candidates = [
                    candidate for candidate, count in counts.items()
                    if count > 0 and candidate[:2] == (current_task, role)
                ]
                if candidates:
                    candidate = candidates[-1]
                    counts[candidate] = max(0, counts[candidate] - 1)
    result = []
    for key, count in counts.items():
        if count <= 0:
            continue
        item = latest[key]
        if task_id and item["task_id"] != task_id:
            continue
        if session_id and item["session_id"] != session_id:
            continue
        result.append(item)
    return result


def start_dispatch(
    base_dir: str | Path,
    task_id: str,
    subagent_type: str,
    session_id: str,
    plan_id: str,
    worktree_path: str,
) -> str:
    path = dispatch_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": _now(),
        "subagent_type": subagent_type,
        "task_id": task_id,
        "plan_id": plan_id,
        "worktree_path": worktree_path,
        "session_id": session_id,
        "status": "started",
    }
    with _exclusive_operation_lock(str(resolve_control_root(base_dir)), "agent-dispatch", timeout=2):
        running = [
            item for item in running_dispatches(
                base_dir, task_id=task_id, session_id=session_id,
            )
            if item["subagent_type"] in WORKFLOW_ROLES
        ]
        if subagent_type in WORKFLOW_ROLES and running:
            return running[0]["subagent_type"]
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
    return ""


def finish_dispatch(
    base_dir: str | Path,
    subagent_type: str,
    task_id: str = "",
    session_id: str = "",
    status: str = "completed",
    source: str = "agent",
) -> bool:
    if status not in TERMINAL:
        raise ValueError(f"invalid Agent terminal status: {status}")
    control = resolve_control_root(base_dir)
    path = dispatch_path(control)
    with _exclusive_operation_lock(str(control), "agent-dispatch", timeout=2):
        candidates = [
            item for item in running_dispatches(
                control, task_id=task_id, session_id=session_id,
            )
            if item["subagent_type"] == subagent_type
        ]
        if not candidates and session_id:
            candidates = [
                item for item in running_dispatches(control, task_id=task_id)
                if item["subagent_type"] == subagent_type
            ]
        if len(candidates) != 1:
            return False
        target = candidates[0]
        entry = {
            "timestamp": _now(),
            "subagent_type": subagent_type,
            "task_id": target["task_id"],
            "session_id": target["session_id"],
            "status": status,
            "completion_source": source,
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
    return True


def cancel_task_dispatches(base_dir: str | Path, task_id: str, source: str) -> None:
    for item in running_dispatches(base_dir, task_id=task_id):
        finish_dispatch(
            base_dir,
            item["subagent_type"],
            task_id=task_id,
            session_id=item["session_id"],
            status="cancelled",
            source=source,
        )
