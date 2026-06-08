#!/usr/bin/env python3
import sys
from pathlib import Path
# Bootstrap: add project root and AIWF toolkit root so aiwf_core is importable
_AH_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_AH_TOOLKIT_ROOT = Path("/Users/wzx/Documents/AI-Workflow-Toolkit-for-Reasonix")
for _AH_ROOT in (_AH_TOOLKIT_ROOT, _AH_PROJECT_ROOT):
    _AH_ROOT_STR = str(_AH_ROOT)
    if _AH_ROOT_STR not in sys.path:
        sys.path.insert(0, _AH_ROOT_STR)
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
