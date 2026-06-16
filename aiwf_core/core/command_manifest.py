"""Command Manifest — every command must answer 5 questions.

1. Which core does it serve? (Active Plan / Boundary / Verification / Goal Progress)
2. Who calls it? (planner / executor / tester / reviewer / user)
3. What triggers it? (always / on-activation / on-test / on-review / on-close / on-demand)
4. Visible in default help? (yes / no)
5. Has test coverage? (yes / partial / no)

Commands that can't answer these are marked quarantine.
"""
from __future__ import annotations
from typing import Dict, List

# Tier definitions
PRIMARY = "primary"       # default help, always visible
ADVANCED = "advanced"     # --help --all only
INTERNAL = "internal"     # called by hooks/skills, not user-facing
DEPRECATED = "deprecated" # kept for compat, emit warning
QUARANTINE = "quarantine" # no clear trigger path, candidate for removal

# Core affiliations
CORES = {
    "active_plan": "Active Plan — AI workbench",
    "boundary": "Boundary — write scope",
    "verification": "Verification — evidence/testing/review",
    "goal_progress": "Goal Progress — task ≠ goal",
    "recovery": "Recovery — fix-loop, checkpoint, safety",
    "infra": "Infrastructure — install, doctor, status",
}

COMMAND_MANIFEST: Dict[str, Dict] = {
    # === PRIMARY: default help, serves core ===
    "install": {
        "tier": PRIMARY, "core": "infra",
        "caller": "user", "trigger": "on-demand",
        "visible": True, "tested": "yes",
        "in_status_prompt": True,
        "keep": "entry point — no install, no AIWF",
    },
    "doctor": {
        "tier": PRIMARY, "core": "infra",
        "caller": "user", "trigger": "on-demand",
        "visible": True, "tested": "partial",
        "in_status_prompt": True,
        "keep": "health check — first thing to run when something seems off",
    },
    "status": {
        "tier": PRIMARY, "core": "infra",
        "caller": "all", "trigger": "always",
        "visible": True, "tested": "yes",
        "in_status_prompt": True,
        "keep": "every turn anchor — --prompt for AI, --debug for human",
    },
    "plan": {
        "tier": PRIMARY, "core": "active_plan",
        "caller": "planner", "trigger": "on-planning",
        "visible": True, "tested": "yes",
        "in_status_prompt": True,
        "keep": "Active Plan workbench — create/update/show task plans",
    },
    "mission": {
        "tier": ADVANCED, "core": "goal_progress",
        "caller": "planner", "trigger": "on-project-start",
        "visible": False, "tested": "partial", "in_status_prompt": False,
        "keep": "project-level why and boundaries — semantic container above the Goal Tree",
    },
    "milestone": {
        "tier": ADVANCED, "core": "goal_progress",
        "caller": "planner", "trigger": "on-long-task-or-L3",
        "visible": False, "tested": "yes", "in_status_prompt": False,
        "keep": "optional stage node — long-task phase synthesis without burdening L0/L1",
    },
    "goal-tree": {
        "tier": ADVANCED, "core": "goal_progress",
        "caller": "planner", "trigger": "on-architecture-or-decomposition",
        "visible": False, "tested": "yes", "in_status_prompt": False,
        "keep": "recursive Goal Tree registry — structural skeleton, no activation/close impact",
    },
    "relation": {
        "tier": ADVANCED, "core": "goal_progress",
        "caller": "planner", "trigger": "on-architecture-or-review",
        "visible": False, "tested": "yes", "in_status_prompt": False,
        "keep": "sibling relations between goals — advisory, not gate-driving",
    },
    "change": {
        "tier": ADVANCED, "core": "goal_progress",
        "caller": "planner", "trigger": "on-new-work",
        "visible": False, "tested": "partial", "in_status_prompt": False,
        "keep": "change admission — entry judgment: attach_plan / graft_goal / temporary_root",
    },
    "frontier": {
        "tier": ADVANCED, "core": "goal_progress",
        "caller": "planner", "trigger": "on-dispatch",
        "visible": False, "tested": "partial", "in_status_prompt": False,
        "keep": "execution frontier — semantic dispatch + Work Packet: Planner decides, AIWF validates, agents consume",
    },
    "task": {
        "tier": PRIMARY, "core": "goal_progress",
        "caller": "planner", "trigger": "on-activation",
        "visible": True, "tested": "yes",
        "in_status_prompt": True,
        "keep": "task ledger — plan/activate/suspend/close tasks with goal context",
    },
    "fixloop": {
        "tier": PRIMARY, "core": "recovery",
        "caller": "planner/tester/reviewer", "trigger": "on-failure",
        "visible": True, "tested": "yes",
        "in_status_prompt": True,
        "keep": "fix-loop recovery — open/resolve/revalidate repair cycles",
    },
    "route": {
        "tier": PRIMARY, "core": "active_plan",
        "caller": "planner", "trigger": "on-planning",
        "visible": True, "tested": "yes",
        "in_status_prompt": True,
        "keep": "routing V2-A — explain/downgrade/substitute execution topology",
    },
    "claim": {
        "tier": ADVANCED, "core": "verification",
        "caller": "planner/reviewer", "trigger": "on-review",
        "visible": False, "tested": "partial", "in_status_prompt": False,
        "keep": "claim-evidence alignment — record/verify/list claims",
        "note": "promote to primary after claim-evidence tests + trust_level alignment complete",
    },
    "workspace": {
        "tier": PRIMARY, "core": "boundary",
        "caller": "planner", "trigger": "on-demand",
        "visible": True, "tested": "yes",
        "in_status_prompt": True,
        "keep": "workspace drift scan — detect uncommitted/missing files",
    },

    # === ADVANCED: on-demand, not in default help ===
    "state": {
        "tier": ADVANCED, "core": "verification",
        "caller": "tester/reviewer/planner", "trigger": "on-test/on-review",
        "visible": False, "tested": "yes", "in_status_prompt": False,
        "keep": "record testing/review/quality policy — internal API, not user-facing",
        "note": "long-term: merge into aiwf verify / aiwf close",
    },
    "cleanup": {
        "tier": ADVANCED, "core": "verification",
        "caller": "reviewer", "trigger": "on-review",
        "visible": False, "tested": "yes", "in_status_prompt": False,
        "keep": "cleanup verification before review",
        "note": "long-term: merge into aiwf verify",
    },
    "checkpoint": {
        "tier": ADVANCED, "core": "recovery",
        "caller": "planner", "trigger": "on-L3-or-risky-change",
        "visible": False, "tested": "partial", "in_status_prompt": False,
        "keep": "rollback safety net — create/restore checkpoints",
    },
    "git": {
        "tier": ADVANCED, "core": "recovery",
        "caller": "planner", "trigger": "on-commit",
        "visible": False, "tested": "partial", "in_status_prompt": False,
        "keep": "safe git commit with confirmation guard",
    },
    "goal": {
        "tier": ADVANCED, "core": "goal_progress",
        "caller": "planner", "trigger": "on-planning",
        "visible": False, "tested": "partial", "in_status_prompt": False,
        "keep": "goal revision — update goal intent",
        "note": "long-term: merge into aiwf plan",
    },
    "arch-change": {
        "tier": ADVANCED, "core": "boundary",
        "caller": "executor/reviewer", "trigger": "on-architecture-drift",
        "visible": False, "tested": "yes", "in_status_prompt": False,
        "keep": "architecture change request — formal boundary expansion",
    },
    "project-map": {
        "tier": ADVANCED, "core": "active_plan",
        "caller": "planner/reviewer", "trigger": "impact.project_map=yes",
        "visible": False, "tested": "yes", "in_status_prompt": False,
        "keep": "project structure map — only when plan says Impact.project_map=yes",
    },
    "env": {
        "tier": ADVANCED, "core": "active_plan",
        "caller": "planner/tester", "trigger": "impact.environment=yes",
        "visible": False, "tested": "partial", "in_status_prompt": False,
        "keep": "environment profile — only when plan says Impact.environment=yes",
    },
    "capability": {
        "tier": ADVANCED, "core": "active_plan",
        "caller": "planner", "trigger": "impact.capabilities=yes",
        "visible": False, "tested": "partial", "in_status_prompt": False,
        "keep": "external capability registry — only when plan says Impact.capabilities=yes",
    },
    "research": {
        "tier": ADVANCED, "core": "active_plan",
        "caller": "planner", "trigger": "on-research-mode",
        "visible": False, "tested": "partial", "in_status_prompt": False,
        "keep": "external research records — only in research mode",
    },
    "quality": {
        "tier": ADVANCED, "core": "verification",
        "caller": "reviewer", "trigger": "on-review",
        "visible": False, "tested": "partial", "in_status_prompt": False,
        "keep": "quality surfaces and digest — review-time only",
        "note": "long-term: merge quality digest into close gate; surfaces into review skill",
    },
    "architecture-doc": {
        "tier": ADVANCED, "core": "verification",
        "caller": "planner/architect/user", "trigger": "milestone/release/handoff/user-request",
        "visible": False, "tested": "yes", "in_status_prompt": True,
        "keep": "architecture snapshot requirement — prevents milestone/handoff docs from being forgotten",
    },

    "next": {
        "tier": INTERNAL, "core": "infra",
        "caller": "all", "trigger": "on-demand",
        "visible": False, "tested": "partial", "in_status_prompt": False,
        "keep": "machine-readable next-action directive — used by hooks to route to the right skill",
    },

    # === INTERNAL: called by hooks/skills, not user-facing ===
    "init": {
        "tier": INTERNAL, "core": "infra",
        "caller": "install", "trigger": "on-install",
        "visible": False, "tested": "partial", "in_status_prompt": False,
        "keep": "bootstrap .aiwf state files — called by install",
    },

    # === DEPRECATED: kept for backward compat, emit warning ===
    "idea": {
        "tier": QUARANTINE, "core": "",
        "caller": "", "trigger": "",
        "visible": False, "tested": "yes", "in_status_prompt": False,
        "keep": "idea inbox — no clear trigger or main-chain service path",
        "deprecation": "ideas are not requirements; use plan decisions instead",
    },
    "recipe": {
        "tier": DEPRECATED, "core": "",
        "caller": "", "trigger": "",
        "visible": False, "tested": "partial", "in_status_prompt": False,
        "keep": "workflow recipe templates — routing V2-A replaces this",
        "deprecation": "route explain/downgrade/substitute replaces recipe recommend",
    },
    "memory": {
        "tier": QUARANTINE, "core": "",
        "caller": "", "trigger": "",
        "visible": False, "tested": "partial", "in_status_prompt": False,
        "keep": "lesson memory — no clear trigger or main-chain service path",
        "deprecation": "memory suggest has no default trigger; use plan Risks instead",
    },
    "rule": {
        "tier": DEPRECATED, "core": "boundary",
        "caller": "scope-guard", "trigger": "on-write",
        "visible": False, "tested": "yes", "in_status_prompt": False,
        "keep": "project rules — negative rules still used by scope guard",
        "deprecation": "negative rules keep; positive/global rules are noise without trigger",
    },
    "asset": {
        "tier": DEPRECATED, "core": "",
        "caller": "", "trigger": "",
        "visible": False, "tested": "yes", "in_status_prompt": False,
        "keep": "asset init/refresh — tier 1 assets are silent background now",
        "deprecation": "asset commands replaced by plan Impact block + project-map on demand",
    },
    "audit-archive": {
        "tier": DEPRECATED, "core": "",
        "caller": "", "trigger": "",
        "visible": False, "tested": "partial", "in_status_prompt": False,
        "keep": "release audit — CI-only, not for agent use",
        "deprecation": "CI-only command; should not appear in agent help",
    },
}


