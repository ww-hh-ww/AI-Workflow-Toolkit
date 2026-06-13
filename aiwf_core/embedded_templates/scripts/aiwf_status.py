
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
    "state/goal.json",
    "state/contexts.json",
    "state/fix-loop.json",
    "state/plans.json",
    "state/milestones.json",
    "artifacts/evidence/records.json",
    "artifacts/quality/testing.json",
    "artifacts/quality/review.json",
    "runtime/history/task-history.json",
    "runtime/history/task-ledger.json",
]

def gravity_summary_lines(cwd):
    """Gravity: historical pressure — hotspots, fix-loop trend, drift, pending ADV."""
    history = rj(cwd / ".aiwf" / "runtime" / "history" / "task-history.json", {"tasks": []})
    review = rj(cwd / ".aiwf" / "artifacts" / "quality" / "review.json", {})
    state = rj(cwd / ".aiwf" / "state" / "state.json", {})
    tasks = history.get("tasks", []) if isinstance(history.get("tasks"), list) else []
    recent = tasks[-5:]
    file_counts = {}
    for task in recent:
        for path in task.get("changed_files", []) or []:
            file_counts[path] = file_counts.get(path, 0) + 1
    archived = history.get("archived_hotspots", {})
    if isinstance(archived, dict):
        for path, count in archived.items():
            file_counts[path] = file_counts.get(path, 0) + max(1, int(count or 0) // 2)
    hotspots = sorted(
        [(p, c) for p, c in file_counts.items() if c >= 2],
        key=lambda item: (-item[1], item[0])
    )
    fix_attempts = sum(int(t.get("fix_loop_attempt_count", 0) or 0) for t in recent)
    lines = []
    if hotspots:
        hs_strs = [f"{p}({c}x)" for p, c in hotspots[:3]]
        lines.append(f"Gravity: hotspots {', '.join(hs_strs)}")
        severe = [p for p, c in hotspots if c >= 3]
        if severe:
            lines.append(f"QUALITY ESCALATION: repeated hotspot {severe[0]}")
    if fix_attempts >= 2:
        lines.append(f"Gravity: fix-loop trend {fix_attempts} recent attempts")
    if fix_attempts >= 3:
        lines.append(f"QUALITY ESCALATION: {fix_attempts} recent fix-loop attempts")
    if review.get("architecture_drift"):
        lines.append(f"Gravity: architecture drift ({len(review.get('architecture_drift', []))})")
    if state.get("quality_escalation_required"):
        lines.append(f"Gravity escalation: {state.get('recommended_minimum_level', '?')}")
    adv_obs = review.get("adversarial_observations", []) or []
    pending_adv = [o for o in adv_obs if isinstance(o, dict) and o.get("disposition") == "pending"]
    if pending_adv:
        lines.append(f"Gravity: {len(pending_adv)} adversarial observation(s) pending disposition")
    return lines[:5]


def active_task_quality_warning_lines(cwd):
    """Warn when the current active task is already touching a severe hotspot."""
    history = rj(cwd / ".aiwf" / "runtime" / "history" / "task-history.json", {"tasks": []})
    ledger = rj(cwd / ".aiwf" / "runtime" / "history" / "task-ledger.json", {"tasks": []})
    history_tasks = history.get("tasks", []) if isinstance(history.get("tasks"), list) else []
    ledger_tasks = ledger.get("tasks", []) if isinstance(ledger.get("tasks"), list) else []
    file_counts = {}
    for task in history_tasks[-5:]:
        for path in task.get("changed_files", []) or []:
            file_counts[path] = file_counts.get(path, 0) + 1
    severe_hotspots = {path for path, count in file_counts.items() if count >= 3}
    if not severe_hotspots:
        return []

    def hits(allowed, hotspot):
        allowed = str(allowed).rstrip("/")
        hotspot = str(hotspot).rstrip("/")
        return allowed == hotspot or allowed.startswith(hotspot + "/") or hotspot.startswith(allowed + "/")

    lines = []
    for task in ledger_tasks:
        if task.get("status") != "active":
            continue
        allowed_write = task.get("allowed_write", []) or []
        for hotspot in sorted(severe_hotspots):
            if any(hits(path, hotspot) for path in allowed_write):
                lines.append(f"ACTIVE TASK QUALITY WARNING: {task.get('id')} hits hotspot {hotspot}")
                break
    return lines[:3]


def quality_signal_lines(cwd):
    """Quality: current tester/reviewer observations — cross-task risks, testing debt."""
    testing = rj(cwd / ".aiwf" / "artifacts" / "quality" / "testing.json", {})
    lines = []
    if testing.get("cross_task_risks"):
        lines.append(f"Quality: tester cross-task risks ({len(testing.get('cross_task_risks', []))})")
    if testing.get("testing_debt"):
        lines.append(f"Quality: testing debt observations ({len(testing.get('testing_debt', []))})")
    return lines[:3]


def architect_hint(cwd):
    """Lightweight architecture review trigger check. JSON reads only."""
    history = rj(cwd / ".aiwf" / "runtime" / "history" / "task-history.json", {"tasks": []})
    tasks = history.get("tasks", []) if isinstance(history.get("tasks"), list) else []
    closed = len(tasks)
    cadence = 10
    hints = []
    if closed > 0 and closed % cadence == 0:
        hints.append(f"{closed} closed tasks — architecture review recommended")
    pm_path = cwd / ".aiwf" / "artifacts" / "reports" / "项目地图.md"
    if pm_path.exists():
        try:
            from datetime import datetime, timezone
            age = (datetime.now(timezone.utc).timestamp() - pm_path.stat().st_mtime) / 86400
            if age > 30:
                hints.append(f"PROJECT-MAP {age:.0f}d old — architecture review recommended")
        except Exception:
            pass
    return hints


def planner_process_lines(cwd, state, goal, review, fix_loop):
    """Concise process explanation: why this depth, what role/action is next."""
    level = state.get("workflow_level", "L1_review_light")
    factors = state.get("routing_factors", []) or []
    background = state.get("routing_background_factors", []) or []
    request_mode = state.get("request_mode", "execution")
    pattern = state.get("workflow_pattern", "linear")
    lines = [
        f"Process: {level} complexity={state.get('complexity', 'standard')} score={state.get('routing_score', 0)}",
        "Routing current: " + (", ".join(str(f) for f in factors[:5]) if factors else "not mechanically routed yet"),
    ]
    if background:
        lines.append("Routing background: " + ", ".join(str(f) for f in background[:5]) + " (explain, not direct score)")
    if request_mode != "execution" or pattern != "linear":
        lines.insert(1, f"Mode: {request_mode}/{pattern}")
    if state.get("pattern_reason"):
        lines.append("Pattern why: " + str(state.get("pattern_reason"))[:160])
    lines.extend(recovery_lines(cwd, state, goal, review, fix_loop))
    if any(line.startswith("Recovery:") for line in lines):
        return lines[:10]
    if request_mode in ("discussion", "clarification", "research"):
        lines.append(f"REQUIRED NEXT: continue {request_mode}; switch to request_mode=execution only after the user confirms execution")
        return lines[:5]
    if request_mode == "spike" or pattern == "spike_first":
        lines.append("REQUIRED NEXT: record spike findings, then switch to request_mode=execution for final implementation")
        return lines[:5]
    if fix_loop.get("status") == "open":
        lines.append(f"REQUIRED NEXT: resolve fix-loop via {fix_loop.get('route') or 'planner'}")
        return lines
    if level != "L0_direct" and not state.get("active_task_id"):
        lines.append("REQUIRED NEXT: plan and activate one task before project writes")
        return lines
    brief = goal.get("quality_brief", {}) or {}
    evaluation = brief.get("evaluation_contract", {}) or {}
    if level in ("L2_standard_team", "L3_full_power"):
        missing = [k for k in ("user_visible_outcome", "acceptance_criteria", "test_obligations", "review_obligations") if not evaluation.get(k)]
        if missing:
            lines.append("REQUIRED NEXT: complete Evaluation Contract: " + ", ".join(missing))
        elif rj(cwd / ".aiwf" / "artifacts" / "quality" / "testing.json", {}).get("status") not in ("adequate", "passed"):
            lines.append(f"REQUIRED NEXT: dispatch independent Tester ({state.get('test_template') or 'selected depth'})")
        elif not review.get("cleanup_verified_at"):
            lines.append("REQUIRED NEXT: verify cleanup before Reviewer")
        elif review.get("result") != "accepted":
            lines.append(f"REQUIRED NEXT: dispatch independent Reviewer ({state.get('review_template') or 'selected depth'})")
        else:
            lines.append("REQUIRED NEXT: Planner meta-critique and adversarial disposition")
    return lines[:5]


def _research_unresolved(cwd):
    data = rj(cwd / ".aiwf" / "artifacts" / "research" / "external.json", {"records": [], "skip": {}})
    if any(r.get("status") == "promoted" for r in data.get("records", []) if isinstance(r, dict)):
        return False
    skip = data.get("skip", {}) if isinstance(data.get("skip"), dict) else {}
    return not (skip.get("status") == "skipped" and str(skip.get("reason", "")).strip())


def recovery_lines(cwd, state, goal, review, fix_loop):
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
                       "promote a research record, or ask user to approve aiwf research skip",
                       user=True)
    if active_task and state.get("phase") == "closed":
        return blocked("close_ledger_task", "planner",
                       f"close active ledger task {active_task}",
                       f"run aiwf task close {active_task}; prepare-close passed but task ledger is still active",
                       user=False)
    if not active_task and state.get("phase") in ("reviewing", "closing"):
        if review.get("result") == "accepted":
            return blocked("closure", "planner", "follow active plan Impact and run prepare-close",
                           "follow active plan Impact, then run aiwf state prepare-close")
        return blocked("missing_step", "reviewer", "complete review or resolve review blockers",
                       "dispatch Reviewer or route fix-loop before prepare-close")
    if not active_task:
        active_plan = state.get("active_plan_id")
        if active_plan and request_mode == "execution":
            return blocked("plan_only_drift", "planner",
                           f"freeze execution contract and activate planned task {active_plan}",
                           "record policy/brief/context, then aiwf task plan and aiwf task activate")
        return blocked("missing_step", "planner", "plan and activate one scoped task",
                       "run aiwf task plan, aiwf task activate, then aiwf status")
    if level in ("L2_standard_team", "L3_full_power"):
        brief = goal.get("quality_brief", {}) or {}
        evaluation = brief.get("evaluation_contract", {}) or {}
        missing = [k for k in ("user_visible_outcome", "acceptance_criteria", "test_obligations", "review_obligations") if not evaluation.get(k)]
        if missing:
            return blocked("missing_contract", "planner", "complete Evaluation Contract",
                           "record missing fields or ask the user for acceptance criteria",
                           user=True)
        testing = rj(cwd / ".aiwf" / "artifacts" / "quality" / "testing.json", {})
        if testing.get("status") not in ("adequate", "passed"):
            return blocked("missing_step", "tester", "dispatch independent Tester",
                           "use aiwf-tester; do not roleplay Tester or dispatch Reviewer first")
        if testing.get("full_suite_status", "not_run") == "not_run" or testing.get("real_usage_status", "not_run") == "not_run":
            return blocked("quality_gap", "tester", "disposition full suite and real usage validation",
                           "run/disposition both layers; ask user before accepting residual risk",
                           user=True)
        if not review.get("cleanup_verified_at"):
            return blocked("wrong_order", "planner", "verify cleanup before Reviewer",
                           "run cleanup checks and mark cleanup fresh before review")
        if review.get("result") != "accepted":
            return blocked("missing_step", "reviewer", "dispatch independent Reviewer",
                           "use aiwf-reviewer; do not roleplay Reviewer")
        pending = [o for o in review.get("adversarial_observations", []) if isinstance(o, dict) and o.get("disposition") == "pending"]
        if pending:
            return blocked("missing_step", "planner", "disposition adversarial observations",
                           "record meta-critique dispositions before prepare-close")
    return out


