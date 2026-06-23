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
    # Merge routing state (V2: lives in runtime/internal/, not state.json)
    try:
        from ..core.task_ledger import load_routing_state
        routing = load_routing_state(str(root))
        for k, v in routing.items():
            if k not in state or state.get(k) in (None, "", [], 0, False):
                state[k] = v
    except Exception:
        pass
    goal = get_active_goal(str(root))
    evidence = _read_json(root / ".aiwf" / "records" / "evidence.json", {"records": []})
    testing = _read_json(root / ".aiwf" / "records" / "testing.json", {"status": "missing"})
    review = _read_json(root / ".aiwf" / "records" / "review.json", {"result": "unknown", "closure_allowed": False, "blockers": []})
    fix_loop = _read_json(root / ".aiwf" / "state" / "fix-loop.json", {"status": "none"})

    if debug_mode:
        _print_status_debug(root, state, goal, evidence, testing, review, fix_loop,
                           reasonix_settings, claude_settings)
    elif prompt_mode:
        _print_status_prompt(root, state, goal, testing, review, fix_loop)
    else:
        _print_status_human(root, state, goal, evidence, testing, review, fix_loop)
    return


def _print_status_human(root, state, goal, evidence, testing, review, fix_loop):
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

    # ── Reminders (advisory, not gates) ──
    architect_due = _architect_due(root, state)
    milestone_due = _milestone_due(root, state)
    if architect_due or milestone_due:
        print(f"Architect due: {'yes' if architect_due else 'no'}")
        if milestone_due: print(f"Milestone acceptance due: yes (use /aiwf-architect)")

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


