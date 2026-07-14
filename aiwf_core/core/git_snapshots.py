"""Immutable local Git snapshots for Executor and Tester handoffs."""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..hooks.common.diff_snapshot import filter_internal, parse_nul_paths


_INTERNAL_EXCLUDES = [
    ":(exclude).aiwf", ":(exclude).aiwf/**",
]


def _run(base: Path, *args: str, env: Optional[Dict[str, str]] = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(base), env=env, capture_output=True,
        text=True, timeout=30,
    )


def _required(base: Path, *args: str, env: Optional[Dict[str, str]] = None) -> str:
    result = _run(base, *args, env=env)
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or result.stdout.strip() or "git command failed")
    return result.stdout.strip()


def _snapshot_env(index_path: str) -> Dict[str, str]:
    env = os.environ.copy()
    env.update({
        "GIT_AUTHOR_NAME": "AIWF Snapshot",
        "GIT_AUTHOR_EMAIL": "aiwf-snapshot@local",
        "GIT_COMMITTER_NAME": "AIWF Snapshot",
        "GIT_COMMITTER_EMAIL": "aiwf-snapshot@local",
    })
    if index_path:
        env["GIT_INDEX_FILE"] = index_path
    return env


def _worktree_tree(base: Path, parent_ref: str) -> str:
    fd, index_path = tempfile.mkstemp(prefix="aiwf-index-")
    os.close(fd)
    os.unlink(index_path)
    env = _snapshot_env(index_path)
    try:
        _required(base, "read-tree", parent_ref, env=env)
        _required(base, "add", "-A", "--", ".", *_INTERNAL_EXCLUDES, env=env)
        return _required(base, "write-tree", env=env)
    finally:
        try:
            os.unlink(index_path)
        except OSError:
            pass


def _safe_ref_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip(".-") or "task"


def create_task_snapshot(
    base_dir: str, task_id: str, kind: str, parent_ref: str, summary: str = "",
) -> Dict[str, Any]:
    base = Path(base_dir)
    if not parent_ref:
        raise ValueError("snapshot parent ref is missing")
    _required(base, "rev-parse", f"{parent_ref}^{{commit}}")
    tree = _worktree_tree(base, parent_ref)
    prefix = f"refs/aiwf/tasks/{_safe_ref_part(task_id)}/{_safe_ref_part(kind)}/"
    existing = _required(base, "for-each-ref", "--format=%(refname)", prefix).splitlines()
    attempt = len([item for item in existing if item.strip()]) + 1
    message = f"aiwf {task_id} {kind} {attempt}"
    if summary.strip():
        message += f"\n\n{summary.strip()[:500]}"
    commit = _required(
        base, "commit-tree", tree, "-p", parent_ref, "-m", message,
        env=_snapshot_env(""),
    )
    ref = f"{prefix}{attempt:03d}"
    _required(base, "update-ref", ref, commit)
    return {
        "ref": commit,
        "named_ref": ref,
        "attempt": attempt,
        "parent_ref": parent_ref,
        "files": diff_files(base_dir, parent_ref, commit),
    }


def ref_tree(base_dir: str, ref: str) -> str:
    if not ref:
        return ""
    result = _run(Path(base_dir), "rev-parse", f"{ref}^{{tree}}")
    return result.stdout.strip() if result.returncode == 0 else ""


def worktree_matches_ref(base_dir: str, ref: str) -> bool:
    expected = ref_tree(base_dir, ref)
    return bool(expected) and _worktree_tree(Path(base_dir), ref) == expected


def tree_changes(base_dir: str, start_ref: str, end_ref: str) -> List[Dict[str, str]]:
    """Return path-level changes from one commit/tree to another."""
    result = _run(
        Path(base_dir), "diff", "--name-status", "-z", "--no-renames",
        start_ref, end_ref,
    )
    if result.returncode != 0:
        return []
    tokens = parse_nul_paths(result.stdout)
    changes: List[Dict[str, str]] = []
    for index in range(0, len(tokens) - 1, 2):
        status, path = tokens[index], tokens[index + 1]
        if path.startswith(".aiwf/") or path == ".aiwf":
            continue
        changes.append({"status": status[:1], "path": path})
    return changes


def worktree_changes_from_ref(base_dir: str, ref: str) -> List[Dict[str, str]]:
    """Describe how the current project worktree differs from an immutable ref."""
    worktree_tree = _worktree_tree(Path(base_dir), ref)
    return tree_changes(base_dir, ref, worktree_tree)


def format_tree_changes(changes: List[Dict[str, str]], limit: int = 8) -> str:
    labels = {"A": "extra", "D": "missing", "M": "modified", "T": "modified"}
    items = [
        f"{labels.get(item.get('status', ''), 'changed')}: {item.get('path', '')}"
        for item in changes[:limit]
    ]
    if len(changes) > limit:
        items.append(f"and {len(changes) - limit} more")
    return "; ".join(items)


def diff_files(base_dir: str, start_ref: str, end_ref: str) -> List[str]:
    result = _run(
        Path(base_dir), "diff", "--name-only", "-z", "--no-renames",
        start_ref, end_ref,
    )
    if result.returncode != 0:
        return []
    return sorted(filter_internal(
        parse_nul_paths(result.stdout),
        cwd=Path(base_dir),
    ))
