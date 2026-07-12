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
    soft_drift: bool = False
    file_path: str = ""
    active_context_id: str = ""
    allowed_write: List[str] = field(default_factory=list)
    forbidden_write: List[str] = field(default_factory=list)
    reason: str = ""
