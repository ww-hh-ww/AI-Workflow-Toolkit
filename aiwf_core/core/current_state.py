"""Freshness checks for .aiwf/reports/当前状态.md."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List


SOURCE_FILES = [
    "state/state.json",
    "state/goal.json",
    "evidence/records.json",
    "quality/testing.json",
    "quality/review.json",
    "state/fix-loop.json",
    "state/contexts.json",
    "history/task-history.json",
    "history/task-ledger.json",
]

def current_state_freshness(base_dir: str) -> Dict[str, object]:
    """Check whether AIWF state files are mutually consistent. Reads .json directly."""
    root = Path(base_dir)
    aiwf = root / ".aiwf"

    json_sources = [f for f in SOURCE_FILES if f.endswith(".json")]
    missing = [f for f in json_sources if not (aiwf / f).exists()]
    if missing:
        return {"status": "incomplete", "missing": missing, "exists": False}

    try:
        mtimes = [(f, (aiwf / f).stat().st_mtime) for f in json_sources]
    except OSError:
        return {"status": "unreadable", "stale_sources": [], "exists": True}

    max_mtime = max(mt for _, mt in mtimes)
    stale_sources = [f for f, mt in mtimes if mt < max_mtime - 60]

    return {
        "status": "stale" if stale_sources else "fresh",
        "stale_sources": stale_sources,
        "structure_issues": structure_issues,
        "exists": True,
    }


def rebuild_current_state(base_dir: str) -> str:
    """Mechanically rebuild .aiwf/reports/当前状态.md from state files + PROJECT-MAP.

    Zero model involvement. Pure extraction of deterministic facts.
    Planner reads this; Planner does not write this.
    """
    import json
    from datetime import datetime, timezone

    root = Path(base_dir)
    aiwf = root / ".aiwf"

    def _rj(name, default=None):
        p = aiwf / name
        try:
            return json.loads(p.read_text(encoding="utf-8")) if p.exists() else (default or {})
        except Exception:
            return default or {}

    state = _rj("state/state.json", {})
    goal = _rj("state/goal.json", {})
    evidence = _rj("evidence/records.json", {"records": []})
    testing = _rj("quality/testing.json", {})
    review = _rj("quality/review.json", {})
    fix_loop = _rj("state/fix-loop.json", {})
    history = _rj("history/task-history.json", {"tasks": []})
    ledger = _rj("history/task-ledger.json", {"tasks": []})

    # PROJECT-MAP sections for strategic context
    pm_text = ""
    pm_path = aiwf / "reports" / "项目地图.md"
    if pm_path.exists():
        try:
            pm_text = pm_path.read_text(encoding="utf-8")
        except Exception:
            pass

    def _extract_pm_section(header):
        import re
        m = re.search(rf'## {re.escape(header)}\n(.*?)(?=\n## |\Z)', pm_text, re.DOTALL)
        return m.group(1).strip() if m else ""

    lines = [
        "# AIWF Current State",
        f"<!-- mechanically generated {datetime.now(timezone.utc).isoformat()} -->",
        "",
    ]

    active_goal = goal.get("current_goal") or goal.get("active_goal", "") or "(none)"
    recs = evidence.get("records", []) or []
    accepted = sum(1 for r in recs if r.get("status") == "accepted")
    summary_blockers = []
    if fix_loop.get("status") == "open":
        summary_blockers.append(f"fix-loop route={fix_loop.get('route','?')}")
    if state.get("scope_violation"):
        summary_blockers.append("scope violation")
    pending_adv = [
        o for o in (review.get("adversarial_observations", []) or [])
        if isinstance(o, dict) and o.get("disposition") == "pending"
    ]
    if pending_adv:
        summary_blockers.append(f"{len(pending_adv)} pending adversarial observation(s)")

    lines.append("## Executive Summary")
    lines.append(f"- Goal: {active_goal[:200]}")
    lines.append(f"- Now: phase={state.get('phase', 'unknown')}, task={state.get('active_task_id') or '(none)'}, workflow={state.get('workflow_level', '?')}")
    lines.append(f"- Quality: testing={testing.get('status', 'missing')}, review={review.get('result', 'unknown')}, evidence={accepted}/{len(recs)} accepted")
    lines.append("- Blockers: " + (", ".join(summary_blockers) if summary_blockers else "none"))
    lines.append("")

    # ── Goal & Intent ──
    lines.append("## Goal & Intent")
    lines.append(f"- Goal: v{goal.get('goal_version', 1)}/{goal.get('goal_status', 'discussion')} / {active_goal[:200]}")
    intent_changes = goal.get("intent_changes", []) or []
    if intent_changes:
        lines.append("- How we got here:")
        for ic in intent_changes[-5:]:
            lines.append(f"  - v{ic.get('version','?')}: {ic.get('from','?')[:80]} → {ic.get('to','?')[:80]}")
    decisions = goal.get("decisions", []) or []
    if decisions:
        lines.append("- Key decisions:")
        for d in decisions[-5:]:
            lines.append(f"  - {str(d.get('decision', ''))[:120]}")
    lines.append("")

    # ── Architecture Direction ──
    arch_direction = _extract_pm_section("Architecture Direction")
    arch_brief = goal.get("quality_brief", {}).get("architecture_brief", {}) if isinstance(goal.get("quality_brief"), dict) else {}
    has_arch = arch_brief and any(v for v in arch_brief.values() if v and v != [] and v != "")
    if arch_direction or has_arch:
        lines.append("## Architecture Direction")
        if arch_direction:
            lines.append(arch_direction[:500])
        if has_arch:
            target = arch_brief.get("target_structure", "")
            if target:
                lines.append(f"- Target: {target[:200]}")
            boundaries = arch_brief.get("module_boundaries", []) or []
            if boundaries:
                lines.append(f"- Module boundaries: {', '.join(str(b)[:80] for b in boundaries[:5])}")
            invariants = arch_brief.get("architecture_invariants", []) or []
            if invariants:
                lines.append(f"- Invariants: {', '.join(str(i)[:80] for i in invariants[:5])}")
            protected = arch_brief.get("protected_files", []) or []
            if protected:
                lines.append(f"- Protected: {', '.join(str(p)[:80] for p in protected[:5])}")
            forbidden = arch_brief.get("forbidden_restructures", []) or []
            if forbidden:
                lines.append(f"- Forbidden: {', '.join(str(f)[:80] for f in forbidden[:5])}")
            if arch_brief.get("migration_source_of_truth"):
                lines.append(f"- Migration source of truth: {str(arch_brief['migration_source_of_truth'])[:160]}")
            legacy_paths = arch_brief.get("legacy_paths", []) or []
            legacy_terms = arch_brief.get("legacy_terms", []) or []
            if legacy_paths or legacy_terms:
                lines.append(f"- Migration legacy sweep: paths={len(legacy_paths)}, terms={len(legacy_terms)}")
            entrypoints = arch_brief.get("default_entrypoints", []) or []
            validators = arch_brief.get("validators", []) or []
            if entrypoints or validators:
                lines.append(f"- Migration behavior checks: entrypoints={len(entrypoints)}, validators={len(validators)}")
        lines.append("")

    # ── Rejected Routes ──
    rejected = _extract_pm_section("Not-now / Rejected Routes")
    if rejected and "None yet" not in rejected:
        lines.append("## Rejected Routes")
        lines.append(rejected[:500])
        lines.append("")

    # ── Open Decisions & Deferred Risks ──
    open_dec = _extract_pm_section("Open Decisions")
    deferred = _extract_pm_section("Deferred Risks")
    if (open_dec and "None yet" not in open_dec) or (deferred and "None yet" not in deferred):
        lines.append("## Decisions & Risks")
        if open_dec and "None yet" not in open_dec:
            lines.append("### Open Decisions")
            lines.append(open_dec[:400])
        if deferred and "None yet" not in deferred:
            lines.append("### Deferred Risks")
            lines.append(deferred[:400])
        lines.append("")

    # ── Current Task & Blockers ──
    lines.append("## Current Status")
    lines.append(f"- Phase: {state.get('phase', 'unknown')}")
    active_task_id = state.get("active_task_id") or ""
    if active_task_id:
        lines.append(f"- Active task: {active_task_id}")
    lines.append(f"- Workflow: {state.get('workflow_level', '?')} / {state.get('task_type', '?')}")
    ctx_id = state.get("active_context_id") or ""
    if ctx_id:
        lines.append(f"- Active context: {ctx_id}")

    # Blockers
    blockers_list = []
    if fix_loop.get("status") == "open":
        blockers_list.append(f"Fix-loop open: route={fix_loop.get('route','?')}")
    if state.get("scope_violation"):
        blockers_list.append("Scope violation")
    if review.get("result") not in ("accepted", "unknown"):
        blockers_list.append(f"Review: {review.get('result')}")
    if pending_adv:
        blockers_list.append(f"{len(pending_adv)} adversarial observation(s) pending")
    if blockers_list:
        lines.append("- Blockers:")
        for b in blockers_list:
            lines.append(f"  - {b}")
    else:
        lines.append("- Blockers: none")
    lines.append("")

    # ── Quality Snapshot ──
    lines.append("## Quality Snapshot")
    lines.append(f"- Testing: {testing.get('status', 'missing')}")
    lines.append(f"- Review: {review.get('result', 'unknown')}")

    lines.append(f"- Evidence: {accepted} accepted / {len(recs)} records")

    tasks = history.get("tasks", []) if isinstance(history.get("tasks"), list) else []
    lines.append(f"- Task history: {len(tasks)} closed tasks")

    # Last closed task
    if tasks:
        last = tasks[-1]
        lines.append(f"- Last closed: {last.get('id','?')} / {last.get('testing_status','?')} / {last.get('review_result','?')}")

    # Gravity from task_gravity
    try:
        from .task_gravity import task_gravity as _tg
        g = _tg(base_dir)
        lines.append(f"- Gravity: weight={g.get('history_weight', 0):.2f}, suggested_level={g.get('suggested_min_level') or 'none'}")
        hotspots = g.get("expanded_read_hints", []) or []
        if hotspots:
            lines.append("- Hotspot files:")
            for h in hotspots[:5]:
                lines.append(f"  - {h}")
    except Exception:
        pass

    lines.append("")
    lines.append("## Raw References")
    lines.append(f"- state/state.json: phase={state.get('phase','?')}, workflow={state.get('workflow_level','?')}")
    lines.append(f"- state/goal.json: v{goal.get('goal_version',1)}, confirmed={goal.get('confirmed',False)}")
    lines.append(f"- evidence/records.json: {len(recs)} records")
    lines.append(f"- quality/review.json: result={review.get('result','?')}")
    lines.append(f"- quality/testing.json: status={testing.get('status','?')}")
    lines.append(f"- state/fix-loop.json: status={fix_loop.get('status','none')}")
    lines.append(f"- history/task-history.json: {len(tasks)} tasks")
    lines.append(f"- history/task-ledger.json: {len(ledger.get('tasks', []))} tasks")

    content = "\n".join(lines) + "\n"
    path = aiwf / "reports" / "当前状态.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return content
