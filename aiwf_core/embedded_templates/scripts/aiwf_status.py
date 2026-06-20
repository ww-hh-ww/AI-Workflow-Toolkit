
#!/usr/bin/env python3
'''AIWF UserPromptSubmit — standalone, stdlib-only, no aiwf_core imports.

Fast path: reads .aiwf state files directly, outputs Claude hook JSON.
No heavy imports — prompt cache safe, runs without PYTHONPATH.
'''
import json, os, sys
from pathlib import Path


def rj(path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else (default or {})
    except Exception:
        return default or {}


SOURCE_FILES = [
    "state/state.json",
    "state/fix-loop.json",
    "state/plans.json",
    "state/milestones.json",
    "records/evidence.json",
    "records/testing.json",
    "records/review.json",
    "records/architecture-review.json",
    "state/tasks.json",
]

def _research_unresolved(cwd):
    data = rj(cwd / ".aiwf" / "records" / "events.json", {"records": [], "skip": {}})
    if any(r.get("status") == "promoted" for r in data.get("records", []) if isinstance(r, dict)):
        return False
    skip = data.get("skip", {}) if isinstance(data.get("skip"), dict) else {}
    return not (skip.get("status") == "skipped" and str(skip.get("reason", "")).strip())


def recovery_lines(cwd, state, goal, review, fix_loop):
    # Simplified mirror of process_contract._recovery_guidance().
    # When changing either, check whether the other needs the same change.
    level = state.get("workflow_level", "L1_review_light")
    request_mode = state.get("request_mode", "execution")
    active_task = state.get("active_task_id")
    out = []
    def blocked(category, owner, primary, legal, user=False):
        lines = [f"Recovery:{category} {owner}", f"PRIMARY: {primary}", "REQUIRED NEXT: see PRIMARY"]
        if user:
            lines.append("USER DECISION REQUIRED")
        return lines

    if fix_loop.get("status") == "open":
        route = fix_loop.get("route") or "planner"
        return blocked("fix_loop", "user" if route == "planner" or fix_loop.get("escalation_required") else route,
                       f"resolve fix-loop via route={route}",
                       "follow required_fixes/verification, then run aiwf fixloop resolve",
                       user=route == "planner" or bool(fix_loop.get("escalation_required")))
    if state.get("scope_violation"):
        return blocked("scope", "planner", "recover scope violation",
                       "revert violating files, then run aiwf fixloop resolve; new extra work needs a new scoped task",
                       user=False)
    if not active_task and state.get("phase") == "closed":
        return []
    if request_mode in ("discussion", "clarification", "research"):
        return [f"Recovery: open/{request_mode} owner=planner",
                f"PRIMARY: continue {request_mode}",
                f"REQUIRED NEXT: continue {request_mode}"]
    if request_mode == "spike" or state.get("workflow_pattern") == "spike_first":
        return ["Recovery: open/spike owner=planner",
                "PRIMARY: finish spike and record findings",
                "REQUIRED NEXT: finish spike and record findings"]
    if state.get("external_research_required") and request_mode == "execution" and _research_unresolved(cwd):
        return blocked("user_decision", "planner", "resolve external research requirement",
                       "promote a research record, or ask user whether to skip external research",
                       user=True)
    if active_task and state.get("phase") == "closed":
        return blocked("close_ledger_task", "planner",
                       f"close active ledger task {active_task}",
                       f"run aiwf task close (active task must be closed)",
                       user=False)
    if not active_task and state.get("phase") in ("reviewing", "closing"):
        if review.get("result") == "accepted":
            return blocked("closure", "planner", "complete testing and review before close",
                           "record testing and review, then run aiwf task close")
        return blocked("missing_step", "reviewer", "complete review or resolve review blockers",
                       "dispatch Reviewer or resolve fix-loop before task close")
    if not active_task:
        active_plan = state.get("active_plan_id")
        if active_plan and request_mode == "execution":
            plan_complete = False
            try:
                plans_path = Path(cwd) / ".aiwf" / "state" / "plans.json"
                if plans_path.exists():
                    plans = json.loads(plans_path.read_text())
                    for p in plans.get("plans", []) or []:
                        if p.get("plan_id") == active_plan:
                            remaining = p.get("remaining_task_ids", []) or []
                            plan_complete = not remaining
                            break
            except Exception:
                pass
            if not plan_complete:
                # Plan exists without active task — advisory, not blocking.
                # forbidden_write should be used to protect sensitive paths instead.
                return []  # Health: ok
        # No active task: scope defaults to unrestricted.
        # forbidden_write is the recommended mechanism for restricting writes.
        return []  # Health: ok
    # Recovery is derived from current phase + Task.requirements, not workflow_level
    # Close gate checks (evidence/testing/review) are done mechanically in aiwf task close
    return out


def _active_task(cwd, task_id):
    if not task_id:
        return {}
    ledger = rj(cwd / ".aiwf" / "state" / "tasks.json", {"tasks": []})
    for task in ledger.get("tasks", []) or []:
        if isinstance(task, dict) and task.get("id") == task_id:
            return task
    return {}


def _node_ids(cwd, state):
    task_id = state.get("active_task_id") or ""
    task = _active_task(cwd, task_id)
    plan_id = state.get("active_plan_id") or task.get("plan_id") or ""
    goal_id = state.get("active_task_parent_goal") or task.get("goal_id") or task.get("parent_goal") or ""
    milestone_id = state.get("active_milestone_id") or task.get("milestone_id") or ""
    if not milestone_id:
        milestones = rj(cwd / ".aiwf" / "state" / "milestones.json", {})
        milestone_id = milestones.get("active_milestone_id") or ""
    return task_id, plan_id, goal_id, milestone_id


def _milestone_signals(cwd, active_milestone_id):
    milestones_data = rj(cwd / ".aiwf" / "state" / "milestones.json", {})
    plans_data = rj(cwd / ".aiwf" / "state" / "plans.json", {"plans": []})
    all_plans = plans_data.get("plans", []) or []
    all_milestones = milestones_data.get("milestones", []) or []
    ledger = rj(cwd / ".aiwf" / "state" / "tasks.json", {"tasks": []})
    goals_data = rj(cwd / ".aiwf" / "state" / "goals.json", {"goals": []})
    all_goals = goals_data.get("goals", []) or []
    goal_ids_set = {str(g.get("id") or g.get("goal_id") or "") for g in all_goals if isinstance(g, dict)}

    signals = []

    for m in all_milestones:
        if not isinstance(m, dict):
            continue
        mid = m.get("id") or m.get("milestone_id") or ""
        if not mid or m.get("status") != "pending":
            continue
        covered = m.get("covered_goal_ids", []) or []
        if not covered:
            continue
        ok = True
        for gid in covered:
            goal_plans = [p for p in all_plans
                          if str(p.get("goal_id") or p.get("target_goal_id") or "") == str(gid)]
            if not goal_plans:
                ok = False
                break
            for p in goal_plans:
                if not (p.get("task_ids") or []):
                    ok = False
                    break
        if ok:
            plan_count = len(m.get("plan_ids", []) or [])
            signals.append(
                f"MILESTONE ACTIVATABLE {mid}: {len(covered)} goals, {plan_count} plans ready. "
                f"Load /aiwf-milestone to assess and close."
            )

    if active_milestone_id:
        ms = None
        for m in all_milestones:
            if (m.get("id") or m.get("milestone_id")) == active_milestone_id:
                ms = m
                break
        if ms and ms.get("status") not in ("closed",):
            blockers = []
            for pid in (ms.get("plan_ids", []) or []):
                pid_str = str(pid)
                plan = None
                for p in all_plans:
                    if (p.get("plan_id") or p.get("id") or "") == pid_str:
                        plan = p
                        break
                if not plan:
                    blockers.append(f"plan missing: {pid_str}")
                    continue
                remaining = plan.get("remaining_task_ids", []) or []
                if plan.get("status") not in ("complete", "completed") or remaining:
                    blockers.append(f"plan not complete: {pid_str}")

            task_by_id = {str(t.get("id")): t for t in (ledger.get("tasks") or [])
                          if isinstance(t, dict) and t.get("id")}
            for tid in (ms.get("task_ids", []) or []):
                t = task_by_id.get(str(tid))
                if not t:
                    blockers.append(f"task missing: {tid}")
                elif t.get("status") not in ("closed", "rejected"):
                    blockers.append(f"task not terminal: {tid}")

            for gid in (ms.get("covered_goal_ids", []) or []):
                if str(gid) not in goal_ids_set:
                    blockers.append(f"covered goal not registered: {gid}")

            it = ms.get("integration_test", {}) or {}
            if it.get("status") != "passed":
                blockers.append("integration test not passed")
            else:
                if it.get("coverage_mode") != "function_reverse_trace":
                    blockers.append("integration test missing function reverse trace")
                if it.get("main_path_status") != "passed":
                    blockers.append("integration test main path not passed")
                traces = it.get("function_traces", []) or []
                if not traces:
                    blockers.append("integration test function inventory missing")
                elif any(t.get("status") in ("untraced", "disconnected") for t in traces):
                    blockers.append("integration test has unresolved function traces")
            ar = ms.get("architecture_review", {}) or {}
            if ar.get("status") == "issues_found":
                blockers.append("architecture review has unresolved issues")
            elif ar.get("status") not in ("intact",):
                blockers.append("architecture review not done")
            ar_blocked = any("architecture review" in b.lower() for b in blockers)
            it_blocked = any("integration test" in b.lower() for b in blockers)
            other_blocked = [b for b in blockers
                             if "integration test" not in b.lower()
                             and "architecture review not done" not in b.lower()]

            if not other_blocked and (it_blocked or ar_blocked):
                # V1: milestone verification routes through /aiwf-milestone,
                # which internally uses integration and arch-review as sub-steps
                signals.append(
                    f"MILESTONE NEEDS VERIFICATION {active_milestone_id}: "
                    "load /aiwf-milestone. If verification task missing, Planner creates "
                    "TASK-MS-VERIFY-* with kind=milestone_verification."
                )
            elif not blockers:
                signals.append(
                    f"MILESTONE CLOSABLE {active_milestone_id}: verification complete "
                    f"— aiwf milestone close {active_milestone_id}"
                )

    return signals


def _build_short_context(cwd, state, goal, review, fix_loop):
    """Per-turn injection: only what the model needs to decide its next action.
    No Mission, no full tree, no reports, no assets, no raw artifact content.
    """
    phase = state.get("phase", "planning")
    mode = state.get("request_mode", "execution")
    pattern = state.get("workflow_pattern", "linear")
    task_id, plan_id, goal_id, milestone_id = _node_ids(cwd, state)
    ctx_id = state.get("active_context_id", "")

    lines = ["[AIWF]"]
    parts = [f"Phase: {phase}"]
    if task_id:
        parts.append(f"task={task_id}")
    if plan_id:
        parts.append(f"plan={plan_id}")
    if goal_id:
        parts.append(f"goal={goal_id}")
    if milestone_id:
        parts.append(f"milestone={milestone_id}")
    if ctx_id:
        parts.append(f"ctx={ctx_id}")
    lines.append(" ".join(parts))
    lines.append(f"Process: mode={mode} route={pattern}")

    health_parts = []
    if state.get("scope_violation"):
        health_parts.append("scope violation")
    if fix_loop.get("status") == "open":
        health_parts.append(f"fix-loop open -> {fix_loop.get('route', '?')}")
    rev = review.get("result", "unknown")
    if rev in ("rejected", "needs_fix", "needs_more_testing", "scope_violation"):
        health_parts.append(f"review={rev}")
    if health_parts:
        lines.append(f"BLOCKED: {', '.join(health_parts)}")
    else:
        lines.append("Health: ok")

    # Milestone activation / verification signals
    ms_signals = _milestone_signals(cwd, milestone_id)
    if ms_signals:
        lines.extend(ms_signals[:2])

    # Recovery / PRIMARY / REQUIRED NEXT (from recovery_lines)
    rec = recovery_lines(cwd, state, goal, review, fix_loop)
    if rec:
        lines.extend(rec[:3])  # Recovery, PRIMARY, REQUIRED NEXT

    # 5. Forbidden (derived from phase + blockers)
    forbidden = []
    if state.get("scope_violation"):
        forbidden.append("project writes outside active context")
    if fix_loop.get("status") == "open" and not fix_loop.get("escalation_required"):
        forbidden.append("resolve fix-loop before task close")
    if rev not in ("accepted", "unknown") and phase in ("reviewing", "closing"):
        forbidden.append("task close (review not accepted)")
    if phase == "closed" and state.get("active_task_id"):
        forbidden.append("project writes until task ledger is closed")
    if forbidden:
        lines.append(f"Forbidden: {', '.join(forbidden)}")

    # 6. Phase anchor [ATTN] — always last for recency weight.
    # Every phase gets explicit next step. No vague suggestions.
    phase_anchors = {
        "planning": (
            "PLANNING - /aiwf-planner → read state files → "
            "create goals/plans/tasks via CLI → activate task."
        ),
        "executing": (
            "EXECUTING - /aiwf-implement → implement → "
            "aiwf record evidence --role executor --scan-git --summary \"...\""
        ),
        "testing": (
            "TESTING - /aiwf-test → test → "
            "aiwf record testing --scan-git --status passed|failed|adequate --summary \"...\""
        ),
        "reviewing": (
            "REVIEWING - /aiwf-review → review → "
            "aiwf record review --result accepted|needs_fix|rejected --summary \"...\""
        ),
        "closing": (
            "CLOSING - /aiwf-close → verify evidence+testing+review → "
            "aiwf task close"
        ),
        "blocked": "BLOCKED - resolve blockers before continuing.",
        "closed": ("CLOSED - start next task or periodic Architect review."
                    if not state.get("active_task_id")
                    else "Closure gate passed. Next: run aiwf task close."),
        "discussing": (
            "PLANNING - /aiwf-planner → read state files → "
            "create goals/plans/tasks via CLI → activate task."
        ),
        "planned": "PLANNING - /aiwf-planner; pick ready task → aiwf task activate.",
        "implementing": (
            "EXECUTING - /aiwf-implement → implement → "
            "aiwf record evidence --role executor --scan-git --summary \"...\""
        ),
    }
    anchor = phase_anchors.get(phase, "")
    if anchor:
        lines.append(f"[ATTN] {anchor}")
    lines.append("If lost: run `aiwf status --debug`, then load the [ATTN] skill.")

    return "\n".join(lines)


def _build_full_context(cwd, state, goal, review, fix_loop):
    """Full context: all state details for debugging. The original verbose output."""
    lines = ["[AIWF]"]
    lines.append(f"Phase: {state.get('phase', 'unknown')}")
    ledger = rj(cwd / ".aiwf" / "state" / "tasks.json", {"tasks": []})
    tasks = ledger.get("tasks", []) if isinstance(ledger.get("tasks"), list) else []
    active_tasks = [t.get("id") for t in tasks if t.get("status") == "active" and t.get("id")]
    if tasks:
        lines.append(f"Task ledger: {len(active_tasks)} active / {len(tasks)} tasks")
    # Gravity: closed task counts from ledger
    if tasks:
        closed_count = sum(1 for t in tasks if t.get("status") == "closed")
        if closed_count:
            lines.append(f"Gravity: {closed_count} closed tasks")
    drift_path = cwd / ".aiwf" / "runtime" / "internal" / "workspace-drift.json"
    if drift_path.exists():
        try:
            drift_json = json.loads(drift_path.read_text(encoding="utf-8"))
            if drift_json.get("needs_planner_review"): lines.append("Workspace drift: pending Planner review")
            elif drift_json.get("dirty"): lines.append("Workspace drift: dirty workspace")
            else: lines.append("Workspace drift: last scan clean")
        except Exception: lines.append("Workspace drift: not scanned")
    else: lines.append("Workspace drift: not scanned")
    stypes = goal.get("quality_brief", {}).get("surface_types", [])
    if stypes: lines.append(f"Surfaces: {', '.join(stypes)}")
    ab = goal.get("quality_brief", {}).get("architecture_brief", {})
    has_ab = ab and any(v for v in ab.values() if v and v != "" and v != [])
    if has_ab: lines.append("Architecture: brief present")
    else: lines.append("Architecture: missing")
    acrs = fix_loop.get("architecture_change_requests", []) or []
    has_pending_acr = any(a.get("status") == "proposed" for a in acrs)
    if has_pending_acr: lines.append("Architecture changes: pending")
    active_goal = goal.get("active_goal", "")
    gv = goal.get("goal_version", 1)
    gs = goal.get("goal_status", "discussion")
    if active_goal:
        lines.append(f"Goal: v{gv}/{gs} / {active_goal[:120]}")
    ctx_id = state.get("active_context_id")
    if ctx_id:
        lines.append(f"Active context: {ctx_id}")
    if state.get("scope_violation"):
        lines.append("SCOPE VIOLATION DETECTED")
    if fix_loop.get("status") == "open":
        lines.append(f"FIX-LOOP OPEN -> {fix_loop.get('route', '?')}")
    rev_result = review.get("result", "unknown")
    if rev_result not in ("unknown",):
        verdict = review.get("verdict", "pending")
        verdict_part = f" verdict={verdict}" if verdict not in ("", "pending", None) else ""
        lines.append(f"Review: {rev_result}{verdict_part}")
    if state.get("close_attempt"):
        lines.append("Close attempt in progress")
    brief = goal.get("quality_brief", {})
    if brief.get("acceptance_criteria") or brief.get("test_focus"):
        lines.append("Quality brief: present")
    elif goal.get("confirmed"):
        lines.append("Quality brief: missing; planner should record before execution")
    # Active task requirements summary
    active_task = state.get("active_task_id")
    if active_task:
        tasks_data = rj(cwd / ".aiwf" / "state" / "tasks.json", {"tasks": []})
        for t in tasks_data.get("tasks", []) or []:
            if isinstance(t, dict) and t.get("id") == active_task:
                reqs = t.get("requirements", {}) or {}
                lines.append(f"  Reqs: executor={reqs.get('executor_required', True)}, tester={reqs.get('tester_required', True)}, reviewer={reqs.get('reviewer_required', True)}")
                break
    phase = state.get("phase", "planning")
    gates = {"planning": "load /aiwf-planner to shape Goal Tree and create Plan",
             "discussing": "load /aiwf-planner to shape Goal Tree and create Plan",
             "planned": "Planner directs implementation",
             "executing": "Planner directs testing",
             "implementing": "Planner directs testing",
             "testing": "Planner directs independent review",
             "reviewing": "Planner prepares closure" if rev_result == "accepted" else f"Review result: {rev_result} — resolve blockers",
             "closing": "Stop hook will verify gates",
             "closed": "Task closed"}
    next_gate = gates.get(phase, "Discuss with user to determine next step")
    lines.append(f"Next: {next_gate}")
    # Recovery guidance for debugging
    rec = recovery_lines(cwd, state, goal, review, fix_loop)
    if rec:
        lines.extend(rec[:3])
    return "\n".join(lines)


def _build_agent_context(cwd, state, goal, review, fix_loop, json_mode=False):
    """Model dispatch info: what skill to load, what checklists to trigger.

    Returns JSON when json_mode=True (--agent), text when False (--prompt).
    """
    phase = state.get("phase", "planning")
    level = state.get("workflow_level", "L1_review_light")
    blockers = []
    if fix_loop.get("status") == "open":
        blockers.append("fix-loop")
    if state.get("scope_violation"):
        blockers.append("scope-violation")
    if review.get("result") in ("rejected", "needs_fix", "scope_violation"):
        blockers.append("review-blocked")

    # Phase → skill dispatch (from config/skill-map.json, fallback to hardcoded)
    skill_map_path = cwd / ".aiwf" / "config" / "skill-map.json"
    phase_skill = {
        "discussing": "aiwf-planner", "planning": "aiwf-planner",
        "planned": "aiwf-planner", "implementing": "aiwf-implement",
        "executing": "aiwf-implement", "testing": "aiwf-test",
        "reviewing": "aiwf-review", "closing": "aiwf-close",
        "closed": "aiwf-planner", "blocked": "aiwf-planner",
    }
    if skill_map_path.exists():
        try:
            sm = json.loads(skill_map_path.read_text(encoding="utf-8"))
            phase_skills = sm.get("phase_skills", {})
            # Map phase to list of skills
            phase = state.get("phase", "planning")
            skills = phase_skills.get(phase, phase_skills.get("planning", []))
            if skills:
                primary_skill = skills[0]
            else:
                primary_skill = phase_skill.get(phase, "aiwf-planner")
        except Exception:
            primary_skill = phase_skill.get(state.get("phase", "planning"), "aiwf-planner")
    else:
        primary_skill = phase_skill.get(state.get("phase", "planning"), "aiwf-planner")

    # Skill list from skill-map: phase skills + signal skills
    required_skills = []
    if skill_map_path.exists():
        try:
            sm = json.loads(skill_map_path.read_text(encoding="utf-8"))
            phase_skills = sm.get("phase_skills", {})
            signal_skills = sm.get("signal_skills", {})
            phase = state.get("phase", "planning")
            required_skills = list(phase_skills.get(phase, phase_skills.get("planning", [])))

            # Signal skills: check conditions and merge into required_skills
            # Architect: every N closed tasks or PROJECT-MAP staleness
            try:
                from aiwf_core.core.task_gravity import should_trigger_architecture_review
                arch = should_trigger_architecture_review(str(cwd))
                if arch.get("should_trigger"):
                    required_skills.extend(signal_skills.get("architect_due", ["aiwf-architect"]))
            except Exception:
                pass

            # Milestone: activatable or closable milestone exists
            milestone_id = state.get("active_milestone_id") or ""
            ms_signals = _milestone_signals(cwd, milestone_id) if milestone_id else []
            if not ms_signals:
                # Even without active milestone, check for any activatable
                ms_signals = _milestone_signals(cwd, "")
            if any("ACTIVATABLE" in s or "CLOSABLE" in s for s in ms_signals):
                required_skills.extend(signal_skills.get("milestone_due", ["aiwf-milestone"]))
        except Exception:
            pass

    # Checklists derived from phase and milestone state, not workflow_level
    checklists = []
    if phase == "reviewing":
        checklists.append("trace")
        checklists.append("verify")
    if phase == "closing" and blockers:
        checklists.append("recovery")

    milestone_id = state.get("active_milestone_id") or ""
    ms_signals = _milestone_signals(cwd, milestone_id) if milestone_id else []
    if any("CLOSABLE" in s for s in ms_signals):
        checklists.append("integration")
        checklists.append("arch-review")

    # Hard gates (never skip)
    hard_gates = []
    if phase in ("executing", "implementing", "testing", "reviewing", "closing"):
        hard_gates.append("scope-guard")
    if phase == "closing":
        hard_gates.extend(["evidence-required", "test-required", "review-required", "fixloop-clear"])
    if state.get("scope_violation"):
        hard_gates.append("scope-clean-required")

    # Required read: active task narrative doc
    required_read = []
    active_task_id = state.get("active_task_id")
    task_reqs = {}
    if active_task_id:
        task_doc = f".aiwf/tasks/{active_task_id}.md"
        if (cwd / task_doc).exists():
            required_read.append(task_doc)
        try:
            ledger = rj(cwd / ".aiwf" / "state" / "tasks.json", {"tasks": []})
            for t in ledger.get("tasks", []) or []:
                if isinstance(t, dict) and t.get("id") == active_task_id:
                    task_reqs = t.get("requirements", {}) or {}
                    break
        except Exception:
            pass

    # Build per-phase next_action. Every phase gets explicit steps.
    # When *_required=false: inline path with recording command inline.
    # When *_required=true: dispatch path — subagent records itself.
    next_action = {
        "planning": "load /aiwf-planner → read state files → create goals/plans/tasks via CLI → activate task",
        "discussing": "load /aiwf-planner → read state files → create goals/plans/tasks via CLI → activate task",
        "planned": "aiwf task activate <TASK-ID>",
        "executing": "load /aiwf-implement → implement → record evidence",
        "implementing": "load /aiwf-implement → implement → record evidence",
        "testing": "load /aiwf-test → test → record testing",
        "reviewing": "load /aiwf-review → review → record review",
        "blocked": "resolve blockers before continuing",
        "closing": "load /aiwf-close → verify gates → aiwf task close",
        "closed": "load /aiwf-planner for next cycle (or architect review if signal active)",
    }.get(phase, "load skill for current phase")

    if phase in ("executing", "implementing"):
        if task_reqs.get("executor_required"):
            next_action += " (subagent: aiwf-executor)"
        else:
            next_action = (
                "read inline-execution.md → implement → "
                "aiwf record evidence --role executor --scan-git --summary \"<what changed>\""
            )
            required_read.append("inline-execution.md")
    elif phase == "testing":
        if task_reqs.get("tester_required"):
            next_action += " (subagent: aiwf-tester)"
        else:
            next_action = (
                "read inline-execution.md → test → "
                "aiwf record testing --scan-git --status passed|failed|adequate --summary \"<summary>\""
            )
            required_read.append("inline-execution.md")
    elif phase == "reviewing":
        if task_reqs.get("reviewer_required"):
            next_action += " (subagent: aiwf-reviewer)"
        else:
            next_action = (
                "read inline-execution.md → review → "
                "aiwf record review --result accepted|needs_fix|rejected --summary \"<why>\""
            )
            required_read.append("inline-execution.md")

    if json_mode:
        return json.dumps({
            "phase": phase, "level": level,
            "primary_skill": primary_skill,
            "required_skills": required_skills,
            "checklists": checklists,
            "hard_gates": hard_gates,
            "blockers": blockers,
            "next_action": next_action,
            "active_task": active_task_id or None,
            "active_plan": state.get("active_plan_id") or None,
            "required_read": required_read,
        })
    else:
        # Text format for prompt injection
        lines = [f"Skill: {primary_skill}"]
        if required_skills:
            lines.append(f"Required skills: {', '.join(required_skills)}")
        if required_read:
            lines.append(f"Required read: {', '.join(required_read)}")
        if checklists:
            lines.append(f"Checklists: {', '.join(checklists)}")
        if hard_gates:
            lines.append(f"Gates: {', '.join(hard_gates)}")
        if blockers:
            lines.append(f"Blockers: {', '.join(blockers)}")
        lines.append(f"Next: {next_action}")
        return "\n".join(lines)


def main():
    raw = sys.stdin.read().strip()
    cwd = Path.cwd()
    if raw:
        try:
            d = json.loads(raw)
            if d.get("cwd"):
                cwd = Path(d["cwd"])
        except json.JSONDecodeError:
            pass

    state_path = cwd / ".aiwf" / "state" / "state.json"
    if not state_path.exists():
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "[AIWF] Not initialized. Run: aiwf install claude (or reasonix)"
        }}))
        return

    state = rj(state_path)
    # Merge routing state (V2: lives in runtime/internal/, not state.json)
    routing_path = cwd / ".aiwf" / "runtime" / "internal" / "routing-state.json"
    if routing_path.exists():
        routing = rj(routing_path)
        for k, v in routing.items():
            if k not in state or state.get(k) in (None, "", [], 0, False):
                state[k] = v
    # Read active goal from goals.json (single source of truth)
    goals_data = rj(cwd / ".aiwf" / "state" / "goals.json", {"goals": []})
    active_id = goals_data.get("active_goal_id") or "GOAL-001"
    goal = next((g for g in goals_data.get("goals", []) if isinstance(g, dict) and g.get("id") == active_id), {})
    review = rj(cwd / ".aiwf" / "records" / "review.json")
    fix_loop = rj(cwd / ".aiwf" / "state" / "fix-loop.json")

    # --short: per-turn human injection (~8 lines). Default for UserPromptSubmit hook.
    # --debug: full verbose output.
    # --agent: JSON dispatch info for model (primary_skill, checklists, gates).
    # --prompt: machine-optimized context injection.
    short_mode = "--short" in sys.argv
    debug_mode = "--debug" in sys.argv
    agent_mode = "--agent" in sys.argv
    prompt_mode = "--prompt" in sys.argv

    if prompt_mode or agent_mode:
        context = _build_agent_context(cwd, state, goal, review, fix_loop, agent_mode)
    elif debug_mode:
        context = _build_full_context(cwd, state, goal, review, fix_loop)
        # Append [ATTN] anchor to debug mode too
        phase = state.get("phase", "planning")
        phase_anchors = {
            "planning": (
                "PLANNING - /aiwf-planner → read state files → "
                "create goals/plans/tasks via CLI → activate task."
            ),
            "executing": (
                "EXECUTING - /aiwf-implement → implement → "
                "aiwf record evidence --role executor --scan-git --summary \"...\""
            ),
            "testing": (
                "TESTING - /aiwf-test → test → "
                "aiwf record testing --scan-git --status passed|failed|adequate --summary \"...\""
            ),
            "reviewing": (
                "REVIEWING - /aiwf-review → review → "
                "aiwf record review --result accepted|needs_fix|rejected --summary \"...\""
            ),
            "closing": (
                "CLOSING - /aiwf-close → verify evidence+testing+review → "
                "aiwf task close"
            ),
            "blocked": "BLOCKED - resolve blockers before continuing.",
            "closed": "CLOSED.",
            "discussing": (
                "PLANNING - /aiwf-planner → read state files → "
                "create goals/plans/tasks via CLI → activate task."
            ),
            "planned": "PLANNING - /aiwf-planner; pick ready task → aiwf task activate.",
            "implementing": (
                "EXECUTING - /aiwf-implement → implement → "
                "aiwf record evidence --role executor --scan-git --summary \"...\""
            ),
        }
        anchor = phase_anchors.get(phase, "")
        if anchor:
            context += f"\n\n[ATTN] {anchor}"
    else:
        context = _build_short_context(cwd, state, goal, review, fix_loop)

    if os.environ.get("AIWF_HOOK_ENGINE", "").lower() == "reasonix":
        print(context)
    else:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": context
        }}))

if __name__ == "__main__":
    main()
