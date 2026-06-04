"""Small project-local IO helpers for the embedded AIWF mainline."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def project_root() -> Path:
    return Path.cwd().resolve()


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(project_root()))
    except Exception:
        return str(path)


def read_json(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    if not path.exists():
        return default
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else default
    except Exception:
        return default


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

