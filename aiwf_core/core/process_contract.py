"""Planner-facing workflow explanation derived from machine-readable state."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .state.goal_ops import get_active_goal


def _read(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _base_recovery() -> Dict[str, Any]:
    return {
        "state": "clear",
        "category": "",
        "owner": "planner",
        "primary": "",
        "legal_options": [],
        "forbidden": [],
        "user_decision_required": False,
        "why": "",
    }


def _has_evidence(base_dir: str) -> bool:
    """Check if any evidence records exist for the active task."""
    evidence = _read(Path(base_dir) / ".aiwf" / "records" / "evidence.json", {"records": []})
    return len(evidence.get("records", []) or []) > 0


def _blocked(
    category: str,
    owner: str,
    primary: str,
    why: str,
    legal_options: List[str],
    forbidden: Optional[List[str]] = None,
    user_decision_required: bool = False,
) -> Dict[str, Any]:
    return {
        "state": "blocked",
        "category": category,
        "owner": owner,
        "primary": primary,
        "legal_options": legal_options,
        "forbidden": forbidden or [],
        "user_decision_required": user_decision_required,
        "why": why,
    }


def _recovery_guidance(
    base_dir: str,
    state: Dict[str, Any],
    goal: Dict[str, Any],
    testing: Dict[str, Any],
    review: Dict[str, Any],
    fix_loop: Dict[str, Any],
) -> Dict[str, Any]:
    """Return the primary recovery path without collapsing normal workflow topology."""
    root = Path(base_dir)
    level = state.get("workflow_level", "L1_review_light")
    request_mode = state.get("request_mode", "execution")
    active_task = state.get("active_task_id")

    if fix_loop.get("status") == "open":
        route = fix_loop.get("route") or "planner"
        needs_user = route == "planner" or bool(fix_loop.get("escalation_required"))
        return _blocked(
            "fix_loop",
            "user" if needs_user else route,
            f"resolve fix-loop via route={route}",
            "An open fix-loop freezes forward progress until its required fixes and verification are satisfied.",
            [
                "follow required_fixes and required_verification, then run aiwf fixloop resolve --resolution '...'",
                "if route=planner or escalation_required=true, ask the user for the decision before more work",
            ],
            [
                "do not start unrelated implementation",
                "do not edit fix-loop.json by hand",
                "do not lower workflow level to escape the fix-loop",
            ],
            user_decision_required=needs_user,
        )

    if state.get("scope_violation"):
        events = [
            event for event in (review.get("scope_violation_events", []) or [])
            if isinstance(event, dict) and event.get("status", "recorded") != "resolved_reverted"
        ]
        paths = ", ".join(str(event.get("path")) for event in events[:3] if event.get("path"))
        return _blocked(
            "scope",
            "planner",
            "recover scope violation",
            "Past out-of-scope writes cannot be legalized by widening context after the fact.",
            [
                "revert the originally violating files" + (f": {paths}" if paths else ""),
                "run aiwf fixloop resolve --resolution '<what was reverted>' after mechanical verification passes",
                "ask the user whether the desired extra work should become a new scoped task",
            ],
            [
                "do not widen allowed_write retrospectively",
                "do not close while scope_violation=true",
                "do not hand-edit review/state JSON to clear the violation",
            ],
            user_decision_required=not paths,
        )

    if request_mode in ("discussion", "clarification", "research"):
        return {
            "state": "open",
            "category": request_mode,
            "owner": "planner",
            "primary": f"continue {request_mode}",
            "legal_options": [
                f"continue {request_mode} without project writes",
                "ask the user to confirm when ready to switch request_mode=execution",
            ],
            "forbidden": ["do not activate implementation while request_mode is non-execution"],
            "user_decision_required": request_mode != "discussion",
            "why": "Non-execution request modes intentionally keep topology open while blocking implementation.",
        }

    if request_mode == "spike" or state.get("workflow_pattern") == "spike_first":
        return {
            "state": "open",
            "category": "spike",
            "owner": "planner",
            "primary": "finish spike and record findings",
            "legal_options": [
                "record spike findings",
                "ask the user to confirm execution after feasibility is known",
            ],
            "forbidden": ["do not treat spike output as final implementation closure"],
            "user_decision_required": False,
            "why": "Spike topology permits exploration before the final execution contract.",
        }

    if state.get("external_research_required") and request_mode == "execution":
        try:
            from .external_research import research_requirement_blocker
            if research_requirement_blocker(base_dir):
                return _blocked(
                    "user_decision",
                    "planner",
                    "resolve external research requirement",
                    "Execution requires promoted external research or an explicit Planner/user skip decision.",
                    [
                        "promote a relevant research record with aiwf research promote <ID> --decision '...'",
                        "ask the user whether to skip external research, then run aiwf research skip --reason '...'",
                    ],
                    [
                        "do not start implementation",
                        "do not silently clear external_research_required",
                    ],
                    user_decision_required=True,
                )
        except Exception:
            pass

    if request_mode == "execution" and not goal.get("confirmed") and not active_task:
        return _blocked(
            "user_decision",
            "planner",
            "ask the user to confirm the goal before execution",
            "Goal is not confirmed. Planner must present the plan and get explicit user approval.",
            [
                "present the plan to the user and ask for confirmation",
                "run aiwf state set-goal-confirmed after user approves",
            ],
            [
                "do not activate tasks or start implementation",
                "do not treat discussion as confirmed execution intent",
            ],
            user_decision_required=True,
        )

    try:
        from .capabilities import capability_use_blockers
        cap_blockers = capability_use_blockers(base_dir)
        if cap_blockers:
            return _blocked(
                "user_decision",
                "planner",
                "resolve planned external capability decision",
                cap_blockers[0],
                [
                    "record a decision with aiwf capability decide <ID> --decision '...'",
                    "ask the user whether to use, avoid, or replace the overlapping capability",
                ],
                [
                    "do not use lifecycle-overlap external capabilities without an explicit decision",
                    "do not delete capability registry entries to bypass the gate",
                ],
                user_decision_required=True,
            )
    except Exception:
        pass

    if not active_task and state.get("phase") == "closed":
        return _base_recovery()

    if not active_task:
        active_plan = state.get("active_plan_id")
        if active_plan and request_mode == "execution":
            # Skip if the plan is already complete (all tasks closed)
            plan_complete = False
            try:
                from .state.plan_ops import get_plan
                plan = get_plan(base_dir, active_plan, migrate=False)
                remaining = plan.get("remaining_task_ids", []) or []
                plan_complete = not remaining
            except Exception:
                pass
            if not plan_complete:
                return _blocked(
                    "plan_only_drift",
                    "planner",
                    f"freeze execution contract and activate planned task {active_plan}",
                "A human-readable plan exists, but no active task/context execution contract is running.",
                [
                    "record quality policy and Architecture/Evaluation Brief for the plan",
                    f"set allowed_write, forbidden_write, and purpose on Plan {active_plan}",
                    f"run aiwf task plan <TASK-ID> --plan {active_plan} --title '...'",
                    "run aiwf task activate <TASK-ID>",
                    "or switch request_mode to discussion/research/spike if execution is not confirmed",
                ],
                [
                    "do not keep rewriting the plan as progress",
                    "do not dispatch implementation without task activation",
                    "do not treat plan.md as evidence or mechanical truth",
                ],
            )
        return _blocked(
            "missing_step",
            "planner",
            "plan and activate one scoped task",
            "Project writes need an active task with Plan scope and mechanical routing.",
            [
                "create a Plan with allowed_write, forbidden_write, and purpose",
                "run aiwf task plan <TASK-ID> --plan <PLAN-ID> --title '...'",
                "run aiwf task activate <TASK-ID>",
                "run aiwf status after activation and explain current/background routing signals",
            ],
            [
                "do not edit project files before task activation",
                "do not rely on plan.md as mechanical truth",
            ],
        )

    # V1: Subagent dispatch is governed by Task.requirements, not workflow_level.
    # Check readiness against actual Task.requirements rather than L2/L3 gates.
    active_task_id = state.get("active_task_id")
    if active_task_id:
        try:
            from .task_ledger import load_ledger, _find
            tasks = load_ledger(base_dir).get("tasks", [])
            task = _find(tasks, active_task_id)
            if task:
                reqs = task.get("requirements", {})
                # Check in workflow order: executor → tester → reviewer
                if reqs.get("tester_required") and testing.get("status") not in ("adequate", "passed"):
                    return _blocked(
                        "missing_step",
                        "tester",
                        "dispatch independent Tester",
                        "Task.requirements.tester_required=true but testing not yet adequate/passed.",
                        ["dispatch aiwf-tester as a separate subagent role"],
                        ["do not close without adequate testing"],
                    )
                if reqs.get("reviewer_required") and review.get("result") != "accepted":
                    return _blocked(
                        "missing_step",
                        "reviewer",
                        "dispatch independent Reviewer",
                        "Task.requirements.reviewer_required=true but review not yet accepted.",
                        ["dispatch aiwf-reviewer as a separate subagent role"],
                        ["do not close without accepted review"],
                    )
        except Exception:
            pass

    pending = [
        o for o in (review.get("adversarial_observations", []) or [])
        if isinstance(o, dict) and o.get("disposition") == "pending"
    ]
    if pending:
        return _blocked(
            "missing_step",
            "planner",
            "disposition adversarial observations",
            "Pending adversarial observations must be resolved before close.",
            ["record structured dispositions for pending adversarial observations"],
            ["do not close while adversarial observations are pending"],
        )

    if review.get("result") == "accepted":
        return {
            "state": "ready",
            "category": "close",
            "owner": "planner",
            "primary": "run aiwf task close <TASK-ID>",
            "legal_options": ["run aiwf task close <TASK-ID>"],
            "forbidden": ["do not close without resolving all blockers"],
            "user_decision_required": False,
            "why": "All requirements satisfied. Ready to close.",
        }

    return _base_recovery()


def build_activation_summary(base_dir: str) -> str:
    """Build a user-facing activation summary. Two sections: what we're doing
    (project plan, for the user) and how we're doing it (governance, for a glance).
    """
    root = Path(base_dir)
    state = _read(root / ".aiwf" / "state" / "state.json", {})
    goal = get_active_goal(base_dir)
    plans = _read(root / ".aiwf" / "state" / "plans.json", {})
    lines = []
    warns = []

    active_goal = goal.get("active_goal") or goal.get("current_goal", "") or "(none)"
    level = state.get("workflow_level", "L1_review_light")

    # ── Project Plan ──
    lines.append("## What We're Doing")
    lines.append(f"  {active_goal[:200]}")

    # Scope is mechanical Plan truth. Context remains advisory dispatch data.
    active_plan = None
    active_plan_id = state.get("active_plan_id", "") or ""
    for plan in plans.get("plans", []):
        if plan.get("plan_id") == active_plan_id:
            active_plan = plan
            break
    if active_plan:
        aw = active_plan.get("allowed_write", []) or []
        fw = active_plan.get("forbidden_write", []) or []
        if aw:
            lines.append(f"  Files: {', '.join(aw[:5])}" + (f" (+{len(aw)-5} more)" if len(aw) > 5 else ""))
        if fw:
            lines.append(f"  Forbidden: {', '.join(fw[:3])}")

    # Acceptance criteria
    brief = goal.get("quality_brief", {})
    criteria = brief.get("acceptance_criteria", []) or []
    if criteria:
        lines.append(f"  Success: {', '.join(criteria[:3])}")

    # ── Governance ──
    lines.append("")
    lines.append("## Process (glance, not read)")
    # V1: Subagent dispatch is decided by Task.requirements, not workflow_level
    active_task_id = state.get("active_task_id")
    if active_task_id:
        try:
            from .task_ledger import load_ledger, _find
            tasks = load_ledger(base_dir).get("tasks", [])
            task = _find(tasks, active_task_id)
            if task:
                reqs = task.get("requirements", {})
                roles = []
                if reqs.get("executor_required"): roles.append("executor")
                if reqs.get("tester_required"): roles.append("tester")
                if reqs.get("reviewer_required"): roles.append("reviewer")
                lines.append(f"  Required roles: {', '.join(roles) if roles else 'none (main model)'}")
        except Exception:
            pass

    if not goal.get("confirmed", True):
        warns.append("Goal not confirmed by user — ask before proceeding")

    if warns:
        lines.append("")
        for w in warns:
            lines.append(f"  ! {w}")

    return "\n".join(lines)


def planner_process_guidance(base_dir: str) -> Dict[str, Any]:
    """Return actionable guidance: what Planner must do, should do, and may consider."""
    root = Path(base_dir)
    state = _read(root / ".aiwf" / "state" / "state.json", {})
    goal = get_active_goal(base_dir)
    testing = _read(root / ".aiwf" / "records" / "testing.json", {})
    review = _read(root / ".aiwf" / "records" / "review.json", {})
    fix_loop = _read(root / ".aiwf" / "state" / "fix-loop.json", {})
    level = state.get("workflow_level", "L1_review_light")
    request_mode = state.get("request_mode", "execution")
    active_task = state.get("active_task_id")
    required: List[str] = []
    advisory: List[str] = []

    # Fix-loop blocks everything else
    if fix_loop.get("status") == "open":
        route = fix_loop.get("route") or "planner"
        esc = " (escalated)" if fix_loop.get("escalation_required") else ""
        required.append(f"Resolve fix-loop via route={route}{esc}: aiwf fixloop resolve --resolution '...'")

    # Scope violation
    if state.get("scope_violation"):
        required.append("Scope violation: revert violating files, then aiwf fixloop resolve")

    # Plan/task activation advisory
    if not active_task and state.get("phase") != "closed" and request_mode not in ("discussion", "clarification", "research"):
        plan_id = state.get("active_plan_id", "")
        if plan_id:
            advisory.append(f"Plan {plan_id} exists without active task; consider aiwf task activate")
        else:
            advisory.append("Consider planning a task: aiwf plan create ... && aiwf task activate")

    # V1: Task.requirements controls dispatch. Check if requirements are satisfied.
    if active_task:
        try:
            from .task_ledger import load_ledger, _find
            tasks = load_ledger(base_dir).get("tasks", [])
            task = _find(tasks, active_task)
            if task:
                reqs = task.get("requirements", {})
                if reqs.get("executor_required") and not _has_evidence(base_dir):
                    required.append("Task.requirements.executor_required=true: record executor evidence")
                if reqs.get("tester_required") and testing.get("status") not in ("adequate", "passed"):
                    required.append("Task.requirements.tester_required=true: record testing")
                if reqs.get("reviewer_required") and review.get("result") != "accepted":
                    required.append("Task.requirements.reviewer_required=true: record accepted review")
        except Exception:
            pass

    recovery = _recovery_guidance(base_dir, state, goal, testing, review, fix_loop)
    # V1: Task.requirements controls dispatch, not these legacy topology fields.
    # Keep them for backward-compat with debug display but derive safe defaults.
    return {
        "workflow_level": level,
        "execution_topology": "light_review",
        "verification_need": "standard",
        "review_need": "optional_light_review",
        "required_now": required,
        "recovery": recovery,
        "advisory": advisory,
    }
