"""Explicit tracked/local migration for AIWF governance files."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .governance_git import (
    LOCAL,
    VALID_MODES,
    _POLICY_PATH,
    _commit_env,
    _required,
    _require_checkpoint_ready,
    _run,
    _stage_paths,
    _staged_paths,
    governance_tracking_mode,
    pending_governance_paths,
)
from .worktree_context import resolve_control_root


_BLOCK_START = "# BEGIN AIWF GOVERNANCE"
_BLOCK_END = "# END AIWF GOVERNANCE"


def _managed_gitignore(mode: str) -> str:
    lines = [_BLOCK_START, "/.aiwf/runtime/"]
    if mode == LOCAL:
        lines.extend([
            "/.aiwf/**",
            "!/.aiwf/config/",
            "!/.aiwf/config/**",
        ])
    lines.append(_BLOCK_END)
    return "\n".join(lines)


def _write_managed_gitignore(control: Path, mode: str) -> None:
    path = control / ".gitignore"
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    start = current.find(_BLOCK_START)
    end = current.find(_BLOCK_END)
    if start >= 0 and end >= start:
        end += len(_BLOCK_END)
        current = (current[:start].rstrip() + "\n" + current[end:].lstrip()).strip()
    block = _managed_gitignore(mode)
    updated = current.rstrip() + ("\n\n" if current.strip() else "") + block + "\n"
    if updated != (path.read_text(encoding="utf-8") if path.exists() else ""):
        path.write_text(updated, encoding="utf-8")


def ensure_governance_gitignore(base_dir: str | Path) -> None:
    """Keep runtime local and apply the configured tracked/local layout."""
    control = resolve_control_root(base_dir)
    if _run(control, "rev-parse", "--git-dir").returncode != 0:
        return
    _write_managed_gitignore(control, governance_tracking_mode(control))


def set_governance_tracking(
    base_dir: str | Path,
    mode: str,
) -> Dict[str, Any]:
    from .state._common import _governance_state_lock

    with _governance_state_lock(str(base_dir)):
        return _set_governance_tracking_locked(base_dir, mode)


def _set_governance_tracking_locked(
    base_dir: str | Path,
    mode: str,
) -> Dict[str, Any]:
    if mode not in VALID_MODES:
        raise ValueError("governance tracking must be 'tracked' or 'local'")
    control = resolve_control_root(base_dir)
    from .task_ledger import active_tasks

    active = active_tasks(str(control))
    if active:
        raise ValueError(
            "finish or interrupt active Tasks before changing governance Git tracking: "
            + ", ".join(str(task.get("id") or "") for task in active[:8])
        )
    _require_checkpoint_ready(control)

    policy_path = control / _POLICY_PATH
    if not policy_path.exists():
        raise ValueError(f"missing {_POLICY_PATH}; run aiwf install first")
    try:
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"cannot read {_POLICY_PATH}: {exc}") from exc
    policy["governance_git_tracking"] = mode
    policy_path.write_text(
        json.dumps(policy, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_managed_gitignore(control, mode)

    if mode == LOCAL:
        remove = _run(control, "rm", "-r", "--cached", "--ignore-unmatch", "--", ".aiwf")
        if remove.returncode != 0:
            raise ValueError(remove.stderr.strip() or "cannot stop tracking .aiwf")
        _required(control, "add", "-f", "--", ".aiwf/config", ".gitignore")
        message = "chore(aiwf): keep governance local"
    else:
        _required(control, "add", "-A", "--", ".gitignore")
        _stage_paths(control, pending_governance_paths(control))
        message = "chore(aiwf): track governance"

    staged = _staged_paths(control)
    if not staged:
        return {"mode": mode, "committed": False, "commit": "", "paths": []}
    commit = _run(control, "commit", "-m", message, env=_commit_env(control))
    if commit.returncode != 0:
        raise ValueError(commit.stderr.strip() or commit.stdout.strip() or "tracking change failed")
    return {
        "mode": mode,
        "committed": True,
        "commit": _required(control, "rev-parse", "HEAD"),
        "paths": staged,
    }
