
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
    "evidence/records.json",
    "quality/testing.json",
    "quality/review.json",
    "history/task-history.json",
    "history/task-ledger.json",
    "reports/当前状态.md",
    "reports/闭合报告.md",
    "reports/质量摘要.md",
]

REQUIRED_CURRENT_STATE_SECTIONS = [
    "## Goal & Intent",
    "## Current Status",
    "## Quality Snapshot",
    "## Raw References",
]


def current_state_status(cwd):
    current = cwd / ".aiwf" / "reports" / "当前状态.md"
    if not current.exists():
        return "none"
    try:
        current_mtime = current.stat().st_mtime
    except OSError:
        return "unreadable"
    stale = []
    for name in SOURCE_FILES:
        source = cwd / ".aiwf" / name
        if not source.exists():
            continue
        try:
            if source.stat().st_mtime > current_mtime:
                stale.append(name)
        except OSError:
            stale.append(name)
    if stale:
        return "stale"
    try:
        text = current.read_text(encoding="utf-8", errors="ignore")
        if any(section not in text for section in REQUIRED_CURRENT_STATE_SECTIONS) or len(text.strip()) < 120:
            return "incomplete"
    except OSError:
        return "unreadable"
    return "available"


def gravity_summary_lines(cwd):
    """Gravity: historical pressure — hotspots, fix-loop trend, drift, pending ADV."""
    history = rj(cwd / ".aiwf" / "history" / "task-history.json", {"tasks": []})
    review = rj(cwd / ".aiwf" / "quality" / "review.json", {})
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
    history = rj(cwd / ".aiwf" / "history" / "task-history.json", {"tasks": []})
    ledger = rj(cwd / ".aiwf" / "history" / "task-ledger.json", {"tasks": []})
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
    testing = rj(cwd / ".aiwf" / "quality" / "testing.json", {})
    lines = []
    if testing.get("cross_task_risks"):
        lines.append(f"Quality: tester cross-task risks ({len(testing.get('cross_task_risks', []))})")
    if testing.get("testing_debt"):
        lines.append(f"Quality: testing debt observations ({len(testing.get('testing_debt', []))})")
    return lines[:3]


def architect_hint(cwd):
    """Lightweight architecture review trigger check. JSON reads only."""
    history = rj(cwd / ".aiwf" / "history" / "task-history.json", {"tasks": []})
    tasks = history.get("tasks", []) if isinstance(history.get("tasks"), list) else []
    closed = len(tasks)
    cadence = 10
    hints = []
    if closed > 0 and closed % cadence == 0:
        hints.append(f"{closed} closed tasks — architecture review recommended")
    pm_path = cwd / ".aiwf" / "reports" / "项目地图.md"
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
    lines = [
        f"Process: {level} complexity={state.get('complexity', 'standard')} score={state.get('routing_score', 0)}",
        "Routing why: " + (", ".join(str(f) for f in factors[:5]) if factors else "not mechanically routed yet"),
    ]
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
        elif rj(cwd / ".aiwf" / "quality" / "testing.json", {}).get("status") not in ("adequate", "passed"):
            lines.append(f"REQUIRED NEXT: dispatch independent Tester ({state.get('test_template') or 'selected depth'})")
        elif not review.get("cleanup_verified_at"):
            lines.append("REQUIRED NEXT: verify cleanup before Reviewer")
        elif review.get("result") != "accepted":
            lines.append(f"REQUIRED NEXT: dispatch independent Reviewer ({state.get('review_template') or 'selected depth'})")
        else:
            lines.append("REQUIRED NEXT: Planner meta-critique and adversarial disposition")
    return lines[:5]


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
            "additionalContext": "[AIWF] Not initialized. Run: aiwf install reasonix"
        }}))
        return

    state = rj(state_path)
    goal = rj(cwd / ".aiwf" / "state" / "goal.json")
    review = rj(cwd / ".aiwf" / "quality" / "review.json")
    fix_loop = rj(cwd / ".aiwf" / "state" / "fix-loop.json")

    lines = ["[AIWF]"]
    lines.append(f"Phase: {state.get('phase', 'unknown')}")
    cs_status = current_state_status(cwd)
    lines.append(f"Current state: {cs_status}")
    if cs_status in ("stale", "missing", "incomplete"):
        lines.append("Hint: run aiwf state rebuild-current-state to mechanically regenerate current-state.md")
    ledger = rj(cwd / ".aiwf" / "history" / "task-ledger.json", {"tasks": []})
    tasks = ledger.get("tasks", []) if isinstance(ledger.get("tasks"), list) else []
    active_tasks = [t.get("id") for t in tasks if t.get("status") == "active" and t.get("id")]
    if tasks:
        lines.append(f"Task ledger: {len(active_tasks)} active / {len(tasks)} tasks")
    if (cwd / ".aiwf" / "reports" / "质量摘要.md").exists():
        lines.append("Quality digest: available")
    lines.extend(gravity_summary_lines(cwd))
    lines.extend(active_task_quality_warning_lines(cwd))
    lines.extend(quality_signal_lines(cwd))
    lines.extend(architect_hint(cwd))
    lines.extend(planner_process_lines(cwd, state, goal, review, fix_loop))
    drift_path = cwd / ".aiwf" / "internal" / "workspace-drift.json"
    if drift_path.exists():
        try:
            drift_json = json.loads(drift_path.read_text(encoding="utf-8"))
            if drift_json.get("needs_planner_review"): lines.append("Workspace drift: pending Planner review")
            elif drift_json.get("dirty"): lines.append("Workspace drift: dirty workspace")
            else: lines.append("Workspace drift: last scan clean")
        except Exception: lines.append("Workspace drift: not scanned")
    else: lines.append("Workspace drift: not scanned")
    cap_path = cwd / ".aiwf" / "assets" / "capabilities.json"
    cap_legacy = cwd / ".aiwf" / "capabilities.json"  # legacy pre-v2 flat path
    if not cap_path.exists() and cap_legacy.exists():
        cap_path = cap_legacy
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
    # Environment profile
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
    # Project map
    pm_path = cwd / ".aiwf" / "reports" / "项目地图.md"
    if pm_path.exists(): lines.append("Project Map: present")
    else: lines.append("Project Map: missing")
    # Quality surfaces
    stypes = goal.get("quality_brief", {}).get("surface_types", [])
    if stypes: lines.append(f"Surfaces: {', '.join(stypes)}")
    # Architecture brief
    ab = goal.get("quality_brief", {}).get("architecture_brief", {})
    has_ab = ab and any(v for v in ab.values() if v and v != "" and v != [])
    if has_ab: lines.append("Architecture: brief present")
    else: lines.append("Architecture: missing")
    # ACR status
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
        lines.append(f"Review: {rev_result}")
    if state.get("close_attempt"):
        lines.append("Close attempt in progress")

    # Quality brief presence
    brief = goal.get("quality_brief", {})
    if brief.get("acceptance_criteria") or brief.get("test_focus"):
        lines.append("Quality brief: present")
    elif goal.get("confirmed"):
        lines.append("Quality brief: missing; planner should record before execution")

    # Quality policy summary (short keys only)
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

    # Determine next gate
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

    context = "\n".join(lines)
    if os.environ.get("AIWF_HOOK_ENGINE", "").lower() == "reasonix":
        print(context)
    else:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": context
        }}))

if __name__ == "__main__":
    main()
