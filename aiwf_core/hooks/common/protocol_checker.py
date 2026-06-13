"""Protocol precondition checks for the Write Guard.

Checks whether the system is in a state that permits project writes.
Only checks phase prerequisites — does NOT check quality (contracts, testing, review).

Each check returns (blocked: bool, reason: str, fix_command: str).
These are minimum necessary conditions; quality is guided by prompt injection,
not by write blocking.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Tuple


def _read(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def check_protocol_preconditions(cwd: Path) -> Tuple[bool, str, str]:
    """Check write prerequisites. Returns (blocked, reason, fix_command).

    Checked in priority order. First failure blocks.
    Fix-loop repair window overrides are handled by the caller (scope_checker).
    """
    state = _read(cwd / ".aiwf" / "state" / "state.json", {})
    goal = _read(cwd / ".aiwf" / "state" / "goal.json", {})
    fix_loop = _read(cwd / ".aiwf" / "state" / "fix-loop.json", {})

    # P0: request_mode must be execution
    request_mode = state.get("request_mode", "execution")
    if request_mode != "execution":
        return (
            True,
            f"request_mode is '{request_mode}', not 'execution' — project writes blocked",
            "aiwf state set-workflow-mode --request-mode execution",
        )

    # P0: goal must be confirmed by user
    if not goal.get("confirmed", True):
        return (
            True,
            "goal is not confirmed — user must approve before implementation",
            "aiwf state set-goal-confirmed --confirmed true",
        )

    # P0: fix-loop must be closed
    if fix_loop.get("status") == "open":
        route = fix_loop.get("route") or "planner"
        fixes = "; ".join(map(str, (fix_loop.get("required_fixes", []) or [])[:2]))
        return (
            True,
            f"fix-loop is open (route={route}) — resolve before writing"
            + (f" (fixes: {fixes})" if fixes else ""),
            "aiwf fixloop resolve --resolution '<what was fixed>'",
        )

    # P0: scope violation must be resolved
    if state.get("scope_violation"):
        return (
            True,
            "scope_violation is true — revert violating files before writing",
            "revert the originally violating files, then run: aiwf fixloop resolve --resolution '<what was reverted>'",
        )

    return (False, "", "")
