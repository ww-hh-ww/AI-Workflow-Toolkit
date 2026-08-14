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
_INTERNAL_EXCLUDES = [
    ":(exclude).aiwf", ":(exclude).aiwf/**",
]
SNAPSHOT_GUIDANCE = (
    "AIWF snapshots are intentionally outside the branch; do not commit, "
    "cherry-pick, merge, or reset them manually"
)


def _integration_parents(base: Path, ref: str) -> List[str]:
    return _required(base, "show", "-s", "--format=%P", ref).split()


def integration_close_readiness(
    base_dir: str,
    task: Dict[str, Any],
    origin_ref: str,
    reviewed_ref: str,
) -> Dict[str, str]:
    """Classify an integration Task's Git state without changing it."""
    base = Path(base_dir)
    info = repository_info(base_dir)
    expected_base = str(task.get("integration_base_ref") or "")
    expected_parents = [origin_ref, expected_base]
    if not origin_ref or not expected_base or not reviewed_ref:
        return {
            "status": "blocked",
            "message": "integration Task is missing its recorded origin, base, or reviewed ref",
        }
    if worktree_changes_from_ref(base_dir, reviewed_ref):
        return {
            "status": "blocked",
            "message": reviewed_snapshot_mismatch_message(base_dir, reviewed_ref),
        }
    merge_head = _run(base, "rev-parse", "-q", "--verify", "MERGE_HEAD")
    open_merge_ref = merge_head.stdout.strip() if merge_head.returncode == 0 else ""
    if info["head"] == origin_ref:
        if not open_merge_ref:
            return {
                "status": "blocked",
                "message": (
                    "integration Task has not opened the recorded merge; run the merge "
                    "from Task.md and resolve it before close"
                ),
            }
        if open_merge_ref != expected_base:
            return {
                "status": "blocked",
                "message": "integration Task is resolving a different base commit than it activated with",
            }
        return {"status": "ready", "mode": "open_merge"}
    if open_merge_ref:
        return {
            "status": "blocked",
            "message": "integration Task HEAD changed while another merge is still open",
        }
    if _integration_parents(base, info["head"]) != expected_parents:
        return {
            "status": "blocked",
            "message": (
                "existing integration commit does not have the recorded Plan and "
                "base refs as its two parents"
            ),
        }
    if not tree_changes(base_dir, reviewed_ref, info["head"]):
        return {"status": "ready", "mode": "existing_merge"}
    staged_tree = _required(base, "write-tree")
    staged_changes = tree_changes(base_dir, reviewed_ref, staged_tree)
    if staged_changes:
        detail = format_tree_changes(staged_changes) or "tree content or file modes differ"
        return {
            "status": "blocked",
            "message": (
                "the current integration index does not match the reviewed project "
                f"snapshot ({detail})"
            ),
        }
    staged_result = _run(base, "diff", "--cached", "--name-only", "-z")
    if staged_result.returncode != 0:
        return {
            "status": "blocked",
            "message": staged_result.stderr.strip() or "cannot inspect the Git index",
        }
    staged_paths = parse_nul_paths(staged_result.stdout)
    internal_staged = [
        path for path in staged_paths
        if path == ".aiwf" or path.startswith(".aiwf/")
    ]
    if internal_staged:
        return {
            "status": "blocked",
            "message": (
                "AIWF governance files are staged with the premature merge: "
                + ", ".join(internal_staged[:8])
            ),
        }
    return {"status": "ready", "mode": "amend_merge"}


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
        text=True, encoding="utf-8", errors="surrogateescape", timeout=30,
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


