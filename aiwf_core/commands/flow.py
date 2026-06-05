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
        print("  aiwf install reasonix")
        print("  reasonix code .")
        print('  /skill aiwf-planner "describe your goal"')
        return

    state = _read_json(root / ".aiwf" / "state" / "state.json", {})
    goal = _read_json(root / ".aiwf" / "state" / "goal.json", {})
    evidence = _read_json(root / ".aiwf" / "evidence" / "records.json", {"records": []})
    testing = _read_json(root / ".aiwf" / "quality" / "testing.json", {"status": "missing"})
    review = _read_json(root / ".aiwf" / "quality" / "review.json", {"result": "unknown", "closure_allowed": False, "blockers": []})
    fix_loop = _read_json(root / ".aiwf" / "state" / "fix-loop.json", {"status": "none"})

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
    report_exists = (root / ".aiwf" / "reports" / "闭合报告.md").exists()
    drift_path = root / ".aiwf" / "internal" / "workspace-drift.json"
    drift_legacy = root / ".aiwf" / "workspace-drift.json"  # legacy pre-v2 flat path
    drift_exists = drift_path.exists() or drift_legacy.exists()
    cap_path = root / ".aiwf" / "assets" / "capabilities.json"
    cap_legacy = root / ".aiwf" / "capabilities.json"  # legacy pre-v2 flat path
    cap_exists = cap_path.exists() or cap_legacy.exists()

    blockers = []
    if fix_loop.get("status") == "open":
        blockers.append("fix-loop open")
    if state.get("scope_violation"):
        blockers.append("scope violation")
    if review.get("result") not in ("accepted", "unknown"):
        blockers.append(f"review {review['result']}")

    drift_pending = False
    if drift_exists:
        _drift_src = drift_path if drift_path.exists() else drift_legacy
        drift_pending = _read_json(_drift_src, {}).get("needs_planner_review", False)
    if drift_pending:
        blockers.append("drift pending")

    cap_high = False
    cap_count = 0
    if cap_exists:
        _cap_src = cap_path if cap_path.exists() else cap_legacy
        # if v2 path has no caps but legacy does (migration edge case), use legacy
        if _cap_src == cap_path:
            _caps = _read_json(_cap_src, {}).get("capabilities", [])
            if not _caps and cap_legacy.exists():
                _legacy_caps = _read_json(cap_legacy, {}).get("capabilities", [])
                if _legacy_caps:
                    _cap_src = cap_legacy
        caps = _read_json(_cap_src, {}).get("capabilities", [])
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
    print("── Control Panel ──")
    goal_text = goal.get("current_goal") or goal.get("active_goal", "") or "(none)"
    print(f"  Goal:     v{goal.get('goal_version', 1)}/{goal.get('goal_status', 'discussion')} / {goal_text[:120]}")
    print(f"  Phase:    {state.get('phase', 'unknown')}")
    print(f"  Workflow: {state.get('workflow_level', 'L1_review_light')} / {state.get('task_type', '') or 'not selected'}")
    print(f"  Health:   {health}")
    print(f"  Next:     {_next_action(state, review, fix_loop, drift_pending, cap_high)}")
    print()

    print("── Quality & Closure ──")
    print(f"  Testing:  {testing.get('status', 'missing')}")
    print(f"  Review:   {review.get('result', 'unknown')}  closure_allowed={review.get('closure_allowed', False)}")
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
    print(f"  Project Map:      {'present' if (root / '.aiwf' / 'reports' / '项目地图.md').exists() else 'missing'}")
    print(f"  Rules:            {_rules_status(root)}")
    print(f"  Ideas: {_ideas_status(root)}")
    print(f"  Report:           {'available' if report_exists else 'none'}")
    signals = quality_digest.get("signals", []) or []
    if signals:
        print(f"  Quality digest:   signals ({len(signals)})")
    else:
        print(f"  Quality digest:   clear" if (root / ".aiwf" / "reports" / "质量摘要.md").exists() else "  Quality digest:   none")
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
    print(
        f"  Routing: {guidance['workflow_level']} / complexity={guidance['complexity']} "
        f"/ score={guidance['routing_score']}"
    )
    factors = guidance.get("routing_factors", [])
    print(f"  Why:     {', '.join(factors[:6]) if factors else 'no mechanical routing factors recorded yet'}")
    print(
        f"  Depth:   test={guidance.get('test_template') or 'not selected'}; "
        f"review={guidance.get('review_template') or 'not selected'}; "
        f"explore={guidance.get('exploration_budget') or 'not selected'}"
    )
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
    ckpt_dir = root / ".aiwf" / "checkpoints"
    ckpt_exists = ckpt_dir.exists() and any(ckpt_dir.iterdir())
    print(f"  Checkpoint: {'available' if ckpt_exists else 'none'}")
    print("  .aiwf/reports/当前状态.md      carry-forward summary")
    print("  .aiwf/reports/闭合报告.md      closure basis")
    print("  .aiwf/state|quality|evidence   machine state")
    print()
    print("  CLI: aiwf doctor | aiwf export-report | aiwf workspace scan | aiwf capability scan")


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
    ideas_path = root / ".aiwf" / "reports" / "ideas.md"
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
