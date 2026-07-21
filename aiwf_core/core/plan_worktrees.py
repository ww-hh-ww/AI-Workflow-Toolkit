"""Create and reuse persistent Git worktrees for Plans."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from .git_workflow import (
    _existing_branch,
    _required,
    bind_plan_worktree,
    changed_project_files,
    repository_info,
)
from .worktree_context import resolve_control_root, same_path


def _plan_slug(plan: Dict[str, Any]) -> str:
    plan_id = str(plan.get("plan_id") or plan.get("id") or "plan").strip().lower()
    slug = "".join(char if char.isalnum() else "-" for char in plan_id)
    return "-".join(part for part in slug.split("-") if part) or "plan"


def _ensure_local_ignore(control: Path, relative_parent: Path) -> None:
    exclude_raw = _required(control, "rev-parse", "--git-path", "info/exclude")
    exclude = Path(exclude_raw)
    if not exclude.is_absolute():
        exclude = control / exclude
    exclude.parent.mkdir(parents=True, exist_ok=True)
    pattern = f"/{relative_parent.as_posix().strip('/')}/"
    current = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
    if pattern in {line.strip() for line in current.splitlines()}:
        return
    prefix = "" if not current or current.endswith("\n") else "\n"
    with exclude.open("a", encoding="utf-8") as handle:
        handle.write(f"{prefix}{pattern}\n")


def create_plan_worktree(
    base_dir: str,
    plan: Dict[str, Any],
    worktree_path: str | Path | None = None,
) -> Dict[str, Any]:
    """Create or reuse a persistent worktree for one Plan, then bind it."""
    control = resolve_control_root(base_dir)
    bound_path = str(plan.get("git_worktree_path") or "").strip()
    if bound_path:
        if worktree_path and not same_path(bound_path, worktree_path):
            raise ValueError(f"Plan is already bound to worktree '{bound_path}'")
        binding = bind_plan_worktree(str(control), plan, bound_path)
        return {**binding, "created": False}

    info = repository_info(str(control))
    if not info["root"]:
        raise ValueError("Plan worktree creation requires a Git repository")
    if not info["head"]:
        raise ValueError("Plan worktree creation requires an initial Git commit")
    if not info["branch"]:
        raise ValueError("control root must be on a named base branch")

    relative_parent: Path | None = None
    if not worktree_path:
        host = os.environ.get("AIWF_HOST", "").strip().lower()
        if host == "opencode" and (control / ".opencode/plugins/aiwf.js").exists():
            config_dir = ".opencode"
        elif (control / ".claude/settings.json").exists():
            config_dir = ".claude"
        elif (control / ".opencode/plugins/aiwf.js").exists():
            config_dir = ".opencode"
        else:
            config_dir = ".reasonix"
        relative_parent = Path(config_dir) / "worktrees"
        managed_worktree_roots = {relative_parent}
        if (control / ".claude/settings.json").exists():
            managed_worktree_roots.add(Path(".claude/worktrees"))
        if (control / ".opencode/plugins/aiwf.js").exists():
            managed_worktree_roots.add(Path(".opencode/worktrees"))
        if (control / ".reasonix/settings.json").exists():
            managed_worktree_roots.add(Path(".reasonix/worktrees"))
        for managed_root in sorted(managed_worktree_roots, key=str):
            _ensure_local_ignore(control, managed_root)
    dirty = changed_project_files(str(control))
    if dirty:
        raise ValueError(
            "control root has uncommitted project changes; resolve them before creating "
            "a Plan worktree: " + ", ".join(dirty[:8])
        )

    slug = _plan_slug(plan)
    if worktree_path:
        target = Path(worktree_path).expanduser()
        if not target.is_absolute():
            target = control / target
        target = target.resolve()
    else:
        assert relative_parent is not None
        target = (control / relative_parent / slug).resolve()

    if same_path(target, control):
        raise ValueError(
            "the control root owns shared AIWF state and cannot be a new Plan worktree"
        )

    branch = str(plan.get("git_branch") or f"aiwf/{slug}")
    created = False
    if target.exists():
        target_info = repository_info(str(target))
        if not target_info["root"] or not same_path(target_info["root"], target):
            raise ValueError(
                f"Plan worktree path already exists and is not a Git worktree: {target}"
            )
        if target_info["branch"] != branch:
            raise ValueError(
                f"Plan worktree '{target}' uses branch '{target_info['branch']}', "
                f"expected '{branch}'"
            )
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        args = ["worktree", "add"]
        if _existing_branch(control, branch):
            args.extend([str(target), branch])
        else:
            args.extend(["-b", branch, str(target), info["head"]])
        _required(control, *args)
        created = True

    binding = bind_plan_worktree(str(control), plan, target)
    return {**binding, "created": created}
