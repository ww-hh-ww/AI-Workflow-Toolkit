"""Prepare and finish one Plan integration without dirtying the base branch."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .git_snapshots import ref_tree
from .git_workflow import changed_project_files, repository_info
from .plan_integration_git import (
    conflict_paths,
    git_operation,
    is_ancestor,
    require_git,
    resolve_ref,
    run_git,
)
from .state._common import _exclusive_operation_lock
from .state.plan_ops import load_plans, save_plans
from .worktree_context import resolve_control_root


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _find_plan(data: Dict[str, Any], plan_id: str) -> Optional[Dict[str, Any]]:
    return next(
        (
            plan for plan in data.get("plans", []) or []
            if isinstance(plan, dict)
            and str(plan.get("plan_id") or plan.get("id") or "") == plan_id
        ),
        None,
    )


def _basic_blockers(control: Path, plan: Dict[str, Any]) -> List[str]:
    blockers: List[str] = []
    statuses = plan.get("task_status", {}) or {}
    unfinished = [tid for tid, status in statuses.items() if status not in ("closed", "cancelled")]
    if unfinished:
        blockers.append("Plan still has unfinished Tasks: " + ", ".join(unfinished[:8]))
    if not any(status == "closed" for status in statuses.values()):
        blockers.append("Plan has no completed Task result to integrate")

    worktree_raw = str(plan.get("git_worktree_path") or "")
    branch = str(plan.get("git_branch") or "")
    base_branch = str(plan.get("git_base_branch") or "")
    recorded_head = str(plan.get("git_head_ref") or "")
    if not worktree_raw or not Path(worktree_raw).exists():
        blockers.append("Plan worktree is missing")
        return blockers
    worktree = Path(worktree_raw)
    plan_info = repository_info(str(worktree))
    control_info = repository_info(str(control))
    if plan_info.get("branch") != branch:
        blockers.append(
            f"Plan worktree is on '{plan_info.get('branch') or '(detached)'}', expected '{branch}'"
        )
    if plan_info.get("head") != recorded_head:
        blockers.append(
            "Plan branch HEAD changed after the last governed Task. Inspect the commit and "
            "bring it into AIWF through a Task before integration"
        )
    if not base_branch:
        blockers.append("Plan base branch is unknown")
    elif control_info.get("branch") != base_branch:
        blockers.append(
            f"run Plan integration from the control root on base branch '{base_branch}'"
        )
    if changed_project_files(str(control)):
        blockers.append("base worktree has uncommitted project changes")
    if changed_project_files(str(worktree)):
        blockers.append("Plan worktree has uncommitted project changes")
    for path, label in ((control, "base"), (worktree, "Plan")):
        operation = git_operation(path)
        if operation:
            blockers.append(f"{label} worktree has an unfinished Git {operation}")

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


def prepare_plan_integration(base_dir: str, plan_id: str) -> Dict[str, Any]:
    """Bring the Plan branch up to the current base when the merge is conflict-free."""
    control = resolve_control_root(base_dir)
    with _exclusive_operation_lock(str(control), "plan-integration"):
        data = load_plans(str(control))
        plan = _find_plan(data, plan_id)
        if not plan:
            raise ValueError(f"Plan not found: {plan_id}")
        if str(plan.get("status") or "open") != "open":
            raise ValueError(f"Plan is {plan.get('status')}; only an open Plan can be integrated")
        blockers = _basic_blockers(control, plan)
        if blockers:
            raise ValueError("; ".join(blockers))

        worktree = Path(str(plan["git_worktree_path"]))
        base_branch = str(plan["git_base_branch"])
        base_ref = resolve_ref(control, base_branch)
        plan_ref = resolve_ref(worktree, str(plan["git_branch"]))
        if not base_ref or not plan_ref:
            raise ValueError("cannot resolve the Plan and base commits")

        # A legacy/manual merge may already contain the recorded Plan result.
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
                plan["integration"] = {
                    "status": "conflict",
                    "base_ref": base_ref,
                    "plan_ref": plan_ref,
                    "conflicts": conflicts[:20],
                    "prepared_at": _now(),
                }
                plan.pop("integration_hold_ref", None)
                plan["updated_at"] = _now()
                save_plans(str(control), data)
                return {
                    "prepared": False,
                    "conflict": True,
                    "plan": plan,
                    "conflicts": conflicts,
                    "base_ref": base_ref,
                    "plan_ref": plan_ref,
                }
            merge = run_git(
                worktree, "merge", "--no-edit", base_ref,
                "-m", f"Integrate {base_branch} into {plan_id}",
            )
            if merge.returncode != 0:
                if git_operation(worktree) == "merge":
                    run_git(worktree, "merge", "--abort")
                raise ValueError(merge.stderr.strip() or merge.stdout.strip() or "base merge failed")
            candidate_ref = require_git(worktree, "rev-parse", "HEAD")
            plan["git_head_ref"] = candidate_ref

        plan["integration"] = {
            "status": "prepared",
            "base_ref": base_ref,
            "plan_ref": plan_ref,
            "candidate_ref": candidate_ref,
            "candidate_tree": ref_tree(str(control), candidate_ref),
            "candidate_worktree": str(control if already_merged else worktree),
            "commands": [],
            "verification_results": [],
            "summary": "",
            "prepared_at": _now(),
        }
        plan.pop("integration_hold_ref", None)
        plan["updated_at"] = _now()
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
        }


def finish_plan_integration(
    base_dir: str,
    plan_id: str,
    status: str,
    commands: List[str],
    verification_results: List[Dict[str, Any]],
    summary: str,
) -> Dict[str, Any]:
    """Record candidate proof and merge the exact passing candidate into its base."""
    if status not in ("passed", "failed"):
        raise ValueError("integration status must be passed or failed")
    if not commands:
        raise ValueError("integration proof requires at least one exact command")
    if not summary.strip():
        raise ValueError("integration proof requires a concise summary")
    normalized_commands = {" ".join(command.split()) for command in commands if command.strip()}
    matched_commands = {
        " ".join(str(item.get("command") or "").split())
        for item in verification_results
        if item.get("matched") and str(item.get("observed") or "").strip()
    }
    if status == "passed" and normalized_commands - matched_commands:
        raise ValueError(
            "passed integration requires a matched expected/observed result for every command"
        )

    control = resolve_control_root(base_dir)
    with _exclusive_operation_lock(str(control), "plan-integration"):
        data = load_plans(str(control))
        plan = _find_plan(data, plan_id)
        if not plan:
            raise ValueError(f"Plan not found: {plan_id}")
        blockers = _basic_blockers(control, plan)
        if blockers:
            raise ValueError("; ".join(blockers))
        integration = plan.get("integration", {}) or {}
        if integration.get("status") not in ("prepared", "failed"):
            raise ValueError("prepare this Plan with 'aiwf plan integrate' before recording proof")

        worktree = Path(str(plan["git_worktree_path"]))
        candidate_ref = str(integration.get("candidate_ref") or "")
        base_ref = str(integration.get("base_ref") or "")
        current_base = resolve_ref(control, str(plan.get("git_base_branch") or ""))
        current_plan = resolve_ref(worktree, str(plan.get("git_branch") or ""))
        if current_base != base_ref:
            raise ValueError("base branch changed after preparation; run 'aiwf plan integrate' again")
        if current_plan != str(plan.get("git_head_ref") or ""):
            raise ValueError("Plan branch changed after preparation; inspect it before integrating")
        if not is_ancestor(control, str(integration.get("plan_ref") or ""), candidate_ref):
            raise ValueError("prepared candidate no longer contains the reviewed Plan result")

        integration.update({
            "status": status,
            "commands": list(dict.fromkeys(commands)),
            "verification_results": verification_results,
            "summary": summary.strip()[:1000],
            "verified_at": _now(),
        })
        plan["integration"] = integration
        plan["updated_at"] = _now()
        if status == "failed":
            save_plans(str(control), data)
            return {"merged": False, "plan": plan, "integration": integration}

        if is_ancestor(control, candidate_ref, current_base):
            merge_commit = current_base
        else:
            merge = run_git(
                control, "merge", "--no-ff", "--no-commit", candidate_ref,
            )
            if merge.returncode != 0:
                if git_operation(control) == "merge":
                    run_git(control, "merge", "--abort")
                raise ValueError(merge.stderr.strip() or merge.stdout.strip() or "Plan merge failed")
            staged_tree = require_git(control, "write-tree")
            if staged_tree != str(integration.get("candidate_tree") or ""):
                run_git(control, "merge", "--abort")
                raise ValueError(
                    "base changed while integrating; the unverified merge was aborted"
                )
            commit = run_git(
                control, "commit", "-m",
                f"Merge {plan_id}: {plan.get('title_cache') or plan.get('title') or plan_id}",
            )
            if commit.returncode != 0:
                if git_operation(control) == "merge":
                    run_git(control, "merge", "--abort")
                raise ValueError(commit.stderr.strip() or commit.stdout.strip() or "Plan merge commit failed")
            merge_commit = require_git(control, "rev-parse", "HEAD")
        if ref_tree(str(control), merge_commit) != str(integration.get("candidate_tree") or ""):
            raise ValueError("merged base tree differs from the verified integration candidate")

        integration.update({
            "status": "merged",
            "merge_commit": merge_commit,
            "merged_at": _now(),
        })
        plan["integration"] = integration
        plan["updated_at"] = _now()
        save_plans(str(control), data)
        return {"merged": True, "plan": plan, "integration": integration}