def abort_open_task_merge(base_dir: str) -> bool:
    """Abort an open merge when a human ends the owning Task."""
    from .plan_integration_git import git_operation

    operation = git_operation(Path(base_dir))
    if not operation:
        return False
    if operation != "merge":
        raise ValueError(f"worktree has an unfinished Git {operation}")
    result = _run(Path(base_dir), "merge", "--abort")
    if result.returncode != 0:
        raise ValueError(
            result.stderr.strip()
            or result.stdout.strip()
            or "cannot abort the open Task merge"
        )
    return True


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
    integration_task = str(task.get("kind") or "") == "integration"
    if expected_branch and info["branch"] != expected_branch:
        raise ValueError(
            f"Task is bound to Git branch '{expected_branch}', current branch is '{info['branch']}'"
        )
    integration_mode = ""
    if integration_task:
        readiness = integration_close_readiness(
            base_dir, task, origin_ref, reviewed_ref,
        )
        if readiness.get("status") != "ready":
            raise ValueError(str(readiness.get("message") or "integration Task is not ready to close"))
        integration_mode = str(readiness.get("mode") or "")
        if integration_mode == "existing_merge":
            return info["head"]
    elif info["head"] != origin_ref:
        if (
            ref_tree(base_dir, info["head"]) == ref_tree(base_dir, reviewed_ref)
            and worktree_matches_ref(base_dir, reviewed_ref)
        ):
            return info["head"]
        raise ValueError(
            "Git HEAD changed since Task activation; " + SNAPSHOT_GUIDANCE +
            ". Re-plan or restart the Task on the current branch"
        )
    if integration_task:
        if worktree_changes_from_ref(base_dir, reviewed_ref):
            raise ValueError(reviewed_snapshot_mismatch_message(base_dir, reviewed_ref))
    elif not worktree_matches_ref(base_dir, reviewed_ref):
        raise ValueError(reviewed_snapshot_mismatch_message(base_dir, reviewed_ref))
    files = diff_files(base_dir, origin_ref, reviewed_ref)
    if not files:
        if (
            str(task.get("adopted_head_ref") or "") == info["head"]
            and ref_tree(base_dir, info["head"]) == ref_tree(base_dir, reviewed_ref)
            and worktree_matches_ref(base_dir, reviewed_ref)
        ):
            return info["head"]
        raise ValueError("Task has no reviewed project changes to commit")
    staged_result = _run(base, "diff", "--cached", "--name-only", "-z")
    if staged_result.returncode != 0:
        raise ValueError(staged_result.stderr.strip() or "cannot inspect the Git index")
    staged_before = parse_nul_paths(staged_result.stdout)
    if staged_before and not integration_task:
        staged = ", ".join(staged_before[:8])
        raise ValueError(
            f"Git index already contains staged files: {staged}; "
            "unstage them before Task close"
        )
    if integration_task and integration_mode == "open_merge":
        from .plan_integration_git import (
            is_governance_path,
            resolve_governance_from_ref,
            unmerged_paths,
        )

        _required(base, "add", "-A", "--", ".", *_INTERNAL_EXCLUDES)
        unresolved = unmerged_paths(base)
        if unresolved and all(is_governance_path(path) for path in unresolved):
            resolve_governance_from_ref(base, "HEAD")
        elif unresolved:
            raise ValueError(
                "integration Task still has unresolved project conflicts: "
                + ", ".join(unresolved[:8])
            )
    else:
        _required(base, "add", "-A", "--", *files)
    staged_tree = _required(base, "write-tree")
    expected_tree = ref_tree(base_dir, reviewed_ref)
    project_mismatch = bool(tree_changes(base_dir, reviewed_ref, staged_tree))
    if (integration_task and project_mismatch) or (not integration_task and staged_tree != expected_tree):
        changes = tree_changes(base_dir, reviewed_ref, staged_tree)
        detail = format_tree_changes(changes) or "tree content or file modes differ"
        if not integration_task:
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
    commit_args = ["commit"]
    if integration_mode == "amend_merge":
        commit_args.append("--amend")
    result = _run(base, *commit_args, "-m", subject, *message_args)
    if result.returncode != 0:
        if integration_mode != "amend_merge":
            _run(base, "reset", "-q", "HEAD", "--", ".")
        raise ValueError(result.stderr.strip() or result.stdout.strip() or "git commit failed")
    commit = _required(base, "rev-parse", "HEAD")
    if integration_task:
        if tree_changes(base_dir, reviewed_ref, commit):
            raise ValueError("created integration commit differs from the reviewed project snapshot")
    elif ref_tree(base_dir, commit) != expected_tree:
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
    integration = plan.get("integration", {}) or {}
    integration_status = str(integration.get("status") or "")
    if integration_status == "auditing":
        return "integration_audit"
    if integration_status == "conflict":
        return "integration_conflict"
    if integration_status == "failed":
        return "integration_failed"
    branch = str(plan.get("git_branch") or "")
    head_ref = str(plan.get("git_head_ref") or "")
    if branch and head_ref:
        actual = _run(Path(base_dir), "rev-parse", f"{branch}^{{commit}}")
        if actual.returncode != 0 or actual.stdout.strip() != head_ref:
            return "git_incomplete"
    if integration_status == "prepared":
        # A deliberate hold is authoritative for an otherwise prepared
        # candidate. Check it before the prepared/base comparison; governance
        # checkpoints made while holding another Plan can legitimately move the
        # base branch without reopening this Plan's merge decision.
        if head_ref and str(plan.get("integration_hold_ref") or "") == head_ref:
            return "held"
        base_branch = str(plan.get("git_base_branch") or "")
        current_base = _run(Path(base_dir), "rev-parse", f"{base_branch}^{{commit}}")
        if current_base.returncode != 0:
            return "git_incomplete"
        current_base_ref = current_base.stdout.strip()
        prepared_base_ref = str(integration.get("base_ref") or "")
        if current_base_ref != prepared_base_ref:
            parents = _run(
                Path(base_dir), "show", "-s", "--format=%P", current_base_ref,
            )
            tree = _run(
                Path(base_dir), "show", "-s", "--format=%T", current_base_ref,
            )
            if (
                parents.returncode == 0
                and parents.stdout.split()
                == [prepared_base_ref, str(integration.get("candidate_ref") or "")]
                and tree.returncode == 0
                and tree.stdout.strip() == str(integration.get("candidate_tree") or "")
            ):
                return "closure_recovery"
            return "base_changed"
        return "integration_ready"
    merge_state = plan_merge_state(base_dir, plan)
    if merge_state == "merged":
        if integration_status != "merged":
            return "merged_unverified"
        return "closure_recovery"
    if merge_state == "unknown":
        return "git_incomplete"
    if head_ref and str(plan.get("integration_hold_ref") or "") == head_ref:
        return "held"
    return "awaiting_decision"
