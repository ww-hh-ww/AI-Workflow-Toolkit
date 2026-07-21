"""Resolve the installed AIWF project root from nested working directories."""
from __future__ import annotations

from pathlib import Path
from typing import Union


PathLike = Union[str, Path]


def is_installed_aiwf_root(path: PathLike) -> bool:
    root = Path(path).expanduser().resolve()
    state = root / ".aiwf" / "state" / "state.json"
    integration = (
        (root / ".claude" / "settings.json").exists()
        or (root / ".reasonix" / "settings.json").exists()
        or (root / ".opencode" / "plugins" / "aiwf.js").exists()
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
