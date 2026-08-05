"""Git tracking and compact checkpoints for the shared AIWF governance layer."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from .worktree_context import resolve_control_root


TRACKED = "tracked"
LOCAL = "local"
VALID_MODES = {TRACKED, LOCAL}
_POLICY_PATH = ".aiwf/config/write-policy.json"


def _run(base: Path, *args: str, env: Dict[str, str] | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["git", *args], cwd=str(base), env=env, capture_output=True,
            text=True, encoding="utf-8", errors="surrogateescape", timeout=30,
        )
    except OSError as exc:
        return subprocess.CompletedProcess(
            ["git", *args], 127, stdout="", stderr=str(exc),
        )


def _required(base: Path, *args: str, env: Dict[str, str] | None = None) -> str:
    result = _run(base, *args, env=env)
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or result.stdout.strip() or "git command failed")
    return result.stdout.strip()


def governance_tracking_mode(base_dir: str | Path) -> str:
    control = resolve_control_root(base_dir)
    path = control / _POLICY_PATH
    try:
        value = str(json.loads(path.read_text(encoding="utf-8")).get(
            "governance_git_tracking", TRACKED,
        ))
    except Exception:
        value = TRACKED
    return value if value in VALID_MODES else TRACKED


def _git_operation(base: Path) -> str:
    git_dir_raw = _required(base, "rev-parse", "--git-dir")
    git_dir = Path(git_dir_raw)
    if not git_dir.is_absolute():
        git_dir = base / git_dir
    for marker, label in (
        ("MERGE_HEAD", "merge"),
        ("CHERRY_PICK_HEAD", "cherry-pick"),
        ("REVERT_HEAD", "revert"),
        ("rebase-merge", "rebase"),
        ("rebase-apply", "rebase"),
    ):
        if (git_dir / marker).exists():
            return label
    return ""


def _status_paths(base: Path, *pathspecs: str) -> List[str]:
    result = _run(
        base, "-c", "core.quotepath=false", "status", "--porcelain=v1", "-z",
        "--untracked-files=all", "--", *pathspecs,
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
            index += 1
    return paths


def pending_governance_paths(base_dir: str | Path) -> List[str]:
    control = resolve_control_root(base_dir)
    paths = _status_paths(control, ".aiwf")
    return sorted({
        path for path in paths
        if path != ".aiwf/runtime" and not path.startswith(".aiwf/runtime/")
    })


def _staged_paths(base: Path) -> List[str]:
    result = _run(base, "diff", "--cached", "--name-only", "-z")
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or "cannot inspect the Git index")
    return [path for path in result.stdout.split("\0") if path]


def _commit_env(base: Path) -> Dict[str, str]:
    env = os.environ.copy()
    name = _run(base, "config", "--get", "user.name").stdout.strip()
    email = _run(base, "config", "--get", "user.email").stdout.strip()
    if not name:
        env.setdefault("GIT_AUTHOR_NAME", "AIWF Governance")
        env.setdefault("GIT_COMMITTER_NAME", "AIWF Governance")
    if not email:
        env.setdefault("GIT_AUTHOR_EMAIL", "aiwf-governance@local")
        env.setdefault("GIT_COMMITTER_EMAIL", "aiwf-governance@local")
    return env


def _require_checkpoint_ready(
    control: Path,
    *,
    allow_staged_governance: bool = False,
) -> None:
    if _run(control, "rev-parse", "--verify", "HEAD").returncode != 0:
        raise ValueError("governance checkpoint requires an initial Git commit")
    if _git_operation(control):
        raise ValueError("finish the current Git operation before checkpointing governance")
    staged = _staged_paths(control)
    stable_governance = all(
        (path == ".aiwf" or path.startswith(".aiwf/"))
        and path != ".aiwf/runtime"
        and not path.startswith(".aiwf/runtime/")
        for path in staged
    )
    if staged and not (allow_staged_governance and stable_governance):
        raise ValueError(
            "governance checkpoint will not disturb an existing Git index; "
            "finish or unstage these files first: " + ", ".join(staged[:8])
        )


def _stage_paths(control: Path, paths: List[str]) -> None:
    for index in range(0, len(paths), 100):
        batch = paths[index:index + 100]
        if batch:
            _required(control, "add", "-A", "--", *batch)


def checkpoint_governance(
    base_dir: str | Path,
    reason: str = "",
) -> Dict[str, Any]:
    from .state._common import _governance_state_lock

    with _governance_state_lock(str(base_dir)):
        return _checkpoint_governance_locked(base_dir, reason=reason)


def _checkpoint_governance_locked(
    base_dir: str | Path,
    reason: str = "",
) -> Dict[str, Any]:
    """Commit pending stable .aiwf files without staging project changes."""
    control = resolve_control_root(base_dir)
    mode = governance_tracking_mode(control)
    pending = pending_governance_paths(control)
    if mode == LOCAL:
        return {
            "mode": mode,
            "committed": False,
            "commit": "",
            "paths": pending,
        }
    if not pending:
        return {
            "mode": mode,
            "committed": False,
            "commit": "",
            "paths": [],
        }

    _require_checkpoint_ready(control, allow_staged_governance=True)
    _stage_paths(control, pending)
    staged = [
        path for path in _staged_paths(control)
        if path == ".aiwf" or path.startswith(".aiwf/")
    ]
    if not staged:
        return {
            "mode": mode,
            "committed": False,
            "commit": "",
            "paths": pending,
        }

    message = "chore(aiwf): checkpoint governance"
    if reason.strip():
        message += f"\n\n{reason.strip()[:240]}"
    commit = _run(control, "commit", "-m", message, env=_commit_env(control))
    if commit.returncode != 0:
        _run(control, "reset", "-q", "HEAD", "--", ".aiwf")
        raise ValueError(commit.stderr.strip() or commit.stdout.strip() or "governance commit failed")
    return {
        "mode": mode,
        "committed": True,
        "commit": _required(control, "rev-parse", "HEAD"),
        "paths": staged,
    }


def ensure_governance_gitignore(base_dir: str | Path) -> None:
    from .governance_tracking import ensure_governance_gitignore as ensure

    ensure(base_dir)


def set_governance_tracking(
    base_dir: str | Path,
    mode: str,
) -> Dict[str, Any]:
    from .governance_tracking import set_governance_tracking as set_tracking

    return set_tracking(base_dir, mode)
