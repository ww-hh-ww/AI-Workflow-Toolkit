"""Derive the current Plan integration stage without adding a workflow."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from .plan_integration_git import run_git
from .worktree_context import resolve_control_root, same_path


def _canonical_control(base_dir: str | Path) -> Path:
    """Prefer the primary worktree's governance state over tracked copies."""
    worktree = Path(base_dir).expanduser().resolve()
    control = resolve_control_root(worktree)
    common = run_git(worktree, "rev-parse", "--git-common-dir")
    if common.returncode == 0 and common.stdout.strip():
        common_dir = Path(common.stdout.strip())
        if not common_dir.is_absolute():
            common_dir = (worktree / common_dir).resolve()
        primary = common_dir.parent.resolve()
        if (primary / ".aiwf/state/plans.json").exists():
            return primary
    return control


def plan_ready_for_integration(plan: Dict[str, Any]) -> bool:
    if str(plan.get("status") or "open") != "open":
        return False
    statuses = plan.get("task_status", {}) or {}
    return bool(statuses) and any(
        status == "closed" for status in statuses.values()
    ) and all(status in ("closed", "cancelled") for status in statuses.values())


def integration_stage_for_path(
    base_dir: str | Path,
) -> Optional[Dict[str, Any]]:
    """Return the integration-ready Plan owning this worktree or control root."""
    current = Path(base_dir).expanduser().resolve()
    control = _canonical_control(current)
    try:
        registry = json.loads(
            (control / ".aiwf/state/plans.json").read_text(encoding="utf-8")
        )
    except Exception:
        registry = {"plans": []}
    plans = [
        plan for plan in registry.get("plans", []) or []
        if isinstance(plan, dict) and plan_ready_for_integration(plan)
    ]
    worktree_matches = []
    for plan in plans:
        plan_worktree = str(plan.get("git_worktree_path") or "")
        if plan_worktree and same_path(plan_worktree, current):
            worktree_matches.append(plan)
    candidates = worktree_matches
    if not candidates and same_path(current, control):
        engaged = [
            plan for plan in plans
            if str(((plan.get("integration") or {}).get("status") or ""))
            in {"auditing", "conflict", "prepared", "failed"}
        ]
        active_plan_id = str(registry.get("active_plan_id") or "")
        active = [
            plan for plan in plans
            if str(plan.get("plan_id") or plan.get("id") or "") == active_plan_id
        ]
        candidates = engaged if len(engaged) == 1 else active
        if not candidates and len(plans) == 1:
            candidates = plans
    if len(candidates) != 1:
        return None
    plan = candidates[0]
    integration = plan.get("integration", {}) or {}
    return {
        "plan_id": str(plan.get("plan_id") or plan.get("id") or ""),
        "worktree": str(plan.get("git_worktree_path") or ""),
        "control_root": str(control),
        "status": str(integration.get("status") or "ready"),
        "conflicts": list(integration.get("conflicts", []) or []),
        "base_ref": str(integration.get("base_ref") or ""),
        "plan_ref": str(integration.get("plan_ref") or ""),
    }


def integration_conflict_for_worktree(
    base_dir: str | Path,
) -> Optional[Dict[str, Any]]:
    """Compatibility helper for callers needing an actual conflict."""
    stage = integration_stage_for_path(base_dir)
    if stage and stage.get("status") == "conflict":
        return stage
    return None
