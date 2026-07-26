"""Small Git primitives used by the Plan integration transaction."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple


def run_git(
    base: Path,
    *args: str,
    input_text: Optional[str] = None,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(base), capture_output=True, text=True,
        input=input_text, timeout=60,
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


def is_governance_path(path: str) -> bool:
    normalized = path.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized == ".aiwf" or normalized.startswith(".aiwf/")


def unmerged_paths(base: Path) -> List[str]:
    result = run_git(base, "diff", "--name-only", "--diff-filter=U", "-z")
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or "cannot inspect merge conflicts")
    return [item for item in result.stdout.split("\0") if item]


def resolve_governance_from_ref(base: Path, source_ref: str) -> None:
    """Resolve merge-only .aiwf conflicts from the canonical base commit."""
    unresolved = unmerged_paths(base)
    if not unresolved or any(not is_governance_path(path) for path in unresolved):
        raise ValueError("merge contains unresolved project conflicts")
    restored = run_git(
        base, "restore", f"--source={source_ref}", "--staged", "--worktree", "--", ".aiwf",
    )
    if restored.returncode != 0:
        raise ValueError(
            restored.stderr.strip() or restored.stdout.strip()
            or "cannot restore canonical governance state"
        )
    if unmerged_paths(base):
        raise ValueError("governance conflicts remain after canonical restore")


def integration_tree(base: Path, candidate_ref: str, base_ref: str) -> str:
    """Return candidate project content with canonical base governance state."""
    candidate = require_git(base, "ls-tree", "-z", f"{candidate_ref}^{{tree}}")
    canonical = run_git(base, "ls-tree", "-z", f"{base_ref}^{{tree}}", "--", ".aiwf")
    if canonical.returncode != 0:
        raise ValueError(canonical.stderr.strip() or "cannot read canonical AIWF tree")

    entries = [
        entry for entry in candidate.split("\0")
        if entry and not entry.endswith("\t.aiwf")
    ]
    entries.extend(entry for entry in canonical.stdout.split("\0") if entry)
    tree = run_git(base, "mktree", "-z", input_text="\0".join(entries) + "\0")
    if tree.returncode != 0:
        raise ValueError(tree.stderr.strip() or tree.stdout.strip() or "cannot build integration tree")
    return tree.stdout.strip()


def canonical_candidate(
    base: Path,
    candidate_ref: str,
    base_ref: str,
    plan_id: str,
) -> Tuple[str, str]:
    """Create an immutable candidate that cannot carry branch-local .aiwf state."""
    tree = integration_tree(base, candidate_ref, base_ref)
    current_tree = require_git(base, "rev-parse", f"{candidate_ref}^{{tree}}")
    if tree == current_tree:
        return candidate_ref, tree

    commit = require_git(
        base, "commit-tree", tree, "-p", candidate_ref,
        "-m", f"AIWF integration candidate for {plan_id}",
    )
    safe_id = re.sub(r"[^A-Za-z0-9._-]+", "-", plan_id).strip(".-") or "plan"
    require_git(base, "update-ref", f"refs/aiwf/plans/{safe_id}/candidate", commit)
    return commit, tree