def _active_task(cwd, task_id):
    if not task_id:
        return {}
    ledger = rj(cwd / ".aiwf" / "runtime" / "history" / "task-ledger.json", {"tasks": []})
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
    """Return activation/verification signals for milestones. Stdlib-only."""
    milestones_data = rj(cwd / ".aiwf" / "state" / "milestones.json", {})
    plans_data = rj(cwd / ".aiwf" / "state" / "plans.json", {"plans": []})
    all_plans = plans_data.get("plans", []) or []
    all_milestones = milestones_data.get("milestones", []) or []
    ledger = rj(cwd / ".aiwf" / "runtime" / "history" / "task-ledger.json", {"tasks": []})
    goals_data = rj(cwd / ".aiwf" / "state" / "goals.json", {"goals": []})
    all_goals = goals_data.get("goals", []) or []
    goal_ids_set = {str(g.get("id") or g.get("goal_id") or "") for g in all_goals if isinstance(g, dict)}

    signals = []

    # Scan pending milestones for activatability
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
            gid_str = str(gid)
            goal_plans = [p for p in all_plans
                          if str(p.get("goal_id") or p.get("target_goal_id") or "") == gid_str]
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
                f"aiwf milestone update {mid} --status active"
            )

    # Active milestone verification readiness
    if active_milestone_id:
        ms = None
        for m in all_milestones:
            if (m.get("id") or m.get("milestone_id")) == active_milestone_id:
                ms = m
                break
        if ms and ms.get("status") not in ("completed", "archived"):
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
            ar = ms.get("architecture_review", {}) or {}
            if ar.get("status") not in ("intact",):
                blockers.append("architecture review not done")
            ar_blocked = any("architecture review" in b.lower() for b in blockers)
            it_blocked = any("integration test" in b.lower() for b in blockers)
            other_blocked = [b for b in blockers
                             if "integration test" not in b.lower()
                             and "architecture review" not in b.lower()]

            if not other_blocked and (it_blocked or ar_blocked):
                missing = []
                if it_blocked:
                    missing.append("load /aiwf-milestone-integration")
                if ar_blocked:
                    missing.append("load /aiwf-milestone-arch-review")
                signals.append(f"MILESTONE READY {active_milestone_id}: {'; '.join(missing)}")
            elif not blockers:
                signals.append(
                    f"MILESTONE READY {active_milestone_id}: verification complete "
                    f"— aiwf milestone close {active_milestone_id}"
                )

    return signals


