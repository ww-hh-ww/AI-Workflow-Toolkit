
import json, sys
from pathlib import Path
from aiwf_core.adapters.claude.normalize_event import parse_claude_stdin, normalize
from aiwf_core.hooks.common.scope_checker import check_bash
from aiwf_core.adapters.claude.responses import allow, allow_with_updated_input, deny_pre_tool_use
from aiwf_core.core.agent_worktree import AgentWorktreeError, route_agent_tool

def main():
    data = parse_claude_stdin()
    if not data:
        allow()

    event = normalize(data)
    if event.tool_name != "Bash":
        allow()

    routed = None
    try:
        routed = route_agent_tool(event)
    except AgentWorktreeError as exc:
        deny_pre_tool_use(str(exc))
    if routed is not None:
        event.cwd = str(routed.assignment.worktree)
        event.tool_input = routed.tool_input

    result = check_bash(event)

    if result["decision"] == "deny":
        deny_pre_tool_use(
            f"AIWF Bash guard blocked: {result['command'][:100]}\n"
            f"Reason: {result['reason']} (pattern: {result['matched_pattern']})\n"
            "If this command is necessary, request approval from planner-main."
        )

    if result["decision"] == "ask":
        warning = f"AIWF: {result['reason']} — command: {result['command'][:80]}"
        if routed is not None and routed.changed:
            allow_with_updated_input(routed.tool_input, warning)
        print(json.dumps({"systemMessage": warning}))
        sys.exit(0)

    if routed is not None and routed.changed:
        allow_with_updated_input(routed.tool_input)
    allow()

if __name__ == "__main__":
    main()
