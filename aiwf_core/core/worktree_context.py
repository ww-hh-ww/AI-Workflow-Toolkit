"""Resolve the shared AIWF control root and the current Git worktree."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Union

from .project_root import resolve_aiwf_project_root


PathLike = Union[str, Path]


def _git(start: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(start), capture_output=True, text=True, timeout=15,
    )


def resolve_worktree_root(start: PathLike) -> Path:
    """Return the Git worktree containing start, or the nearest project root."""
    current = Path(start).expanduser().resolve()
    if current.is_file():
        current = current.parent
    result = _git(current, "rev-parse", "--show-toplevel")
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip()).resolve()
    return resolve_aiwf_project_root(current)


def resolve_control_root(start: PathLike) -> Path:
    """Return the primary worktree whose .aiwf directory owns shared state."""
    configured = os.environ.get("AIWF_CONTROL_ROOT", "").strip()
    if configured:
        candidate = Path(configured).expanduser().resolve()
        if (candidate / ".aiwf" / "state" / "tasks.json").exists():
            return candidate

    worktree = resolve_worktree_root(start)
    common = _git(worktree, "rev-parse", "--git-common-dir")
    if common.returncode == 0 and common.stdout.strip():
        common_dir = Path(common.stdout.strip())
        if not common_dir.is_absolute():
            common_dir = (worktree / common_dir).resolve()
        primary = common_dir.parent
        if (primary / ".aiwf" / "state" / "tasks.json").exists():
            return primary.resolve()

    return resolve_aiwf_project_root(worktree)


def worktree_info(start: PathLike) -> Dict[str, Any]:
    """Describe the current worktree without mutating Git or AIWF state."""
    worktree = resolve_worktree_root(start)
    control = resolve_control_root(worktree)
    branch = _git(worktree, "branch", "--show-current")
    head = _git(worktree, "rev-parse", "HEAD")
    return {
        "path": str(worktree),
        "control_root": str(control),
        "branch": branch.stdout.strip() if branch.returncode == 0 else "",
        "head": head.stdout.strip() if head.returncode == 0 else "",
        "is_primary": worktree == control,
    }


def same_path(left: PathLike, right: PathLike) -> bool:
    return Path(left).expanduser().resolve() == Path(right).expanduser().resolve()
