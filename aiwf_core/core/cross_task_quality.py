"""Cross-task quality signals for Planner, Tester, and Reviewer."""
from __future__ import annotations

import json

from .state.goal_ops import get_active_goal
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
        history.setdefault("historical_hotspots", {})
        return history
    cold_spots = history.get("historical_hotspots", {})
    if not isinstance(cold_spots, dict):
        cold_spots = {}
    for task in tasks[:-100]:
        for path in task.get("changed_files", []) or []:
            cold_spots[path] = int(cold_spots.get(path, 0) or 0) + 1
    history["historical_hotspots"] = cold_spots
    history["tasks"] = tasks[-100:]
    return history


def append_task_history_from_state(base_dir: str, task_id: str = "", title: str = "") -> Dict[str, Any]:
    """V1: No-op. Task ledger (state/tasks.json) is the single source of truth.

    Closed tasks remain in the ledger with full entries (status, plan_id,
    milestone_id, requirements, closure, etc.). Cross-task quality signals
    are derived by scanning the ledger directly; a separate history file
    is no longer needed.
    """
    return {"id": task_id, "status": "noop"}


def evaluate_cross_task_quality(base_dir: str, recent_limit: int = 5) -> Dict[str, Any]:
    """Summarize cross-task quality signals without making semantic judgments."""
    root = Path(base_dir)
    history = _read(root / ".aiwf" / "state" / "tasks.json", {"tasks": []})
    testing = _read(root / ".aiwf" / "records" / "testing.json", {})
    review = _read(root / ".aiwf" / "records" / "review.json", {})
    tasks = history.get("tasks", []) if isinstance(history.get("tasks"), list) else []
    recent = tasks[-recent_limit:]

    file_counts: Dict[str, int] = {}
    for task in recent:
        for path in task.get("changed_files", []) or []:
            file_counts[path] = file_counts.get(path, 0) + 1
    # Merge historical hotspots with half weight to preserve long-term memory
    cold_spots = history.get("historical_hotspots", {})
    if isinstance(cold_spots, dict):
        for path, count in cold_spots.items():
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
    path = Path(base_dir) / ".aiwf" / "records" / "质量摘要.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_quality_digest(base_dir), encoding="utf-8")
    sync_quality_escalation_state(base_dir)
    return path
