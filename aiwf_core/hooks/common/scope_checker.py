"""Scope checker using backend-neutral core.

Checks tool actions against active context scope.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

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
        ".aiwf/history/task-ledger.json",
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
    if normalized == ".aiwf/quality/review.json":
        level = state.get("workflow_level", "L1_review_light")
        if level in ("L2_standard_team", "L3_full_power"):
            review = _read_json(cwd / ".aiwf" / "quality" / "review.json", {})
            if not review.get("cleanup_verified_at"):
                return ScopeResult(
                    file_path=normalized,
                    allowed=False,
                    active_context_id=state.get("active_context_id") or "(none)",
                    reason="cleanup must be mechanically verified before L2/L3 review.json is written",
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
    active_ctx_id = state.get("active_context_id")
    if not active_ctx_id:
        # Block project file writes without an active context.
        # Governance files are always allowed.
        if _is_governance_file(normalized):
            return ScopeResult(file_path=file_path, allowed=True, reason="governance file, no context needed")
        return ScopeResult(
            file_path=file_path, allowed=False, active_context_id="(none)",
            reason=f"no active context — run 'aiwf state start-context' to create one before writing to '{file_path}'"
        )

    contexts = _read_json(cwd / ".aiwf" / "state" / "contexts.json", default_contexts())
    active_ctx = None
    for ctx in contexts.get("contexts", []):
        if ctx.get("id") == active_ctx_id:
            active_ctx = ctx
            break

    # Plan-only drift: plan exists but no task activated
    if state.get("active_plan_id") and state.get("request_mode") == "execution" and not state.get("active_task_id"):
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

    # Runtime build artifacts — warn but don't block
    _artifact_patterns = (".pytest_cache/", ".coverage", ".mypy_cache/", ".ruff_cache/",
                          "__pycache__/", ".tox/", "node_modules/", ".nyc_output/")
    if any(p in file_path for p in _artifact_patterns):
        return ScopeResult(file_path=file_path, allowed=True,
                          reason="runtime artifact — allowed, add to project excludes if persistent")

    # Fix-loop repair window: when a fix-loop is open, allow minimal writes
    # to files referenced in required_fixes. This breaks the deadlock where
    # fix-loop says "fix file X" but scope guard says "can't write file X".
    fix_loop = _read_json(cwd / ".aiwf" / "state" / "fix-loop.json", {})
    if fix_loop.get("status") == "open":
        import re
        required_fixes = fix_loop.get("required_fixes", []) or []
        for rf in required_fixes:
            if not isinstance(rf, str):
                continue
            # Extract file paths from the fix description
            paths = re.findall(r'([\w./-]+\.[\w]+)', rf)
            for p in paths:
                p_clean = p.lstrip("./")
                if normalized == p_clean or normalized.endswith("/" + p_clean):
                    return ScopeResult(
                        file_path=file_path, allowed=True,
                        reason=f"fix-loop repair window: '{normalized}' is a required_fix target"
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
