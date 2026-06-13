"""Pre/post operation file snapshot for true per-operation evidence.

PreToolUse takes a snapshot of project file hashes.
PostToolUse diffs against the snapshot to detect exactly what changed.
Already-dirty files modified again are correctly detected (hash changed).
No-op operations produce empty changed_files.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from .diff_snapshot import is_internal_path, AIWF_INTERNAL_DIRS, AIWF_INTERNAL_PATTERNS

SNAPSHOT_PATH = ".aiwf/runtime/internal/pre-tool-snapshot.json"

# Directories to exclude from snapshot scanning entirely
SNAPSHOT_EXCLUDE_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    ".aiwf", ".claude", ".reasonix", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "htmlcov", "dist", "build", "*.egg-info",
}



def _detect_project_excludes(root: Path) -> set:
    """Auto-detect project-specific build/test artifact directories."""
    known_patterns = {
        "dist", "build", "target", "out", ".next", ".nuxt", ".output",
        "coverage", ".nyc_output", ".jest-cache", ".turbo",
        "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
        ".tox", ".eggs", "*.egg-info", "htmlcov",
        ".terraform", ".serverless",
    }
    detected = set()
    try:
        for item in root.iterdir():
            if item.is_dir() and item.name in known_patterns:
                detected.add(item.name)
    except Exception:
        pass
    return detected


def _file_hash(path: Path) -> str:
    """Quick MD5 hash of a file. Returns empty string on error."""
    try:
        h = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""


def _file_stat(path: Path) -> Dict[str, Any]:
    """Get mtime and size for quick change detection."""
    try:
        st = path.stat()
        return {"mtime": st.st_mtime, "size": st.st_size}
    except Exception:
        return {"mtime": 0, "size": 0}


def _should_scan(path: Path, root: Path, detected_excludes: set = None) -> bool:
    """Check if a path should be included in project file scanning."""
    try:
        rel = str(path.relative_to(root))
    except ValueError:
        return False

    # Exclude AIWF internal paths
    if is_internal_path(rel):
        return False

    # Exclude known non-project directories + auto-detected
    parts = rel.replace("\\", "/").split("/")
    all_excludes = SNAPSHOT_EXCLUDE_DIRS | (detected_excludes or set())
    for part in parts:
        if part in SNAPSHOT_EXCLUDE_DIRS:
            return False

    return True


def _scan_project_files(root: Path) -> Dict[str, Dict[str, Any]]:
    """Scan all project files and return {rel_path: {hash, mtime, size}}."""
    result = {}
    try:
        for dirpath, dirnames, filenames in os.walk(str(root)):
            # Filter out excluded directories in-place
            dirnames[:] = [
                d for d in dirnames
                if d not in SNAPSHOT_EXCLUDE_DIRS
                and not is_internal_path(str(Path(dirpath).relative_to(root) / d) if dirpath != str(root) else d)
            ]

            for fname in filenames:
                fpath = Path(dirpath) / fname
                rel = str(fpath.relative_to(root))

                if is_internal_path(rel):
                    continue

                stat = _file_stat(fpath)
                # Only hash small/medium files (< 1MB for performance)
                if stat["size"] < 1_000_000:
                    fhash = _file_hash(fpath)
                else:
                    fhash = f"large:{stat['mtime']}:{stat['size']}"

                result[rel] = {"hash": fhash, "mtime": stat["mtime"], "size": stat["size"]}
    except Exception:
        pass

    return result


def take_snapshot(cwd: Path, tool_name: str = "", tool_input: Optional[Dict] = None) -> Dict[str, Any]:
    """Take a pre-tool snapshot of project files. Stores to .aiwf/runtime/internal/.

    Returns the snapshot dict.
    """
    files = _scan_project_files(cwd)
    snapshot = {
        "timestamp": _now(),
        "tool_name": tool_name,
        "tool_input": tool_input or {},
        "file_count": len(files),
        "files": files,
    }

    # Write to disk for PostToolUse to read
    snap_path = cwd / SNAPSHOT_PATH
    snap_path.parent.mkdir(parents=True, exist_ok=True)
    snap_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return snapshot


def read_snapshot(cwd: Path) -> Optional[Dict[str, Any]]:
    """Read the most recent pre-tool snapshot. Returns None if not found."""
    snap_path = cwd / SNAPSHOT_PATH
    if not snap_path.exists():
        return None
    try:
        return json.loads(snap_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def diff_snapshot(cwd: Path) -> Dict[str, Any]:
    """Compare current project files against the pre-tool snapshot.

    Returns dict with:
      - changed_files: list of files created, modified, or deleted
      - new_files: files not in snapshot
      - modified_files: files with changed hash/mtime/size
      - deleted_files: files in snapshot but gone from disk
      - source: "pre_post_snapshot" or "snapshot_unavailable"
      - attribution: "strong" or "weak"
    """
    previous = read_snapshot(cwd)
    if not previous:
        return {
            "changed_files": [],
            "new_files": [],
            "modified_files": [],
            "deleted_files": [],
            "source": "snapshot_unavailable",
            "attribution": "weak",
        }

    prev_files = previous.get("files", {})
    current_files = _scan_project_files(cwd)

    new_files = []
    modified_files = []
    deleted_files = []

    # Check for new and modified files
    for rel, curr_info in current_files.items():
        if rel not in prev_files:
            new_files.append(rel)
        else:
            prev_info = prev_files[rel]
            if (curr_info["hash"] != prev_info["hash"] or
                curr_info["mtime"] != prev_info["mtime"] or
                curr_info["size"] != prev_info["size"]):
                modified_files.append(rel)

    # Check for deleted files
    for rel in prev_files:
        if rel not in current_files:
            deleted_files.append(rel)

    changed = sorted(set(new_files + modified_files + deleted_files))

    return {
        "changed_files": changed,
        "new_files": sorted(new_files),
        "modified_files": sorted(modified_files),
        "deleted_files": sorted(deleted_files),
        "source": "pre_post_snapshot",
        "attribution": "strong",
    }


def clear_snapshot(cwd: Path) -> None:
    """Remove the pre-tool snapshot after use."""
    snap_path = cwd / SNAPSHOT_PATH
    if snap_path.exists():
        try:
            snap_path.unlink()
        except Exception:
            pass


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
