"""Claude Code / Reasonix event normalizer.

Translates coding-shell hook JSON into backend-neutral AIWF events.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from ...core.event_model import NormalizedEvent
from ...core.worktree_context import resolve_worktree_root


def parse_claude_stdin() -> Dict[str, Any]:
    """Read and parse Claude Code hook JSON from stdin. Returns empty dict on failure."""
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def normalize(data: Dict[str, Any]) -> NormalizedEvent:
    """Convert Claude Code or Reasonix hook JSON to a normalized AIWF event.

    Claude input shape (from official docs):
    {
      "session_id": "...",
      "cwd": "/path/to/project",
      "tool_name": "Write",
      "tool_input": {"file_path": "src/x.py", ...},
      "tool_response": {...},       # PostToolUse only
      "hook_event_name": "PreToolUse",
      "agent_id": "...",            # subagent only
      "agent_type": "...",          # subagent only
    }
    """
    if "event" in data or "toolName" in data or "toolArgs" in data:
        return _normalize_reasonix(data)

    event_type = data.get("hook_event_name", "")
    # Map Claude event names to AIWF normalized names
    type_map = {
        "PreToolUse": "pre_tool_use",
        "PostToolUse": "post_tool_use",
        "UserPromptSubmit": "user_prompt",
        "Stop": "stop",
        "SubagentStart": "subagent_start",
        "SubagentStop": "subagent_stop",
        "PostToolUseFailure": "post_tool_use",
    }
    normalized_type = type_map.get(event_type, event_type.lower())

    return NormalizedEvent(
        engine="claude",
        event_type=normalized_type,
        session_id=data.get("session_id", ""),
        cwd=str(resolve_worktree_root(data.get("cwd", str(Path.cwd())))),
        tool_name=data.get("tool_name", ""),
        tool_input=data.get("tool_input", {}) or {},
        tool_response=data.get("tool_response"),
        exit_code=_extract_exit_code(data),
        agent_id=data.get("agent_id", ""),
        agent_type=data.get("agent_type", ""),
        transcript_path=str(
            data.get("agent_transcript_path")
            or data.get("transcript_path", "")
        ),
    )


def _normalize_reasonix(data: Dict[str, Any]) -> NormalizedEvent:
    event_type = data.get("event", "")
    type_map = {
        "PreToolUse": "pre_tool_use",
        "PostToolUse": "post_tool_use",
        "UserPromptSubmit": "user_prompt",
        "Stop": "stop",
    }
    raw_tool_name = data.get("toolName", "")
    tool_name = _normalize_reasonix_tool_name(raw_tool_name)
    tool_input = _normalize_reasonix_tool_args(raw_tool_name, data.get("toolArgs", {}) or {})
    return NormalizedEvent(
        engine="reasonix",
        event_type=type_map.get(event_type, event_type.lower()),
        session_id=str(data.get("sessionId", data.get("session_id", ""))),
        cwd=str(resolve_worktree_root(data.get("cwd", str(Path.cwd())))),
        tool_name=tool_name,
        tool_input=tool_input,
        tool_response=data.get("toolResult") or data.get("toolResponse"),
        exit_code=_extract_exit_code(data),
        agent_id=str(data.get("agentId", "")),
        agent_type=str(data.get("agentType", "")),
        transcript_path=str(data.get("transcriptPath", data.get("transcript_path", ""))),
    )


def _normalize_reasonix_tool_name(tool_name: str) -> str:
    mapping = {
        "write": "Write",
        "edit": "Edit",
        "edit_file": "Edit",
        "multi_edit": "MultiEdit",
        "bash": "Bash",
    }
    return mapping.get(str(tool_name), str(tool_name))


def _normalize_reasonix_tool_args(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(args) if isinstance(args, dict) else {}
    if "file_path" not in normalized:
        for key in ("path", "file", "filename", "target"):
            if normalized.get(key):
                normalized["file_path"] = normalized[key]
                break
    if str(tool_name) == "bash" and "command" not in normalized:
        for key in ("cmd", "script"):
            if normalized.get(key):
                normalized["command"] = normalized[key]
                break
    return normalized


def _extract_exit_code(data: Dict[str, Any]) -> Optional[int]:
    """Try to extract exit code from tool_response if available."""
    tr = data.get("tool_response") or data.get("toolResult") or data.get("toolResponse")
    if isinstance(tr, dict):
        ec = tr.get("exit_code")
        if ec is not None:
            try:
                return int(ec)
            except (ValueError, TypeError):
                pass
    return None
