#!/usr/bin/env python3
"""AIWF UserPromptSubmit — one-line context injection. No heavy imports."""

import json, sys
from pathlib import Path


def main():
    cwd = Path(__file__).resolve().parent.parent

    state_path = cwd / ".aiwf" / "state" / "state.json"
    if not state_path.exists():
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "[AIWF] Not initialized. Run: aiwf install claude"
        }}))
        return

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return

    phase = state.get("phase", "planning")
    task_id = state.get("active_task_id", "")
    plan_id = state.get("active_plan_id", "")
    goal_id = state.get("active_task_parent_goal", "")

    parts = [f"Phase: {phase}"]
    if task_id:
        parts.append(f"task={task_id}")
    if plan_id:
        parts.append(f"plan={plan_id}")
    if goal_id:
        parts.append(f"goal={goal_id}")

    context = f"[AIWF] {'  '.join(parts)}"

    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": context
    }}))


if __name__ == "__main__":
    main()
