"""Audit and prepare one Plan integration candidate."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .git_workflow import repository_info
from .plan_integration_audit import integration_audit
from .plan_integration_checks import basic_blockers
from .plan_integration_closure import write_plan_closure_doc as _write_plan_closure_doc
from .plan_integration_common import find_plan, now
from .plan_integration_git import (
    canonical_candidate,
    conflict_paths,
    git_operation,
    is_ancestor,
    is_governance_path,
    require_git,
    resolve_governance_from_ref,
    resolve_ref,
    run_git,
    unmerged_paths,
)
from .plan_integration_refresh import (
    changed_paths,
    refreshable_integration_task,
    reset_integration_task_critiques,
)
from .plan_worktrees import _hide_worktree_governance
from .state._common import _governance_state_lock
from .state.plan_ops import load_plans, save_plans
from .worktree_context import resolve_control_root


def prepare_plan_integration(base_dir: str, plan_id: str) -> Dict[str, Any]:
    """Audit the Plan and prepare a candidate without changing the base branch."""
    control = resolve_control_root(base_dir)
    from .governance_git import checkpoint_governance

    try:
        checkpoint = checkpoint_governance(
            control, reason=f"before Plan integration: {plan_id}",
        )
    except ValueError as exc:
        checkpoint = {
            "committed": False, "commit": "", "paths": [], "warning": str(exc),
        }
    with _governance_state_lock(str(control)):
        data = load_plans(str(control))
        plan = find_plan(data, plan_id)
        if not plan:
            raise ValueError(f"Plan not found: {plan_id}")
        if str(plan.get("status") or "open") != "open":
            raise ValueError(f"Plan is {plan.get('status')}; only an open Plan can be integrated")
        refresh_task = refreshable_integration_task(control, plan)
        blockers = basic_blockers(control, plan, refresh_task=refresh_task)
        if blockers:
            raise ValueError("; ".join(blockers))

        worktree = Path(str(plan["git_worktree_path"]))
        if not git_operation(worktree):
            _hide_worktree_governance(worktree, restore_index=True)
        base_branch = str(plan["git_base_branch"])
        prior_integration = dict(plan.get("integration", {}) or {})
        current_plan_head = str(repository_info(str(worktree)).get("head") or "")
        resolved_conflicts = (
            list(prior_integration.get("conflicts", []) or [])
            if (
                str(prior_integration.get("status") or "") == "conflict"
                and current_plan_head
                and current_plan_head != str(prior_integration.get("plan_ref") or "")
            )
            else []
        )
        base_ref = resolve_ref(control, base_branch)
        plan_ref = resolve_ref(worktree, str(plan["git_branch"]))
        old_recorded_head = str(plan.get("git_head_ref") or "")
        if not base_ref or not plan_ref:
            raise ValueError("cannot resolve the Plan and base commits")
        head_refreshed = bool(old_recorded_head and old_recorded_head != plan_ref)
        audit = integration_audit(control, worktree)
        if head_refreshed:
            audit["head_changes_since_task"] = changed_paths(
                worktree, old_recorded_head, plan_ref,
            )
        if not audit["clean_for_candidate"]:
            plan["integration"] = {
                "status": "auditing",
                "base_ref": base_ref,
                "plan_ref": plan_ref,
                "audit": audit,
                "prepared_at": now(),
            }
            plan.pop("integration_hold_ref", None)
            plan["updated_at"] = now()
            save_plans(str(control), data)
            return {
                "prepared": False,
                "conflict": False,
                "audit_required": True,
                "plan": plan,
                "base_ref": base_ref,
                "plan_ref": plan_ref,
                "audit": audit,
                "head_refreshed": head_refreshed,
                "governance_checkpoint": checkpoint,
            }
        if head_refreshed:
            plan["git_head_ref"] = plan_ref

        already_merged = is_ancestor(control, plan_ref, base_ref)
        if already_merged:
            candidate_ref = base_ref
        elif is_ancestor(worktree, base_ref, plan_ref):
            candidate_ref = plan_ref
        else:
            preview = run_git(
                worktree, "merge-tree", "--write-tree", "--name-only", plan_ref, base_ref,
            )
            if preview.returncode != 0:
                diagnostic = (preview.stdout + "\n" + preview.stderr).lower()
                if "unknown option" in diagnostic or "usage: git merge-tree" in diagnostic:
                    raise ValueError(
                        "installed Git does not support safe merge preflight; update Git before "
                        "integrating this Plan"
                    )
                conflicts = conflict_paths(preview.stdout + "\n" + preview.stderr)
                project_conflicts = [
                    path for path in conflicts if not is_governance_path(path)
                ]
                if not conflicts or project_conflicts:
                    plan["integration"] = {
                        "status": "conflict",
                        "base_ref": base_ref,
                        "plan_ref": plan_ref,
                        "conflicts": (project_conflicts or conflicts)[:20],
                        "prepared_at": now(),
                        "audit": audit,
                    }
                    reset_tasks = reset_integration_task_critiques(
                        control, plan_id, prior_integration, base_ref, plan_ref,
                    )
                    plan.pop("integration_hold_ref", None)
                    plan["updated_at"] = now()
                    save_plans(str(control), data)
                    return {
                        "prepared": False,
                        "conflict": True,
                        "plan": plan,
                        "conflicts": project_conflicts or conflicts,
                        "base_ref": base_ref,
                        "plan_ref": plan_ref,
                        "head_refreshed": head_refreshed,
                        "critique_reset_task_ids": reset_tasks,
                        "integration_task_id": str((refresh_task or {}).get("id") or ""),
                        "governance_checkpoint": checkpoint,
                    }
            merge = run_git(
                worktree, "merge", "--no-edit", base_ref,
                "-m", f"Integrate {base_branch} into {plan_id}",
            )
            if merge.returncode != 0:
                unresolved = unmerged_paths(worktree)
                if unresolved and all(is_governance_path(path) for path in unresolved):
                    try:
                        resolve_governance_from_ref(worktree, base_ref)
                        commit = run_git(worktree, "commit", "--no-edit")
                        if commit.returncode != 0:
                            raise ValueError(
                                commit.stderr.strip() or commit.stdout.strip()
                                or "cannot finish governance-only merge"
                            )
                    except ValueError:
                        if git_operation(worktree) == "merge":
                            run_git(worktree, "merge", "--abort")
                        raise
                else:
                    if git_operation(worktree) == "merge":
                        run_git(worktree, "merge", "--abort")
                    raise ValueError(
                        merge.stderr.strip() or merge.stdout.strip() or "base merge failed"
                    )
            candidate_ref = require_git(worktree, "rev-parse", "HEAD")
            plan["git_head_ref"] = candidate_ref

        _hide_worktree_governance(worktree, restore_index=True)
        candidate_ref, candidate_tree = canonical_candidate(
            control, candidate_ref, base_ref, plan_id,
        )
        plan["integration"] = {
            "status": "prepared",
            "base_ref": base_ref,
            "plan_ref": plan_ref,
            "candidate_ref": candidate_ref,
            "candidate_tree": candidate_tree,
            "candidate_worktree": str(control if already_merged else worktree),
            "commands": [],
            "verification_results": [],
            "summary": "",
            "prepared_at": now(),
            "audit": audit,
        }
        if resolved_conflicts:
            plan["integration"]["resolved_conflicts"] = resolved_conflicts
        reset_tasks = reset_integration_task_critiques(
            control, plan_id, prior_integration, base_ref, plan_ref,
        )
        plan.pop("integration_hold_ref", None)
        plan["updated_at"] = now()
        save_plans(str(control), data)
        return {
            "prepared": True,
            "conflict": False,
            "already_merged": already_merged,
            "plan": plan,
            "base_ref": base_ref,
            "plan_ref": plan_ref,
            "candidate_ref": candidate_ref,
            "candidate_worktree": str(control if already_merged else worktree),
            "head_refreshed": head_refreshed,
            "critique_reset_task_ids": reset_tasks,
            "integration_task_no_longer_needed": bool(refresh_task),
            "integration_task_id": str((refresh_task or {}).get("id") or ""),
            "governance_checkpoint": checkpoint,
            "audit": audit,
        }


from .plan_integration_finalize import finish_plan_integration  # noqa: E402,F401
