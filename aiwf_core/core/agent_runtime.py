"""Small runtime helpers for task-role Agent dispatch lifecycle."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

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
                "plan_id": str(entry.get("plan_id") or ""),
                "worktree_path": str(entry.get("worktree_path") or ""),
                "agent_id": str(entry.get("agent_id") or ""),
            }
        elif status == "bound" and counts.get(key, 0) > 0:
            latest[key]["agent_id"] = str(entry.get("agent_id") or "")
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
    agent_id: str = "",
    resumed: bool = False,
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
    if agent_id:
        entry["agent_id"] = agent_id
    if resumed:
        entry["resumed"] = True
    with _exclusive_operation_lock(str(resolve_control_root(base_dir)), "agent-dispatch", timeout=2):
        running = [
            item for item in running_dispatches(base_dir, task_id=task_id)
            if item["subagent_type"] in WORKFLOW_ROLES
        ]
        if subagent_type in WORKFLOW_ROLES and running:
            return running[0]["subagent_type"]
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
    return ""


def bind_dispatch_agent(
    base_dir: str | Path,
    subagent_type: str,
    agent_id: str,
    task_id: str = "",
    session_id: str = "",
) -> bool:
    """Attach Claude's concrete Agent ID to one open dispatch."""
    if not agent_id:
        return False
    control = resolve_control_root(base_dir)
    path = dispatch_path(control)
    with _exclusive_operation_lock(str(control), "agent-dispatch", timeout=2):
        candidates = [
            item for item in running_dispatches(
                control, task_id=task_id, session_id=session_id,
            )
            if item["subagent_type"] == subagent_type
            and not item.get("agent_id")
        ]
        if len(candidates) != 1:
            return False
        target = candidates[0]
        entry = {
            "timestamp": _now(),
            "subagent_type": subagent_type,
            "task_id": target["task_id"],
            "plan_id": target.get("plan_id", ""),
            "worktree_path": target.get("worktree_path", ""),
            "session_id": target["session_id"],
            "agent_id": agent_id,
            "status": "bound",
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
    return True


def resumable_agent(
    base_dir: str | Path,
    task_id: str = "",
    subagent_type: str = "aiwf-executor",
    agent_id: str = "",
) -> Optional[Dict[str, str]]:
    """Return the latest successfully completed Agent that Claude may resume."""
    running_agent_ids = {
        str(item.get("agent_id") or "")
        for item in running_dispatches(base_dir)
        if item.get("agent_id")
    }
    latest_by_agent: Dict[str, Optional[Dict[str, str]]] = {}
    order: Dict[str, int] = {}
    for index, entry in enumerate(_entries(base_dir)):
        current_agent = str(entry.get("agent_id") or "")
        current_task = str(entry.get("task_id") or "")
        current_role = str(entry.get("subagent_type") or "")
        if not current_agent or current_role != subagent_type:
            continue
        if task_id and current_task != task_id:
            continue
        if agent_id and current_agent != agent_id:
            continue
        status = str(entry.get("status") or "")
        if status not in TERMINAL:
            continue
        order[current_agent] = index
        if status == "cancelled":
            latest_by_agent[current_agent] = None
            continue
        latest_by_agent[current_agent] = {
            "task_id": current_task,
            "subagent_type": current_role,
            "session_id": str(entry.get("session_id") or ""),
            "agent_id": current_agent,
            "plan_id": str(entry.get("plan_id") or ""),
            "worktree_path": str(entry.get("worktree_path") or ""),
            "completed_at": str(entry.get("timestamp") or ""),
        }
    candidates = [
        (order[current_agent], value)
        for current_agent, value in latest_by_agent.items()
        if value is not None and current_agent not in running_agent_ids
    ]
    return max(candidates, default=(-1, None), key=lambda item: item[0])[1]


def start_resumed_dispatch(
    base_dir: str | Path,
    subagent_type: str,
    agent_id: str,
    session_id: str,
) -> Optional[str]:
    """Reopen the recorded task-role window when Claude resumes an Agent."""
    prior = resumable_agent(
        base_dir, subagent_type=subagent_type, agent_id=agent_id,
    )
    if not prior:
        return None
    running = start_dispatch(
        base_dir,
        prior["task_id"],
        subagent_type,
        session_id or prior["session_id"],
        prior["plan_id"],
        prior["worktree_path"],
        agent_id=agent_id,
        resumed=True,
    )
    return "" if running else prior["task_id"]


def latest_agent_dispatch(
    base_dir: str | Path,
    subagent_type: str,
    agent_id: str,
    task_id: str = "",
) -> Optional[Dict[str, str]]:
    """Return the latest dispatch cycle associated with one concrete Agent."""
    entries = _entries(base_dir)
    anchor = -1
    target_task = task_id
    target_session = ""
    for index, entry in enumerate(entries):
        if str(entry.get("agent_id") or "") != agent_id:
            continue
        if str(entry.get("subagent_type") or "") != subagent_type:
            continue
        current_task = str(entry.get("task_id") or "")
        if task_id and current_task != task_id:
            continue
        anchor = index
        target_task = current_task
        target_session = str(entry.get("session_id") or "")
    if anchor < 0 or not target_task:
        return None

    for entry in reversed(entries[:anchor + 1]):
        if str(entry.get("status") or "") != "started":
            continue
        if str(entry.get("subagent_type") or "") != subagent_type:
            continue
        if str(entry.get("task_id") or "") != target_task:
            continue
        if target_session and str(entry.get("session_id") or "") != target_session:
            continue
        started_agent = str(entry.get("agent_id") or "")
        if started_agent and started_agent != agent_id:
            continue
        return {
            "task_id": target_task,
            "subagent_type": subagent_type,
            "session_id": target_session,
            "agent_id": agent_id,
            "started_at": str(entry.get("timestamp") or ""),
            "plan_id": str(entry.get("plan_id") or ""),
            "worktree_path": str(entry.get("worktree_path") or ""),
        }
    return None


def request_return_check(
    base_dir: str | Path,
    subagent_type: str,
    agent_id: str,
    task_id: str,
) -> bool:
    """Record one final contract-check request for this Agent dispatch."""
    if not agent_id:
        return False
    dispatch = latest_agent_dispatch(
        base_dir, subagent_type, agent_id, task_id=task_id,
    )
    if not dispatch:
        return False
    started_at = str(dispatch.get("started_at") or "")
    for entry in _entries(base_dir):
        if (
            entry.get("status") == "return_check"
            and str(entry.get("subagent_type") or "") == subagent_type
            and str(entry.get("agent_id") or "") == agent_id
            and str(entry.get("task_id") or "") == task_id
            and str(entry.get("dispatch_started_at") or "") == started_at
        ):
            return False

    control = resolve_control_root(base_dir)
    path = dispatch_path(control)
    entry = {
        "timestamp": _now(),
        "subagent_type": subagent_type,
        "task_id": task_id,
        "session_id": dispatch.get("session_id", ""),
        "agent_id": agent_id,
        "status": "return_check",
        "dispatch_started_at": started_at,
    }
    with _exclusive_operation_lock(str(control), "agent-dispatch", timeout=2):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
    return True


def finish_dispatch(
    base_dir: str | Path,
    subagent_type: str,
    task_id: str = "",
    session_id: str = "",
    status: str = "completed",
    source: str = "agent",
    agent_id: str = "",
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
        if len(candidates) == 1:
            target = candidates[0]
        elif agent_id:
            history = [
                entry for entry in _entries(control)
                if str(entry.get("agent_id") or "") == agent_id
                and str(entry.get("subagent_type") or "") == subagent_type
                and (not task_id or str(entry.get("task_id") or "") == task_id)
            ]
            if not history:
                return False
            previous = history[-1]
            target = {
                "task_id": str(previous.get("task_id") or ""),
                "session_id": str(previous.get("session_id") or session_id),
                "plan_id": str(previous.get("plan_id") or ""),
                "worktree_path": str(previous.get("worktree_path") or ""),
                "agent_id": agent_id,
            }
        else:
            return False
        effective_agent_id = agent_id or str(target.get("agent_id") or "")
        entry = {
            "timestamp": _now(),
            "subagent_type": subagent_type,
            "task_id": target["task_id"],
            "session_id": target["session_id"],
            "status": status,
            "completion_source": source,
            "plan_id": target.get("plan_id", ""),
            "worktree_path": target.get("worktree_path", ""),
        }
        if effective_agent_id:
            entry["agent_id"] = effective_agent_id
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
    return True


def cancel_agent_dispatch(
    base_dir: str | Path,
    agent_id: str,
    source: str = "task_stop",
) -> Optional[Dict[str, str]]:
    """Cancel the one running dispatch bound to a stopped Claude Agent."""
    if not agent_id:
        return None
    candidates = [
        item for item in running_dispatches(base_dir)
        if str(item.get("agent_id") or "") == agent_id
    ]
    if len(candidates) != 1:
        return None
    target = candidates[0]
    if not finish_dispatch(
        base_dir,
        target["subagent_type"],
        task_id=target["task_id"],
        session_id=target["session_id"],
        status="cancelled",
        source=source,
        agent_id=agent_id,
    ):
        return None
    return target


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
