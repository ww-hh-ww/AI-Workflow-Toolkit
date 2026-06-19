"""Command Manifest — V1 whitelist."""
from __future__ import annotations
from typing import Dict, List

PRIMARY = "primary"
ADVANCED = "advanced"
INTERNAL = "internal"
DEPRECATED = "deprecated"
QUARANTINE = "quarantine"

COMMAND_MANIFEST: Dict[str, Dict] = {
    "install": {
        "tier": PRIMARY, "core": "infra",
        "caller": "user", "trigger": "on-demand",
        "visible": True, "tested": "yes", "in_status_prompt": True,
        "keep": "entry point",
    },
    "doctor": {
        "tier": PRIMARY, "core": "infra",
        "caller": "user", "trigger": "on-demand",
        "visible": True, "tested": "partial", "in_status_prompt": True,
        "keep": "health check",
    },
    "status": {
        "tier": PRIMARY, "core": "infra",
        "caller": "all", "trigger": "always",
        "visible": True, "tested": "yes", "in_status_prompt": True,
        "keep": "every turn anchor",
    },
    "fixloop": {
        "tier": PRIMARY, "core": "recovery",
        "caller": "planner/tester/reviewer", "trigger": "on-failure",
        "visible": True, "tested": "yes", "in_status_prompt": True,
        "keep": "fix-loop recovery",
    },
    "mission": {
        "tier": PRIMARY, "core": "goal_progress",
        "caller": "planner", "trigger": "on-project-start",
        "visible": True, "tested": "partial", "in_status_prompt": True,
        "keep": "project mission — show only",
    },
    "goal": {
        "tier": PRIMARY, "core": "goal_progress",
        "caller": "planner", "trigger": "on-planning",
        "visible": True, "tested": "partial", "in_status_prompt": True,
        "keep": "goal CRUD and linking",
    },
    "plan": {
        "tier": PRIMARY, "core": "active_plan",
        "caller": "planner", "trigger": "on-planning",
        "visible": True, "tested": "yes", "in_status_prompt": True,
        "keep": "plan CRUD and task linking",
    },
    "task": {
        "tier": PRIMARY, "core": "goal_progress",
        "caller": "planner", "trigger": "on-activation",
        "visible": True, "tested": "yes", "in_status_prompt": True,
        "keep": "task CRUD and runtime",
    },
    "record": {
        "tier": PRIMARY, "core": "verification",
        "caller": "executor/tester/reviewer", "trigger": "on-task",
        "visible": True, "tested": "yes", "in_status_prompt": False,
        "keep": "evidence/testing/review/architecture-review",
    },
    "ui": {
        "tier": PRIMARY, "core": "infra",
        "caller": "user", "trigger": "on-demand",
        "visible": True, "tested": "partial", "in_status_prompt": True,
        "keep": "TUI browser for governance structure",
    },
    "sync": {
        "tier": PRIMARY, "core": "infra",
        "caller": "all", "trigger": "on-change",
        "visible": True, "tested": "partial", "in_status_prompt": True,
        "keep": "MD frontmatter -> JSON compiler",
    },
    "milestone": {
        "tier": PRIMARY, "core": "goal_progress",
        "caller": "planner", "trigger": "on-milestone",
        "visible": True, "tested": "yes", "in_status_prompt": True,
        "keep": "milestone node and acceptance",
    },
}


def manifest_commands(tier: str | None = None) -> List[str]:
    if tier:
        return sorted(k for k, v in COMMAND_MANIFEST.items() if v["tier"] == tier)
    return sorted(COMMAND_MANIFEST.keys())


def manifest_summary() -> str:
    primary = manifest_commands(PRIMARY)
    internal = manifest_commands(INTERNAL)
    return f"PRIMARY({len(primary)}): {', '.join(primary)} | INTERNAL({len(internal)}): {', '.join(internal)}"
