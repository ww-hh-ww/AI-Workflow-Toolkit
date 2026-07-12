"""Shared utilities and constants for state operation modules."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, Dict, TypeVar

BLOCKING_REVIEW_RESULTS = {
    "needs_fix", "needs_more_testing", "evidence_insufficient",
    "scope_violation", "rejected",
}

T = TypeVar("T")


def _read(path: Path) -> Dict:
    try: return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except: return {}


def _write(path: Path, data: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _atomic_write(path: Path, data: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _locked_json_update(path: Path, default: Dict, mutator: Callable[[Dict], T]) -> T:
    """Update a JSON object under a sibling lock file.

    Evidence writes can come from several hook/subagent processes at nearly the
    same time. The lock covers read -> compute next ID -> append -> write so
    records are not overwritten by a concurrent writer.
    """
    import fcntl

    lock_path = path.with_name(f"{path.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        data = _read(path)
        if not data:
            data = dict(default)
        result = mutator(data)
        _atomic_write(path, data)
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        return result
