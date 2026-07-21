"""Small Git primitives used by the Plan integration transaction."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List


def run_git(base: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(base), capture_output=True, text=True, timeout=60,
    )


def require_git(base: Path, *args: str) -> str:
    result = run_git(base, *args)
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or result.stdout.strip() or "git command failed")
    return result.stdout.strip()


def resolve_ref(base: Path, name: str) -> str:
    result = run_git(base, "rev-parse", f"{name}^{{commit}}")
    return result.stdout.strip() if result.returncode == 0 else ""


def is_ancestor(base: Path, older: str, newer: str) -> bool:
    return bool(older and newer) and run_git(
        base, "merge-base", "--is-ancestor", older, newer,
    ).returncode == 0


def git_operation(base: Path) -> str:
    git_dir = run_git(base, "rev-parse", "--git-dir")
    if git_dir.returncode != 0:
        return ""
    path = Path(git_dir.stdout.strip())
    if not path.is_absolute():
        path = base / path
    for marker, label in (
        ("MERGE_HEAD", "merge"),
        ("REBASE_HEAD", "rebase"),
        ("CHERRY_PICK_HEAD", "cherry-pick"),
        ("REVERT_HEAD", "revert"),
    ):
        if (path / marker).exists():
            return label
    return ""


def conflict_paths(output: str) -> List[str]:
    paths: List[str] = []
    for line in output.splitlines():
        text = line.strip()
        if "CONFLICT" not in text or " in " not in text:
            continue
        candidate = text.rsplit(" in ", 1)[1].strip()
        if candidate and candidate not in paths:
            paths.append(candidate)
    return paths
