"""Embedded status surface."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from ..constants import VERSION
from ..core.state.goal_ops import get_active_goal


def _read_json(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    if not path.exists():
        return default
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else default
    except Exception:
        return default


def cmd_status(args) -> None:
    root = Path.cwd()
    aiwf_state = root / ".aiwf" / "state" / "state.json"
    claude_settings = root / ".claude" / "settings.json"
    reasonix_settings = root / ".reasonix" / "settings.json"

    if not (aiwf_state.exists() and (reasonix_settings.exists() or claude_settings.exists())):
        print(f"AIWF V{VERSION}")
        print()
        print("No embedded AIWF installation found in this project.")
        print()
        print("Install the supported mainline:")
        print("  aiwf install claude      # Claude Code")
        print("  aiwf install reasonix    # Reasonix")
        return

    debug_mode = getattr(args, 'debug', False)
    prompt_mode = getattr(args, 'prompt', False)

    state = _read_json(root / ".aiwf" / "state" / "state.json", {})
    goal = get_active_goal(str(root))
    implementation = _read_json(root / ".aiwf" / "records" / "implementation.json", {})
    testing = _read_json(root / ".aiwf" / "records" / "testing.json", {"status": "missing"})
    review = _read_json(root / ".aiwf" / "records" / "review.json", {"result": "unknown", "closure_allowed": False, "blockers": []})
    fix_loop = _read_json(root / ".aiwf" / "state" / "fix-loop.json", {"status": "none"})

    if debug_mode:
        _print_status_debug(root, state, goal, implementation, testing, review, fix_loop,
                           reasonix_settings, claude_settings)
    elif prompt_mode:
        _print_status_prompt(root, state, goal, testing, review, fix_loop)
    else:
        _print_status_human(root, state, goal, implementation, testing, review, fix_loop)
    return


def _print_status_human(root, state, goal, implementation, testing, review, fix_loop):
    """Human-readable short status — V1: write permissions, reminders, next action."""
    product = "Reasonix" if (root / ".reasonix" / "settings.json").exists() else "Claude Code"
    print(f"AIWF V{VERSION} — {product}")
    print()

    phase = state.get("phase", "planning")
    goal_text = goal.get("current_goal") or goal.get("active_goal", "") or "(none)"
    active_task_id = state.get("active_task_id") or ""

    print(f"Phase: {phase}")
    if active_task_id:
        print(f"Active task: {active_task_id}")
    else:
        print(f"Active task: none")

    # ── Write permissions ──
    if not active_task_id:
        print(f"Project writes: blocked (no active task)")
        print(f"Governance writes: allowed")
    else:
        reqs = _read_task_requirements(root, active_task_id)
        if reqs.get("executor_required", True):
            print(f"Project writes: executor subagent required")
        else:
            print(f"Project writes: allowed (executor_required=false)")

    # ── Milestone reminder ──
    milestone_due = _milestone_due(root, state)
    if milestone_due:
        print("Milestone acceptance due: yes (use /aiwf-architect)")

    # ── Active task status ──
    if active_task_id:
        tstat = testing.get("status", "missing")
        rstat = review.get("result", "unknown")
        print(f"Testing: {tstat}  Review: {rstat}")
        if fix_loop.get("status") == "open":
            print(f"Fix-loop: OPEN (route={fix_loop.get('route', '?')})")
        if state.get("scope_violation"):
            print(f"Scope violation: unresolved")

    # ── Next action ──
    print(f"Next: {_next_human(phase, active_task_id, fix_loop, state, root)}")


def _read_task_requirements(root, task_id):
    try:
        tasks_data = _read_json(root / ".aiwf" / "state" / "tasks.json", {"tasks": []})
        for t in tasks_data.get("tasks", []) or []:
            if isinstance(t, dict) and t.get("id") == task_id:
                return t.get("requirements", {})
    except Exception:
        pass
    return {}


def _milestone_due(root, state):
    """Check if milestone assessment is due."""
    try:
        ms_data = _read_json(root / ".aiwf" / "state" / "milestones.json", {})
        active_ms = ms_data.get("active_milestone_id") or state.get("active_milestone_id") or ""
        if active_ms:
            for ms in ms_data.get("milestones", []) or []:
                if isinstance(ms, dict) and ms.get("id") == active_ms:
                    return ms.get("status") not in ("closed", "completed")
    except Exception:
        pass
    return False


def _milestone_acceptance_confirmed(root, milestone_id):
    if not milestone_id:
        return False
    data = _read_json(root / ".aiwf" / "state" / "milestones.json", {})
    for milestone in data.get("milestones", []) or []:
        if not isinstance(milestone, dict):
            continue
        current_id = milestone.get("milestone_id") or milestone.get("id")
        if current_id == milestone_id:
            acceptance = milestone.get("user_acceptance", {}) or {}
            return acceptance.get("status") == "confirmed"
    return False


def _milestone_detail(root, state):
    """Return milestone problems (activatable, closable, blocked). Only when triggered."""
    problems = []
    try:
        ms_data = _read_json(root / ".aiwf" / "state" / "milestones.json", {})
        plans_data = _read_json(root / ".aiwf" / "state" / "plans.json", {"plans": []})
        all_plans = plans_data.get("plans", []) or []
        all_ms = ms_data.get("milestones", []) or []
        tasks_data = _read_json(root / ".aiwf" / "state" / "tasks.json", {"tasks": []})
        all_tasks = tasks_data.get("tasks", []) or []
        active_ms_id = state.get("active_milestone_id") or ""

        task_by_id = {str(t.get("id")): t for t in all_tasks if isinstance(t, dict) and t.get("id")}

        for ms in all_ms:
            if not isinstance(ms, dict):
                continue
            mid = ms.get("id") or ms.get("milestone_id") or ""
            if not mid or ms.get("status") == "closed":
                continue

            blockers = []
            for pid in (ms.get("plan_ids", []) or []):
                plan = next((p for p in all_plans
                            if str(p.get("plan_id") or p.get("id") or "") == str(pid)), None)
                if not plan:
                    blockers.append(f"plan missing: {pid}")
                elif plan.get("status") not in ("complete", "completed") or (plan.get("remaining_task_ids", []) or []):
                    blockers.append(f"plan incomplete: {pid}")

            for tid in (ms.get("task_ids", []) or []):
                t = task_by_id.get(str(tid))
                if not t:
                    blockers.append(f"task missing: {tid}")
                elif t.get("status") not in ("closed", "cancelled"):
                    blockers.append(f"task not closed: {tid}")

            it = ms.get("integration_test", {}) or {}
            if it.get("status") != "passed":
                blockers.append("integration test not passed")
            ar = ms.get("architecture_review", {}) or {}
            if ar.get("status") == "issues_found":
                blockers.append("architecture review has unresolved issues")
            elif ar.get("status") not in ("intact",):
                blockers.append("architecture review missing")

            if not blockers:
                problems.append(
                    f"milestone {mid} closable: run /aiwf-architect with milestone-acceptance lens to assess and close"
                )
            elif mid == active_ms_id:
                problems.append(f"milestone {mid} blocked: {'; '.join(blockers[:3])}")
    except Exception:
        pass
    return problems


def _next_human(phase, active_task_id, fix_loop, state, root):
    """Return a concise next-action line based on phase and state."""
    if fix_loop.get("status") == "open":
        route = fix_loop.get("route", "planner")
        return f"resolve fix-loop (route={route})"
    if state.get("scope_violation"):
        return "resolve scope violation before any task activation"
    if not active_task_id:
        remaining = _remaining_tasks(root)
        if remaining:
            return f"aiwf-planner ({len(remaining)} task(s) remaining)"
        return "aiwf-planner"
    if phase in ("executing", "implementing"):
        return "complete implementation, then record testing"
    if phase == "testing":
        return "complete testing, then record review"
    if phase == "reviewing":
        return "complete review, then close task"
    if phase == "closing":
        return "resolve blockers, then close task"
    if phase == "closed":
        return "planner reviews closed state, plans next cycle"
    return "planner decides next step"


def _remaining_tasks(root):
    """Return remaining non-closed task IDs, excluding the just-closed one."""
    try:
        tasks_data = _read_json(root / ".aiwf" / "state" / "tasks.json", {"tasks": []})
        return [
            t.get("id", "") for t in tasks_data.get("tasks", []) or []
            if isinstance(t, dict) and t.get("status") not in ("closed", "cancelled")
        ][:5]
    except Exception:
        return []


def _ready_to_close_missing_calibration(root, state, testing, review, fix_loop):
    """Return true when close is allowed but Task.md lacks final reality notes."""
    task_id = state.get("active_task_id") or ""
    if not _ready_to_close(state, testing, review, fix_loop):
        return False

    task_doc = root / ".aiwf" / "tasks" / f"{task_id}.md"
    if not task_doc.exists():
        return False
    try:
        return "## Closure Calibration" not in task_doc.read_text(
            encoding="utf-8",
            errors="ignore",
        )
    except Exception:
        return False


def _ready_to_close(state, testing, review, fix_loop):
    task_id = state.get("active_task_id") or ""
    if not task_id:
        return False
    if fix_loop.get("status") == "open" or state.get("scope_violation"):
        return False
    if testing.get("status") not in ("adequate", "passed"):
        return False
    return review.get("result") == "accepted" and bool(review.get("closure_allowed", False))


def _planner_plan_focus(root, state):
    """Identify the useful Planner step between Tasks or at Plan completion."""
    if state.get("active_task_id"):
        return ""
    plan_id = str(state.get("active_plan_id") or "")
    if not plan_id:
        return ""

    plans = _read_json(root / ".aiwf" / "state" / "plans.json", {"plans": []})
    plan = next(
        (
            item for item in plans.get("plans", []) or []
            if isinstance(item, dict)
            and str(item.get("plan_id") or item.get("id") or "") == plan_id
        ),
        None,
    )
    if not plan or str(plan.get("status") or "open") in ("closed", "cancelled"):
        return ""

    task_ids = [str(item) for item in plan.get("task_ids", []) or [] if item]
    if not task_ids:
        return ""
    task_status = dict(plan.get("task_status", {}) or {})
    tasks = _read_json(root / ".aiwf" / "state" / "tasks.json", {"tasks": []})
    for task in tasks.get("tasks", []) or []:
        if isinstance(task, dict) and str(task.get("id") or "") in task_ids:
            task_status[str(task["id"])] = str(task.get("status") or "unknown")

    closed = [item for item in task_ids if task_status.get(item) == "closed"]
    remaining = [
        item for item in task_ids
        if task_status.get(item) not in ("closed", "cancelled")
    ]
    if closed and remaining:
        return "After a Task"
    if not remaining:
        return "Close Out a Plan"
    return ""


def _status_prompt_action(
    primary_skill, state, testing, review, fix_loop, calibration_missing,
    ready_to_close, plan_focus="",
):
    if fix_loop.get("status") == "open":
        route = fix_loop.get("route") or "planner"
        if route == "planner":
            return (
                "decide returned finding",
                "load aiwf-planner, verify the finding, and decide whether the active task still holds",
            )
        if route == "environment":
            return (
                "resolve environment blocker",
                "load aiwf-planner, verify the blocker, and ask the user for any required environment action",
            )
        return (
            f"resolve fix-loop ({route})",
            f"load {primary_skill}, resolve the required work, verify it, then run aiwf fixloop resolve",
        )
    if state.get("scope_violation"):
        return (
            "resolve scope violation",
            "revert or account for violating files before continuing",
        )
    if review.get("result") in ("rejected", "needs_fix", "scope_violation"):
        return (
            "handle review finding",
            "route the finding to Planner/fix-loop; do not close",
        )
    if calibration_missing:
        return (
            "calibrate before close",
            "write Closure Calibration, then run aiwf status --prompt again",
        )
    if ready_to_close:
        return (
            "close task",
            "run aiwf task close after confirming gates remain clean",
        )
    if plan_focus == "After a Task":
        return (
            "reconcile the completed Task with its Plan",
            "load aiwf-planner, compare the actual result with the Plan and remaining Task assumptions before choosing the next Task",
        )
    if plan_focus == "Close Out a Plan":
        return (
            "close out the Plan",
            "load aiwf-planner, confirm the delivered parts work together before asking the human to merge",
        )

    phase = state.get("phase", "planning")
    if primary_skill == "aiwf-architect":
        return (
            "architect review",
            "run the selected Architect lens and report findings",
        )
    if primary_skill == "aiwf-implement":
        return (
            "implement",
            "load aiwf-implement and serve the active Task.md contract",
        )
    if primary_skill == "aiwf-test":
        return (
            "test",
            "load aiwf-test, prove the Task.md claim, and record testing",
        )
    if primary_skill == "aiwf-review":
        return (
            "review",
            "load aiwf-review and judge whether implementation, testing, and the final snapshot hold",
        )
    if primary_skill == "aiwf-close":
        return (
            "close",
            "load aiwf-close and complete closure only if gates pass",
        )
    if phase in ("planning", "planned", "discussing"):
        return (
            "plan before work",
            "load aiwf-planner, read reality, write/repair contract, and critique before activation",
        )
    return (
        primary_skill.replace("aiwf-", "") or "plan",
        f"load {primary_skill} and follow status requirements",
    )


def _print_status_prompt(root, state, goal, testing, review, fix_loop):
    """AI prompt injection — minimal. Reads skill-map.json for dispatch, outputs required skills + required read."""
    phase = state.get("phase", "planning")
    task_id = state.get("active_task_id", "")
    plan_id = state.get("active_plan_id", "")

    # Read skill-map.json for dispatch
    skill_map_path = root / ".aiwf" / "config" / "skill-map.json"
    required_skills = []
    primary_skill = ""
    if skill_map_path.exists():
        try:
            sm = json.loads(skill_map_path.read_text(encoding="utf-8"))
            phase_skills = sm.get("phase_skills", {})
            required_skills = phase_skills.get(phase, phase_skills.get("planning", []))
            primary_skill = required_skills[0] if required_skills else ""
        except Exception:
            pass
    if not primary_skill:
        primary_skill = {"planning": "aiwf-planner", "executing": "aiwf-implement",
                         "testing": "aiwf-test", "reviewing": "aiwf-review",
                         "closing": "aiwf-close", "blocked": "aiwf-planner",
                         "closed": "aiwf-planner"}.get(phase, "aiwf-planner")

    # Check if active task is a milestone verification task
    task_kind = ""
    task_milestone_id = ""
    if task_id:
        try:
            tasks_data = _read_json(root / ".aiwf" / "state" / "tasks.json", {"tasks": []})
            for t in tasks_data.get("tasks", []) or []:
                if isinstance(t, dict) and t.get("id") == task_id:
                    task_kind = t.get("kind", "") or ""
                    task_milestone_id = t.get("milestone_id", "") or ""
                    break
        except Exception:
            pass

    # Required read: active task narrative doc
    required_read = []
    if task_id:
        task_doc = root / ".aiwf" / "tasks" / f"{task_id}.md"
        if task_doc.exists():
            required_read.append(f".aiwf/tasks/{task_id}.md")
        # Milestone verification: also read the milestone doc
        if task_kind == "milestone_verification" and task_milestone_id:
            ms_doc = root / ".aiwf" / "milestones" / f"{task_milestone_id}.md"
            if ms_doc.exists():
                required_read.append(f".aiwf/milestones/{task_milestone_id}.md")
    if fix_loop.get("status") == "open":
        required_read.append(".aiwf/state/fix-loop.json")

    # Override primary skill for milestone verification tasks
    if task_kind == "milestone_verification":
        primary_skill = "aiwf-architect"
        required_skills = ["aiwf-architect"]

    if fix_loop.get("status") == "open":
        route_skill = {
            "planner": "aiwf-planner",
            "executor": "aiwf-implement",
            "tester": "aiwf-test",
            "environment": "aiwf-planner",
        }.get(fix_loop.get("route") or "planner", "aiwf-planner")
        primary_skill = route_skill
        required_skills = [route_skill]

    task_ready = _ready_to_close(state, testing, review, fix_loop)
    if task_kind == "milestone_verification":
        task_ready = task_ready and _milestone_acceptance_confirmed(
            root, task_milestone_id
        )
    calibration_missing = (
        _ready_to_close_missing_calibration(root, state, testing, review, fix_loop)
        if task_ready else False
    )
    if task_ready:
        if calibration_missing:
            primary_skill = "aiwf-planner"
            required_skills = ["aiwf-planner"]
        else:
            primary_skill = "aiwf-close"
            required_skills = ["aiwf-close"]

    plan_focus = _planner_plan_focus(root, state)
    if plan_focus:
        primary_skill = "aiwf-planner"
        required_skills = ["aiwf-planner"]
        plan_doc = root / ".aiwf" / "plans" / f"{plan_id}.md"
        if plan_doc.exists():
            required_read.append(f".aiwf/plans/{plan_id}.md")

    if primary_skill == "aiwf-planner" and (root / ".aiwf" / "mission.md").exists():
        required_read.append(".aiwf/mission.md")

    next_action, do_action = _status_prompt_action(
        primary_skill, state, testing, review, fix_loop, calibration_missing,
        task_ready, plan_focus,
    )

    # Output
    print(f"[ATTN] /{primary_skill}")
    print(f"Do: {do_action}")
    print(f"Next: {next_action}")
    if plan_focus:
        print(f"Focus: {plan_focus}")
    if required_skills:
        print(f"Required skills: {', '.join(required_skills)}")
    if required_read:
        print(f"Required read: {', '.join(required_read)}")

    parts = [f"Phase: {phase}"]
    if task_id:
        parts.append(f"task={task_id}")
    if plan_id:
        parts.append(f"plan={plan_id}")
    print("  ".join(parts))

    # Health
    health_ok = True
    if fix_loop.get("status") == "open":
        route = fix_loop.get("route", "?")
        print(f"BLOCKED: fix-loop open -> {route}")
        health_ok = False
    if state.get("scope_violation"):
        print("BLOCKED: scope violation")
        health_ok = False
    if health_ok:
        print("Health: ok")

    # Problems — only shown when something needs attention
    problems = []

    # Recovery: fix-loop open → specific instructions
    if fix_loop.get("status") == "open":
        route = fix_loop.get("route") or "planner"
        if fix_loop.get("escalation_required"):
            problems.append(
                "fix-loop: resolve required_fixes, verify, then aiwf fixloop resolve "
                "(USER DECISION REQUIRED)"
            )
        elif route == "planner":
            problems.append(
                "fix-loop: Planner must verify the finding and decide whether the active task still holds"
            )
        else:
            problems.append(
                f"fix-loop: dispatch {route} to resolve required_fixes, "
                "then aiwf fixloop resolve"
            )

    # Recovery: scope violation
    if state.get("scope_violation"):
        problems.append(
            "scope violation: revert violating files, "
            "then aiwf fixloop resolve"
        )

    # Recovery: review blocked
    review_result = review.get("result", "")
    if review_result in ("rejected", "needs_fix", "scope_violation"):
        problems.append(
            f"review: {review_result} — resolve review blockers before close"
        )
    elif calibration_missing:
        problems.append(
            "closure calibration missing: run aiwf task calibrate --summary \"<actual completion; notable deviation; follow-up if any>\" before task close"
        )

    # Milestone detailed signals (only when activatable/closable)
    ms_problems = _milestone_detail(root, state)
    problems.extend(ms_problems)

    if problems:
        print("")
        print("Problems:")
        for p in problems[:5]:
            print(f"  - {p}")

    # Write permissions for no-active-task state
    if not task_id:
        if problems:
            print("")
        print("Allowed writes:")
        print("  - governance/planning (.aiwf/goals/, .aiwf/plans/, .aiwf/tasks/, .aiwf/config/)")
        print("  - .claude/ skills and agent templates")
        print("No project writes until a task is activated.")

    print(f"Do now: {do_action}")


def _print_status_debug(root, state, goal, implementation, testing, review, fix_loop,
                        reasonix_settings, claude_settings):
    """Full debug panel — current verbose output with all sections."""
    try:
        from ..core.task_ledger import ledger_summary
        task_summary = ledger_summary(str(root))
    except Exception:
        task_summary = {"active_task_ids": [], "counts": {}}
    blockers = []
    if fix_loop.get("status") == "open":
        blockers.append("fix-loop open")
    if state.get("scope_violation"):
        blockers.append("scope violation")
    if review.get("result") not in ("accepted", "unknown"):
        blockers.append(f"review {review['result']}")
    health = "clear" if not blockers else f"blocked ({len(blockers)}): {', '.join(blockers[:3])}"

    product = "Reasonix" if reasonix_settings.exists() else "Claude Code"
    print(f"AIWF V{VERSION} — Embedded {product}")
    print()

    print("── Control Panel ──")
    goal_text = goal.get("current_goal") or goal.get("active_goal", "") or "(none)"
    print(f"  Goal:     v{goal.get('goal_version', 1)}/{goal.get('goal_status', 'discussion')} / {goal_text[:120]}")
    print(f"  Phase:    {state.get('phase', 'unknown')}")
    print(f"  Health:   {health}")
    print(f"  Next:     {_next_action(state, review, fix_loop)}")
    print()

    # Milestone
    active_milestone_id = state.get("active_milestone_id", "")
    if not active_milestone_id:
        try:
            m_data = _read_json(root / ".aiwf" / "state" / "milestones.json", {})
            active_milestone_id = m_data.get("active_milestone_id", "") or ""
        except Exception:
            pass
    if active_milestone_id:
        from ..core.state.milestone_ops import get_milestone
        ms = get_milestone(str(root), active_milestone_id)
        print(f"  Milestone: {active_milestone_id}  status={ms.get('status','?')}  title={ms.get('title','')[:60]}")
    else:
        print(f"  Milestone: none")

    print("── Quality & Closure ──")
    print(f"  Testing:  {testing.get('status', 'missing')}")
    print(f"  Review:   {review.get('result', 'unknown')}  review_gate={review.get('closure_allowed', False)}")
    print(f"  Implementation: {'recorded' if implementation.get('implementation_ref') else 'missing'}")
    print(f"  Fix-loop: {fix_loop.get('status', 'none')}")
    print(f"  Cleanup:  {review.get('cleanup_status', '?')}  stale_items={len(review.get('stale_items', []) or [])}")
    print(f"  Structure:{review.get('structure_status', '?')}")

    print(f"  Closure:  {'task close pending' if state.get('phase') == 'closing' else 'closed' if state.get('phase') == 'closed' else 'not ready'}")
    print()

    print("── Awareness ──")
    active_tasks = task_summary.get("active_task_ids", [])
    task_counts = task_summary.get("counts", {})
    total_tasks = sum(task_counts.values())
    print(f"  Task ledger:      {len(active_tasks)} active / {total_tasks} tasks")
    try:
        from ..core.state.plan_ops import load_plans, plan_readiness
        plan_entries = [
            p for p in load_plans(str(root)).get("plans", []) or []
            if isinstance(p, dict) and p.get("status") != "complete"
        ]
        ready_plans = []
        blocked_plans = []
        for plan in plan_entries:
            plan_id = str(plan.get("plan_id") or plan.get("id") or "")
            readiness = plan_readiness(str(root), plan_id)
            if readiness["ready"]:
                ready_plans.append(plan_id)
            else:
                blocked_plans.append(
                    f"{plan_id} ({'; '.join(readiness['blockers'])})"
                )
        summary = f"{len(ready_plans)} ready / {len(blocked_plans)} blocked"
        print(f"  Plan readiness:   {summary}")
        if ready_plans:
            print(f"  Ready Plans:      {', '.join(ready_plans)}")
        for blocked in blocked_plans[:3]:
            print(f"  Blocked Plan:     {blocked}")
    except Exception:
        print("  Plan readiness:   unknown")
    print()

    print("── Detail ──")
    print("  .aiwf/state + .aiwf/records   machine state")
    print()
    print("  CLI: aiwf doctor | aiwf status --prompt | aiwf sync --check")


def _next_action(state, review, fix_loop):
    phase = state.get("phase", "planning")
    if fix_loop.get("status") == "open":
        return "resolve fix-loop"
    if state.get("scope_violation"):
        return "resolve scope violation"
    if phase in ("planning", "discussing", "planned"):
        return "load /aiwf-planner"
    if phase in ("executing", "implementing"):
        return "ask Planner to direct testing"
    if phase == "testing":
        return "ask Planner to direct review"
    if phase == "reviewing":
        return "ask Planner to close" if review.get("result") == "accepted" else f"resolve review: {review.get('result', 'unknown')}"
    if phase == "closing":
        return "Stop hook will verify gates"
    if phase == "closed":
        return "run aiwf status and aiwf doctor"
    return "discuss with Planner"
