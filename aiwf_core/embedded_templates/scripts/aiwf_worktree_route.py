import sys
from aiwf_core.adapters.claude.normalize_event import parse_claude_stdin, normalize
from aiwf_core.adapters.claude.responses import allow, allow_with_updated_input, deny_pre_tool_use
from aiwf_core.core.agent_worktree import AgentWorktreeError, route_agent_tool


def main():
    data = parse_claude_stdin()
    if not data:
        allow()

    event = normalize(data)
    if event.tool_name not in ("Read", "Glob", "Grep", "List"):
        allow()

    try:
        routed = route_agent_tool(event)
    except AgentWorktreeError as exc:
        deny_pre_tool_use(str(exc))
    if routed is not None and routed.changed:
        allow_with_updated_input(routed.tool_input)
    allow()


if __name__ == "__main__":
    main()
