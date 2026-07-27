"""Refresh rules for stale Plan integration inputs."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .plan_integration_git import is_ancestor, is_governance_path, run_git


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def refreshable_integration_task(
    control: Path,
    plan: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    statuses = plan.get("task_status", {}) or {}
    unfinished = {
        str(task_id)
        for task_id, status in statuses.items()
        if status not in ("closed", "cancelled")
    }
    if len(unfinished) != 1:
        return None
    from .task_ledger import load_ledger

    plan_id = str(plan.get("plan_id") or plan.get("id") or "")
    task = next(
        (
            item for item in load_ledger(str(control)).get("tasks", []) or []
            if isinstance(item, dict)
            and str(item.get("id") or "") in unfinished
            and str(item.get("plan_id") or item.get("parent_plan") or "") == plan_id
        ),
        None,
    )
    if (
        not task
        or task.get("kind") != "integration"
        or task.get("status") not in ("candidate", "ready", "blocked", "suspended")
    ):
        return None
    return task


def changed_paths(base: Path, old_ref: str, new_ref: str) -> List[str]:
    if not old_ref or not new_ref or old_ref == new_ref:
        return []
    result = run_git(base, "diff", "--name-only", "-z", old_ref, new_ref)
    if result.returncode != 0:
        return ["<unresolved Git change>"]
    return [item for item in result.stdout.split("\0") if item]


def governance_only_head_change(
    worktree: Path,
    old_ref: str,
    new_ref: str,
) -> bool:
    if not old_ref or not new_ref or old_ref == new_ref:
        return False
    if not is_ancestor(worktree, old_ref, new_ref):
        return False
    return all(
        is_governance_path(path)
        for path in changed_paths(worktree, old_ref, new_ref)
    )


def reset_integration_task_critiques(
    control: Path,
    plan_id: str,
    old_integration: Dict[str, Any],
    base_ref: str,
    plan_ref: str,
) -> List[str]:
    if (
        str(old_integration.get("base_ref") or "") == base_ref
        and str(old_integration.get("plan_ref") or "") == plan_ref
    ):
        return []
    from .task_ledger import load_ledger, save_ledger

    ledger = load_ledger(str(control))
    reset: List[str] = []
    for task in ledger.get("tasks", []) or []:
        if (
            not isinstance(task, dict)
            or str(task.get("plan_id") or task.get("parent_plan") or "") != plan_id
            or task.get("kind") != "integration"
            or task.get("status") not in ("candidate", "ready", "blocked", "suspended")
        ):
            continue
        task["activation_critique_count"] = 0
        task.pop("activation_critique_updated_at", None)
        task["updated_at"] = _now()
        reset.append(str(task.get("id") or ""))
    if reset:
        save_ledger(str(control), ledger)
    return reset