def _build_short_context(cwd, state, goal, review, fix_loop):
    """Per-turn injection: only what the model needs to decide its next action.
    No Mission, no full tree, no reports, no assets, no raw artifact content.
    """
    phase = state.get("phase", "discussing")
    level = state.get("workflow_level", "L1_review_light")
    mode = state.get("request_mode", "execution")
    pattern = state.get("workflow_pattern", "linear")
    task_id, plan_id, goal_id, milestone_id = _node_ids(cwd, state)
    ctx_id = state.get("active_context_id", "")

    lines = ["[AIWF]"]
    parts = [f"Phase: {phase}", f"level={level}"]
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
    lines.append(f"Process: level={level} mode={mode} route={pattern}")

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
        lines.extend(ms_signals[:2])  # max 2 milestone lines per turn

    # 4. Recovery / PRIMARY / REQUIRED NEXT (from recovery_lines)
    rec = recovery_lines(cwd, state, goal, review, fix_loop)
    if rec:
        lines.extend(rec[:3])  # Recovery, PRIMARY, REQUIRED NEXT

    # 5. Forbidden (derived from phase + blockers)
    forbidden = []
    if state.get("scope_violation"):
        forbidden.append("project writes outside active context")
    if fix_loop.get("status") == "open" and not fix_loop.get("escalation_required"):
        forbidden.append("resolve fix-loop before prepare-close")
    if rev not in ("accepted", "unknown") and phase in ("reviewing", "closing"):
        forbidden.append("prepare-close (review not accepted)")
    if phase == "closed" and state.get("active_task_id"):
        forbidden.append("project writes until task ledger is closed")
    if forbidden:
        lines.append(f"Forbidden: {', '.join(forbidden)}")

    # 6. Phase anchor [ATTN] — always last for recency weight
    phase_anchors = {
        "discussing": "DISCUSSION - /aiwf-planner; no code.",
        "planned": "PLANNED - freeze contracts, then activate task.",
        "implementing": "EXECUTING - /aiwf-implement; stay in allowed_write.",
        "testing": "TESTING - /aiwf-test; run commands, record evidence.",
        "reviewing": "REVIEWING - /aiwf-review chain.",
        "closing": "CLOSING - /aiwf-close; prepare_close before task close.",
        "closed": ("CLOSED - start next task or periodic Architect review."
                    if not state.get("active_task_id")
                    else f"Closure gate passed. Next: run aiwf task close {state['active_task_id']}."),
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
    ledger = rj(cwd / ".aiwf" / "runtime" / "history" / "task-ledger.json", {"tasks": []})
    tasks = ledger.get("tasks", []) if isinstance(ledger.get("tasks"), list) else []
    active_tasks = [t.get("id") for t in tasks if t.get("status") == "active" and t.get("id")]
    if tasks:
        lines.append(f"Task ledger: {len(active_tasks)} active / {len(tasks)} tasks")
    if (cwd / ".aiwf" / "artifacts" / "reports" / "质量摘要.md").exists():
        lines.append("Quality digest: available")
    lines.extend(gravity_summary_lines(cwd))
    lines.extend(active_task_quality_warning_lines(cwd))
    lines.extend(quality_signal_lines(cwd))
    lines.extend(architect_hint(cwd))
    lines.extend(planner_process_lines(cwd, state, goal, review, fix_loop))
    drift_path = cwd / ".aiwf" / "runtime" / "internal" / "workspace-drift.json"
    if drift_path.exists():
        try:
            drift_json = json.loads(drift_path.read_text(encoding="utf-8"))
            if drift_json.get("needs_planner_review"): lines.append("Workspace drift: pending Planner review")
            elif drift_json.get("dirty"): lines.append("Workspace drift: dirty workspace")
            else: lines.append("Workspace drift: last scan clean")
        except Exception: lines.append("Workspace drift: not scanned")
    else: lines.append("Workspace drift: not scanned")
    cap_path = cwd / ".aiwf" / "assets" / "capabilities.json"
    if cap_path.exists():
        try:
            cap_reg = json.loads(cap_path.read_text(encoding="utf-8"))
            caps = cap_reg.get("capabilities", [])
            high_risk = [c for c in caps if c.get("use_policy") in ("requires_user_decision", "ask_before_use")
                         or c.get("risk") in ("destructive_or_deploy", "project_mutation", "unknown")]
            if not caps:
                lines.append("External capabilities: none")
            elif high_risk:
                lines.append("External capabilities: registry available; high-risk entries need Planner review")
            else:
                lines.append("External capabilities: registry available")
        except Exception:
            lines.append("External capabilities: registry available")
    else:
        lines.append("External capabilities: none")
    env_path = cwd / ".aiwf" / "assets" / "environment.json"
    if env_path.exists():
        try:
            ep = json.loads(env_path.read_text(encoding="utf-8"))
            risks = ep.get("known_environment_risks") or []
            missing = ep.get("missing_tools") or []
            if risks or missing:
                lines.append("Environment: risks")
            else:
                lines.append("Environment: profiled")
        except Exception:
            lines.append("Environment: available")
    else:
        lines.append("Environment: missing")
    pm_path = cwd / ".aiwf" / "artifacts" / "reports" / "项目地图.md"
    if pm_path.exists(): lines.append("Project Map: present")
    else: lines.append("Project Map: missing")
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
        ctxs = rj(cwd / ".aiwf" / "state" / "contexts.json", {"contexts": []})
        act_ctx = None
        for cx in ctxs.get("contexts", []):
            if cx.get("id") == ctx_id: act_ctx = cx; break
        if act_ctx:
            has_disp = bool(act_ctx.get("purpose") or act_ctx.get("test_focus") or act_ctx.get("review_focus"))
            if has_disp: lines.append("Context dispatch: present")
            elif state.get("phase") in ("implementing", "testing", "reviewing"):
                lines.append("Context dispatch: missing; planner should record purpose/test_focus/review_focus")
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
    if state.get("test_template") and state.get("review_template"):
        lines.append(f"Quality: {state.get('workflow_level', '?')} / {state.get('task_type', '?')}")
        lines.append(f"Templates: test={state['test_template']}, review={state['review_template']}")
        if state.get("quality_escalation_required"):
            lines.append(f"ESCALATION REQUIRED: current={state.get('workflow_level', '?')}, recommended={state.get('recommended_minimum_level', '?')}")
            if state.get("quality_escalation_reason"):
                lines.append(f"Reason: {state['quality_escalation_reason'][:150]}")
            lines.append("Planner must resolve/escalate before execution")
    elif state.get("phase") in ("implementing", "testing", "reviewing"):
        lines.append("Quality: not selected yet; planner should record quality policy before execution")
    phase = state.get("phase", "discussing")
    gates = {"discussing": "Confirm goal with user and move to planning",
             "planned": "Planner directs implementation",
             "implementing": "Planner directs testing",
             "testing": "Planner directs independent review",
             "reviewing": "Planner prepares closure" if rev_result == "accepted" else f"Review result: {rev_result} — resolve blockers",
             "closing": "Stop hook will verify gates",
             "closed": "Task closed"}
    next_gate = gates.get(phase, "Discuss with user to determine next step")
    lines.append(f"Next: {next_gate}")
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
    goal = rj(cwd / ".aiwf" / "state" / "goal.json")
    review = rj(cwd / ".aiwf" / "artifacts" / "quality" / "review.json")
    fix_loop = rj(cwd / ".aiwf" / "state" / "fix-loop.json")

    # --short: per-turn injection (~8-12 lines). Default for UserPromptSubmit hook.
    # --debug: full verbose output with Gravity, capabilities, env, etc.
    short_mode = "--short" in sys.argv
    debug_mode = "--debug" in sys.argv

    if debug_mode:
        context = _build_full_context(cwd, state, goal, review, fix_loop)
        # Append [ATTN] anchor to debug mode too
        phase = state.get("phase", "discussing")
        phase_anchors = {
            "discussing": "DISCUSSION - /aiwf-planner; no code.",
            "planned": "PLANNED - freeze contracts, then activate task.",
            "implementing": "EXECUTING - /aiwf-implement; stay in allowed_write.",
            "testing": "TESTING - /aiwf-test; run commands, record evidence.",
            "reviewing": "REVIEWING - /aiwf-review chain.",
            "closing": "CLOSING - /aiwf-close; prepare_close before task close.",
            "closed": "CLOSED.",
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