def commands_by_tier(tier: str) -> List[str]:
    return sorted(k for k, v in COMMAND_MANIFEST.items() if v["tier"] == tier)


def visible_commands() -> List[str]:
    return sorted(k for k, v in COMMAND_MANIFEST.items() if v.get("visible", False))


def all_commands() -> List[str]:
    return sorted(COMMAND_MANIFEST.keys())



def side_channel_inventory() -> str:
    """Side-channel inventory — every non-PRIMARY command classified by main-chain service path.

    Format: command → tier | serves: node | trigger: condition | default: silent
    """
    lines = ["Side-Channel Inventory", "=" * 21, ""]
    lines.append("Non-primary commands classified by main-chain service path.")
    lines.append("Default: silent (in_status_prompt=false, visible=false).")
    lines.append("")
    for tier in [ADVANCED, INTERNAL, DEPRECATED, QUARANTINE]:
        cmds = commands_by_tier(tier)
        if not cmds:
            continue
        lines.append(f"{tier.upper()} ({len(cmds)}):")
        for cmd in cmds:
            e = COMMAND_MANIFEST[cmd]
            serves = e.get("core", "—")
            trigger = e.get("trigger", "—")
            tested = e.get("tested", "—")
            lines.append(f"  {cmd:16s} tier={tier:10s} serves={serves:16s} trigger={trigger}")
            if e.get("deprecation"):
                lines.append(f"  {'':16s}  {'':10s}  {'':16s}  ⚠ {e['deprecation'][:90]}")
            if e.get("note"):
                lines.append(f"  {'':16s}  {'':10s}  {'':16s}  ℹ {e['note'][:90]}")
        lines.append("")
    return "\n".join(lines)

def manifest_summary() -> str:
    lines = ["Command Manifest Summary", "=" * 24, ""]
    for tier in [PRIMARY, ADVANCED, INTERNAL, DEPRECATED, QUARANTINE]:
        cmds = commands_by_tier(tier)
        if not cmds:
            continue
        lines.append(f"{tier.upper()} ({len(cmds)}):")
        for cmd in cmds:
            entry = COMMAND_MANIFEST[cmd]
            core = entry["core"]
            lines.append(f"  {cmd:20s} → {core}")
            if entry.get("deprecation"):
                lines.append(f"  {'':20s}   DEPRECATED: {entry['deprecation'][:80]}")
            if entry.get("note"):
                lines.append(f"  {'':20s}   NOTE: {entry['note'][:80]}")
        lines.append("")
    return "\n".join(lines)
