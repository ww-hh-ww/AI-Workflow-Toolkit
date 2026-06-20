"""Scope checker — project writes require active task; executor dispatch per Task.requirements."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import subprocess

from ...core.event_model import NormalizedEvent, ScopeResult
from ...core.scope_policy import check_scope, check_bash_command
from ...core.state_schema import default_contexts
from ...core.state.goal_ops import get_active_goal


def _read_json(path: Path, default: Dict) -> Dict:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _is_gitignored(file_path: str, cwd: Path) -> bool:
    # Fast path: no .git directory means not a git repo
    if not (cwd / ".git").exists():
        return False
    try:
        r = subprocess.run(
            ["git", "check-ignore", "-q", file_path],
            capture_output=True, cwd=str(cwd), timeout=5,
        )
        return r.returncode == 0
    except Exception:
        return False


def _get_active_task_requirements(cwd: Path) -> Optional[Dict[str, Any]]:
    """Read the active task's requirements from Task.md frontmatter.

    Reads directly from the MD contract, not from synced JSON. This means
    editing Task.md and changing executor_required takes effect immediately
    without needing aiwf sync — same as forbidden_write already works.
    """
    state = _read_json(cwd / ".aiwf" / "state" / "state.json", {})
    task_id = state.get("active_task_id")
    if not task_id:
        return None
    task_md = cwd / ".aiwf" / "tasks" / f"{task_id}.md"
    if not task_md.exists():
        return None
    try:
        text = task_md.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            return None
        end_idx = text.find("\n---\n", 4)
        if end_idx == -1:
            return None
        import yaml
        fm = yaml.safe_load(text[4:end_idx]) or {}
        reqs = {}
        for key in ("executor_required", "tester_required", "reviewer_required"):
            val = fm.get(key)
            if isinstance(val, bool):
                reqs[key] = val
        return reqs or None
    except Exception:
        return None


def _get_task_forbidden_write(cwd: Path, task_id: str) -> list:
    """Read forbidden_write from active Task.md frontmatter."""
    task_md = cwd / ".aiwf" / "tasks" / f"{task_id}.md"
    if not task_md.exists():
        return []
    try:
        text = task_md.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            return []
        end_idx = text.find("\n---\n", 4)
        if end_idx == -1:
            return []
        import yaml
        fm = yaml.safe_load(text[4:end_idx]) or {}
        fw = fm.get("forbidden_write", [])
        if isinstance(fw, list):
            return [str(x).strip() for x in fw if str(x).strip()]
        if isinstance(fw, str) and fw.strip():
            return [s.strip() for s in fw.replace(",", " ").split() if s.strip()]
        return []
    except Exception:
        return []


def check_file_write(event: NormalizedEvent) -> ScopeResult:
    """Check if a file write/edit is within active scope.

    V2 policy:
    - Project writes require an active task.
    - Governance/planning writes do not require an active task.
    - Executor subagent requirement is decided by Task.requirements.executor_required.
    """
    file_path = event.tool_input.get("file_path", "")
    if not file_path:
        return ScopeResult(file_path="", allowed=True, reason="no file_path in event")

    cwd = Path(event.cwd) if event.cwd else Path.cwd()

    state = _read_json(cwd / ".aiwf" / "state" / "state.json", {})
    from ...core.scope_policy import _is_governance_file, _normalize_path
    normalized = _normalize_path(file_path, str(cwd))

    # ── Mechanical truth: JSON run state must use CLI, never direct Write/Edit ──
    _PROTECTED_JSON_PREFIXES = (".aiwf/state/", ".aiwf/records/")
    if normalized.endswith(".json") and any(normalized.startswith(p) for p in _PROTECTED_JSON_PREFIXES):
        return ScopeResult(
            file_path=normalized,
            allowed=False,
            active_context_id=state.get("active_context_id") or "(none)",
            reason=(
                f"mechanical truth '{normalized}' must be changed through aiwf CLI commands; "
                "direct Write/Edit of .aiwf/state/*.json and .aiwf/records/*.json is denied."
            ),
        )

    # ── Fix-loop repair window: allow explicit repair targets ──
    fix_loop = _read_json(cwd / ".aiwf" / "state" / "fix-loop.json", {})
    if fix_loop.get("status") == "open":
        import re
        required_fixes = fix_loop.get("required_fixes", []) or []
        for rf in required_fixes:
            if not isinstance(rf, str):
                continue
            paths = re.findall(r'([\w./-]+\.[\w]+)', rf)
            for p in paths:
                p_clean = p.lstrip("./")
                candidates = {p_clean, "." + p_clean}
                if normalized in candidates or any(normalized.endswith("/" + c) for c in candidates):
                    role = str(event.agent_type or "").lower()
                    active_task_id = state.get("active_task_id")
                    if (
                        not _is_governance_file(normalized)
                        and active_task_id
                    ):
                        reqs = _get_active_task_requirements(cwd) or {}
                        if reqs.get("executor_required") and "executor" not in role:
                            return ScopeResult(
                                file_path=normalized,
                                allowed=False,
                                active_context_id=state.get("active_context_id") or "(none)",
                                reason=(
                                    f"fix-loop repair for project file '{normalized}' requires executor subagent. "
                                    "Dispatch aiwf-executor for the fix instead of repairing inline."
                                ),
                            )
                    return ScopeResult(
                        file_path=file_path,
                        allowed=True,
                        reason=f"fix-loop repair window: '{normalized}' is a required_fix target"
                    )

    # ── Governance files ──
    if _is_governance_file(normalized):
        active_task_id = state.get("active_task_id")
        # Only the active Task.md is frozen during execution
        if active_task_id:
            task_md_path = f".aiwf/tasks/{active_task_id}.md"
            if normalized == task_md_path:
                return ScopeResult(
                    file_path=normalized,
                    allowed=False,
                    active_context_id=state.get("active_context_id") or "(none)",
                    reason=(
                        f"active Task.md '{normalized}' is frozen during execution. "
                        f"Do NOT modify the active Task.md. "
                        f"Other governance MDs (goals, plans, milestones, other tasks) may be edited."
                    ),
                )

        return ScopeResult(file_path=normalized, allowed=True,
                          reason="governance file — always allowed")

    # ── Project files: require active task ──
    active_task_id = state.get("active_task_id")
    if not active_task_id:
        return ScopeResult(
            file_path=normalized,
            allowed=False,
            active_context_id=state.get("active_context_id") or "(none)",
            reason=(
                f"no active task — run 'aiwf task activate <TASK-ID>' before writing to '{normalized}'. "
                "Project writes require an active task."
            ),
        )

    # ── Executor subagent requirement ──
    reqs = _get_active_task_requirements(cwd) or {}
    role = str(event.agent_type or "").lower()
    if reqs.get("executor_required") and "executor" not in role:
        return ScopeResult(
            file_path=normalized,
            allowed=False,
            active_context_id=state.get("active_context_id") or "(none)",
            reason=(
                f"Task.requirements.executor_required=true: project writes must be performed by "
                f"an aiwf-executor subagent. Dispatch aiwf-executor before writing '{normalized}'."
            ),
        )

    # ── Forbidden write: mechanically enforce Task.md forbidden_write patterns ──
    forbidden = _get_task_forbidden_write(cwd, active_task_id)
    if forbidden:
        from ...core.scope_policy import _matches
        for pattern in forbidden:
            if _matches(normalized, pattern):
                return ScopeResult(
                    file_path=normalized,
                    allowed=False,
                    active_context_id=active_task_id,
                    reason=(
                        f"'{normalized}' matches Forbidden Write pattern '{pattern}' "
                        f"from active Task.md ({active_task_id}). "
                        f"Task contract prohibits writing to this path."
                    ),
                )

    # ── Project file: allowed (guarded by active_task_id + executor_required + forbidden_write above) ──
    return ScopeResult(file_path=normalized, allowed=True,
                      reason=f"project write allowed (task={active_task_id}, executor_required={reqs.get('executor_required', False)})")


def _path_matches(file_path: str, pattern: str) -> bool:
    fp = file_path.lstrip("./")
    pat = pattern.lstrip("./")
    if pat.endswith("/") or pat.endswith("/**"):
        prefix = pat.rstrip("*").rstrip("/")
        return fp == prefix or fp.startswith(prefix + "/")
    if pat.startswith("**/"):
        suffix = pat[3:]
        return fp == suffix or fp.endswith("/" + suffix)
    if "*" in pat:
        import fnmatch
        return fnmatch.fnmatch(fp, pat)
    return fp == pat


def check_bash(event: NormalizedEvent) -> Dict:
    command = event.tool_input.get("command", "")
    cwd = Path(event.cwd) if event.cwd else Path.cwd()

    # ── Command-policy: mechanically block AI-forbidden commands ──
    policy_result = _check_command_policy(command, cwd)
    if policy_result:
        return policy_result

    # ── Active Task.md: block bash writes to frozen contract ──
    active_lock_result = _check_active_task_md_bash(command, cwd)
    if active_lock_result:
        return active_lock_result

    return check_bash_command(command)


def _check_active_task_md_bash(command: str, cwd: Path) -> Optional[Dict]:
    """Block bash commands that write to or delete the active Task.md during execution."""
    state_path = cwd / ".aiwf" / "state" / "state.json"
    if not state_path.exists():
        return None
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    active_task_id = state.get("active_task_id", "")
    if not active_task_id:
        return None

    import re
    md_path = f".aiwf/tasks/{active_task_id}.md"
    esc = re.escape(md_path)

    # Destructive patterns targeting the active Task.md
    deny_patterns = [
        # Redirect/append: echo x >> path, echo x > path
        rf">>?\s*{esc}",
        # In-place edit: sed -i ... path, perl -i ... path
        rf"(sed|perl)\s+.*-i[^ ]*\s+.*{esc}",
        # Remove/unlink: rm path, rm -f path, unlink path
        rf"\brm\s+[^;|&]*{esc}",
        rf"\bunlink\s+{esc}",
        # Move/rename: mv path dest, mv -f path dest
        rf"\bmv\s+.*{esc}\s",
        # Copy over: cp ... path (copies TO the locked file)
        rf"\bcp\s+.*\s+{esc}",
        # Tee overwrite: | tee path, tee path
        rf"\btee\s+.*{esc}",
        # Python write: open("path","w"), open('path','w')
        rf"open\s*\(\s*['\"]{esc}['\"]\s*,\s*['\"]w",
        # dd write: dd of=path
        rf"\bdd\s+.*of={esc}",
        # Truncate: truncate path, > path
        rf"\btruncate\s+.*{esc}",
    ]

    for pattern in deny_patterns:
        if re.search(pattern, command, re.IGNORECASE):
            return {
                "allowed": False,
                "decision": "deny",
                "command": command[:200],
                "matched_pattern": pattern,
                "reason": (
                    f"Active Task.md '{md_path}' is frozen during execution. "
                    f"Bash writes to the active Task.md are blocked. "
                    f"Other governance files may be edited."
                ),
            }
    return None


def _check_command_policy(command: str, cwd: Path) -> Optional[Dict]:
    """Check .aiwf/config/command-policy.json for AI-blocked commands.

    Returns a deny result dict if the command matches a blocked pattern,
    or None if the command is allowed.
    """
    policy_path = cwd / ".aiwf" / "config" / "command-policy.json"
    if not policy_path.exists():
        return None
    try:
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    for entry in policy.get("deny", []) or []:
        if not isinstance(entry, dict):
            continue
        pattern = entry.get("command", "")
        if not pattern:
            continue
        if pattern.lower() in command.lower():
            return {
                "allowed": False,
                "decision": "deny",
                "command": command[:200],
                "matched_pattern": pattern,
                "reason": (
                    f"Command '{pattern}' is blocked by command-policy: "
                    f"{entry.get('reason', 'AI is not allowed to run this command.')}"
                ),
            }
    return None
