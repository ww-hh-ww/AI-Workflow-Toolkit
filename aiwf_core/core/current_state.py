"""Freshness checks for .aiwf state files."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List


SOURCE_FILES = [
    "state/state.json",
    "state/goal.json",
    "artifacts/evidence/records.json",
    "artifacts/quality/testing.json",
    "artifacts/quality/review.json",
    "state/fix-loop.json",
    "state/contexts.json",
    "runtime/history/task-history.json",
    "runtime/history/task-ledger.json",
]

def current_state_freshness(base_dir: str) -> Dict[str, object]:
    """Check whether AIWF state files are mutually consistent. Reads .json directly."""
    root = Path(base_dir)
    aiwf = root / ".aiwf"

    json_sources = [f for f in SOURCE_FILES if f.endswith(".json")]
    missing = [f for f in json_sources if not (aiwf / f).exists()]
    if missing:
        return {"status": "incomplete", "missing": missing, "exists": False}

    try:
        mtimes = [(f, (aiwf / f).stat().st_mtime) for f in json_sources]
    except OSError:
        return {"status": "unreadable", "stale_sources": [], "exists": True}

    max_mtime = max(mt for _, mt in mtimes)
    stale_sources = [f for f, mt in mtimes if mt < max_mtime - 60]

    return {
        "status": "stale" if stale_sources else "fresh",
        "stale_sources": stale_sources,
        "exists": True,
    }


