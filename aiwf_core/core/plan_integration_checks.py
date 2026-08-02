"""Structural checks shared by Plan integration prepare and finish."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from .git_workflow import repository_info
from .plan_integration_git import git_operation, is_ancestor, resolve_ref
from .state.plan_ops import load_plans


def basic_blockers(
    control: Path,
    plan: Dict[str, Any],
    *,
    refresh_task: Optional[Dict[str, Any]] = None,
) -> List[str]:
    blockers: List[str] = []
    statuses = plan.get("task_status", {}) or {}
    unfinished = [
        task_id for task_id, status in statuses.items()
        if status not in ("closed", "cancelled")
    ]
    refresh_task_id = str((refresh_task or {}).get("id") or "")
    if unfinished and set(map(str, unfinished)) != {refresh_task_id}:
        blockers.append("Plan still has unfinished Tasks: " + ", ".join(unfinished[:8]))
    if not any(status == "closed" for status in statuses.values()):
        blockers.append("Plan has no completed Task result to integrate")

    worktree_raw = str(plan.get("git_worktree_path") or "")
    branch = str(plan.get("git_branch") or "")
    base_branch = str(plan.get("git_base_branch") or "")
    if not worktree_raw or not Path(worktree_raw).exists():
        blockers.append("Plan worktree is missing")
        return blockers
    worktree = Path(worktree_raw)
    plan_info = repository_info(str(worktree))
    control_info = repository_info(str(control))
    if plan_info.get("branch") != branch and not git_operation(worktree):
        blockers.append(
            f"Plan worktree is on '{plan_info.get('branch') or '(detached)'}', expected '{branch}'"
        )
    if not base_branch:
        blockers.append("Plan base branch is unknown")
    elif control_info.get("branch") != base_branch and not git_operation(control):
        blockers.append(
            f"run Plan integration from the control root on base branch '{base_branch}'"
        )

    data = load_plans(str(control))
    by_id = {
        str(item.get("plan_id") or item.get("id") or ""): item
        for item in data.get("plans", []) or [] if isinstance(item, dict)
    }
    for dependency_id in plan.get("dependencies", []) or []:
        dependency = by_id.get(str(dependency_id))
        if not dependency or dependency.get("status") != "closed":
            blockers.append(f"Plan dependency is not closed: {dependency_id}")
            continue
        dependency_ref = str(
            ((dependency.get("integration") or {}).get("merge_commit"))
            or ((dependency.get("closure") or {}).get("merged_commit"))
            or ""
        )
        base_ref = resolve_ref(control, base_branch)
        if dependency_ref and not is_ancestor(control, dependency_ref, base_ref):
            blockers.append(f"Plan dependency is not present on {base_branch}: {dependency_id}")
    return blockers
