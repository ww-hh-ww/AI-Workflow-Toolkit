"""Embedded status surface."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from ..constants import VERSION


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
    goal = _read_json(root / ".aiwf" / "state" / "goal.json", {})
    evidence = _read_json(root / ".aiwf" / "artifacts" / "evidence" / "records.json", {"records": []})
    testing = _read_json(root / ".aiwf" / "artifacts" / "quality" / "testing.json", {"status": "missing"})
    review = _read_json(root / ".aiwf" / "artifacts" / "quality" / "review.json", {"result": "unknown", "closure_allowed": False, "blockers": []})
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
    """Human-readable short status — ~15 lines. What's happening, can we close, what's next."""
    product = "Reasonix" if (root / ".reasonix" / "settings.json").exists() else "Claude Code"
    print(f"AIWF V{VERSION} — {product}")
    print()

    phase = state.get("phase", "unknown")
    goal_text = goal.get("current_goal") or goal.get("active_goal", "") or "(none)"
    print(f"Goal:  {goal_text[:120]}")
    print(f"Phase: {phase}  level={state.get('workflow_level', 'L1')}  mode={state.get('request_mode', 'execution')}")

    # Can close?
    blockers = []
    if fix_loop.get("status") == "open":
        blockers.append("fix-loop open")
    if state.get("scope_violation"):
        blockers.append("scope violation")
    rstat = review.get("result", "unknown")
    if rstat not in ("accepted", "unknown"):
        blockers.append(f"review={rstat}")
    tstat = testing.get("status", "missing")
    if tstat == "failed":
        blockers.append("testing failed")
    if review.get("cleanup_status") != "fresh":
        blockers.append("cleanup not fresh")
    recs = evidence.get("records", []) or []
    ev_acc = sum(1 for r in recs if r.get("status") == "accepted")
    if not ev_acc:
        blockers.append("no accepted evidence")

    can_close = phase == "closed" or (not blockers and phase in ("reviewing", "closing"))
    print(f"Can close: {'yes' if can_close else 'no'}")
    if blockers:
        print(f"  Why: {', '.join(blockers[:3])}")

    # Next action
    try:
        from ..core.process_contract import planner_process_guidance
        guidance = planner_process_guidance(str(root))
        rec = guidance.get("recovery") or {}
        if rec and rec.get("state") != "clear":
            primary = rec.get("primary", "")
            if primary:
                print(f"Next: {primary[:160]}")
    except Exception:
        pass

    # Surfaces
    brief = goal.get("quality_brief", {}) or {}
    surface_types = brief.get("surface_types", []) or []
    print(f"Surfaces: {', '.join(surface_types) if surface_types else 'none'}")

    # Evidence + quality
    print(f"Evidence: {ev_acc} accepted / {len(recs)} raw")
    verdict = review.get("verdict", "pending")
    verdict_part = f" verdict={verdict}" if verdict not in ("", "pending", None) else ""
    print(f"Testing:  {tstat}  Review: {rstat}{verdict_part}  Cleanup: {review.get('cleanup_status', '?')}")
    if state.get("active_task_id"):
        print(f"Task:     {state['active_task_id']}")

    # Risk
    risks = []
    if testing.get("cross_task_risks"):
        risks.append(f"cross-task risks ({len(testing.get('cross_task_risks', []))})")
    if testing.get("testing_debt"):
        risks.append("testing debt")
    if fix_loop.get("architecture_change_requests"):
        pending = [a for a in fix_loop.get("architecture_change_requests", [])
                   if a.get("status") == "proposed"]
        if pending:
            risks.append(f"{len(pending)} pending ACR(s)")
    if risks:
        print(f"Risk: {', '.join(risks)}")


def _print_status_prompt(root, state, goal, testing, review, fix_loop):
    """AI prompt injection — minimal. Only what the model needs to decide next action.

    A2-class: phase, active task/plan, health/blockers, PRIMARY, forbidden, current skill.
    No routing topology, no advisory, no assets, no reports, no history.
    """
    phase = state.get("phase", "unknown")
    level = state.get("workflow_level", "L1_review_light")
    task_id = state.get("active_task_id", "")
    plan_id = state.get("active_plan_id", "")
    ctx_id = state.get("active_context_id", "")

    # Phase anchor with topology: tells AI what to do NOW, placed FIRST so it
    # can't be missed. Repeated at the end as well.
    #
    # Per-topology subagent requirements:
    #   single_agent: all inline
    #   light_review: executor=subagent, tester+reviewer=inline (same agent)
    #   standard_team: all subagent (executor, tester, reviewer)
    #   fanout_merge: all subagent (parallel)
    topo = state.get("execution_topology", "")
    # Per-topology subagent requirements:
    #   single_agent: all inline (L0)
    #   light_review: executor=subagent, tester+reviewer=same subagent (L1)
    #   standard_team: executor+tester+reviewer each subagent (L2)
    #   fanout_merge: same as standard_team, adversarial depth (L3/security)
    topo = state.get("execution_topology", "")
    needs_exec_sub = topo in ("light_review", "standard_team", "fanout_merge")
    needs_test_sub = topo in ("standard_team", "fanout_merge")
    needs_review_sub = topo in ("standard_team", "fanout_merge")
    is_light_review = topo == "light_review"
    anchors = {
        "discussing": ("/aiwf-planner — shape Goal Tree. No project code.", False),
        "planned": ("/aiwf-planner-contracts — freeze contracts, then aiwf plan activate.", False),
        "implementing": ("/aiwf-implement — "
            + ("SPAWN aiwf-executor SUBAGENT. Do NOT inline." if needs_exec_sub
               else "inline OK. Stay in allowed_write."), needs_exec_sub),
        "testing": ("/aiwf-test — "
            + ("SPAWN aiwf-tester SUBAGENT. Evidence first." if needs_test_sub
               else "reviewer-light subagent does testing+review." if is_light_review
               else "inline OK. record-testing --status adequate."), needs_test_sub or is_light_review),
        "reviewing": ("/aiwf-review — "
            + ("SPAWN aiwf-reviewer SUBAGENT. Cleanup first." if needs_review_sub
               else "same reviewer-light subagent. record-review." if is_light_review
               else "inline OK. record-review."), needs_review_sub or is_light_review),
        "closing": ("/aiwf-close — prepare-close then task close. No JSON hand-edits.", False),
        "closed": ("CLOSED. Run aiwf status.", False),
    }
    anchor, requires_subagent = anchors.get(phase, ("", False))
    if requires_subagent:
        print(f"DO: {anchor}")
    else:
        print(f"[ATTN] {anchor}")

    # One-line status with goal context
    parts = [f"Phase: {phase}", f"level={level}"]
    if task_id:
        parts.append(f"task={task_id}")
    if plan_id:
        parts.append(f"plan={plan_id}")
    if ctx_id:
        parts.append(f"ctx={ctx_id}")

    # Goal context from active task
    parent_goal = state.get("active_task_parent_goal", "") or ""
    if not parent_goal and task_id:
        try:
            from ..core.task_ledger import load_ledger
            ledger = load_ledger(str(root))
            for t in ledger.get("tasks", []):
                if t.get("id") == task_id:
                    parent_goal = t.get("parent_goal", "") or ""
                    break
        except Exception:
            pass
    if parent_goal:
        parts.append(f"goal={parent_goal}")
    # Active milestone from plans.json
    active_milestone_id = state.get("active_milestone_id", "")
    if not active_milestone_id:
        try:
            milestones_data = _read_json(root / ".aiwf" / "state" / "milestones.json", {})
            active_milestone_id = milestones_data.get("active_milestone_id", "") or ""
        except Exception:
            pass
    if active_milestone_id:
        parts.append(f"milestone={active_milestone_id}")
    print("  ".join(parts))
    topo_short = {
        "single_agent": "1-agent",
        "single_agent_with_machine_evidence": "1-agent+machine-evidence",
        "light_review": "executor+light-review",
        "standard_team": "executor→tester→reviewer",
        "fanout_merge": "parallel-agents→merge",
    }
    topo_label = topo_short.get(topo, topo)
    print(f"level={level} mode={state.get('request_mode', 'execution')} topo={topo_label}")

    # Health
    blockers = []
    if fix_loop.get("status") == "open":
        route = fix_loop.get("route", "?")
        blockers.append(f"fix-loop open -> {route}")
    if state.get("scope_violation"):
        blockers.append("scope violation")
    rstat = review.get("result", "unknown")
    if rstat not in ("accepted", "unknown"):
        blockers.append(f"review={rstat}")
    tstat = testing.get("status", "missing")
    if tstat == "failed":
        blockers.append("testing failed")
    if blockers:
        print(f"BLOCKED: {', '.join(blockers)}")
    else:
        print("Health: ok")

    # Downgrade check: when routing recommends higher level than current,
    # Planner must explain to user and get confirmation. Cannot silently drop.
    if task_id:
        lvls = ["L0_direct","L1_review_light","L2_standard_team","L3_full_power"]
        rec_level = state.get("recommended_minimum_level", "")
        if rec_level and rec_level in lvls and level in lvls and lvls.index(rec_level) > lvls.index(level):
            factors = state.get("routing_factors", []) or []
            reasons = [f for f in factors if not f.startswith("downgrade:")]
            print(f"DOWNGRADE: routing recommends {rec_level} (current {level}). "
                  f"User must confirm. Reasons: {', '.join(reasons[:3])}")

    # Technical debt summary: one compact line of what needs attention
    debt_items = []
    try:
        from ..core.task_gravity import should_trigger_architecture_review
        arch = should_trigger_architecture_review(str(root))
        if arch.get("should_trigger"):
            debt_items.append(f"architect review due ({arch.get('closed_task_count', '?')} tasks)")
    except Exception:
        pass
    try:
        # Hotspots from cross-task quality
        history_path = root / ".aiwf" / "runtime" / "history" / "task-history.json"
        if history_path.exists():
            hist = _read_json(history_path, {"tasks": []})
            file_counts = {}
            for t in hist.get("tasks", [])[-10:]:
                for p in t.get("changed_files", []) or []:
                    file_counts[p] = file_counts.get(p, 0) + 1
            hotspots = [p for p, c in file_counts.items() if c >= 3]
            if hotspots:
                debt_items.append(f"{len(hotspots)} hotspot{'s' if len(hotspots)>1 else ''}")
    except Exception:
        pass
    # Pending adversarial observations
    if review.get("adversarial_observations"):
        pending_adv = [o for o in review.get("adversarial_observations", []) or []
                       if isinstance(o, dict) and o.get("disposition") == "pending"]
        if pending_adv:
            debt_items.append(f"{len(pending_adv)} pending adversarial obs")
    if debt_items:
        print(f"Debt: {', '.join(debt_items)}")

    # Load guidance once
    guidance = None
    try:
        from ..core.process_contract import planner_process_guidance
        guidance = planner_process_guidance(str(root))
    except Exception:
        pass

    # Recovery / PRIMARY (trimmed to fit prompt budget)
    if guidance:
        rec = guidance.get("recovery") or {}
        if rec and rec.get("state") != "clear":
            primary = rec.get("primary", "")
            if primary:
                print(f"PRIMARY: {primary[:160]}")
            for item in (rec.get("legal_options") or [])[:1]:
                print(f"→ {item[:160]}")
            forbidden = rec.get("forbidden", []) or []
            if forbidden:
                print(f"NO: {'; '.join(f[:80] for f in forbidden[:2])}")

    # Repeat the action directive — last thing the model sees before acting
    if anchor:
        print(f"Remember: {anchor}")


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
    report_exists = (root / ".aiwf" / "artifacts" / "reports" / "闭合报告.md").exists()
    drift_path = root / ".aiwf" / "runtime" / "internal" / "workspace-drift.json"
    drift_exists = drift_path.exists()
    cap_path = root / ".aiwf" / "assets" / "capabilities.json"
    cap_exists = cap_path.exists()

    blockers = []
    if fix_loop.get("status") == "open":
        blockers.append("fix-loop open")
    if state.get("scope_violation"):
        blockers.append("scope violation")
    if review.get("result") not in ("accepted", "unknown"):
        blockers.append(f"review {review['result']}")

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
    print(f"  Review:   {review.get('result', 'unknown')}{verdict_part}  closure_allowed={review.get('closure_allowed', False)}")
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

    goal_data = _read_json(root / ".aiwf" / "state" / "goal.json", {})
    brief = goal_data.get("quality_brief", {})
    arch = brief.get("architecture_brief", {})
    has_arch = arch and any(v for v in arch.values() if v and v != "" and v != [])
    print(f"  Architecture: {'brief present' if has_arch else 'missing'}")
    surfaces = brief.get("surface_types", [])
    print(f"  Surfaces: {', '.join(surfaces) if surfaces else 'none'}")
    acrs = fix_loop.get("architecture_change_requests", [])
    if any(a.get("status") == "proposed" for a in acrs):
        print("  Architecture changes: pending")
    elif acrs:
        print("  Architecture changes: resolved")
    else:
        print("  Architecture changes: none")
    closure_ok = state.get("closure_allowed") or review.get("closure_allowed")
    print(f"  Closure:  {'allowed' if closure_ok else 'closed' if state.get('phase') == 'closed' else 'blocked' if state.get('close_attempt') else 'not attempted'}")
    print()

    print("── Awareness ──")
    print(f"  Workspace drift:  {'pending review' if drift_pending else 'clean' if drift_exists else 'not scanned'}")
    print(f"  Ext capabilities: {'high-risk' if cap_high else 'available' if cap_count > 0 else 'none'}")
    print(f"  Context dispatch: {'present' if _has_context_dispatch(root, state) else 'missing'}")
    active_tasks = task_summary.get("active_task_ids", [])
    task_counts = task_summary.get("counts", {})
    total_tasks = sum(task_counts.values())
    print(f"  Task ledger:      {len(active_tasks)} active / {total_tasks} tasks")
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
        print(f"  Quality digest:   clear" if (root / ".aiwf" / "artifacts" / "reports" / "质量摘要.md").exists() else "  Quality digest:   none")
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
    print(
        f"  Routing: {guidance['workflow_level']} / complexity={guidance['complexity']} "
        f"/ score={guidance['routing_score']}"
    )
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
    ckpt_dir = root / ".aiwf" / "runtime" / "checkpoints"
    ckpt_exists = ckpt_dir.exists() and any(ckpt_dir.iterdir())
    print(f"  Checkpoint: {'available' if ckpt_exists else 'none'}")
    print("  .aiwf/artifacts/reports/质量摘要.md      quality trends")
    print("  .aiwf/artifacts/reports/项目地图.md      architecture direction")
    print("  .aiwf/state + .aiwf/artifacts/quality|evidence   machine state")
    print()
    print("  CLI: aiwf doctor | aiwf workspace scan | aiwf capability scan")


def _next_action(state, review, fix_loop, drift_pending, cap_high):
    phase = state.get("phase", "discussing")
    if fix_loop.get("status") == "open":
        return "resolve fix-loop"
    if state.get("scope_violation"):
        return "resolve scope violation"
    if drift_pending:
        return "review workspace drift"
    if cap_high:
        return "review high-risk capabilities"
    if phase == "discussing":
        return "discuss goal with Planner"
    if phase == "planned":
        return "ask Planner to direct implementation"
    if phase == "implementing":
        return "ask Planner to direct testing"
    if phase == "testing":
        return "ask Planner to direct review"
    if phase == "reviewing":
        return "ask Planner to close" if review.get("result") == "accepted" else f"resolve review: {review.get('result', 'unknown')}"
    if phase == "closing":
        return "Stop hook will verify gates"
    if phase == "closed":
        return "check current-state.md"
    return "discuss with Planner"


def _has_context_dispatch(root: Path, state: Dict[str, Any]) -> bool:
    ctx_id = state.get("active_context_id")
    if not ctx_id:
        return False
    contexts = _read_json(root / ".aiwf" / "state" / "contexts.json", {"contexts": []})
    for ctx in contexts.get("contexts", []):
        if ctx.get("id") == ctx_id:
            return bool(ctx.get("purpose") or ctx.get("test_focus") or ctx.get("review_focus"))
    return False


def _environment_status(root: Path) -> str:
    env_path = root / ".aiwf" / "assets" / "environment.json"
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
    ideas_path = root / ".aiwf" / "artifacts" / "reports" / "ideas.md"
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
                        "Roleplaying executor/tester/reviewer for L2+; skipping gates"),
            "executor": ("Read context scope and architecture_brief; implement within allowed_write",
                         "Executor is scoped to assigned context; implement then hand off to Tester",
                         "Architecture changes without ACR; hand-editing AIWF state; committing code"),
            "tester": ("Validate at selected test depth; record all commands with output",
                       "Independent testing is required before review; tests must be traceable",
                       "Recording adequate without running full regression when template requires; prose-only claims"),
            "reviewer": ("Verify cleanup_verified_at, audit evidence, check architecture boundaries, record adversarial observations",
                         "Independent review is required before closure; contract critique, not checklist",
                         "Reviewing own code; skipping cleanup verification; defaulting to full test rerun"),
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
    goal = _read_json(root / ".aiwf" / "state" / "goal.json", {})
    contexts = _read_json(root / ".aiwf" / "state" / "contexts.json", {"contexts": []})
    review = _read_json(root / ".aiwf" / "artifacts" / "quality" / "review.json", {"result": "unknown"})
    fix_loop = _read_json(root / ".aiwf" / "state" / "fix-loop.json", {"status": "none"})
    testing = _read_json(root / ".aiwf" / "artifacts" / "quality" / "testing.json", {"status": "missing"})

    phase = state.get("phase", "discussing")
    request_mode = state.get("request_mode", "execution")
    level = state.get("workflow_level", "L1_review_light")
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
                "forbidden": "Roleplaying executor/tester/reviewer for L2+; skipping gates",
            },
            "executor": {
                "action": f"Read context {ctx_id} scope and architecture_brief; implement within allowed_write",
                "why": "Executor is scoped to assigned context; implement then hand off to Tester",
                "forbidden": "Architecture changes without ACR; hand-editing AIWF state; committing code",
            },
            "tester": {
                "action": f"Validate at depth {state.get('test_template', 'targeted')}; record all commands with output",
                "why": "Independent testing is required before review; tests must be traceable",
                "forbidden": "Recording adequate without running full regression when template requires; prose-only claims",
            },
            "reviewer": {
                "action": "Verify cleanup_verified_at, audit evidence, check architecture boundaries, record adversarial observations",
                "why": "Independent review is required before closure; contract critique, not checklist",
                "forbidden": "Reviewing own code; skipping cleanup verification; defaulting to full test rerun",
            },
        }
        ra = role_actions.get(role, role_actions["planner"])
        print(f"NEXT_ROLE: {role}")
        print(f"ACTION: {ra['action']}")
        print(f"WHY: {ra['why']}")
        print(f"FORBIDDEN: {ra['forbidden']}")
        print(f"PHASE: {phase}")
        print(f"LEVEL: {level}")
        if fix_loop.get("status") == "open":
            print(f"FIX_LOOP: open (route={fix_loop.get('route', '?')})")
        return

    # ── Phase → next role & action ──
    phase_map = {
        "discussing": {
            "role": "planner",
            "action": f"Confirm goal and freeze contracts (request_mode={request_mode})",
            "why": "Contracts must be frozen before any code is written",
            "forbidden": "Project writes; only state, goal, and plan changes allowed",
        },
        "planned": {
            "role": "executor" if level != "L0_direct" else "planner",
            "action": f"Implement within context {ctx_id}" if ctx_id else "Activate task first (aiwf task activate)",
            "why": f"Phase={phase}, level={level}, context={ctx_id or 'none'}",
            "forbidden": f"Writes outside allowed_write; architecture changes without ACR",
        },
        "implementing": {
            "role": "tester",
            "action": f"Validate changes at depth {state.get('test_template', 'targeted')}",
            "why": f"Implementation recorded; independent testing required at level {level}",
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
            "action": "Disposition adversarial observations, then prepare-close",
            "why": f"Review result={review.get('result')}",
            "forbidden": "Closing without meta-critique and fix-loop resolution",
        },
        "closing": {
            "role": "planner",
            "action": "Resolve blockers, complete meta-critique, run prepare-close",
            "why": "Closure requires all gates passed",
            "forbidden": "New implementation; only fix-loop and contract updates",
        },
        "closed": {
            "role": "planner",
            "action": "Carry forward: run aiwf state rebase, review current-state.md",
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
    print(f"LEVEL: {level}")

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
