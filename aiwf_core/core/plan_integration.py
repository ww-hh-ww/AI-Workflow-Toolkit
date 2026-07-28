"""Prepare and finish one Plan integration without dirtying the base branch."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .git_snapshots import ref_tree
from .git_workflow import changed_project_files, repository_info
from .plan_integration_git import (
    canonical_candidate,
    conflict_paths,
    git_operation,
    is_governance_path,
    is_ancestor,
    require_git,
    resolve_governance_from_ref,
    resolve_ref,
    run_git,
    unmerged_paths,
)
from .plan_integration_refresh import (
    changed_paths,
    governance_only_head_change,
    refreshable_integration_task,
    reset_integration_task_critiques,
)
from .state._common import _governance_state_lock
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


def _write_plan_closure_doc(control: Path, plan_id: str, summary: str) -> bool:
    from .index_ops import parse_md, sync_index, write_narrative_doc

    doc = control / ".aiwf" / "plans" / f"{plan_id}.md"
    if not doc.exists():
        return False
    frontmatter, body = parse_md(doc)
    if frontmatter is None:
        raise ValueError(f"cannot read Plan document frontmatter: {doc}")
    if (
        str(frontmatter.get("status") or "") == "closed"
        and str(frontmatter.get("closure_summary") or "") == summary
    ):
        return False
    frontmatter["status"] = "closed"
    frontmatter["closure_summary"] = summary
    write_narrative_doc(doc, frontmatter, body)
    sync_index(str(control))
    return True


def _plan_closure_summary(control: Path, plan_id: str) -> str:
    from .index_ops import parse_md, read_markdown_section

    doc = control / ".aiwf" / "plans" / f"{plan_id}.md"
    if not doc.exists():
        raise ValueError(f"Plan document not found: {doc}")
    frontmatter, body = parse_md(doc)
    if frontmatter is None:
        raise ValueError(f"cannot read Plan document frontmatter: {doc}")
    calibration = read_markdown_section(body, "Closure Calibration")
    if not calibration:
        raise ValueError(
            "Plan.md needs a non-empty '## Closure Calibration' before passing integration"
        )
    first_paragraph = calibration.split("\n\n", 1)[0]
    summary = " ".join(first_paragraph.split())
    if not summary:
        raise ValueError(
            "Plan.md Closure Calibration needs a concise outcome paragraph"
        )
    return summary[:1000]


def _finish_plan_closure(
    control: Path,
    plan_id: str,
    summary: str,
    merge_commit: str,
) -> Dict[str, Any]:
    """Close Plan meaning/state and checkpoint governance after its project merge."""
    _write_plan_closure_doc(control, plan_id, summary)

    with _governance_state_lock(str(control)):
        data = load_plans(str(control))
        plan = _find_plan(data, plan_id)
        if not plan:
            raise ValueError(f"Plan not found while finishing closure: {plan_id}")
        integration = plan.get("integration", {}) or {}
        if (
            str(integration.get("status") or "") != "merged"
            or str(integration.get("merge_commit") or "") != merge_commit
        ):
            raise ValueError("Plan integration record changed before closure finished")
        closure = {
            "mode": "normal",
            "accepted": True,
            "summary": summary,
            "merged_commit": merge_commit,
        }
        if plan.get("status") != "closed" or plan.get("closure") != closure:
            plan["status"] = "closed"
            plan.pop("integration_hold_ref", None)
            plan["closure"] = closure
            plan["updated_at"] = _now()
            save_plans(str(control), data)

    checkpoint: Dict[str, Any]
    try:
        from .governance_git import checkpoint_governance

        checkpoint = checkpoint_governance(
            control, reason=f"after Plan integration and close: {plan_id}",
        )
    except ValueError as exc:
        checkpoint = {
            "committed": False,
            "commit": "",
            "paths": [],
            "warning": str(exc),
        }
    return {"plan": plan, "integration": integration, "governance_checkpoint": checkpoint}


def _basic_blockers(
    control: Path,
    plan: Dict[str, Any],
    *,
    refresh_task: Optional[Dict[str, Any]] = None,
    accept_head_change: bool = False,
    require_clean_base: bool = False,
) -> List[str]:
    blockers: List[str] = []
    statuses = plan.get("task_status", {}) or {}
    unfinished = [tid for tid, status in statuses.items() if status not in ("closed", "cancelled")]
    refresh_task_id = str((refresh_task or {}).get("id") or "")
    if unfinished and set(map(str, unfinished)) != {refresh_task_id}:
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
    current_head = str(plan_info.get("head") or "")
    if current_head != recorded_head and not governance_only_head_change(
        worktree, recorded_head, current_head,
    ) and not accept_head_change:
        changed = changed_paths(worktree, recorded_head, current_head)
        detail = ", ".join(changed[:6]) if changed else "unknown files"
        blockers.append(
            "Plan branch contains project changes after the last governed Task: "
            f"{detail}. Inspect them with the user, then either bring them through a "
            "Task or rerun Plan integration with --accept-head-change"
        )
    if not base_branch:
        blockers.append("Plan base branch is unknown")
    elif control_info.get("branch") != base_branch:
        blockers.append(
            f"run Plan integration from the control root on base branch '{base_branch}'"
        )
    base_changes = changed_project_files(str(control))
    if require_clean_base and base_changes:
        blockers.append(
            "base worktree has uncommitted project changes: "
            f"{', '.join(base_changes[:6])}. Ask the user how to keep or discard "
            "them before merging"
        )
    plan_changes = changed_project_files(str(worktree))
    if plan_changes:
        blockers.append(
            "Plan worktree has uncommitted project changes: "
            f"{', '.join(plan_changes[:6])}. Do not commit test output just to pass "
            "integration. Bring real result changes through a Task and prepare a fresh "
            "candidate; restore generated noise only after the user confirms"
        )
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


def prepare_plan_integration(
    base_dir: str,
    plan_id: str,
    *,
    accept_head_change: bool = False,
) -> Dict[str, Any]:
    """Bring the Plan branch up to the current base when the merge is conflict-free."""
    control = resolve_control_root(base_dir)
    from .governance_git import checkpoint_governance

    checkpoint = checkpoint_governance(
        control, reason=f"before Plan integration: {plan_id}",
    )
    with _governance_state_lock(str(control)):
        data = load_plans(str(control))
        plan = _find_plan(data, plan_id)
        if not plan:
            raise ValueError(f"Plan not found: {plan_id}")
        if str(plan.get("status") or "open") != "open":
            raise ValueError(f"Plan is {plan.get('status')}; only an open Plan can be integrated")
        refresh_task = refreshable_integration_task(control, plan)
        blockers = _basic_blockers(
            control,
            plan,
            refresh_task=refresh_task,
            accept_head_change=accept_head_change,
        )
        if blockers:
            raise ValueError("; ".join(blockers))

        worktree = Path(str(plan["git_worktree_path"]))
        base_branch = str(plan["git_base_branch"])
        base_ref = resolve_ref(control, base_branch)
        plan_ref = resolve_ref(worktree, str(plan["git_branch"]))
        old_integration = dict(plan.get("integration", {}) or {})
        old_recorded_head = str(plan.get("git_head_ref") or "")
        if not base_ref or not plan_ref:
            raise ValueError("cannot resolve the Plan and base commits")
        head_refreshed = bool(old_recorded_head and old_recorded_head != plan_ref)
        if head_refreshed:
            plan["git_head_ref"] = plan_ref

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
                project_conflicts = [
                    path for path in conflicts if not is_governance_path(path)
                ]
                if not conflicts or project_conflicts:
                    plan["integration"] = {
                        "status": "conflict",
                        "base_ref": base_ref,
                        "plan_ref": plan_ref,
                        "conflicts": (project_conflicts or conflicts)[:20],
                        "prepared_at": _now(),
                    }
                    reset_tasks = reset_integration_task_critiques(
                        control, plan_id, old_integration, base_ref, plan_ref,
                    )
                    plan.pop("integration_hold_ref", None)
                    plan["updated_at"] = _now()
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
                        "integration_task_id": str(
                            (refresh_task or {}).get("id") or ""
                        ),
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
            "prepared_at": _now(),
        }
        reset_tasks = reset_integration_task_critiques(
            control, plan_id, old_integration, base_ref, plan_ref,
        )
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
            "head_refreshed": head_refreshed,
            "critique_reset_task_ids": reset_tasks,
            "integration_task_no_longer_needed": bool(refresh_task),
            "integration_task_id": str((refresh_task or {}).get("id") or ""),
            "governance_checkpoint": checkpoint,
        }


def finish_plan_integration(
    base_dir: str,
    plan_id: str,
    status: str,
    commands: List[str],
    verification_results: List[Dict[str, Any]],
    summary: str,
) -> Dict[str, Any]:
    """Record proof, merge the exact passing candidate, and close its Plan."""
    if status not in ("passed", "failed"):
        raise ValueError("integration status must be passed or failed")
    if not commands:
        raise ValueError("integration proof requires at least one exact command")
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
    merge_commit = ""
    if status == "passed":
        closure_summary = _plan_closure_summary(control, plan_id)
    else:
        closure_summary = summary.strip()[:1000]
        if not closure_summary:
            raise ValueError("failed integration requires a concise failure summary")
    with _governance_state_lock(str(control)):
        data = load_plans(str(control))
        plan = _find_plan(data, plan_id)
        if not plan:
            raise ValueError(f"Plan not found: {plan_id}")
        integration = plan.get("integration", {}) or {}
        if (
            status == "passed"
            and str(integration.get("status") or "") == "merged"
            and str(integration.get("merge_commit") or "")
        ):
            merge_commit = str(integration["merge_commit"])
            base_branch = str(plan.get("git_base_branch") or "")
            if not is_ancestor(control, merge_commit, resolve_ref(control, base_branch)):
                raise ValueError("recorded Plan merge commit is not present on its base branch")
            closure_summary = str(
                ((plan.get("closure") or {}).get("summary"))
                or integration.get("summary")
                or closure_summary
            )
        else:
            blockers = _basic_blockers(control, plan, require_clean_base=True)
            if blockers:
                raise ValueError("; ".join(blockers))
            if integration.get("status") not in ("prepared", "failed"):
                raise ValueError("prepare this Plan with 'aiwf plan integrate' before recording proof")

            worktree = Path(str(plan["git_worktree_path"]))
            candidate_ref = str(integration.get("candidate_ref") or "")
            base_ref = str(integration.get("base_ref") or "")
            current_base = resolve_ref(control, str(plan.get("git_base_branch") or ""))
            current_plan = resolve_ref(worktree, str(plan.get("git_branch") or ""))
            recovered_merge = False
            if current_base != base_ref:
                parents = require_git(control, "show", "-s", "--format=%P", current_base).split()
                recovered_merge = (
                    status == "passed"
                    and parents == [base_ref, candidate_ref]
                    and ref_tree(str(control), current_base)
                    == str(integration.get("candidate_tree") or "")
                )
                if not recovered_merge:
                    raise ValueError(
                        "base branch changed after preparation; run 'aiwf plan integrate' again"
                    )
            if current_plan != str(plan.get("git_head_ref") or ""):
                raise ValueError("Plan branch changed after preparation; inspect it before integrating")
            if not is_ancestor(control, str(integration.get("plan_ref") or ""), candidate_ref):
                raise ValueError("prepared candidate no longer contains the reviewed Plan result")

            integration.update({
                "status": status,
                "commands": list(dict.fromkeys(commands)),
                "verification_results": verification_results,
                "summary": closure_summary,
                "verified_at": _now(),
            })
            plan["integration"] = integration
            plan["updated_at"] = _now()
            if status == "failed":
                save_plans(str(control), data)
                return {"merged": False, "closed": False, "plan": plan, "integration": integration}

            if recovered_merge:
                merge_commit = current_base
            elif is_ancestor(control, candidate_ref, current_base):
                merge_commit = current_base
            else:
                merge = run_git(
                    control, "merge", "--no-ff", "--no-commit", candidate_ref,
                )
                if merge.returncode != 0:
                    if git_operation(control) == "merge":
                        run_git(control, "merge", "--abort")
                    raise ValueError(
                        merge.stderr.strip() or merge.stdout.strip() or "Plan merge failed"
                    )
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
                    raise ValueError(
                        commit.stderr.strip() or commit.stdout.strip()
                        or "Plan merge commit failed"
                    )
                merge_commit = require_git(control, "rev-parse", "HEAD")
            if ref_tree(str(control), merge_commit) != str(integration.get("candidate_tree") or ""):
                raise ValueError("merged base tree differs from the verified integration candidate")

            integration.update({
                "status": "merged",
                "merge_commit": merge_commit,
                "merged_at": _now(),
            })
            plan["integration"] = integration
            plan["closure"] = {
                "mode": "normal",
                "accepted": True,
                "summary": closure_summary,
                "merged_commit": merge_commit,
            }
            plan["updated_at"] = _now()
            save_plans(str(control), data)

    try:
        closed = _finish_plan_closure(
            control, plan_id, closure_summary, merge_commit,
        )
    except Exception as exc:
        raise ValueError(
            "Plan project merge succeeded but governance closure is incomplete. "
            "Rerun the same 'aiwf plan integrate --status passed' command to finish it: "
            f"{exc}"
        ) from exc
    return {
        "merged": True,
        "closed": True,
        "plan": closed["plan"],
        "integration": closed["integration"],
        "governance_checkpoint": closed["governance_checkpoint"],
    }
