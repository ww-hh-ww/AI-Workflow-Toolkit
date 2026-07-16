"""Human-controlled temporary AI project writes."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Union

from .worktree_context import resolve_control_root


PathLike = Union[str, Path]
MARKER = ".aiwf/runtime/internal/temporary-ai-writes.json"


def marker_path(base_dir: PathLike) -> Path:
    base = Path(base_dir).expanduser()
    try:
        control = resolve_control_root(base)
    except OSError:
        control = base.resolve()
    return control / MARKER


def temporary_ai_writes_enabled(base_dir: PathLike) -> bool:
    path = marker_path(base_dir)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return isinstance(value, dict) and value.get("enabled") is True


def enable_temporary_ai_writes(base_dir: PathLike) -> None:
    path = marker_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"enabled": true}\n', encoding="utf-8")


def disable_temporary_ai_writes(base_dir: PathLike) -> None:
    marker_path(base_dir).unlink(missing_ok=True)
