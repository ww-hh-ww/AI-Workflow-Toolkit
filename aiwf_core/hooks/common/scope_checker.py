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

    # Runtime build artifacts — warn but don't block
    _artifact_patterns = (".pytest_cache/", ".coverage", ".mypy_cache/", ".ruff_cache/",
                          "__pycache__/", ".tox/", "node_modules/", ".nyc_output/")
    if any(p in file_path for p in _artifact_patterns):
        return ScopeResult(file_path=file_path, allowed=True,
                          reason="runtime artifact — allowed, add to project excludes if persistent")

    return check_scope(file_path, active_ctx, state, project_root=str(cwd))


def check_bash(event: NormalizedEvent) -> Dict:
    """Check a Bash command for dangerous patterns."""
    command = event.tool_input.get("command", "")
    return check_bash_command(command)
