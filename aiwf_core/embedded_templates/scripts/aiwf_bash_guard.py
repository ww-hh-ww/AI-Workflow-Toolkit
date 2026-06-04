
import json, sys
from pathlib import Path
from aiwf_core.adapters.claude.normalize_event import parse_claude_stdin, normalize
from aiwf_core.hooks.common.scope_checker import check_bash
from aiwf_core.adapters.claude.responses import allow, deny_pre_tool_use

def main():
    data = parse_claude_stdin()
    if not data:
        allow()

    event = normalize(data)
    if event.tool_name != "Bash":
        allow()

    result = check_bash(event)

    if result["decision"] == "deny":
        deny_pre_tool_use(
            f"AIWF Bash guard blocked: {result['command'][:100]}\n"
            f"Reason: {result['reason']} (pattern: {result['matched_pattern']})\n"
            "If this command is necessary, request approval from planner-main."
        )

    if result["decision"] == "ask":
        # For 'ask', we still allow but with a system message warning
        print(json.dumps({
            "systemMessage": f"AIWF: {result['reason']} — command: {result['command'][:80]}"
        }))
        sys.exit(0)

    allow()

if __name__ == "__main__":
    main()
