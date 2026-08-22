"""Eligibility checks for reopening a closed Task."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from .git_workflow import changed_project_files, repository_info
from .plan_integration_git import git_operation, is_ancestor, resolve_ref
from .state.plan_ops import load_plans
from .task_records import load_task_record
from .worktree_context import resolve_control_root, resolve_worktree_root, same_path


def _find_plan(base_dir: str, plan_id: str) -> Optional[Dict[str, Any]]:
    return next(
        (
            item for item in load_plans(base_dir).get("plans", []) or []
            if isinstance(item, dict)
            and str(item.get("plan_id") or item.get("id") or "") == plan_id
        ),
        None,
    )


def _plan_blockers(plan: Optional[Dict[str, Any]], plan_id: str) -> List[str]:
    if plan_id and not plan:
        return [f"parent Plan not found: {plan_id}"]
    if not plan:
        return []
    blockers = []
    if str(plan.get("status") or "open") == "closed":
        blockers.append(f"parent Plan is closed: {plan_id}; create a corrective Task in a new Plan")
    integration = plan.get("integration", {}) or {}
    if str(integration.get("status") or "") == "merged" or plan.get("closure"):
        blockers.append(f"parent Plan result is already merged: {plan_id}")
    return blockers


def _worktree_blockers(
    base_dir: str,
    task: Dict[str, Any],
    plan: Optional[Dict[str, Any]],
) -> tuple[Path, List[str]]:
    blockers = []
    task_commit = str(((task.get("closure") or {}).get("git_commit")) or "")
    worktree = Path(str(
        task.get("worktree_path")
        or ((plan or {}).get("git_worktree_path") if plan else "")
        or resolve_worktree_root(base_dir)
    )).expanduser().resolve()
    if not worktree.exists():
        return worktree, [f"Task worktree no longer exists: {worktree}"]
    info = repository_info(str(worktree))
    if not info.get("root"):
        return worktree, [f"Task worktree is not a Git repository: {worktree}"]

    expected_head = str((plan or {}).get("git_head_ref") or task_commit)
    if expected_head and info.get("head") != expected_head:
        blockers.append("Plan worktree HEAD changed after this Task closed; use a corrective Task")
    integration = (plan or {}).get("integration", {}) or {}
    integration_from_task = (
        str(integration.get("status") or "") in {"auditing", "conflict", "prepared", "failed"}
        and str(integration.get("plan_ref") or "") == task_commit
    )
    if task_commit and expected_head and task_commit != expected_head and not integration_from_task:
        blockers.append("this is not the Plan's latest closed Task result; use a corrective Task")
    operation = git_operation(worktree)
    if operation:
        blockers.append(f"Task worktree has an unfinished Git {operation} operation")
    dirty = changed_project_files(str(worktree))
    if dirty:
        blockers.append("Task worktree has project changes: " + ", ".join(dirty[:8]))
    base_branch = str((plan or {}).get("git_base_branch") or "")
    if task_commit and base_branch:
        control = resolve_control_root(base_dir)
        base_head = resolve_ref(control, base_branch)
        if base_head and is_ancestor(control, task_commit, base_head):
            blockers.append(f"Task commit is already present on base branch '{base_branch}'")
    return worktree, blockers


def _consumer_blockers(
    base_dir: str,
    task_id: str,
    plan_id: str,
    ledger: Dict[str, Any],
    worktree: Path,
) -> List[str]:
    blockers = []
    for other in ledger.get("tasks", []) or []:
        if not isinstance(other, dict) or other.get("id") == task_id:
            continue
        if other.get("status") == "active" and same_path(
            str(other.get("worktree_path") or ""), worktree
        ):
            blockers.append(f"worktree already has active Task: {other.get('id')}")
        if task_id not in (other.get("dependencies", []) or []):
            continue
        record = load_task_record(base_dir, str(other.get("id") or ""))
        implementation_ref = str(((record.get("implementation") or {}).get("implementation_ref")) or "")
        if other.get("status") in ("active", "closed") or implementation_ref:
            blockers.append(f"dependent Task {other.get('id')} has already started or closed")

    try:
        from .state.milestone_ops import load_milestones

        for milestone in load_milestones(base_dir).get("milestones", []) or []:
            if not isinstance(milestone, dict):
                continue
            linked = task_id in (milestone.get("task_ids", []) or []) or (
                plan_id and plan_id in (milestone.get("plan_ids", []) or [])
            )
            accepted = str(((milestone.get("user_acceptance") or {}).get("status")) or "") == "confirmed"
            if linked and (milestone.get("status") == "closed" or accepted):
                milestone_id = milestone.get("id") or milestone.get("milestone_id")
                blockers.append(f"Milestone {milestone_id} already consumed this result")
    except Exception as exc:
        blockers.append(f"could not inspect Milestone consumption: {exc}")
    return blockers


def reopen_blockers(
    base_dir: str,
    task: Dict[str, Any],
    ledger: Dict[str, Any],
) -> List[str]:
    task_id = str(task.get("id") or "")
    plan_id = str(task.get("plan_id") or task.get("parent_plan") or "")
    plan = _find_plan(base_dir, plan_id) if plan_id else None
    blockers = _plan_blockers(plan, plan_id)
    worktree, worktree_gaps = _worktree_blockers(base_dir, task, plan)
    blockers.extend(worktree_gaps)
    blockers.extend(_consumer_blockers(base_dir, task_id, plan_id, ledger, worktree))
    return list(dict.fromkeys(blockers))
