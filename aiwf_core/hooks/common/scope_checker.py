"""Scope checker using backend-neutral core.

Checks tool actions against active context scope.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import subprocess

from ...core.event_model import NormalizedEvent, ScopeResult
from ...core.scope_policy import check_scope, check_bash_command
from ...core.state_schema import default_contexts


def _read_json(path: Path, default: Dict) -> Dict:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _is_gitignored(file_path: str, cwd: Path) -> bool:
    """Check if a file is gitignored using git check-ignore."""
    try:
        r = subprocess.run(
            ["git", "check-ignore", "-q", file_path],
            capture_output=True, cwd=str(cwd), timeout=5,
        )
        return r.returncode == 0
    except Exception:
        return False


def check_file_write(event: NormalizedEvent) -> ScopeResult:
    """Check if a file write/edit is within active scope.

    Normalizes Claude's absolute paths to project-relative before matching.
    Governance files are allowed except direct edits to core mechanical truth.
    """
    file_path = event.tool_input.get("file_path", "")
    if not file_path:
        return ScopeResult(file_path="", allowed=True, reason="no file_path in event")

    cwd = Path(event.cwd) if event.cwd else Path.cwd()

    # Read active context
    state = _read_json(cwd / ".aiwf" / "state" / "state.json", {})
    normalized = ""
    from ...core.scope_policy import _is_governance_file, _normalize_path
    normalized = _normalize_path(file_path, str(cwd))
    protected_truth = {
        ".aiwf/state/state.json",
        ".aiwf/state/goal.json",
        ".aiwf/state/contexts.json",
        ".aiwf/state/fix-loop.json",
        ".aiwf/runtime/history/task-ledger.json",
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
    if normalized == ".aiwf/artifacts/quality/review.json":
        level = state.get("workflow_level", "L1_review_light")
        if level in ("L2_standard_team", "L3_full_power"):
            review = _read_json(cwd / ".aiwf" / "artifacts" / "quality" / "review.json", {})
            if not review.get("cleanup_verified_at"):
                return ScopeResult(
                    file_path=normalized,
                    allowed=False,
                    active_context_id=state.get("active_context_id") or "(none)",
                    reason="cleanup must be mechanically verified before L2/L3 review.json is written",
                )

    # Fix-loop repair window: allow explicit repair targets before active-task
    # and role gates. This prevents governance repair deadlocks such as needing
    # to fix plans.json before a task can be activated.
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
                    return ScopeResult(
                        file_path=file_path,
                        allowed=True,
                        reason=f"fix-loop repair window: '{normalized}' is a required_fix target"
                    )

    if not _is_governance_file(normalized):
        level = state.get("workflow_level", "L1_review_light")
        if level != "L0_direct" and not state.get("active_task_id"):
            return ScopeResult(
                file_path=normalized,
                allowed=False,
                active_context_id=state.get("active_context_id") or "(none)",
                reason=f"no active task — run 'aiwf task activate <TASK-ID>' before writing to '{normalized}'",
            )
        role = str(event.agent_type or "").lower()
        phase = state.get("phase", "")
        if (
            level != "L0_direct"
            and state.get("active_task_id")
            and phase == "implementing"
            and "executor" not in role
        ):
            return ScopeResult(
                file_path=normalized,
                allowed=False,
                active_context_id=state.get("active_context_id") or "(none)",
                reason=(
                    f"L1+ implementation must be performed by an aiwf-executor subagent before writing '{normalized}'. "
                    "Planner/main or unknown-role Write/Edit is denied before it can create code. "
                    "Fix: dispatch Agent(subagent_type=aiwf-executor) with the active task scope, "
                    "or explicitly downgrade to L0 first with aiwf route downgrade --task-id "
                    f"{state.get('active_task_id')} --to single_agent --reason '<mechanical change>' --user-confirmed."
                ),
            )

    # Context is advisory (purpose, test_focus, review_focus). Scope enforcement
    # reads from the task's allowed_write (in task-ledger.json). If there's no
    # active task, the check at line 85-93 already blocks non-L0 writes.
    active_ctx_id = state.get("active_context_id", "")
    contexts = _read_json(cwd / ".aiwf" / "state" / "contexts.json", default_contexts())
    active_ctx = {}
    for ctx in contexts.get("contexts", []):
        if ctx.get("id") == active_ctx_id:
            active_ctx = ctx
            break

    # Plan-only drift: plan exists but no task activated.
    # Allow governance files — editing the plan artifact, context, or quality
    # brief is the way to RESOLVE the drift. Blocking them creates a deadlock:
    # need task to edit plan → need to edit plan to get task.
    if state.get("active_plan_id") and state.get("request_mode") == "execution" and not state.get("active_task_id"):
        if not _is_governance_file(normalized):
            return ScopeResult(
                file_path=file_path, allowed=False,
                active_context_id=state.get("active_context_id") or "(none)",
                reason="plan_only_drift: a plan exists but no task is activated. Activate the planned task before writing project files."
            )

    # Architecture brief constraints: protected_files and forbidden_restructures
    goal = _read_json(cwd / ".aiwf" / "state" / "goal.json", {})
    arch_brief = goal.get("quality_brief", {}).get("architecture_brief", {})
    if arch_brief:
        protected = arch_brief.get("protected_files", []) or []
        for pattern in protected:
            if _path_matches(normalized, pattern):
                return ScopeResult(
                    file_path=file_path, allowed=False,
                    active_context_id=state.get("active_context_id") or "(none)",
                    reason=f"protected file: '{normalized}' matches protected pattern '{pattern}'. Requires Planner override."
                )
        forbidden = arch_brief.get("forbidden_restructures", []) or []
        for pattern in forbidden:
            if _path_matches(normalized, pattern):
                return ScopeResult(
                    file_path=file_path, allowed=False,
                    active_context_id=state.get("active_context_id") or "(none)",
                    reason=f"forbidden restructure: '{normalized}' matches '{pattern}'. This structural change is prohibited by the architecture brief."
                )

    # Project rules: negative rules block matching file writes
    try:
        from ...core.project_rules import list_project_rules
        rules = list_project_rules(str(cwd), include_retired=False)
        for rule in rules:
            if rule.get("type") == "negative" and rule.get("text"):
                rule_text = rule["text"]
                if normalized in rule_text or rule_text in normalized:
                    return ScopeResult(
                        file_path=file_path, allowed=False,
                        active_context_id=state.get("active_context_id") or "(none)",
                        reason=f"negative rule {rule.get('id', '?')}: {rule_text[:120]}"
                    )
    except Exception:
        pass

    # Gitignored files are build artifacts / dependencies / generated files —
    # the project has declared them non-project. Don't flag as scope violations.
    if _is_gitignored(file_path, cwd):
        return ScopeResult(file_path=file_path, allowed=True,
                          reason="gitignored file — allowed")

    # Protocol precondition checks (P0): run AFTER repair window so fix targets aren't blocked.
    # These check phase prerequisites — not quality (contracts, testing, review).
    from .protocol_checker import check_protocol_preconditions
    blocked, reason, fix_cmd = check_protocol_preconditions(cwd)
    if blocked:
        return ScopeResult(
            file_path=normalized, allowed=False,
            active_context_id=state.get("active_context_id") or "(none)",
            reason=f"Protocol gate: {reason}\nFix: {fix_cmd}",
        )

    return check_scope(file_path, active_ctx, state, project_root=str(cwd))


def _path_matches(file_path: str, pattern: str) -> bool:
    """Check if file_path matches a simple glob-like pattern."""
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
    """Check a Bash command for dangerous patterns."""
    command = event.tool_input.get("command", "")
    return check_bash_command(command)
