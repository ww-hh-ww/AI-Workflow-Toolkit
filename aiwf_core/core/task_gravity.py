"""Emergent task gravity — historical pressure that grows with project age.

Pure function: reads state, returns result, NEVER writes.
Consumes cross_task_quality signals as its raw data source.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from collections import Counter

LEVELS = ["L0_direct", "L1_review_light", "L2_standard_team", "L3_full_power"]


def architecture_trend_signals(
    base_dir: str,
    min_tasks_for_trend: int = 8,
) -> List[Dict[str, str]]:
    """Forward-looking architecture trends from task-history. Lightweight — JSON only.

    Returns signals about where the project architecture is heading, not where it's been.
    Empty list when history is too thin to draw conclusions.
    """
    history = _read(Path(base_dir) / ".aiwf" / "history" / "task-history.json", {"tasks": []})
    tasks = history.get("tasks", []) if isinstance(history.get("tasks"), list) else []
    if len(tasks) < min_tasks_for_trend:
        return []

    signals: List[Dict[str, str]] = []

    # ── 1. Module coupling: files frequently changed together ──
    # Extract file→module mapping (first path segment as module)
    def _module(path: str) -> str:
        parts = path.replace("\\", "/").split("/")
        if parts[0] in ("src", "lib", "app", "tests", "test") and len(parts) > 1:
            return "/".join(parts[:2])
        return parts[0] if parts[0] else path

    # Build co-change matrix from task history
    module_pairs: Counter = Counter()
    module_change_counts: Counter = Counter()
    for task in tasks:
        files = task.get("changed_files", []) or []
        modules = list(set(_module(f) for f in files if f))
        for m in modules:
            module_change_counts[m] += 1
        for i in range(len(modules)):
            for j in range(i + 1, len(modules)):
                pair = tuple(sorted([modules[i], modules[j]]))
                module_pairs[pair] += 1

    # Find strongly coupled module pairs (changed together in >40% of their appearances)
    coupled_pairs = []
    for (a, b), co_count in module_pairs.most_common(10):
        a_count = module_change_counts.get(a, 1)
        b_count = module_change_counts.get(b, 1)
        max_possible = min(a_count, b_count)
        if max_possible >= 3 and co_count / max_possible > 0.4:
            coupled_pairs.append((a, b, co_count, max_possible))

    if coupled_pairs:
        details = ", ".join(f"{a}↔{b}({c}x)" for a, b, c, _ in coupled_pairs[:3])
        signals.append({
            "severity": "warn",
            "kind": "module_coupling",
            "message": f"coupled module pairs: {details}",
            "suggestion": "Consider whether these modules should be merged or have a defined interface contract",
        })

    # ── 2. Coupling growth: modules whose dependency surface is expanding ──
    if len(tasks) >= 12:
        midpoint = len(tasks) // 2
        early_tasks = tasks[:midpoint]
        late_tasks = tasks[midpoint:]

        early_modules: Counter = Counter()
        late_modules: Counter = Counter()
        for t in early_tasks:
            for f in (t.get("changed_files", []) or []):
                early_modules[_module(f)] += 1
        for t in late_tasks:
            for f in (t.get("changed_files", []) or []):
                late_modules[_module(f)] += 1

        # Modules that appeared only recently (new dependency surfaces)
        new_modules = set(late_modules.keys()) - set(early_modules.keys())
        growing_modules = []
        for m in set(late_modules.keys()) & set(early_modules.keys()):
            if late_modules[m] >= early_modules[m] * 2 and late_modules[m] >= 4:
                growing_modules.append(m)

        if len(new_modules) >= 3:
            signals.append({
                "severity": "warn",
                "kind": "surface_expansion",
                "message": f"{len(new_modules)} new modules emerged in recent tasks: {', '.join(sorted(new_modules)[:5])}",
                "suggestion": "Review whether new module boundaries are intentional or accidental",
            })

        if growing_modules:
            signals.append({
                "severity": "warn",
                "kind": "coupling_growth",
                "message": f"modules with growing change frequency: {', '.join(growing_modules[:5])}",
                "suggestion": "Check if these modules are absorbing responsibilities beyond their original scope",
            })

    # ── 3. Dormant modules: files that haven't been touched in recent history ──
    if len(tasks) >= 15:
        recent_files = set()
        for task in tasks[-10:]:
            for f in (task.get("changed_files", []) or []):
                recent_files.add(f)
        all_files = set()
        for task in tasks:
            for f in (task.get("changed_files", []) or []):
                all_files.add(f)
        dormant = sorted(all_files - recent_files)
        # Only flag if there's a newer path that looks like a replacement
        if dormant:
            # Check for potential "v1/v2" patterns
            dormant_basenames = {}
            for f in dormant:
                name = Path(f).name
                dormant_basenames.setdefault(name, []).append(f)
            # Find names that appear in BOTH dormant and active sets → possible duplicate paths
            active_basenames = set(Path(f).name for f in recent_files)
            duplicate_names = set(dormant_basenames.keys()) & active_basenames
            if duplicate_names:
                examples = []
                for name in sorted(duplicate_names)[:3]:
                    old_paths = dormant_basenames[name][:2]
                    examples.append(f"{name}: dormant={old_paths}")
                signals.append({
                    "severity": "warn",
                    "kind": "dormant_duplicates",
                    "message": f"files with same name exist in both active and dormant paths: {'; '.join(examples)}",
                    "suggestion": "These may be abandoned v1 paths alongside active v2 paths. Architect review recommended.",
                })
            elif len(dormant) >= 5:
                signals.append({
                    "severity": "warn",
                    "kind": "dormant_modules",
                    "message": f"{len(dormant)} files untouched in recent 10 tasks: {', '.join(dormant[:5])}",
                    "suggestion": "Architect should review whether these are stable or abandoned.",
                })

    # ── 4. Pattern emergence: similar change patterns across different modules ──
    # Detect when the same pattern of file changes repeats across tasks
    # (e.g., "always a handler + a model + a test file")
    pattern_counter: Counter = Counter()
    for task in tasks[-15:]:
        files = task.get("changed_files", []) or []
        # Extract file name patterns (strip paths, keep extensions)
        extensions = tuple(sorted(set(
            Path(f).suffix for f in files if Path(f).suffix
        )))
        if len(extensions) >= 2:
            pattern_counter[extensions] += 1

    # Recurring extension patterns across different tasks
    recurring_patterns = [
        (exts, count) for exts, count in pattern_counter.most_common(5)
        if count >= 3 and len(exts) >= 2
    ]
    if recurring_patterns:
        ext_desc = ", ".join(
            f"{'+'.join(exts)}({count}x)" for exts, count in recurring_patterns[:3]
        )
        signals.append({
            "severity": "warn",
            "kind": "pattern_emergence",
            "message": f"recurring file-type patterns: {ext_desc}",
            "suggestion": "If the same file types keep changing together, there may be an implicit architecture not captured in the brief",
        })

    return signals


def _read(path: Path, default=None) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else (default or {})
    except Exception:
        return default or {}


def _level_index(level: str) -> int:
    return LEVELS.index(level) if level in LEVELS else 0


def _structural_architecture_brief_present(base_dir: str) -> bool:
    """Check for a structural Architecture Brief — not just any non-empty field."""
    goal = _read(Path(base_dir) / ".aiwf" / "state" / "goal.json", {})
    brief = goal.get("quality_brief", {})
    arch = brief.get("architecture_brief", {}) if isinstance(brief, dict) else {}
    if not arch:
        return False
    structural_keys = ["target_structure", "module_boundaries", "architecture_invariants", "forbidden_restructures"]
    return any(
        arch.get(k) and arch[k] != "" and arch[k] != []
        for k in structural_keys
    )


def _path_hits(target: str, hotspot: str) -> bool:
    target = target.rstrip("/")
    hotspot = hotspot.rstrip("/")
    return target == hotspot or hotspot.startswith(target + "/") or target.startswith(hotspot + "/")


def task_gravity(
    base_dir: str,
    task_allowed_write: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Pure function. Computes emergent historical pressure. NEVER writes.

    Args:
        base_dir: Project root directory.
        task_allowed_write: Allowed write paths for the task being evaluated.

    Returns:
        history_weight: float 0.0→1.0
        suggested_min_level: None | "L1_review_light" | "L2_standard_team" | "L3_full_power"
        hard_constraints: [{kind, message}] — mechanical blockers
        soft_warnings: [{kind, message}] — advisory only
        context_messages: [str] — ≤5 lines for Planner display
    """
    from .cross_task_quality import evaluate_cross_task_quality

    task_allowed_write = task_allowed_write or []
    quality = evaluate_cross_task_quality(base_dir)
    state = _read(Path(base_dir) / ".aiwf" / "state" / "state.json", {})

    recent_count = quality.get("recent_task_count", 0)
    # Weighted gravity: complex tasks weigh more. Fix-loops, breadth, cross-module, ADVs all add weight.
    # Simple typo fixes weigh ~0.7, complex L2 refactors weigh ~2.0.
    weighted_sum = 0.0
    hist = _read(Path(base_dir) / ".aiwf" / "history" / "task-history.json", {"tasks": []})
    raw_tasks = [t for t in (hist.get("tasks", []) or []) if isinstance(t, dict)]
    if raw_tasks:
        for t in raw_tasks[-20:]:
            w = 1.0
            w += min(int(t.get("fix_loop_attempt_count", 0) or 0) * 0.5, 2.0)
            w += min(len(t.get("changed_files", []) or []) * 0.1, 1.0)
            w += min(int(t.get("adversarial_observation_count", 0) or 0) * 0.3, 1.0)
            lvl = t.get("workflow_level", "")
            if lvl in ("L2_standard_team", "L3_full_power"): w *= 1.3
            elif lvl == "L0_direct": w *= 0.7
            weighted_sum += w
    else:
        weighted_sum = float(recent_count or 0)
    history_weight = min(weighted_sum / 20.0, 1.0)
    has_arch_brief = _structural_architecture_brief_present(base_dir)

    hard_constraints: List[Dict[str, str]] = []
    soft_warnings: List[Dict[str, str]] = []
    context_messages: List[str] = []
    escalate_signals: List[str] = []

    # ── Hotspot analysis ──
    hotspots = quality.get("repeated_change_hotspots", []) or []
    severe_hotspots = [h for h in hotspots if int(h.get("count", 0) or 0) >= 3]
    hotspot_hits = [
        h for h in severe_hotspots
        if any(_path_hits(path, h["path"]) for path in task_allowed_write)
    ] if task_allowed_write else []

    # Task-specific hotspot hits (only when task_allowed_write is known)
    if hotspot_hits:
        if not has_arch_brief:
            paths = ", ".join(f"{h['path']}({h['count']}x)" for h in hotspot_hits[:3])
            hard_constraints.append({
                "kind": "repeated_change_hotspot",
                "message": f"hotspot files require architecture brief before modification: {paths}",
            })
        else:
            paths = ", ".join(f"{h['path']}({h['count']}x)" for h in hotspot_hits[:3])
            soft_warnings.append({
                "kind": "repeated_change_hotspot",
                "message": f"modifying hotspot files: {paths}; architecture brief present",
            })
            context_messages.append(f"repeated hotspot {paths}; architecture brief present, ok to proceed")

    # Project-level severe hotspots always escalate (even without task_allowed_write)
    if severe_hotspots and not has_arch_brief:
        escalate_signals.append("repeated_change_hotspot")
        if not hotspot_hits:
            paths = ", ".join(f"{h['path']}({h['count']}x)" for h in severe_hotspots[:3])
            context_messages.append(f"project hotspots require architecture brief: {paths}")

    if severe_hotspots and not hotspot_hits:
        paths = ", ".join(f"{h['path']}({h['count']}x)" for h in severe_hotspots[:3])
        soft_warnings.append({
            "kind": "repeated_change_hotspot_project",
            "message": f"project has repeated hotspots not touched by this task: {paths}",
        })

    # Mild hotspots (count 2)
    mild_hotspots = [h for h in hotspots if int(h.get("count", 0) or 0) == 2]
    if mild_hotspots:
        paths = ", ".join(h["path"] for h in mild_hotspots[:3])
        context_messages.append(f"emerging hotspot: {paths} (2x each, watching)")

    # ── Fix-loop trend ──
    signals = quality.get("signals", []) or []
    fix_loop_signal = next((s for s in signals if s.get("kind") == "fix_loop_trend"), None)
    if fix_loop_signal and fix_loop_signal.get("severity") == "escalate":
        msg = f"fix-loop trend: {quality.get('fix_loop_attempts', 0)} recent attempts"
        escalate_signals.append("fix_loop_trend")
        current_level = state.get("workflow_level", "L1_review_light")
        if _level_index(current_level) < _level_index("L2_standard_team"):
            hard_constraints.append({
                "kind": "fix_loop_trend",
                "message": f"{msg}; requires L2_standard_team or higher",
            })
        else:
            soft_warnings.append({"kind": "fix_loop_trend", "message": msg})
        context_messages.append(msg)

    # ── Architecture drift ──
    arch_drift = quality.get("architecture_drift", []) or []
    if arch_drift:
        if not has_arch_brief:
            hard_constraints.append({
                "kind": "architecture_drift",
                "message": f"architecture drift detected ({len(arch_drift)} observations); architecture brief required before activation",
            })
            escalate_signals.append("architecture_drift")
        else:
            soft_warnings.append({
                "kind": "architecture_drift",
                "message": f"architecture drift observations exist ({len(arch_drift)}); review before proceeding",
            })
            context_messages.append(f"architecture drift: {len(arch_drift)} observation(s); review recommended")

    # ── Testing debt trend ──
    testing_debt_signal = next((s for s in signals if s.get("kind") == "testing_debt_trend"), None)
    if testing_debt_signal:
        context_messages.append(f"testing debt: {quality.get('risk_task_count', 0)} recent tasks with untested risks")
        soft_warnings.append({
            "kind": "testing_debt_trend",
            "message": f"{quality.get('risk_task_count', 0)} recent tasks have untested/deferred risks",
        })

    # ── Suggested minimum level ──
    suggested_min_level = None
    if len(escalate_signals) >= 2:
        suggested_min_level = "L3_full_power"
    elif escalate_signals:
        suggested_min_level = "L2_standard_team"
    elif len(soft_warnings) >= 3 and history_weight > 0.3:
        suggested_min_level = "L2_standard_team"

    # Capped at 5 context messages
    context_messages = context_messages[:5]

    # ── Architecture trend signals (forward-looking) ──
    trends = architecture_trend_signals(base_dir)
    for t in trends:
        if t.get("severity") == "escalate":
            escalate_signals.append(t["kind"])
            context_messages.append(f"trend: {t['message'][:120]}")
        else:
            context_messages.append(f"trend: {t['message'][:120]}")

    # Capped at 5 context messages
    context_messages = context_messages[:5]

    # Expanded read hints for adversarial Reviewer/Tester — strategic, not blind
    expanded_read_hints: List[str] = []
    for h in severe_hotspots[:5]:
        expanded_read_hints.append(f"{h['path']} (hotspot, {h['count']}x)")
    for h in mild_hotspots[:3]:
        expanded_read_hints.append(f"{h['path']} (emerging hotspot, {h['count']}x)")
    if arch_drift:
        expanded_read_hints.append(f"architecture_brief fields (drift observed: {len(arch_drift)} observations)")
    # Add trend signals as read hints
    for t in trends[:3]:
        expanded_read_hints.append(f"trend: {t['kind']} — {t['message'][:80]}")

    return {
        "history_weight": history_weight,
        "suggested_min_level": suggested_min_level,
        "hard_constraints": hard_constraints,
        "soft_warnings": soft_warnings,
        "context_messages": context_messages,
        "expanded_read_hints": expanded_read_hints[:10],
        "architecture_trends": trends,
    }


