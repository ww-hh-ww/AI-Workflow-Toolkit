import json, sys
from pathlib import Path
from aiwf_core.adapters.claude.normalize_event import parse_claude_stdin, normalize
from aiwf_core.hooks.common.scope_checker import check_file_write
from aiwf_core.adapters.claude.responses import allow, allow_with_updated_input, deny_pre_tool_use
from aiwf_core.core.agent_worktree import (
    AgentWorktreeError,
    apply_patch_paths,
    route_agent_tool,
)
from aiwf_core.core.event_model import NormalizedEvent

def main():
    data = parse_claude_stdin()
    if not data:
        allow()

    event = normalize(data)
    if event.tool_name not in ("Write", "Edit", "MultiEdit", "apply_patch"):
        allow()

    routed = None
    try:
        routed = route_agent_tool(event)
    except AgentWorktreeError as exc:
        deny_pre_tool_use(str(exc))
    if routed is not None:
        event.cwd = str(routed.assignment.worktree)
        event.tool_input = routed.tool_input

    if event.tool_name == "apply_patch":
        paths = apply_patch_paths(event.tool_input)
        if not paths:
            deny_pre_tool_use(
                "Cannot inspect apply_patch scope: no file headers were found. "
                "Use the standard apply_patch format."
            )
        for path in paths:
            file_event = NormalizedEvent(
                engine=event.engine,
                event_type=event.event_type,
                session_id=event.session_id,
                cwd=event.cwd,
                tool_name="Write",
                tool_input={"file_path": path},
                agent_id=event.agent_id,
                agent_type=event.agent_type,
            )
            result = check_file_write(file_event)
            if not result.allowed:
                deny_pre_tool_use(result.reason)
    else:
        result = check_file_write(event)

        if not result.allowed:
            deny_pre_tool_use(result.reason)

    if routed is not None and routed.changed:
        allow_with_updated_input(routed.tool_input)
    allow()

if __name__ == "__main__":
    main()
