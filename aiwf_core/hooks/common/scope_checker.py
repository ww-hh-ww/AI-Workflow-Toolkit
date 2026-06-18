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
    """Read the active task's requirements from tasks.json."""
    state = _read_json(cwd / ".aiwf" / "state" / "state.json", {})
    task_id = state.get("active_task_id")
    if not task_id:
        return None
    tasks_data = _read_json(cwd / ".aiwf" / "state" / "tasks.json", {"tasks": []})
    for t in tasks_data.get("tasks", []) or []:
        if isinstance(t, dict) and t.get("id") == task_id:
            return t.get("requirements", {})
    return None


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

    # ── Mechanical truth: must use CLI, never direct Write/Edit ──
    protected_truth = {
        ".aiwf/state/state.json",
        ".aiwf/state/fix-loop.json",
        ".aiwf/state/tasks.json",
    }
    if normalized in protected_truth:
        return ScopeResult(
            file_path=normalized,
            allowed=False,
            active_context_id=state.get("active_context_id") or "(none)",
            reason=(
                f"mechanical truth '{normalized}' must be changed through aiwf CLI/state operations; "
                "direct Write/Edit is denied so workflow gates cannot be bypassed. "
                "Use the matching command: aiwf state ..., aiwf goal ..., aiwf task ..., or aiwf fix-loop ..."
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

    # ── Governance files: always allowed ──
    if _is_governance_file(normalized):
        # Exception: active Task.md is read-only for AI during execution
        active_task_id = state.get("active_task_id")
        if active_task_id:
            task_md_path = f".aiwf/tasks/{active_task_id}.md"
            if normalized == task_md_path and state.get("phase") in ("executing", "testing", "reviewing"):
                return ScopeResult(
                    file_path=normalized,
                    allowed=False,
                    active_context_id=state.get("active_context_id") or "(none)",
                    reason=(
                        f"active Task.md '{normalized}' is frozen during execution. "
                        f"Do NOT modify the active Task.md. "
                        f"Scope changes must go through Planner."
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

    # ── Project file: allowed (guarded by active_task_id + executor_required above) ──
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

    return check_bash_command(command)


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
