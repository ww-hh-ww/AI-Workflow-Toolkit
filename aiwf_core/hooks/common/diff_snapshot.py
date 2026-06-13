"""Machine-observed file change detection via git diff.

Returns changed files from git, never from model prose.
Filters AIWF internal paths and gitignored files to prevent false scope violations.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List, Optional, Set

# Paths that AIWF generates internally — must not trigger scope violations.
# These are filtered from changed_files before scope checking.
AIWF_INTERNAL_PATTERNS = [
    ".aiwf/",
    ".aiwf",       # bare directory name from git status
    ".claude/",
    ".claude",
    ".reasonix/",
    ".reasonix",
    "scripts/aiwf_",  # AIWF-generated scripts
    "CLAUDE.md",
    "REASONIX.md",
    "AGENTS.md",
]

# Directories fully owned by AIWF — files within are always internal.
# Git status shows these as directory entries when all contents are untracked.
AIWF_INTERNAL_DIRS = [
    ".aiwf",
    ".claude",
    ".reasonix",
]

BASELINE_FILE = ".aiwf/runtime/internal/baseline.json"


def is_internal_path(file_path: str) -> bool:
    """Check if a file path is an AIWF internal/generated file."""
    fp = file_path
    # Strip leading ./ prefix only
    if fp.startswith("./"):
        fp = fp[2:]
    # Strip trailing / from directory entries in git status
    fp = fp.rstrip("/")
    for pattern in AIWF_INTERNAL_PATTERNS:
        p = pattern.rstrip("/")
        if fp == p or fp.startswith(pattern):
            return True
    # Check against AIWF-owned directories
    for d in AIWF_INTERNAL_DIRS:
        if fp == d or fp.startswith(d + "/"):
            return True
    # Also check if fp is a parent directory entry for an AIWF dir
    # e.g., git status might show "scripts/" for untracked scripts dir
    # We don't blanket-filter scripts/ but we check individual files
    return False


def _gitignored_files(cwd: Path, files: List[str]) -> Set[str]:
    """Return the subset of files that are gitignored.

    Uses git check-ignore --stdin for batch checking.
    Falls back to empty set if git is unavailable.
    """
    if not files:
        return set()
    try:
        r = subprocess.run(
            ["git", "check-ignore", "--stdin", "-z"],
            input="\0".join(files),
            capture_output=True, text=True, cwd=str(cwd), timeout=15,
        )
        # git check-ignore with -z outputs matched paths null-terminated
        ignored = set(r.stdout.split("\0"))
        ignored.discard("")
        return ignored
    except Exception:
        return set()


def filter_internal(files: List[str], cwd: Optional[Path] = None) -> List[str]:
    """Remove AIWF internal paths and gitignored files from a list of file paths."""
    result = [f for f in files if not is_internal_path(f)]
    if cwd is not None and result:
        ignored = _gitignored_files(cwd, result)
        if ignored:
            result = [f for f in result if f not in ignored]
    return result


def git_changed_files(cwd: Path) -> Optional[List[str]]:
    """Get changed files from git diff --name-only. Returns None if no git repo."""
    try:
        r = subprocess.run(
            ["git", "diff", "--name-only"],
            capture_output=True, text=True, cwd=str(cwd), timeout=10,
        )
        if r.returncode != 0:
            return None
        files = [f.strip() for f in r.stdout.split("\n") if f.strip()]
        return filter_internal(files, cwd=cwd)
    except Exception:
        return None


def git_untracked_files(cwd: Path) -> Optional[List[str]]:
    """Get untracked files from git status. AIWF internal paths filtered."""
    try:
        r = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, cwd=str(cwd), timeout=10,
        )
        if r.returncode != 0:
            return None
        files = []
        for line in r.stdout.split("\n"):
            if not line.strip():
                continue
            status = line[:2]
            rest = line[3:].strip()
            if not rest:
                continue
            if "?" not in status and "A" not in status and "M" not in status:
                continue
            if " -> " in rest:
                rest = rest.split(" -> ")[-1]
            # If this is a directory entry (ends with /), expand it
            if rest.endswith("/"):
                dir_path = cwd / rest
                if dir_path.is_dir():
                    for f in dir_path.rglob("*"):
                        if f.is_file():
                            rel = str(f.relative_to(cwd))
                            files.append(rel)
                continue
            files.append(rest)
        return filter_internal(files, cwd=cwd)
    except Exception:
        return None


def detect_changed_files(cwd: Path) -> dict:
    """Detect changed project files using git. AIWF internal paths excluded.

    Returns dict with:
    - files: list of changed project file paths (filtered)
    - source: "git_diff", "git_status", or "unavailable"
    """
    files = git_changed_files(cwd)
    if files is not None:
        untracked = git_untracked_files(cwd)
        all_files = list(set(files + (untracked or [])))
        return {"files": sorted(all_files), "source": "git_diff"}

    untracked = git_untracked_files(cwd)
    if untracked is not None:
        return {"files": sorted(set(untracked)), "source": "git_status"}

    return {"files": [], "source": "unavailable"}


# ── baseline snapshot ──────────────────────────────────────────────────

def write_install_baseline(cwd: Path) -> Optional[str]:
    """After install, record the current git HEAD as a baseline ref.

    PostToolUse can diff against this to get only post-install changes.
    Returns the baseline ref string, or None if not in a git repo.
    """
    import json

    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, cwd=str(cwd), timeout=10,
        )
        if r.returncode != 0:
            # No commits yet — record current tree hash instead
            r2 = subprocess.run(
                ["git", "write-tree"],
                capture_output=True, text=True, cwd=str(cwd), timeout=10,
            )
            if r2.returncode != 0:
                return None
            baseline_ref = r2.stdout.strip()
            ref_type = "tree"
        else:
            baseline_ref = r.stdout.strip()
            ref_type = "commit"

        # Write baseline file inside .aiwf/
        baseline_path = cwd / BASELINE_FILE
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(json.dumps({
            "ref": baseline_ref,
            "type": ref_type,
            "source": "git",
            "filtered_patterns": AIWF_INTERNAL_PATTERNS,
        }, indent=2) + "\n", encoding="utf-8")

        return baseline_ref
    except Exception:
        return None


def baseline_diff_files(cwd: Path) -> Optional[List[str]]:
    """Get changed files since the install baseline.

    Uses git diff against baseline + untracked files.
    Returns None if baseline doesn't exist or git is unavailable.
    Returns filtered list (AIWF internals excluded).
    """
    import json

    baseline_path = cwd / BASELINE_FILE
    if not baseline_path.exists():
        return None

    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        baseline_ref = baseline.get("ref", "")
    except Exception:
        return None

    if not baseline_ref:
        return None

    try:
        r = subprocess.run(
            ["git", "diff", "--name-only", baseline_ref],
            capture_output=True, text=True, cwd=str(cwd), timeout=10,
        )
        tracked = []
        if r.returncode == 0:
            tracked = [f.strip() for f in r.stdout.split("\n") if f.strip()]

        # Also get untracked files (not in baseline)
        untracked = git_untracked_files(cwd) or []

        all_files = list(set(tracked + untracked))
        return filter_internal(all_files, cwd=cwd)
    except Exception:
        return None


def detect_changed_files_with_baseline(cwd: Path) -> dict:
    """Detect changed files using baseline diff if available.

    Falls back to normal detect_changed_files if no baseline.
    """
    baseline_files = baseline_diff_files(cwd)
    if baseline_files is not None:
        return {"files": sorted(set(baseline_files)), "source": "baseline_diff"}

    return detect_changed_files(cwd)
