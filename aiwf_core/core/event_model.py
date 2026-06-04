"""Backend-neutral AIWF event model.

Defines normalized event types that any engine adapter (Claude Code,
Codex, etc.) can map into. Core logic operates on these types, never
on engine-specific JSON schemas.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class NormalizedEvent:
    """A tool-use or lifecycle event normalized from any engine."""
    engine: str = ""               # "claude", "codex", etc.
    event_type: str = ""           # "pre_tool_use", "post_tool_use", "user_prompt", "stop"
    session_id: str = ""
    cwd: str = ""
    tool_name: str = ""            # "Write", "Edit", "Bash", etc.
    tool_input: Dict[str, Any] = field(default_factory=dict)
    tool_response: Optional[Dict[str, Any]] = None
    exit_code: Optional[int] = None
    agent_id: str = ""
    agent_type: str = ""


@dataclass
class ScopeResult:
    """Result of checking a tool action against active scope."""
    allowed: bool = True
    file_path: str = ""
    active_context_id: str = ""
    allowed_write: List[str] = field(default_factory=list)
    forbidden_write: List[str] = field(default_factory=list)
    reason: str = ""


@dataclass
class EvidenceRecord:
    """A machine-observed evidence record."""
    id: str = ""
    timestamp: str = ""
    context_id: str = ""
    phase: str = ""
    session_id: str = ""
    agent_id: str = ""             # subagent id, empty for main agent
    agent_type: str = ""           # executor/tester/reviewer/etc when engine provides it
    tool_name: str = ""
    tool_input: Dict[str, Any] = field(default_factory=dict)
    command: str = ""
    exit_code: Optional[int] = None
    changed_files: List[str] = field(default_factory=list)
    changed_files_source: str = ""  # "git_diff", "snapshot", "unavailable"
    stdout_summary: str = ""
    stderr_summary: str = ""
    status: str = "pending"
    trust: str = "machine_observed"


@dataclass
class BashGuardResult:
    """Result of checking a Bash command for dangerous patterns."""
    allowed: bool = True
    decision: str = "allow"        # "allow", "deny", "ask"
    command: str = ""
    matched_pattern: str = ""
    reason: str = ""


@dataclass
class GateResult:
    """Result of evaluating closure gates."""
    passed: bool = False
    evidence_exists: bool = False
    evidence_accepted: bool = False
    testing_adequate: bool = False
    review_accepted: bool = False
    fix_loop_open: bool = False
    scope_violation: bool = False
    close_attempt: bool = False
    blockers: List[str] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)


@dataclass
class StatusContext:
    """Concise AIWF state context for injection into user prompts."""
    phase: str = "unknown"
    active_goal: str = ""
    active_context_id: str = ""
    close_attempt: bool = False
    scope_violation: bool = False
    review_result: str = "unknown"
    fix_loop_status: str = "none"
    fix_loop_route: str = ""
    next_gate: str = ""
    messages: List[str] = field(default_factory=list)