def apply_gravity_to_state(base_dir: str, state: Dict[str, Any]) -> Dict[str, Any]:
    """Mutate state dict with gravity escalation flags. Call ONLY from state_ops."""
    gravity = task_gravity(base_dir)
    suggested = gravity.get("suggested_min_level")
    if suggested:
        current = state.get("workflow_level", "L1_review_light")
        if _level_index(current) < _level_index(suggested):
            state["quality_escalation_required"] = True
            state["quality_escalation_reason"] = f"gravity suggests {suggested}"
            state["recommended_minimum_level"] = suggested
    return state


def should_trigger_architecture_review(base_dir: str) -> Dict[str, Any]:
    """Check if a periodic architecture review is recommended. Lightweight — JSON only.

    Trigger conditions (any one):
      1. Closed task count % cadence == 0 (default cadence=10)
      2. Gravity weight >= 0.5 for the first time
      3. PROJECT-MAP Architecture Direction last updated > 30 days ago
      4. 3+ active escalate signals from cross-task quality
      5. New module surface expansion detected in trends

    Returns dict with should_trigger, reasons, and recommended action.
    """
    import json
    from datetime import datetime, timezone
    from .cross_task_quality import evaluate_cross_task_quality

    root = Path(base_dir)
    history_path = root / ".aiwf" / "history" / "task-history.json"
    pm_path = root / ".aiwf" / "reports" / "项目地图.md"
    state_path = root / ".aiwf" / "state" / "state.json"
    review_path = root / ".aiwf" / "quality" / "review.json"

    history = _read(history_path, {"tasks": []})
    tasks = history.get("tasks", []) if isinstance(history.get("tasks"), list) else []
    closed_count = len(tasks)
    state = _read(state_path, {})
    review = _read(review_path, {})

    reasons = []
    cadence = 10

    # ── 1. Milestone: every N closed tasks ──
    if closed_count > 0 and closed_count % cadence == 0:
        reasons.append(f"milestone: {closed_count} closed tasks")

    # ── 2. Gravity tipping point ──
    quality = evaluate_cross_task_quality(base_dir)
    gravity = task_gravity(base_dir)
    gravity_weight = gravity.get("history_weight", min(closed_count / 20.0, 1.0))
    if gravity_weight >= 0.5:
        reasons.append(f"gravity weight {gravity_weight:.2f} — project is maturing")

    # ── 3. PROJECT-MAP staleness ──
    if pm_path.exists():
        try:
            pm_mtime = pm_path.stat().st_mtime
            pm_age_days = (datetime.now(timezone.utc).timestamp() - pm_mtime) / 86400
            if pm_age_days > 30:
                reasons.append(f"PROJECT-MAP may be stale ({pm_age_days:.0f} days since update)")
        except Exception:
            pass
    elif closed_count >= 5:
        reasons.append("PROJECT-MAP.md missing after 5+ tasks")

    # ── 4. Escalate signal accumulation ──
    signals = quality.get("signals", []) or []
    escalate_count = sum(1 for s in signals if s.get("severity") == "escalate")
    if escalate_count >= 3:
        reasons.append(f"{escalate_count} active escalate signals")

    # ── 5. Architecture surface expansion ──
    trends = architecture_trend_signals(base_dir)
    expansion = next((t for t in trends if t.get("kind") == "surface_expansion"), None)
    if expansion:
        reasons.append(f"surface expansion: {expansion['message'][:100]}")

    # ── Check if recently done (within last 5 closed tasks) ──
    # Avoid triggering every prompt once conditions are met
    last_architect_task = None
    for t in reversed(tasks):
        if t.get("title", "").lower().startswith("[architect]") or t.get("id", "").startswith("ARCH-"):
            last_architect_task = t
            break

    recently_done = False
    if last_architect_task and len(tasks) > 0:
        last_idx = tasks.index(last_architect_task) if last_architect_task in tasks else -1
        if last_idx >= 0 and (len(tasks) - last_idx) < (cadence // 2):
            recently_done = True

    should_trigger = bool(reasons) and not recently_done

    return {
        "should_trigger": should_trigger,
        "reasons": reasons,
        "closed_task_count": closed_count,
        "next_milestone": ((closed_count // cadence) + 1) * cadence,
        "recently_done": recently_done,
        "recommended_action": "Invoke /aiwf-architect for periodic architecture review" if should_trigger else None,
    }
