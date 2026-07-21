"""Shared utilities and constants for state operation modules."""
from __future__ import annotations

import json
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Dict, Optional, TypeVar

from ...platform.file_lock import locked_file

BLOCKING_REVIEW_RESULTS = {
    "needs_fix", "needs_more_testing", "evidence_insufficient",
    "scope_violation", "rejected",
}

T = TypeVar("T")


class StateFileError(ValueError):
    """An AIWF state file exists but cannot be trusted."""


@contextmanager
def _exclusive_operation_lock(base_dir: str, name: str, timeout: float = 5.0):
    """Cross-platform short lock for one multi-file state transition."""
    lock_path = Path(base_dir) / ".aiwf" / "runtime" / "internal" / f"{name}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    fd = None
    while fd is None:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                if time.time() - lock_path.stat().st_mtime > 120.0:
                    lock_path.unlink()
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() >= deadline:
                raise TimeoutError(f"AIWF operation '{name}' is already running")
            time.sleep(0.02)
    try:
        yield
    finally:
        os.close(fd)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def _read_json(path: Path, default: Optional[Dict] = None) -> Dict:
    if not path.exists():
        return default if default is not None else {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StateFileError(f"invalid AIWF state file '{path}': {exc}") from exc
    if not isinstance(data, dict):
        raise StateFileError(f"invalid AIWF state file '{path}': root must be a JSON object")
    return data


def _read(path: Path) -> Dict:
    return _read_json(path)


def _write(path: Path, data: Dict) -> None:
    _atomic_write(path, data)


def _atomic_write(path: Path, data: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            tmp.write(payload)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def _locked_json_update(path: Path, default: Dict, mutator: Callable[[Dict], T]) -> T:
    """Update a JSON object under a sibling lock file.

    Evidence writes can come from several hook/subagent processes at nearly the
    same time. The lock covers read -> compute next ID -> append -> write so
    records are not overwritten by a concurrent writer.
    """
    lock_path = path.with_name(f"{path.name}.lock")
    with locked_file(lock_path):
        data = _read(path)
        if not data:
            data = dict(default)
        result = mutator(data)
        _atomic_write(path, data)
        return result
