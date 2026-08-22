"""Resolve the installed AIWF project root from nested working directories."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Union


PathLike = Union[str, Path]

OPENCODE_PLUGIN_PATH = Path("scripts/aiwf_opencode_plugin.js")
LEGACY_OPENCODE_PLUGIN_PATH = Path(".opencode/plugins/aiwf.js")
INVOCATION_CWD_ENV = "AIWF_INVOKE_CWD"


def has_opencode_adapter(path: PathLike) -> bool:
    root = Path(path).expanduser().resolve()
    return (
        (root / OPENCODE_PLUGIN_PATH).exists()
        or (root / LEGACY_OPENCODE_PLUGIN_PATH).exists()
    )


def has_codex_adapter(path: PathLike) -> bool:
    root = Path(path).expanduser().resolve()
    return (
        (root / ".codex" / "hooks.json").exists()
        and (root / ".agents" / "skills" / "aiwf-planner" / "SKILL.md").exists()
    )


def in_codex_session() -> bool:
    """Return whether the command is running inside a native Codex session."""
    return bool(
        os.environ.get("CODEX_SESSION_ID")
        or os.environ.get("CODEX_THREAD_ID")
        or os.environ.get("CODEX_SHELL")
    )


def is_installed_aiwf_root(path: PathLike) -> bool:
    root = Path(path).expanduser().resolve()
    state = root / ".aiwf" / "state" / "state.json"
    integration = (
        (root / ".claude" / "settings.json").exists()
        or (root / ".reasonix" / "settings.json").exists()
        or has_codex_adapter(root)
        or has_opencode_adapter(root)
    )
    return state.exists() and integration


def resolve_aiwf_project_root(start: PathLike) -> Path:
    """Return the nearest complete AIWF installation at or above start."""
    current = Path(start).expanduser().resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if is_installed_aiwf_root(candidate):
            return candidate
    return current


def resolve_invocation_root(start: PathLike | None = None) -> Path:
    """Return the directory where the current AIWF command was invoked.

    The CLI may chdir to the control root before dispatching a command. Record
    operations still need the original worktree for ownership checks and
    relative evidence paths.
    """
    configured = os.environ.get(INVOCATION_CWD_ENV, "").strip()
    candidate = Path(configured) if configured else Path(start or Path.cwd())
    return candidate.expanduser().resolve()
