"""Local Git hygiene owned by AIWF installation, without repository policy guesses."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List

from .worktree_context import resolve_control_root


_BLOCK_START = "# BEGIN AIWF LOCAL HYGIENE"
_BLOCK_END = "# END AIWF LOCAL HYGIENE"
_LOCAL_RESIDUE = (".DS_Store", "Thumbs.db")


def _git(base: Path, *args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["git", *args], cwd=str(base), capture_output=True,
            text=True, encoding="utf-8", errors="surrogateescape", timeout=30,
        )
    except OSError as exc:
        return subprocess.CompletedProcess(
            ["git", *args], 127, stdout="", stderr=str(exc),
        )


def _git_repository(control: Path) -> bool:
    return _git(control, "rev-parse", "--git-dir").returncode == 0


def _replace_block(current: str, block: str) -> str:
    start = current.find(_BLOCK_START)
    end = current.find(_BLOCK_END)
    if start >= 0 and end >= start:
        end += len(_BLOCK_END)
        current = (current[:start].rstrip() + "\n" + current[end:].lstrip()).strip()
    return current.rstrip() + ("\n\n" if current.strip() else "") + block + "\n"


def ensure_local_git_excludes(base_dir: str | Path) -> bool:
    """Ignore host residue locally; never change shared project policy or the index."""
    control = resolve_control_root(base_dir)
    if not _git_repository(control):
        return False
    result = _git(control, "rev-parse", "--git-path", "info/exclude")
    if result.returncode != 0 or not result.stdout.strip():
        return False
    path = Path(result.stdout.strip())
    if not path.is_absolute():
        path = control / path
    path.parent.mkdir(parents=True, exist_ok=True)
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    block = "\n".join([_BLOCK_START, *_LOCAL_RESIDUE, _BLOCK_END])
    updated = _replace_block(current, block)
    if updated == current:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def inspect_git_hygiene(base_dir: str | Path) -> Dict[str, Any]:
    """Report Git readiness and tracked host residue without mutating the repository."""
    control = resolve_control_root(base_dir)
    repository = _git_repository(control)
    if not repository:
        return {"repository": False, "has_head": False, "tracked_residue": []}
    has_head = _git(control, "rev-parse", "--verify", "HEAD").returncode == 0
    listed = _git(control, "-c", "core.quotepath=false", "ls-files", "-z")
    tracked: List[str] = []
    if listed.returncode == 0:
        tracked = sorted(
            path for path in listed.stdout.split("\0")
            if path and Path(path).name in _LOCAL_RESIDUE
        )
    return {
        "repository": True,
        "has_head": has_head,
        "tracked_residue": tracked,
    }
