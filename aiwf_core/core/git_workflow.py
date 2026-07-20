"""Git snapshots and branch checks for the governed Task lifecycle."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..hooks.common.diff_snapshot import filter_internal, parse_nul_paths
from .git_snapshots import (
    diff_files, format_tree_changes, ref_tree, tree_changes,
    worktree_changes_from_ref, worktree_matches_ref,
)
from .worktree_context import resolve_worktree_root, same_path


PROTECTED_BRANCHES = {"main", "master", "trunk"}
SNAPSHOT_GUIDANCE = (
    "AIWF snapshots are intentionally outside the branch; do not commit, "
    "cherry-pick, merge, or reset them manually"
)


def reviewed_snapshot_mismatch_message(base_dir: str, reviewed_ref: str) -> str:
    changes = worktree_changes_from_ref(base_dir, reviewed_ref)
    detail = format_tree_changes(changes) or "tree content or file modes differ"
    return (
        f"project files changed after review ({detail}); {SNAPSHOT_GUIDANCE}. "
        "Run Tester and Reviewer again"
    )


def _run(base: Path, *args: str, env: Optional[Dict[str, str]] = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(base), env=env, capture_output=True,
        text=True, timeout=30,
    )


def _required(base: Path, *args: str, env: Optional[Dict[str, str]] = None) -> str:
    result = _run(base, *args, env=env)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "git command failed"
        raise ValueError(message)
    return result.stdout.strip()


def repository_info(base_dir: str) -> Dict[str, str]:
    base = Path(base_dir)
    root = _run(base, "rev-parse", "--show-toplevel")
    head = _run(base, "rev-parse", "HEAD")
    branch = _run(base, "branch", "--show-current")
    return {
        "root": root.stdout.strip() if root.returncode == 0 else "",
        "head": head.stdout.strip() if head.returncode == 0 else "",
        "branch": branch.stdout.strip() if branch.returncode == 0 else "",
    }


def changed_project_files(base_dir: str) -> List[str]:
    base = Path(base_dir)
    result = _run(
        base, "-c", "core.quotepath=false", "status", "--porcelain=v1", "-z",
        "--untracked-files=all",
    )
    if result.returncode != 0:
        return []
    paths: List[str] = []
    entries = result.stdout.split("\0")
    index = 0
    while index < len(entries):
        line = entries[index]
        index += 1
        if len(line) < 4:
            continue
        paths.append(line[3:])
        if "R" in line[:2] or "C" in line[:2]:
            if index < len(entries) and entries[index]:
                paths.append(entries[index])
            index += 1  # porcelain -z stores the old path in the next field
    return sorted(filter_internal(paths, cwd=base))


def task_activation_git_blockers(
    base_dir: str,
    plan: Optional[Dict[str, Any]] = None,
    allow_dirty: bool = False,
    expected_head: str = "",
) -> List[str]:
    info = repository_info(base_dir)
    blockers: List[str] = []
    if not info["root"]:
        return ["Task execution requires a Git repository"]
    if not info["head"]:
        return ["Task execution requires an initial Git commit"]
    if not info["branch"]:
        blockers.append("Task execution requires a named Git branch, not detached HEAD")
    elif info["branch"] in PROTECTED_BRANCHES:
        blockers.append(
            f"Task execution cannot start on protected branch '{info['branch']}'; "
            "create or switch to the Plan feature branch first"
        )
    if expected_head and info["head"] != expected_head:
        blockers.append("Git HEAD changed while the Task was suspended")
    dirty = changed_project_files(base_dir)
    if dirty and not allow_dirty:
        blockers.append(
            "Task activation requires a clean project worktree. Inspect these changes "
            "and ask the user whether to keep or discard them; do not commit, stash, "
            "restore, or remove them without that decision. Kept changes may be committed "
            "to the Plan branch before activation: "
            + ", ".join(dirty[:8])
        )
    bound = str((plan or {}).get("git_branch") or "")
    if bound and info["branch"] and bound != info["branch"]:
        blockers.append(
            f"Plan is bound to Git branch '{bound}', current branch is '{info['branch']}'"
        )
    return blockers


def _existing_branch(base: Path, name: str) -> bool:
    return _run(base, "show-ref", "--verify", "--quiet", f"refs/heads/{name}").returncode == 0


def detect_base_branch(base_dir: str, current_branch: str) -> str:
    base = Path(base_dir)
    remote = _run(base, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
    if remote.returncode == 0 and remote.stdout.strip().startswith("origin/"):
        candidate = remote.stdout.strip().split("/", 1)[1]
        if candidate != current_branch:
            return candidate
    for candidate in ("main", "master", "trunk"):
        if candidate != current_branch and _existing_branch(base, candidate):
            return candidate
    return ""


def bind_plan_branch(base_dir: str, plan: Dict[str, Any]) -> Dict[str, str]:
    """Bind a Plan to the current worktree and branch."""
    return bind_plan_worktree(base_dir, plan, resolve_worktree_root(base_dir))


def bind_plan_worktree(
    base_dir: str,
    plan: Dict[str, Any],
    worktree_path: str | Path,
) -> Dict[str, str]:
    worktree = resolve_worktree_root(worktree_path)
    info = repository_info(str(worktree))
    branch = info["branch"]
    if not branch or not info["head"]:
        raise ValueError("cannot bind Plan without a named worktree branch and Git HEAD")
    control_info = repository_info(base_dir)
    if control_info.get("root"):
        control_common = _run(Path(control_info["root"]), "rev-parse", "--git-common-dir")
        worktree_common = _run(worktree, "rev-parse", "--git-common-dir")
        control_common_path = Path(control_common.stdout.strip())
        if not control_common_path.is_absolute():
            control_common_path = Path(control_info["root"]) / control_common_path
        worktree_common_path = Path(worktree_common.stdout.strip())
        if not worktree_common_path.is_absolute():
            worktree_common_path = worktree / worktree_common_path
        if (
            control_common.returncode != 0
            or worktree_common.returncode != 0
            or control_common_path.resolve() != worktree_common_path.resolve()
        ):
            raise ValueError("Plan worktree must belong to the governed Git repository")
    bound = str(plan.get("git_branch") or "")
    if bound and bound != branch:
        raise ValueError(f"Plan is bound to '{bound}', current branch is '{branch}'")
    bound_path = str(plan.get("git_worktree_path") or "")
    if bound_path and not same_path(bound_path, worktree):
        raise ValueError(f"Plan is bound to worktree '{bound_path}'")
    base_branch = str(plan.get("git_base_branch") or "") or detect_base_branch(str(worktree), branch)
    base_ref = str(plan.get("git_base_ref") or "")
    if not base_ref:
        if base_branch:
            merge_base = _run(worktree, "merge-base", "HEAD", base_branch)
            base_ref = merge_base.stdout.strip() if merge_base.returncode == 0 else info["head"]
        else:
            base_ref = info["head"]
    previous_head = str(plan.get("git_head_ref") or "")
    plan["git_worktree_path"] = str(worktree)
    plan["git_branch"] = branch
    plan["git_base_branch"] = base_branch
    plan["git_base_ref"] = base_ref
    plan["git_head_ref"] = info["head"]
    if previous_head != info["head"]:
        plan.pop("integration_hold_ref", None)
    return {
        "worktree_path": str(worktree),
        "branch": branch,
        "base_branch": base_branch,
        "base_ref": base_ref,
    }


def create_task_commit(
    base_dir: str, task: Dict[str, Any], origin_ref: str, reviewed_ref: str,
) -> str:
    base = Path(base_dir)
    info = repository_info(base_dir)
    expected_branch = str(task.get("git_branch") or "")
    if expected_branch and info["branch"] != expected_branch:
        raise ValueError(
            f"Task is bound to Git branch '{expected_branch}', current branch is '{info['branch']}'"
        )
    if info["head"] != origin_ref:
        if (
            ref_tree(base_dir, info["head"]) == ref_tree(base_dir, reviewed_ref)
            and worktree_matches_ref(base_dir, reviewed_ref)
        ):
            return info["head"]
        raise ValueError(
            "Git HEAD changed since Task activation; " + SNAPSHOT_GUIDANCE +
            ". Re-plan or restart the Task on the current branch"
        )
    if not worktree_matches_ref(base_dir, reviewed_ref):
        raise ValueError(reviewed_snapshot_mismatch_message(base_dir, reviewed_ref))
    files = diff_files(base_dir, origin_ref, reviewed_ref)
    if not files:
        raise ValueError("Task has no reviewed project changes to commit")
    staged_result = _run(base, "diff", "--cached", "--name-only", "-z")
    if staged_result.returncode != 0:
        raise ValueError(staged_result.stderr.strip() or "cannot inspect the Git index")
    staged_before = parse_nul_paths(staged_result.stdout)
    if staged_before:
        staged = ", ".join(staged_before[:8])
        raise ValueError(
            f"Git index already contains staged files: {staged}; "
            "unstage them before Task close"
        )
    _required(base, "add", "-A", "--", *files)
    staged_tree = _required(base, "write-tree")
    expected_tree = ref_tree(base_dir, reviewed_ref)
    if staged_tree != expected_tree:
        changes = tree_changes(base_dir, reviewed_ref, staged_tree)
        detail = format_tree_changes(changes) or "tree content or file modes differ"
        _run(base, "reset", "-q", "HEAD", "--", ".")
        raise ValueError(
            f"staged Task tree does not match the reviewed snapshot ({detail}); "
            f"{SNAPSHOT_GUIDANCE}"
        )
    task_id = str(task.get("id") or "TASK")
    title = str(task.get("title_cache") or task.get("title") or "completed task")
    plan_id = str(task.get("plan_id") or task.get("parent_plan") or "")
    goal_id = str(task.get("goal_id") or task.get("parent_goal") or "")
    subject = f"{task_id}: {title}"
    trailers = []
    if plan_id:
        trailers.append(f"Plan: {plan_id}")
    if goal_id:
        trailers.append(f"Goal: {goal_id}")
    message_args = [arg for item in trailers for arg in ("-m", item)]
    result = _run(base, "commit", "-m", subject, *message_args)
    if result.returncode != 0:
        _run(base, "reset", "-q", "HEAD", "--", ".")
        raise ValueError(result.stderr.strip() or result.stdout.strip() or "git commit failed")
    commit = _required(base, "rev-parse", "HEAD")
    if ref_tree(base_dir, commit) != expected_tree:
        raise ValueError("created commit differs from the reviewed snapshot")
    if changed_project_files(base_dir):
        raise ValueError("project files changed during commit; retest and review the remaining changes")
    return commit


def plan_merge_state(base_dir: str, plan: Dict[str, Any]) -> str:
    head_ref = str(plan.get("git_head_ref") or "")
    base_branch = str(plan.get("git_base_branch") or "")
    if not head_ref or not base_branch:
        return "unknown"
    result = _run(
        Path(base_dir), "merge-base", "--is-ancestor", head_ref, base_branch,
    )
    if result.returncode == 0:
        return "merged"
    if result.returncode == 1:
        return "unmerged"
    return "unknown"


def plan_merged_into_base(base_dir: str, plan: Dict[str, Any]) -> bool:
    return plan_merge_state(base_dir, plan) == "merged"


def plan_integration_state(base_dir: str, plan: Dict[str, Any]) -> str:
    """Derive the open Plan's post-Task state without adding lifecycle statuses."""
    persisted = str(plan.get("status") or "open")
    if persisted != "open":
        return persisted
    statuses = plan.get("task_status", {}) or {}
    if not statuses or any(
        status not in ("closed", "cancelled") for status in statuses.values()
    ):
        return "working"
    if not any(status == "closed" for status in statuses.values()):
        return "no_completed_work"
    merge_state = plan_merge_state(base_dir, plan)
    if merge_state == "merged":
        return "merged_pending_close"
    if merge_state == "unknown":
        return "git_incomplete"
    head_ref = str(plan.get("git_head_ref") or "")
    if head_ref and str(plan.get("integration_hold_ref") or "") == head_ref:
        return "held"
    return "awaiting_decision"


def plan_close_blockers(base_dir: str, plan: Dict[str, Any]) -> List[str]:
    blockers: List[str] = []
    statuses = plan.get("task_status", {}) or {}
    unfinished = [tid for tid, status in statuses.items() if status not in ("closed", "cancelled")]
    if unfinished:
        blockers.append("Plan still has unfinished Tasks: " + ", ".join(unfinished[:8]))
    if changed_project_files(base_dir):
        blockers.append("Plan close requires a clean project worktree")
    branch = str(plan.get("git_branch") or "")
    head_ref = str(plan.get("git_head_ref") or "")
    base_branch = str(plan.get("git_base_branch") or "")
    info = repository_info(base_dir)
    if not branch or not head_ref:
        blockers.append("Plan has no Git branch history; close its Tasks through the Git-backed workflow")
    elif not base_branch:
        blockers.append("Plan base branch is unknown; merge the Plan branch and record a standard base branch")
    elif info["branch"] != base_branch:
        blockers.append(
            f"merge '{branch}' into '{base_branch}', switch to '{base_branch}', then close the Plan"
        )
    elif not plan_merged_into_base(base_dir, plan):
        blockers.append(f"Plan branch '{branch}' is not merged into '{base_branch}'")
    return blockers
