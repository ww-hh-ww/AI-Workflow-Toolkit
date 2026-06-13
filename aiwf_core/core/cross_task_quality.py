"""Cross-task quality signals for Planner, Tester, and Reviewer."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def _read(path: Path, default=None) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else (default or {})
    except Exception:
        return default or {}


def _write(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _classify_post_hoc_warning(warning: str) -> str:
    """Classify a post-hoc warning into a kind for cross-task pattern detection."""
    w = warning.lower()
    if "no commands" in w or "no evidence_ids" in w:
        return "testing_no_commands"
    if "not traceable" in w:
        return "testing_untraceable"
    if "all 8 quality dimensions scored pass" in w:
        return "review_no_adversarial"
    if "does not match any evidence" in w:
        return "evidence_id_mismatch"
    return "other"


def _accepted_changed_files(evidence: Dict[str, Any]) -> List[str]:
    changed = set()
    for record in evidence.get("records", []) or []:
        if record.get("status") == "accepted":
            for path in record.get("changed_files", []) or []:
                changed.add(path)
    return sorted(changed)


def _archive_trimmed_tasks(history: Dict[str, Any], tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    if len(tasks) <= 100:
        history["tasks"] = tasks
        history.setdefault("archived_hotspots", {})
        return history
    archived = history.get("archived_hotspots", {})
    if not isinstance(archived, dict):
        archived = {}
    for task in tasks[:-100]:
        for path in task.get("changed_files", []) or []:
            archived[path] = int(archived.get(path, 0) or 0) + 1
    history["archived_hotspots"] = archived
    history["tasks"] = tasks[-100:]
    return history


def append_task_history_from_state(base_dir: str, task_id: str = "", title: str = "") -> Dict[str, Any]:
    """Append/update a closed-task history record from current AIWF state."""
    root = Path(base_dir)
    history_path = root / ".aiwf" / "runtime" / "history" / "task-history.json"
    history = _read(history_path, {"tasks": []})
    tasks = history.get("tasks", []) if isinstance(history.get("tasks"), list) else []
    state = _read(root / ".aiwf" / "state" / "state.json", {})
    goal = _read(root / ".aiwf" / "state" / "goal.json", {})
    evidence = _read(root / ".aiwf" / "artifacts" / "evidence" / "records.json", {"records": []})
    testing = _read(root / ".aiwf" / "artifacts" / "quality" / "testing.json", {})
    review = _read(root / ".aiwf" / "artifacts" / "quality" / "review.json", {})
    fix_loop = _read(root / ".aiwf" / "state" / "fix-loop.json", {})
    contexts = _read(root / ".aiwf" / "state" / "contexts.json", {"contexts": []})

    record_id = task_id or f"goal-v{goal.get('goal_version', 1)}-closed"
    record = {
        "id": record_id,
        "closed_at": datetime.now(timezone.utc).isoformat(),
        "goal_version": goal.get("goal_version", 1),
        "goal": goal.get("current_goal") or goal.get("active_goal", "") or title,
        "title": title,
        "workflow_level": state.get("workflow_level", state.get("workflow_strength", "")),
        "task_type": state.get("task_type", ""),
        "context_ids": [c.get("id", "") for c in contexts.get("contexts", []) or [] if c.get("id")][:20],
        "accepted_evidence_count": len([r for r in evidence.get("records", []) or [] if r.get("status") == "accepted"]),
        "changed_files": _accepted_changed_files(evidence)[:50],
        "testing_status": testing.get("status", "missing"),
        "untested_risk_count": len(testing.get("untested_risks", []) or []),
        "review_result": review.get("result", "unknown"),
        "fix_loop_attempt_count": fix_loop.get("attempt_count", 0) or 0,
        "cleanup_status": review.get("cleanup_status", ""),
        "structure_status": review.get("structure_status", ""),
    }
    # Compact adversarial observation summary — counts only, not full messages
    adv_obs = review.get("adversarial_observations", []) or []
    if adv_obs:
        record["adversarial_observation_count"] = len(adv_obs)
        record["adversarial_escalation_count"] = sum(
            1 for o in adv_obs if isinstance(o, dict) and o.get("severity") == "escalate"
        )
        record["adversarial_kinds"] = list(set(
            o.get("kind", "") for o in adv_obs if isinstance(o, dict) and o.get("kind")
        ))
    # Post-hoc warning summary — for cross-task pattern detection
    ph_warnings = review.get("post_hoc_warnings", []) or []
    if ph_warnings:
        record["post_hoc_warning_count"] = len(ph_warnings)
        record["post_hoc_warning_kinds"] = list(set(
            _classify_post_hoc_warning(w) for w in ph_warnings
        ))
    tasks = [t for t in tasks if t.get("id") != record_id]
    tasks.append(record)
    history = _archive_trimmed_tasks(history, tasks)
    _write(history_path, history)
    return record


def evaluate_cross_task_quality(base_dir: str, recent_limit: int = 5) -> Dict[str, Any]:
    """Summarize cross-task quality signals without making semantic judgments."""
    root = Path(base_dir)
    history = _read(root / ".aiwf" / "runtime" / "history" / "task-history.json", {"tasks": []})
    testing = _read(root / ".aiwf" / "artifacts" / "quality" / "testing.json", {})
    review = _read(root / ".aiwf" / "artifacts" / "quality" / "review.json", {})
    tasks = history.get("tasks", []) if isinstance(history.get("tasks"), list) else []
    recent = tasks[-recent_limit:]

    file_counts: Dict[str, int] = {}
    for task in recent:
        for path in task.get("changed_files", []) or []:
            file_counts[path] = file_counts.get(path, 0) + 1
    # Merge archived hotspots with half weight to preserve long-term memory
    archived = history.get("archived_hotspots", {})
    if isinstance(archived, dict):
        for path, count in archived.items():
            file_counts[path] = file_counts.get(path, 0) + max(1, int(count or 0) // 2)
    repeated = [
        {"path": path, "count": count}
        for path, count in sorted(file_counts.items(), key=lambda item: (-item[1], item[0]))
        if count >= 2
    ]
    fix_attempts = sum(int(t.get("fix_loop_attempt_count", 0) or 0) for t in recent)
    risk_tasks = sum(1 for t in recent if int(t.get("untested_risk_count", 0) or 0) > 0)

    signals: List[Dict[str, str]] = []
    if repeated:
        signals.append({
            "severity": "warn" if repeated[0]["count"] < 3 else "escalate",
            "kind": "repeated_change_hotspot",
            "message": f"{len(repeated)} file(s) changed repeatedly across recent tasks",
        })
    if fix_attempts >= 3:
        signals.append({
            "severity": "escalate",
            "kind": "fix_loop_trend",
            "message": f"{fix_attempts} fix-loop attempt(s) across recent tasks",
        })
    if risk_tasks >= 2:
        signals.append({
            "severity": "warn",
            "kind": "testing_debt_trend",
            "message": f"{risk_tasks} recent task(s) carried untested/deferred risks",
        })
    if testing.get("cross_task_risks"):
        signals.append({
            "severity": "warn",
            "kind": "tester_cross_task_risks",
            "message": f"{len(testing.get('cross_task_risks', []))} tester cross-task risk(s) recorded",
        })
    if review.get("architecture_drift"):
        signals.append({
            "severity": "warn",
            "kind": "reviewer_architecture_drift",
            "message": f"{len(review.get('architecture_drift', []))} reviewer architecture drift observation(s)",
        })
    if review.get("testing_debt"):
        signals.append({
            "severity": "warn",
            "kind": "reviewer_testing_debt",
            "message": f"{len(review.get('testing_debt', []))} reviewer testing debt observation(s)",
        })

    # Post-hoc warning pattern detection: same warning kind across 2+ recent tasks
    warning_kind_counts: Dict[str, int] = {}
    for t in recent:
        for kind in (t.get("post_hoc_warning_kinds", []) or []):
            warning_kind_counts[kind] = warning_kind_counts.get(kind, 0) + 1
    for kind, count in warning_kind_counts.items():
        if count >= 3:
            signals.append({
                "severity": "escalate",
                "kind": f"post_hoc_{kind}_trend",
                "message": (
                    f"Post-hoc warning '{kind}' appeared in {count} recent tasks — "
                    "systematic quality gap. Next activation requires explicit Planner disposition."
                ),
            })
        elif count >= 2:
            signals.append({
                "severity": "warn",
                "kind": f"post_hoc_{kind}_repeat",
                "message": f"Post-hoc warning '{kind}' repeated in {count} recent tasks.",
            })

    return {
        "recent_task_count": len(recent),
        "fix_loop_attempts": fix_attempts,
        "risk_task_count": risk_tasks,
        "repeated_change_hotspots": repeated[:10],
        "tester_cross_task_risks": testing.get("cross_task_risks", []) or [],
        "reviewer_cross_task_risks": review.get("cross_task_risks", []) or [],
        "architecture_drift": review.get("architecture_drift", []) or [],
        "testing_debt": review.get("testing_debt", []) or testing.get("testing_debt", []) or [],
        "signals": signals,
    }


def sync_quality_escalation_state(base_dir: str) -> Dict[str, Any]:
    """Write cross-task escalation flags into state.json."""
    root = Path(base_dir)
    state_path = root / ".aiwf" / "state" / "state.json"
    state = _read(state_path, {})
    quality = evaluate_cross_task_quality(base_dir)
    escalate = [s for s in quality.get("signals", []) or [] if s.get("severity") == "escalate"]
    state["cross_task_quality_escalation_required"] = bool(escalate)
    state["cross_task_quality_escalation_reason"] = ", ".join(
        f"{s.get('kind', '?')}: {s.get('message', '')}" for s in escalate[:3]
    )
    _write(state_path, state)
    return state


def render_quality_digest(base_dir: str) -> str:
    """Render a compact Markdown digest for Planner context."""
    q = evaluate_cross_task_quality(base_dir)
    lines = ["# AIWF Quality Digest", ""]
    lines.append("## Recent Trend")
    lines.append(f"- Recent closed tasks: {q['recent_task_count']}")
    lines.append(f"- Fix-loop attempts: {q['fix_loop_attempts']}")
    lines.append(f"- Tasks with untested/deferred risk: {q['risk_task_count']}")
    lines.append("")
    lines.append("## Signals")
    if q["signals"]:
        for sig in q["signals"]:
            lines.append(f"- {sig['severity']} / {sig['kind']}: {sig['message']}")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Repeated Change Hotspots")
    if q["repeated_change_hotspots"]:
        for item in q["repeated_change_hotspots"][:10]:
            lines.append(f"- {item['path']} ({item['count']} recent tasks)")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Tester / Reviewer Observations")
    observations = (
        list(q["tester_cross_task_risks"])
        + list(q["reviewer_cross_task_risks"])
        + list(q["architecture_drift"])
        + list(q["testing_debt"])
    )
    if observations:
        for obs in observations[:10]:
            lines.append(f"- {str(obs)[:200]}")
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def write_quality_digest(base_dir: str) -> Path:
    """Write .aiwf/artifacts/reports/质量摘要.md and return the path."""
    path = Path(base_dir) / ".aiwf" / "artifacts" / "reports" / "质量摘要.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_quality_digest(base_dir), encoding="utf-8")
    sync_quality_escalation_state(base_dir)
    return path
