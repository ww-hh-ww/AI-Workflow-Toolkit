"""Soft environment and worktree audit for Plan integration."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

from .git_workflow import changed_project_files, repository_info
from .plan_integration_git import git_operation, run_git


_SKIP_EMPTY = {
    ".git", ".aiwf", ".claude", ".opencode", ".reasonix",
    "node_modules", "target", "build", "dist", "coverage", "vendor",
    ".venv", "venv", "__pycache__", ".cache",
}


def _status_paths(root: Path, prefix: str) -> List[str]:
    result = run_git(
        root, "-c", "core.quotepath=false", "status", "--porcelain=v1", "-z",
        "--untracked-files=all",
    )
    if result.returncode != 0:
        return []
    found: List[str] = []
    entries = result.stdout.split("\0")
    index = 0
    while index < len(entries):
        line = entries[index]
        index += 1
        if len(line) < 4:
            continue
        if line[:2] == prefix:
            path = line[3:]
            if path != ".aiwf" and not path.startswith(".aiwf/"):
                found.append(path)
        if "R" in line[:2] or "C" in line[:2]:
            index += 1
    return sorted(dict.fromkeys(found))


def _ignored_samples(root: Path, limit: int = 24) -> Dict[str, Any]:
    result = run_git(
        root, "-c", "core.quotepath=false", "status", "--ignored",
        "--porcelain=v1", "-z", "--untracked-files=normal",
    )
    if result.returncode != 0:
        return {"paths": [], "truncated": False}
    paths = []
    for line in result.stdout.split("\0"):
        if len(line) >= 4 and line[:2] == "!!":
            path = line[3:]
            if path != ".aiwf/" and not path.startswith(".aiwf/"):
                paths.append(path)
    unique = list(dict.fromkeys(paths))
    return {"paths": unique[:limit], "truncated": len(unique) > limit}


def _empty_directories(root: Path, limit: int = 24) -> List[str]:
    found: List[str] = []
    visited = 0
    for current, dirs, files in os.walk(root):
        visited += 1
        if visited > 4000:
            break
        relative = Path(current).relative_to(root)
        if len(relative.parts) >= 4:
            dirs[:] = []
            continue
        dirs[:] = [name for name in dirs if name not in _SKIP_EMPTY]
        if relative.parts and not dirs and not files:
            found.append(relative.as_posix())
            if len(found) >= limit:
                break
    return found


def audit_repository(root: Path) -> Dict[str, Any]:
    ignored = _ignored_samples(root)
    return {
        "path": str(root),
        "branch": repository_info(str(root)).get("branch", ""),
        "changes": changed_project_files(str(root)),
        "untracked": _status_paths(root, "??"),
        "ignored": ignored["paths"],
        "ignored_truncated": ignored["truncated"],
        "empty_directories": _empty_directories(root),
        "git_operation": git_operation(root),
    }


def integration_audit(control: Path, worktree: Path) -> Dict[str, Any]:
    base = audit_repository(control)
    plan = audit_repository(worktree)
    blocking = []
    for label, report in (("base", base), ("Plan", plan)):
        if report["changes"]:
            blocking.append(
                f"{label} worktree has project changes: "
                + ", ".join(report["changes"][:8])
            )
        if report["git_operation"]:
            blocking.append(
                f"{label} worktree has unfinished Git {report['git_operation']}"
            )
    return {
        "base": base,
        "plan": plan,
        "blocking": blocking,
        "clean_for_candidate": not blocking,
    }


def audit_lines(audit: Dict[str, Any]) -> List[str]:
    """Render concise facts for Planner judgment, never automatic disposition."""
    lines: List[str] = []
    for key, label in (("base", "Base"), ("plan", "Plan")):
        report = audit.get(key, {}) or {}
        if report.get("git_operation"):
            lines.append(f"{label} Git operation: {report['git_operation']}")
        if report.get("changes"):
            lines.append(
                f"{label} changes: " + ", ".join(report["changes"][:8])
            )
        if report.get("ignored"):
            suffix = " ..." if report.get("ignored_truncated") else ""
            lines.append(
                f"{label} ignored samples: "
                + ", ".join(report["ignored"][:8]) + suffix
            )
        if report.get("empty_directories"):
            lines.append(
                f"{label} empty directories: "
                + ", ".join(report["empty_directories"][:8])
            )
    if audit.get("head_changes_since_task"):
        lines.append(
            "Plan commits since the last governed Task: "
            + ", ".join(audit["head_changes_since_task"][:8])
        )
    return lines
