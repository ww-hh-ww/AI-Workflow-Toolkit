"""Backend-neutral scope policy engine.

Checks whether a file path is within an active context's allowed_write
or forbidden_write boundaries. No Claude-specific logic.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .event_model import ScopeResult


def check_scope(
    file_path: str,
    active_context: Optional[Dict] = None,
    state: Optional[Dict] = None,
    project_root: str = "",
) -> ScopeResult:
    """Check whether writing to file_path is allowed under the active context.

    Args:
        file_path: The path being written to (absolute or relative).
        active_context: The active context dict from contexts.json.
        state: The current state dict from state.json.
        project_root: Project root for normalizing absolute paths to relative.

    Returns:
        ScopeResult with allowed=True if the write is permitted.
    """
    # Normalize path: strip ./ prefix and convert absolute to relative
    normalized = _normalize_path(file_path, project_root)

    # Governance files: always allow writes to the 7 MVP .aiwf state files.
    # Planner and skills must be able to update AIWF state without self-locking.
    if _is_governance_file(normalized):
        return ScopeResult(
            file_path=normalized, allowed=True,
            reason="governance file — always allowed",
        )

    if not active_context:
        active_context = {}

    # V2: project write permissions are decided by scope_checker.py.
    # This function only handles governance bypass and forbidden_write.
    # Plan.allowed_write is no longer a gate — the execution contract is Task.md.
    forbidden_write: List[str] = active_context.get("forbidden_write", []) or [] if active_context else []
    ctx_id = active_context.get("id", "") if active_context else ""

    # Check forbidden write patterns from Task.md
    for pattern in forbidden_write:
        p = str(pattern).strip()
        if not p:
            continue
        if _matches(normalized, p):
            return ScopeResult(
                allowed=False,
                file_path=normalized,
                active_context_id=ctx_id,
                forbidden_write=forbidden_write,
                reason=f"'{normalized}' matches Forbidden Write pattern '{p}' from active Task.md",
            )

    # Governance files always allowed; project files allowed (checked by scope_checker.py)
    return ScopeResult(file_path=normalized, allowed=True, reason="allowed")


def check_changed_files_scope(
    changed_files: List[str],
    active_context: Optional[Dict] = None,
) -> List[ScopeResult]:
    """Check a batch of changed files against active scope. Returns violations."""
    violations: List[ScopeResult] = []
    for f in changed_files:
        result = check_scope(f, active_context)
        if not result.allowed:
            violations.append(result)
    return violations


DANGEROUS_BASH_PATTERNS: List[Dict] = [
    # Pattern -> (decision, reason)
    {"pattern": "sudo ", "decision": "deny", "reason": "sudo execution is dangerous"},
    {"pattern": "rm -rf", "decision": "deny", "reason": "rm -rf is destructive"},
    {"pattern": "rm -r ", "decision": "deny", "reason": "recursive rm is destructive"},
    {"pattern": "git reset --hard", "decision": "deny", "reason": "git reset --hard discards work"},
    {"pattern": "git clean -f", "decision": "deny", "reason": "git clean -f deletes untracked files"},
    {"pattern": "git checkout -- ", "decision": "deny", "reason": "git checkout -- discards changes"},
    {"pattern": "npm publish", "decision": "deny", "reason": "npm publish pushes to registry"},
    {"pattern": "git push", "decision": "ask", "reason": "git push modifies remote"},
    {"pattern": "chmod -R 777", "decision": "deny", "reason": "chmod -R 777 is insecure"},
    {"pattern": "curl ", "decision": "ask", "reason": "curling to shell is risky"},
    {"pattern": "wget ", "decision": "ask", "reason": "wget to shell is risky"},
    {"pattern": "sed -i", "decision": "ask", "reason": "sed -i modifies files in place"},
    {"pattern": "perl -pi", "decision": "ask", "reason": "perl -pi modifies files in place"},
    {"pattern": "> /dev/", "decision": "deny", "reason": "writing to /dev/ is risky"},
    {"pattern": "mkfs.", "decision": "deny", "reason": "mkfs is destructive"},
    {"pattern": "dd if=", "decision": "deny", "reason": "dd can overwrite disks"},
    {"pattern": ":(){ :|:& };:", "decision": "deny", "reason": "fork bomb"},
    {"pattern": "chown -R", "decision": "deny", "reason": "recursive chown is dangerous"},
]


def check_bash_command(command: str) -> Dict:
    """Check a Bash command for dangerous patterns and mechanical truth bypasses.

    Returns dict with keys: allowed (bool), decision (str), matched_pattern (str), reason (str).
    """
    # ── P0: mechanical truth path guard ──
    # Paths whose files must change through aiwf CLI commands, never through
    # arbitrary Bash. Mirrors the Write Guard's protected_truth set.
    # Using directory prefixes catches naive bypasses; it is not a security
    # boundary — the real boundary is constitutional compliance.
    _MECHANICAL_TRUTH_DIRS = [
        ".aiwf/state/",
        ".aiwf/records/",
    ]
    _MECHANICAL_TRUTH_FILES = [
        ".aiwf/state/tasks.json",
    ]
    for prefix in _MECHANICAL_TRUTH_DIRS:
        if prefix in command:
            return {
                "allowed": False,
                "decision": "deny",
                "command": command[:200],
                "matched_pattern": prefix,
                "reason": (
                    f"Bash command references '{prefix}' — files under this path are "
                    "mechanical truth and must be changed through aiwf CLI commands. "
                    "Use Read tool to inspect them; use the matching aiwf state/task/goal-tree/plan "
                    "command to modify them."
                ),
            }
    for path in _MECHANICAL_TRUTH_FILES:
        if path in command:
            return {
                "allowed": False,
                "decision": "deny",
                "command": command[:200],
                "matched_pattern": path,
                "reason": (
                    f"Bash command references '{path}' — this file is mechanical truth "
                    "and must be changed through aiwf CLI commands. "
                    "Use aiwf task ... or aiwf state ... to modify it."
                ),
            }

    cmd_lower = command.lower()
    for entry in DANGEROUS_BASH_PATTERNS:
        if entry["pattern"].lower() in cmd_lower:
            return {
                "allowed": entry["decision"] != "deny",
                "decision": entry["decision"],
                "command": command[:200],
                "matched_pattern": entry["pattern"],
                "reason": entry["reason"],
            }
    return {
        "allowed": True,
        "decision": "allow",
        "command": command[:200],
        "matched_pattern": "",
        "reason": "",
    }


def _normalize_path(file_path: str, project_root: str = "") -> str:
    """Normalize a file path to project-relative POSIX form.

    - Absolute paths are converted to relative using project_root.
    - Symlinks are resolved (macOS /var → /private/var).
    - ./ prefix is stripped.
    - Backslashes converted to forward slashes.
    - Trailing slashes stripped.
    """
    import os
    fp = str(file_path).replace("\\", "/")

    # Strip ./ prefix (correctly: only if it starts with ./)
    if fp.startswith("./"):
        fp = fp[2:]

    # Convert absolute path to relative using project_root
    if os.path.isabs(fp) and project_root:
        # Resolve symlinks on absolute paths (macOS /var → /private/var)
        fp = os.path.realpath(fp).replace("\\", "/")
        root = os.path.realpath(str(project_root)).replace("\\", "/").rstrip("/")
        fp_norm = fp.rstrip("/")
        if fp_norm.startswith(root + "/"):
            fp = fp_norm[len(root) + 1:]
        elif fp_norm == root:
            fp = "."

    return fp


GOVERNANCE_ALLOWED_PREFIXES = [
    ".aiwf/runtime/internal/",
    # narrative/markdown governance directories (JSON state/records are protected truth)
    ".aiwf/goals/",
    ".aiwf/plans/",
    ".aiwf/tasks/",
    ".aiwf/milestones/",
    ".aiwf/config/",
]

GOVERNANCE_UNKNOWN_POLICY = "deny"  # deny unknown .aiwf paths

def _is_governance_file(normalized_path: str) -> bool:
    """Check if a normalized path is an allowed AIWF governance file.

    Covers: 7 MVP state files, reports/, baseline.json, assets/,
    experiment-artifacts/, internal/. These must always be writable
    by planner/skills to avoid self-lock.
    """
    for prefix in GOVERNANCE_ALLOWED_PREFIXES:
        if prefix.endswith("/"):
            if normalized_path == prefix.rstrip("/") or normalized_path.startswith(prefix):
                return True
        else:
            if normalized_path == prefix:
                return True
    return False


def classify_file_change(file_path: str) -> str:
    """Classify a changed file as 'project' or 'governance'."""
    return "governance" if _is_governance_file(file_path) else "project"


def _matches(file_path: str, pattern: str) -> bool:
    """Check if a normalized relative file_path matches a pattern.

    Supports two forms:
    - Glob patterns: if pattern contains *, ?, [seq], it is treated as a
      fnmatch glob (e.g. ``src/*.py``, ``**/test_*.py``).
    - Prefix patterns: plain paths match as exact or directory prefix
      (e.g. ``src/`` matches ``src/foo.py``, ``README.md`` is exact).
    """
    fp = str(file_path)
    p = str(pattern).rstrip("/")
    # Strip ./ prefix from pattern too
    if p.startswith("./"):
        p = p[2:]

    if p == "*" or p == "." or p == "":
        return True

    # Glob: use fnmatch for patterns with wildcard characters
    if any(c in p for c in ("*", "?", "[")):
        import fnmatch
        return fnmatch.fnmatch(fp, p)

    # Prefix: exact match or directory-prefix match
    if fp == p:
        return True
    if fp.startswith(p + "/"):
        return True
    # Pattern without trailing / should also match prefix
    if fp.startswith(p) and (len(fp) == len(p) or fp[len(p)] == "/"):
        return True

    return False
