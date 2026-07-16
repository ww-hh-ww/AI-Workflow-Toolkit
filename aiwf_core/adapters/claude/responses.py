"""Claude Code hook response formatter.

Converts AIWF core results into Claude-compatible hook responses
(JSON stdout or exit codes). No business logic here — only formatting.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Optional


def _is_reasonix() -> bool:
    return os.environ.get("AIWF_HOOK_ENGINE", "").lower() == "reasonix"


def output_json(data: Dict[str, Any]) -> None:
    """Print JSON to stdout and exit 0 (Claude processes JSON on exit 0)."""
    print(json.dumps(data, ensure_ascii=False))
    sys.exit(0)


def allow() -> None:
    """Allow the tool/action — exit 0 with no output."""
    sys.exit(0)


def allow_with_updated_input(
    tool_input: Dict[str, Any],
    additional_context: str = "",
) -> None:
    """Allow a Claude tool call after replacing its input."""
    if _is_reasonix():
        allow()
    output = {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow",
        "updatedInput": tool_input,
    }
    if additional_context:
        output["additionalContext"] = additional_context
    output_json({"hookSpecificOutput": output})


def deny_pre_tool_use(reason: str) -> None:
    """Block a PreToolUse action with permission decision deny."""
    if _is_reasonix():
        print(reason)
        sys.exit(2)
    output_json({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    })


def deny_permission(reason: str) -> None:
    """Block a PermissionRequest."""
    output_json({
        "hookSpecificOutput": {
            "hookEventName": "PermissionRequest",
            "decision": {"behavior": "deny"},
        }
    })


def block_stop(reason: str) -> None:
    """Block a Stop event — Claude continues conversation."""
    if _is_reasonix():
        print(reason)
        sys.exit(0)
    output_json({
        "decision": "block",
        "reason": reason,
    })


def inject_context(text: str) -> None:
    """Inject additionalContext into UserPromptSubmit response."""
    if _is_reasonix():
        print(text)
        sys.exit(0)
    output_json({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": text,
        }
    })


def system_message(msg: str) -> None:
    """Send a system message to the user (non-blocking)."""
    if _is_reasonix():
        print(msg)
        sys.exit(0)
    output_json({
        "systemMessage": msg,
    })