def _architect_due(root, state):
    """Check if periodic architecture review is due (advisory only)."""
    try:
        from ..core.task_gravity import should_trigger_architecture_review
        trigger = should_trigger_architecture_review(str(root))
        return trigger.get("should_trigger", False)
    except Exception:
        return False


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
                elif t.get("status") not in ("closed", "rejected"):
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
            if isinstance(t, dict) and t.get("status") not in ("closed", "rejected")
        ][:5]
    except Exception:
        return []


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

    # Override primary skill for milestone verification tasks
    if task_kind == "milestone_verification":
        primary_skill = "aiwf-architect"
        required_skills = ["aiwf-architect"]

    # Output
    print(f"[ATTN] /{primary_skill}")
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
        if route == "planner" or fix_loop.get("escalation_required"):
            problems.append(
                "fix-loop: resolve required_fixes, verify, then aiwf fixloop resolve "
                "(USER DECISION REQUIRED)"
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

    # Milestone detailed signals (only when activatable/closable)
    ms_problems = _milestone_detail(root, state)
    problems.extend(ms_problems)

    # Architect signal
    if _architect_due(root, state):
        problems.append(
            "Architect review due. Load /aiwf-architect "
            "(code / design / structure / full)"
        )

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

    print(f"Next: {primary_skill}")


def _print_status_debug(root, state, goal, evidence, testing, review, fix_loop,
                        reasonix_settings, claude_settings):
    """Full debug panel — current verbose output with all sections."""
    recs = evidence.get("records", []) or []
    ev_acc = sum(1 for r in recs if r.get("status") == "accepted")
    from ..core.current_state import current_state_freshness
    cs_freshness = current_state_freshness(str(root))
    try:
        from ..core.task_ledger import ledger_summary
        task_summary = ledger_summary(str(root))
    except Exception:
        task_summary = {"active_task_ids": [], "counts": {}}
    try:
        from ..core.cross_task_quality import evaluate_cross_task_quality
        quality_digest = evaluate_cross_task_quality(str(root))
    except Exception:
        quality_digest = {"signals": []}
    try:
        from ..core.task_gravity import task_gravity, should_trigger_architecture_review
        gravity = task_gravity(str(root))
        architect_trigger = should_trigger_architecture_review(str(root))
    except Exception:
        gravity = {"history_weight": 0.0, "hard_constraints": [], "soft_warnings": []}
        architect_trigger = {"should_trigger": False, "reasons": []}
    architecture_review = _read_json(
        root / ".aiwf" / "records" / "architecture-review.json",
        {},
    )
    report_exists = (root / ".aiwf" / "records" / "闭合报告.md").exists()
    drift_path = root / ".aiwf" / "runtime" / "internal" / "workspace-drift.json"
    drift_exists = drift_path.exists()
    cap_path = root / ".aiwf" / "records" / "events.json"
    cap_exists = cap_path.exists()

    blockers = []
    if fix_loop.get("status") == "open":
        blockers.append("fix-loop open")
    if state.get("scope_violation"):
        blockers.append("scope violation")
    if review.get("result") not in ("accepted", "unknown"):
        blockers.append(f"review {review['result']}")
    if architecture_review.get("status") == "issues_found":
        blockers.append("periodic architecture issues")

    drift_pending = False
    if drift_exists:
        drift_pending = _read_json(drift_path, {}).get("needs_planner_review", False)
    if drift_pending:
        blockers.append("drift pending")

    cap_high = False
    cap_count = 0
    if cap_exists:
        caps = _read_json(cap_path, {}).get("capabilities", [])
        cap_count = len(caps)
        for cap in caps:
            if (
                cap.get("use_policy") in ("requires_user_decision", "ask_before_use")
                or cap.get("risk") in ("destructive_or_deploy", "project_mutation", "unknown")
            ):
                cap_high = True
                break
    if cap_high:
        blockers.append("high-risk capabilities")

    health = "clear" if not blockers else f"blocked ({len(blockers)}): {', '.join(blockers[:3])}"

    product = "Reasonix" if reasonix_settings.exists() else "Claude Code"
    print(f"AIWF V{VERSION} — Embedded {product}")
    print()

    # Activation summary (user-facing, concise)
    from ..core.process_contract import build_activation_summary
    print(build_activation_summary(str(root)))
    print()
    print("── Control Panel ──")
    goal_text = goal.get("current_goal") or goal.get("active_goal", "") or "(none)"
    print(f"  Goal:     v{goal.get('goal_version', 1)}/{goal.get('goal_status', 'discussion')} / {goal_text[:120]}")
    print(f"  Phase:    {state.get('phase', 'unknown')}")
    print(f"  Workflow: {state.get('workflow_level', 'L1_review_light')} / {state.get('task_type', '') or 'not selected'}")
    print(f"  Health:   {health}")
    print(f"  Next:     {_next_action(state, review, fix_loop, drift_pending, cap_high)}")
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
    verdict = review.get("verdict", "pending")
    verdict_part = f" verdict={verdict}" if verdict not in ("", "pending", None) else ""
    print(f"  Review:   {review.get('result', 'unknown')}{verdict_part}  review_gate={review.get('closure_allowed', False)}")
    print(f"  Quality brief: {_quality_brief_status(goal)}")
    print(f"  Task type: {state.get('task_type') or 'not selected'}")
    print(f"  Test:     {state.get('test_template') or 'not selected'}")
    print(f"  Review:   {state.get('review_template') or 'not selected'}")
    print(f"  Git:      {state.get('git_policy') or 'not selected'}")
    if state.get("quality_escalation_required"):
        recommended = state.get("recommended_minimum_level") or "higher workflow level"
        reason = state.get("quality_escalation_reason") or "selected level is below policy"
        print(f"  Escalation required: {recommended} ({reason})")
    print(f"  Evidence: {ev_acc} accepted / {len(recs)} raw")
    print(f"  Fix-loop: {fix_loop.get('status', 'none')}")
    print(f"  Cleanup:  {review.get('cleanup_status', '?')}  stale_items={len(review.get('stale_items', []) or [])}")
    print(f"  Structure:{review.get('structure_status', '?')}")

    goal = get_active_goal(str(root))
    brief = goal.get("quality_brief", {})
    arch = brief.get("architecture_brief", {})
    has_arch = arch and any(v for v in arch.values() if v and v != "" and v != [])
    print(f"  Architecture: {'brief present' if has_arch else 'missing'}")
    print(
        "  Periodic architecture review: "
        f"{architecture_review.get('status', 'not_run')}"
    )
    surfaces = brief.get("surface_types", [])
    print(f"  Surfaces: {', '.join(surfaces) if surfaces else 'none'}")
    acrs = fix_loop.get("architecture_change_requests", [])
    if any(a.get("status") == "proposed" for a in acrs):
        print("  Architecture changes: pending")
    elif acrs:
        print("  Architecture changes: resolved")
    else:
        print("  Architecture changes: none")
    closure_ok = state.get("closure_allowed")
    print(f"  Closure:  {'closed' if state.get('phase') == 'closed' else 'allowed' if closure_ok else 'blocked' if state.get('close_attempt') else 'not attempted'}")
    print()

    print("── Awareness ──")
    print(f"  Workspace drift:  {'pending review' if drift_pending else 'clean' if drift_exists else 'not scanned'}")
    print(f"  Ext capabilities: {'high-risk' if cap_high else 'available' if cap_count > 0 else 'none'}")
    print(f"  Context dispatch: {'present' if _has_context_dispatch(root, state) else 'missing'}")
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
    print(f"  Environment:      {_environment_status(root)}")
    try:
        from ..assets.schema import asset_status
        assets = asset_status(str(root))
        print(f"  Tier 1 assets:    {assets.get('overall', 'unknown')}")
    except Exception:
        print("  Tier 1 assets:    unknown")
    cs_status = cs_freshness["status"]
    if cs_status == "stale":
        stale = cs_freshness.get("stale_sources", [])
        suffix = f" ({', '.join(stale[:3])})" if stale else ""
        print(f"  Current state:    stale{suffix}")
    else:
        print(f"  Current state:    {'available' if cs_status == 'fresh' else cs_status}")
    print(f"  Project Map:      {'present' if (root / '.aiwf' / 'artifacts' / 'reports' / '项目地图.md').exists() else 'missing'}")
    print(f"  Rules:            {_rules_status(root)}")
    print(f"  Ideas: {_ideas_status(root)}")
    print(f"  Report:           {'available' if report_exists else 'none'}")
    signals = quality_digest.get("signals", []) or []
    if signals:
        print(f"  Quality digest:   signals ({len(signals)})")
    else:
        print(f"  Quality digest:   clear" if (root / ".aiwf" / "records" / "质量摘要.md").exists() else "  Quality digest:   none")
    print()

    print("── Gravity ──")
    print(
        f"  Weight:   {gravity.get('history_weight', 0.0):.2f} "
        f"(historical pressure only; it never lowers the selected workflow)"
    )
    print(f"  Minimum:  {gravity.get('suggested_min_level') or 'none'}")
    hard = gravity.get("hard_constraints", []) or []
    soft = gravity.get("soft_warnings", []) or []
    print(f"  Gates:    {len(hard)} hard / {len(soft)} advisory")
    for item in hard[:3]:
        print(f"  BLOCKS:   [{item.get('kind', '?')}] {item.get('message', '')}")
    for item in soft[:2]:
        print(f"  WATCH:    [{item.get('kind', '?')}] {item.get('message', '')}")
    if architect_trigger.get("should_trigger"):
        print(f"  Architect due before next ordinary task: {'; '.join(architect_trigger.get('reasons', [])[:3])}")
    else:
        print("  Architect: not currently due")
    print()

    from ..core.process_contract import planner_process_guidance
    guidance = planner_process_guidance(str(root))
    print("── Planner Process Guidance ──")
    topo = guidance.get("execution_topology", "")
    verif = guidance.get("verification_need", "")
    rev = guidance.get("review_need", "")
    wl = guidance.get("workflow_level", "?")
    cx = guidance.get("complexity", "?")
    rs = guidance.get("routing_score", "?")
    print(f"  Routing: {wl} / complexity={cx} / score={rs}")
    if topo or verif or rev:
        print(f"  Topology: exec={topo}  verify={verif}  review={rev}")
    factors = guidance.get("routing_factors", [])
    background = guidance.get("routing_background_factors", [])
    print(f"  Factors: {', '.join(factors[:6]) if factors else 'no mechanical routing factors recorded yet'}")
    if background:
        print(f"  Background: {', '.join(background[:5])} (not direct score)")
    print(
        f"  Depth:   test={guidance.get('test_template') or 'not selected'}; "
        f"review={guidance.get('review_template') or 'not selected'}; "
        f"explore={guidance.get('exploration_budget') or 'not selected'}"
    )
    recovery = guidance.get("recovery") or {}
    if recovery and recovery.get("state") != "clear":
        print(
            f"  Recovery: {recovery.get('state')} / {recovery.get('category') or 'none'} "
            f"/ owner={recovery.get('owner') or 'planner'}"
        )
        print(f"  PRIMARY: {recovery.get('primary') or 'none'}")
        for option in (recovery.get("legal_options") or [])[:3]:
            print(f"  LEGAL:   {option}")
        if recovery.get("user_decision_required"):
            print("  USER DECISION REQUIRED")
        for item in (recovery.get("forbidden") or [])[:2]:
            print(f"  AVOID:   {item}")
    for item in guidance.get("required_now", [])[:5]:
        print(f"  REQUIRED: {item}")
    for item in guidance.get("conditional", [])[:3]:
        print(f"  WHEN TRIGGERED: {item}")
    freeze_reasons = guidance.get("contract_freeze_reasons", [])
    if freeze_reasons:
        print(f"  CONTRACT FROZEN BY: {', '.join(freeze_reasons)}")
        print("  UNLOCK: satisfy/revert the failing cycle and close it; additions and evidence remain allowed")
    if not guidance.get("required_now"):
        print("  REQUIRED: No unresolved mandatory step detected.")
    print()

    print("── Detail ──")
    print("  .aiwf/state + .aiwf/records   machine state")
    print()
    print("  CLI: aiwf doctor | aiwf status --prompt | aiwf sync --check")


def _next_action(state, review, fix_loop, drift_pending, cap_high):
    phase = state.get("phase", "planning")
    if fix_loop.get("status") == "open":
        return "resolve fix-loop"
    if state.get("scope_violation"):
        return "resolve scope violation"
    if drift_pending:
        return "review workspace drift"
    if cap_high:
        return "review high-risk capabilities"
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


def _has_context_dispatch(root: Path, state: Dict[str, Any]) -> bool:
    ctx_id = state.get("active_context_id")
    if not ctx_id:
        return False
    contexts = _read_json(root / ".aiwf" / "state" / "state.json", {"contexts": []})
    for ctx in contexts.get("contexts", []):
        if ctx.get("id") == ctx_id:
            return bool(ctx.get("purpose") or ctx.get("test_focus") or ctx.get("review_focus"))
    return False


def _environment_status(root: Path) -> str:
    env_path = root / ".aiwf" / "records" / "events.json"
    if not env_path.exists():
        return "missing"
    env = _read_json(env_path, {})
    if env.get("known_environment_risks") or env.get("missing_tools"):
        return "risks"
    return "profiled"


def _rules_status(root: Path) -> str:
    rules_path = root / ".aiwf" / "project-rules.md"
    if not rules_path.exists():
        return "none"
    text = rules_path.read_text(encoding="utf-8", errors="ignore")
    active_count = text.count("| active |")
    if active_count > 30:
        return "many"
    if active_count > 0:
        return "active"
    return "none"


def _ideas_status(root: Path) -> str:
    ideas_path = root / ".aiwf" / "records" / "ideas.md"
    if not ideas_path.exists():
        return "none"
    try:
        from ..core.ideas import _parse_ideas, is_idea_active

        ideas = _parse_ideas(ideas_path.read_text(encoding="utf-8"))
    except Exception:
        return "unreadable"
    raw_candidates = [i for i in ideas if i.get("status") in ("raw", "candidate")]
    if any(not is_idea_active(i) for i in raw_candidates):
        return "stale"
    if any(is_idea_active(i) for i in raw_candidates):
        return "available"
    return "none"


def cmd_next(args) -> None:
    """Output machine-readable next-action directive for the current phase."""
    root = Path.cwd()
    state_path = root / ".aiwf" / "state" / "state.json"

    role = getattr(args, "role", None) or ""
    role = role.strip().lower() if role else ""

    # ── Role-specific mode: works even without state ──
    if role:
        role_actions = {
            "planner": ("Run aiwf status; determine next gate; freeze contracts before execution",
                        "Planner owns the workflow and decides routing",
                        "Skipping required subagent dispatch; writing project files when executor_required=true"),
            "executor": ("Read active Task.md; implement within scope; record evidence",
                         "Executor is scoped to the active task; implement then hand off to Tester",
                         "Architecture changes without ACR; hand-editing AIWF state; committing code"),
            "tester": ("Validate against Task.md Tester Requirements; record all commands with output",
                       "Independent testing is required before review; tests must be traceable",
                       "Prose-only claims without command output; skipping required test surfaces"),
            "reviewer": ("Audit evidence, check Task.md boundaries, record adversarial observations",
                         "Independent review is required before closure; contract critique, not checklist",
                         "Reviewing own code; skipping evidence audit; defaulting to full test rerun"),
        }
        action, why, forbidden = role_actions.get(role, role_actions["planner"])
        print(f"NEXT_ROLE: {role}")
        print(f"ACTION: {action}")
        print(f"WHY: {why}")
        print(f"FORBIDDEN: {forbidden}")
        return

    if not state_path.exists():
        print("NEXT_ROLE: user")
        print("ACTION: aiwf install reasonix (or claude)")
        print("WHY: no AIWF state found")
        return

    state = _read_json(state_path, {})
    goal = get_active_goal(str(root))
    contexts = _read_json(root / ".aiwf" / "state" / "state.json", {"contexts": []})
    review = _read_json(root / ".aiwf" / "records" / "review.json", {"result": "unknown"})
    fix_loop = _read_json(root / ".aiwf" / "state" / "fix-loop.json", {"status": "none"})
    testing = _read_json(root / ".aiwf" / "records" / "testing.json", {"status": "missing"})

    phase = state.get("phase", "planning")
    request_mode = state.get("request_mode", "execution")
    ctx_id = state.get("active_context_id") or ""
    ctx = next((c for c in contexts.get("contexts", []) or [] if c.get("id") == ctx_id), {})

    role = getattr(args, "role", None) or ""
    role = role.strip().lower() if role else ""

    # ── Role-specific mode: show directive for a specific role regardless of phase ──
    if role:
        role_actions = {
            "planner": {
                "action": "Run aiwf status; determine next gate; freeze contracts before execution",
                "why": "Planner owns the workflow and decides routing",
                "forbidden": "Skipping required subagent dispatch; writing project files when executor_required=true",
            },
            "executor": {
                "action": "Read active Task.md; implement within scope; record evidence",
                "why": "Executor is scoped to the active task; implement then hand off to Tester",
                "forbidden": "Architecture changes without ACR; hand-editing AIWF state; committing code",
            },
            "tester": {
                "action": "Validate against Task.md Tester Requirements; record all commands with output",
                "why": "Independent testing is required before review; tests must be traceable",
                "forbidden": "Prose-only claims without command output; skipping required test surfaces",
            },
            "reviewer": {
                "action": "Audit evidence, check Task.md boundaries, record adversarial observations",
                "why": "Independent review is required before closure; contract critique, not checklist",
                "forbidden": "Reviewing own code; skipping evidence audit; defaulting to full test rerun",
            },
        }
        ra = role_actions.get(role, role_actions["planner"])
        print(f"NEXT_ROLE: {role}")
        print(f"ACTION: {ra['action']}")
        print(f"WHY: {ra['why']}")
        print(f"FORBIDDEN: {ra['forbidden']}")
        print(f"PHASE: {phase}")
        if fix_loop.get("status") == "open":
            print(f"FIX_LOOP: open (route={fix_loop.get('route', '?')})")
        return

    # ── Phase → next role & action ──
    # V2 canonical names + V1 backward compat aliases
    phase_map = {
        "planning": {
            "role": "planner",
            "action": f"Confirm goal and freeze contracts (request_mode={request_mode})",
            "why": "Contracts must be frozen before any code is written",
            "forbidden": "Project writes; only state, goal, and plan changes allowed",
        },
        "discussing": {
            "role": "planner",
            "action": f"Confirm goal and freeze contracts (request_mode={request_mode})",
            "why": "Contracts must be frozen before any code is written",
            "forbidden": "Project writes; only state, goal, and plan changes allowed",
        },
        "planned": {
            "role": "planner",
            "action": f"Confirm goal and freeze contracts (request_mode={request_mode})",
            "why": "Contracts must be frozen before any code is written",
            "forbidden": "Project writes; only state, goal, and plan changes allowed",
        },
        "executing": {
            "role": "tester",
            "action": f"Validate changes at depth {state.get('test_template', 'targeted')}",
            "why": "Implementation recorded; independent testing required",
            "forbidden": "Prose-only testing; must record commands and results",
        },
        "implementing": {
            "role": "tester",
            "action": f"Validate changes at depth {state.get('test_template', 'targeted')}",
            "why": "Implementation recorded; independent testing required",
            "forbidden": "Prose-only testing; must record commands and results",
        },
        "testing": {
            "role": "reviewer",
            "action": "Independent review against evaluation contract",
            "why": f"Testing status={testing.get('status')}; review depth={state.get('review_template', 'standard')}",
            "forbidden": "Review before cleanup verification; reviewing own code",
        },
        "reviewing": {
            "role": "planner",
            "action": "Disposition adversarial observations, then close task",
            "why": f"Review result={review.get('result')}",
            "forbidden": "Closing without fix-loop resolution; new implementation",
        },
        "closing": {
            "role": "planner",
            "action": "Resolve blockers, run aiwf task close",
            "why": "Closure requires all gates passed (hash, evidence, testing, review, fix-loop)",
            "forbidden": "New implementation; only fix-loop and contract updates",
        },
        "closed": {
            "role": "planner",
            "action": "Carry forward: run aiwf status --debug to review state, then plan next cycle",
            "why": "Workflow complete; prepare for next cycle",
            "forbidden": "Re-opening closed tasks without new goal",
        },
    }

    info = phase_map.get(phase, phase_map["discussing"])

    # ── Default: next role for current phase ──
    print(f"NEXT_ROLE: {info['role']}")
    print(f"ACTION: {info['action']}")
    print(f"WHY: {info['why']}")
    print(f"FORBIDDEN: {info['forbidden']}")
    print(f"PHASE: {phase}")

    # Extra context
    if fix_loop.get("status") == "open":
        print(f"FIX_LOOP: open (route={fix_loop.get('route', '?')}, attempt={fix_loop.get('attempt_count', 0)})")
    if state.get("scope_violation"):
        print("SCOPE_VIOLATION: true — resolve before closure")
    if state.get("quality_escalation_required"):
        print(f"ESCALATION: {state.get('quality_escalation_reason', '')[:120]}")


def _quality_brief_status(goal: Dict[str, Any]) -> str:
    brief = goal.get("quality_brief", {})
    if isinstance(brief, dict) and _has_meaningful_value(brief):
        return "present"
    if goal.get("confirmed"):
        return "missing"
    return "not confirmed"


def _has_meaningful_value(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_has_meaningful_value(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_meaningful_value(v) for v in value)
    if isinstance(value, str):
        return bool(value.strip())
    return bool(value)


# ── index commands ────────────────────────────────────────────────────

def _cmd_index_check(args: argparse.Namespace) -> None:
    from ..core.index_ops import check_index
    result = check_index(str(Path.cwd()))
    if result["healthy"]:
        print("Index: HEALTHY — all JSON ↔ Markdown bindings OK")
    else:
        print(f"Index: {result['issues_count']} issue(s) found")
        for i in result["issues"]:
            print(f"  [{i['type']}:{i['id']}] {i['issue']}")
        raise SystemExit(1)


def _cmd_index_refresh(args: argparse.Namespace) -> None:
    from ..core.index_ops import refresh_index
    result = refresh_index(str(Path.cwd()))
    print(f"Index refreshed: {result['refreshed']} entries updated")
    if result["updated"]:
        for item in result["updated"][:20]:
            print(f"  {item}")


def _cmd_index_repair(args: argparse.Namespace) -> None:
    from ..core.index_ops import repair_index
    result = repair_index(str(Path.cwd()))
    print(f"Index repaired: {result['repaired']} entries checked")
    if result["fixed_files"]:
        print(f"Fixed frontmatter in {len(result['fixed_files'])} file(s):")
        for f in result["fixed_files"]:
            print(f"  {f}")
