"""Milestone registry operations — optional stage nodes for long tasks."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..state_schema import (
    LEGACY_GOAL_ID,
    VALID_MILESTONE_STATUSES,
    VALID_MILESTONE_VERDICTS,
    default_milestones,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _milestones_path(base_dir: str) -> Path:
    return Path(base_dir) / ".aiwf" / "state" / "milestones.json"


def _read(path: Path, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else (default or {})
    except Exception:
        return default or {}


def _write(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _unique(items: List[str]) -> List[str]:
    return [str(x) for x in dict.fromkeys(items or []) if str(x)]


def _empty_milestone(
    milestone_id: str,
    goal_id: str = "",
    title: str = "",
    status: str = "open",
    intent: str = "",
    plan_ids: Optional[List[str]] = None,
    task_ids: Optional[List[str]] = None,
    covered_goal_ids: Optional[List[str]] = None,
    mission_id: str = "",
    advance_policy: str = "checkpoint",
    checkpoint_level: str = "milestone",
) -> Dict[str, Any]:
    now = _now()
    plans = _unique(plan_ids or [])
    tasks = _unique(task_ids or [])
    covered = _unique(covered_goal_ids or [])
    return {
        "id": milestone_id,
        "milestone_id": milestone_id,
        "title": title or milestone_id,
        "title_cache": title or milestone_id,
        "doc_path": f".aiwf/milestones/{milestone_id}.md",
        "doc_hash": "",
        "doc_updated_at": "",
        "status": status,
        "goal_id": goal_id or LEGACY_GOAL_ID,
        "mission_id": mission_id,
        "plan_ids": plans,
        "task_ids": tasks,
        "covered_goal_ids": covered,
        "intent": intent or "",
        "evidence_rollup": {
            "summary": "",
            "closed_plan_count": 0,
            "total_plan_count": len(plans),
            "open_gaps": [],
        },
        "open_gaps": [],
        "stage_synthesis": {
            "status": "open",
            "verdict": "pending",
            "summary": "",
            "coherence_check": "",
            "interface_stability": "",
            "open_gaps": [],
            "residual_risks": [],
            "next_recommendation": "",
        },
        # Stage 4.7.2: structural convergence fields
        "scope_type": None,
        "scope_refs": [],
        "convergence_meaning": None,
        "downstream_dependency": None,
        "stability_claim": None,
        "risk_summary": None,
        "recommended_next_frontier": None,
        "advance_policy": advance_policy,
        "checkpoint_level": checkpoint_level,
        # Milestone integration verification — cross-Goal system integrity
        "integration_test": {
            "status": "not_run",        # not_run | passed | failed
            "commands": [],             # [{command, output_summary, exit_code}]
            "summary": "",
            "failed_integration_points": [],
            "coverage_mode": "",
            "main_path_status": "not_run",
            "source_files": [],
            "accounted_files": [],
            "function_traces": [],
        },
        "verification_task_required": True,
        "verification_task_id": "",
        "architecture_review": {
            "status": "not_run",        # not_run | intact | issues_found
            "interface_integrity": [],  # [{from_goal, to_goal, status: intact|broken}]
            "cross_goal_issues": [],     # [{severity, description, disposition}]
            "notes": "",
            "review_history": [],
        },
        "user_acceptance": {
            "required": advance_policy != "auto",
            "status": "open" if advance_policy != "auto" else "not_required",
            "confirmed_by": "",
            "summary": "",
            "confirmed_at": "",
            "assessment_recorded_at": "",
        },
        "snapshot": {
            "goals": {},                # {goal_id: {status, plan_count, task_count}}
            "deferred": [],             # items carried to next milestone
            "known_risks": [],
            "next_milestone_focus": "",
        },
        "created_at": now,
        "updated_at": now,
    }


def _ensure_user_acceptance(milestone: Dict[str, Any]) -> Dict[str, Any]:
    policy = str(milestone.get("advance_policy") or "checkpoint")
    verdict = str((milestone.get("stage_synthesis", {}) or {}).get("verdict") or "pending")
    required = policy != "auto" or verdict == "PASS_WITH_RISK"
    acceptance = milestone.setdefault("user_acceptance", {})
    acceptance["required"] = required
    acceptance.setdefault("confirmed_by", "")
    acceptance.setdefault("summary", "")
    acceptance.setdefault("confirmed_at", "")
    acceptance.setdefault("assessment_recorded_at", "")
    if not required:
        acceptance["status"] = "not_required"
    else:
        acceptance.setdefault("status", "pending")
        if acceptance.get("status") == "not_required":
            acceptance["status"] = "pending"
    return acceptance


def _invalidate_user_acceptance(milestone: Dict[str, Any]) -> None:
    acceptance = _ensure_user_acceptance(milestone)
    acceptance["status"] = "pending" if acceptance.get("required") else "not_required"
    acceptance["confirmed_by"] = ""
    acceptance["summary"] = ""
    acceptance["confirmed_at"] = ""


def _find_milestone(data: Dict[str, Any], milestone_id: str) -> Optional[Dict[str, Any]]:
    for milestone in data.get("milestones", []) or []:
        if isinstance(milestone, dict) and (
            milestone.get("milestone_id") == milestone_id or milestone.get("id") == milestone_id
        ):
            return milestone
    return None


def load_milestones(base_dir: str) -> Dict[str, Any]:
    path = _milestones_path(base_dir)
    data = _read(path, default_milestones())
    data.setdefault("schema_version", 1)
    data.setdefault("active_milestone_id", None)
    data.setdefault("mission_id", "")
    data.setdefault("milestones", [])
    if not path.exists():
        _write(path, data)
    return data


def save_milestones(base_dir: str, milestones: Dict[str, Any]) -> None:
    milestones.setdefault("schema_version", 1)
    milestones.setdefault("active_milestone_id", None)
    milestones.setdefault("milestones", [])
    _write(_milestones_path(base_dir), milestones)


def list_milestones(base_dir: str) -> List[Dict[str, Any]]:
    return list(load_milestones(base_dir).get("milestones", []) or [])


def get_milestone(base_dir: str, milestone_id: str) -> Dict[str, Any]:
    return _find_milestone(load_milestones(base_dir), milestone_id) or {}


def milestone_exists(base_dir: str, milestone_id: str) -> bool:
    return bool(get_milestone(base_dir, milestone_id))


def upsert_milestone(
    base_dir: str,
    milestone_id: str,
    goal_id: str = "",
    title: str = "",
    status: str = "open",
    intent: str = "",
    plan_ids: Optional[List[str]] = None,
    task_ids: Optional[List[str]] = None,
    covered_goal_ids: Optional[List[str]] = None,
    mission_id: str = "",
    advance_policy: str = "",
    checkpoint_level: str = "",
    # Stage 4.7.2: structural convergence fields
    scope_type: str = "",
    scope_refs: Optional[List[str]] = None,
    convergence_meaning: str = "",
    downstream_dependency: str = "",
    stability_claim: str = "",
    risk_summary: str = "",
    recommended_next_frontier: str = "",
) -> Dict[str, Any]:
    if status and status not in VALID_MILESTONE_STATUSES:
        raise ValueError(f"invalid milestone status: {status}")
    data = load_milestones(base_dir)
    milestone = _find_milestone(data, milestone_id)
    if not milestone:
        milestone = _empty_milestone(
            milestone_id,
            goal_id=goal_id,
            title=title,
            status=status or "open",
            intent=intent,
            plan_ids=plan_ids,
            task_ids=task_ids,
            covered_goal_ids=covered_goal_ids,
            mission_id=mission_id,
            advance_policy=advance_policy or "checkpoint",
            checkpoint_level=checkpoint_level or "milestone",
        )
        data["milestones"].append(milestone)
    else:
        milestone.setdefault("id", milestone_id)
        milestone.setdefault("milestone_id", milestone_id)
        milestone.setdefault("goal_id", LEGACY_GOAL_ID)
        milestone.setdefault("mission_id", "")
        milestone.setdefault("plan_ids", [])
        milestone.setdefault("task_ids", [])
        milestone.setdefault("covered_goal_ids", [])
        milestone.setdefault("open_gaps", [])
        milestone.setdefault("evidence_rollup", {
            "summary": "",
            "closed_plan_count": 0,
            "total_plan_count": 0,
            "open_gaps": [],
        })
        milestone.setdefault("stage_synthesis", _empty_milestone(milestone_id)["stage_synthesis"])
        _ensure_user_acceptance(milestone)
        if goal_id:
            milestone["goal_id"] = goal_id
        if title:
            milestone["title"] = title
        if status:
            milestone["status"] = status
        if intent:
            milestone["intent"] = intent
        if mission_id:
            milestone["mission_id"] = mission_id
            data["mission_id"] = mission_id
        if advance_policy:
            milestone["advance_policy"] = advance_policy
            _invalidate_user_acceptance(milestone)
        if checkpoint_level:
            milestone["checkpoint_level"] = checkpoint_level
        for pid in plan_ids or []:
            if pid not in milestone["plan_ids"]:
                milestone["plan_ids"].append(pid)
        for tid in task_ids or []:
            if tid not in milestone["task_ids"]:
                milestone["task_ids"].append(tid)
        for gid in covered_goal_ids or []:
            if gid not in milestone["covered_goal_ids"]:
                milestone["covered_goal_ids"].append(gid)
        # Stage 4.7.2: set new structural convergence fields
        for fname in ("scope_type", "convergence_meaning", "downstream_dependency",
                       "stability_claim", "risk_summary", "recommended_next_frontier"):
            milestone.setdefault(fname, None)
        milestone.setdefault("scope_refs", [])
        if scope_type:
            milestone["scope_type"] = scope_type
        if scope_refs is not None:
            for sref in scope_refs:
                if sref not in milestone["scope_refs"]:
                    milestone["scope_refs"].append(sref)
        if convergence_meaning:
            milestone["convergence_meaning"] = convergence_meaning
        if downstream_dependency:
            milestone["downstream_dependency"] = downstream_dependency
        if stability_claim:
            milestone["stability_claim"] = stability_claim
        if risk_summary:
            milestone["risk_summary"] = risk_summary
        if recommended_next_frontier:
            milestone["recommended_next_frontier"] = recommended_next_frontier
        milestone["updated_at"] = _now()
    if milestone.get("status") == "open":
        # Only one active milestone at a time — auto-deactivate any previously active
        for m in data.get("milestones", []) or []:
            if m is milestone:
                continue
            if m.get("status") == "open":
                m["status"] = "open"
                m["updated_at"] = _now()
        data["active_milestone_id"] = milestone_id
    elif data.get("active_milestone_id") == milestone_id and milestone.get("status") != "active":
        data["active_milestone_id"] = None
    save_milestones(base_dir, data)
    return {"milestone": milestone, "milestones": data}


def link_milestone_plan(base_dir: str, milestone_id: str, plan_id: str) -> Dict[str, Any]:
    """Link a plan to a milestone."""
    data = load_milestones(base_dir)
    milestone = _find_milestone(data, milestone_id)
    if not milestone:
        return {"linked": False, "reason": f"milestone not found: {milestone_id}"}
    if plan_id not in milestone.setdefault("plan_ids", []):
        milestone["plan_ids"].append(plan_id)
    milestone["updated_at"] = _now()
    save_milestones(base_dir, data)
    return {"linked": True, "milestone_id": milestone_id, "plan_id": plan_id}


def unlink_milestone_plan(base_dir: str, milestone_id: str, plan_id: str) -> Dict[str, Any]:
    """Unlink a plan from a milestone."""
    data = load_milestones(base_dir)
    milestone = _find_milestone(data, milestone_id)
    if not milestone:
        return {"unlinked": False, "reason": f"milestone not found: {milestone_id}"}
    plist = milestone.get("plan_ids", []) or []
    if plan_id in plist:
        plist.remove(plan_id)
    milestone["updated_at"] = _now()
    save_milestones(base_dir, data)
    return {"unlinked": True, "milestone_id": milestone_id, "plan_id": plan_id}


def link_milestone_task(base_dir: str, milestone_id: str, task_id: str) -> Dict[str, Any]:
    """Link a task to a milestone."""
    data = load_milestones(base_dir)
    milestone = _find_milestone(data, milestone_id)
    if not milestone:
        return {"linked": False, "reason": f"milestone not found: {milestone_id}"}
    if task_id not in milestone.setdefault("task_ids", []):
        milestone["task_ids"].append(task_id)
    milestone["updated_at"] = _now()
    save_milestones(base_dir, data)
    return {"linked": True, "milestone_id": milestone_id, "task_id": task_id}


def unlink_milestone_task(base_dir: str, milestone_id: str, task_id: str) -> Dict[str, Any]:
    """Unlink a task from a milestone."""
    data = load_milestones(base_dir)
    milestone = _find_milestone(data, milestone_id)
    if not milestone:
        return {"unlinked": False, "reason": f"milestone not found: {milestone_id}"}
    tlist = milestone.get("task_ids", []) or []
    if task_id in tlist:
        tlist.remove(task_id)
    milestone["updated_at"] = _now()
    save_milestones(base_dir, data)
    return {"unlinked": True, "milestone_id": milestone_id, "task_id": task_id}


def attach_plan_to_milestone(base_dir: str, milestone_id: str, plan_id: str,
                             task_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    data = load_milestones(base_dir)
    milestone = _find_milestone(data, milestone_id)
    if not milestone:
        return {"attached": False, "milestone": None, "reason": f"milestone not found: {milestone_id}"}
    if plan_id not in milestone.setdefault("plan_ids", []):
        milestone["plan_ids"].append(plan_id)
    for tid in task_ids or []:
        if tid not in milestone.setdefault("task_ids", []):
            milestone["task_ids"].append(tid)
    milestone["updated_at"] = _now()
    save_milestones(base_dir, data)
    return {"attached": True, "milestone": milestone}


def reconcile_plan_to_milestone(base_dir: str, plan: Dict[str, Any]) -> Dict[str, Any]:
    milestone_id = str(plan.get("milestone_id") or "")
    plan_id = str(plan.get("plan_id") or plan.get("id") or "")
    if not milestone_id or not plan_id:
        return {"reconciled": False, "reason": "missing milestone_id"}
    data = load_milestones(base_dir)
    milestone = _find_milestone(data, milestone_id)
    if not milestone:
        return {"reconciled": False, "reason": f"milestone not found: {milestone_id}"}
    if plan_id not in milestone.setdefault("plan_ids", []):
        milestone["plan_ids"].append(plan_id)
    for tid in plan.get("task_ids", []) or []:
        if tid not in milestone.setdefault("task_ids", []):
            milestone["task_ids"].append(tid)
    plan_ids = milestone.get("plan_ids", []) or []
    closed = 0
    open_gaps = list(milestone.get("open_gaps", []) or [])
    try:
        from .plan_ops import get_plan
        for pid in plan_ids:
            p = get_plan(base_dir, pid)
            if p.get("status") == "closed":
                closed += 1
            rollup = p.get("evidence_rollup", {}) or {}
            for gap in rollup.get("open_gaps", []) or []:
                if gap not in open_gaps:
                    open_gaps.append(gap)
    except Exception:
        closed = sum(1 for pid in plan_ids if pid == plan_id and plan.get("status") == "closed")
    if plan.get("status") == "closed" and plan_id not in plan_ids:
        closed += 1
    milestone["open_gaps"] = open_gaps
    milestone["evidence_rollup"] = {
        "summary": f"{closed}/{len(plan_ids)} plans complete under this milestone.",
        "closed_plan_count": closed,
        "total_plan_count": len(plan_ids),
        "open_gaps": open_gaps,
    }
    milestone["updated_at"] = _now()
    save_milestones(base_dir, data)
    return {"reconciled": True, "milestone": milestone}


def record_milestone_assessment(
    base_dir: str,
    milestone_id: str,
    verdict: str,
    summary: str,
    evidence_ids: Optional[List[str]] = None,
    coherence_check: str = "",
    open_gaps: Optional[List[str]] = None,
    residual_risks: Optional[List[str]] = None,
    next_recommendation: str = "",
) -> Dict[str, Any]:
    if verdict not in VALID_MILESTONE_VERDICTS - {"pending"}:
        raise ValueError(f"invalid milestone verdict: {verdict}")
    data = load_milestones(base_dir)
    milestone = _find_milestone(data, milestone_id)
    if not milestone:
        return {"recorded": False, "reason": f"milestone not found: {milestone_id}"}
    milestone["stage_synthesis"] = {
        "status": "closed",
        "verdict": verdict,
        "summary": summary,
        "coherence_check": coherence_check,
        "interface_stability": "",
        "open_gaps": _unique(open_gaps or []),
        "residual_risks": _unique(residual_risks or []),
        "next_recommendation": next_recommendation,
        "recorded_at": _now(),
    }
    _invalidate_user_acceptance(milestone)
    milestone["user_acceptance"]["assessment_recorded_at"] = milestone["stage_synthesis"]["recorded_at"]
    milestone["updated_at"] = _now()
    save_milestones(base_dir, data)

    # Auto-fill review record on active verification task
    _auto_fill_verification_task_review(base_dir, milestone_id, verdict, summary)

    return {"recorded": True, "milestone": milestone}


def _get_active_verification_task(base_dir: str, milestone_id: str) -> Optional[Dict[str, Any]]:
    """Return the active task if it's a milestone_verification task for the given milestone."""
    try:
        state_path = Path(base_dir) / ".aiwf" / "state" / "state.json"
        if not state_path.exists():
            return None
        import json
        state = json.loads(state_path.read_text(encoding="utf-8"))
        active_id = state.get("active_task_id", "")
        if not active_id:
            return None
        tasks_path = Path(base_dir) / ".aiwf" / "state" / "tasks.json"
        if not tasks_path.exists():
            return None
        tasks_data = json.loads(tasks_path.read_text(encoding="utf-8"))
        for t in tasks_data.get("tasks", []) or []:
            if not isinstance(t, dict):
                continue
            if t.get("id") == active_id and t.get("kind") == "milestone_verification" and t.get("milestone_id") == milestone_id:
                return t
    except Exception:
        pass
    return None


def _auto_fill_verification_task_testing(base_dir: str, milestone_id: str, status: str, summary: str) -> None:
    """When milestone integration-test runs under an active verification task,
    auto-fill a testing record so the task can close without manual record-testing."""
    task = _get_active_verification_task(base_dir, milestone_id)
    if not task:
        return
    testing_path = Path(base_dir) / ".aiwf" / "records" / "testing.json"
    import json
    existing = {}
    if testing_path.exists():
        try:
            existing = json.loads(testing_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    testing_status = "passed" if status == "passed" else "failed"
    existing["status"] = testing_status
    existing.setdefault("commands", [])
    existing["commands"].append({
        "command": f"milestone integration-test {milestone_id}",
        "output_summary": summary,
    })
    existing["coverage_summary"] = f"milestone integration {status}: {summary}"
    existing["recorded_at"] = _now()
    testing_path.parent.mkdir(parents=True, exist_ok=True)
    testing_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _auto_fill_verification_task_review(base_dir: str, milestone_id: str, verdict: str, summary: str) -> None:
    """When milestone assess runs under an active verification task,
    auto-fill a review record so the task can close without manual record-review."""
    task = _get_active_verification_task(base_dir, milestone_id)
    if not task:
        return
    review_path = Path(base_dir) / ".aiwf" / "records" / "review.json"
    import json
    existing = {}
    if review_path.exists():
        try:
            existing = json.loads(review_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    review_result = "accepted" if verdict in ("PASS", "PASS_WITH_RISK") else "needs_fix"
    existing["result"] = review_result
    existing["summary"] = f"milestone assessment {verdict}: {summary}"
    existing["blockers"] = []
    existing["recorded_at"] = _now()
    review_path.parent.mkdir(parents=True, exist_ok=True)
    review_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def record_milestone_integration(
    base_dir: str,
    milestone_id: str,
    status: str,
    commands: Optional[List[Dict[str, Any]]] = None,
    summary: str = "",
    failed_points: Optional[List[str]] = None,
    coverage_mode: str = "",
    main_path_status: str = "",
    source_files: Optional[List[str]] = None,
    accounted_files: Optional[List[str]] = None,
    function_traces: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Record milestone-level integration test results.

    V1: Default mode is end_to_end_flow — verifies the milestone's main path works.
    function_reverse_trace is only used when Milestone.md explicitly requires it.
    """
    if status not in ("passed", "failed"):
        raise ValueError(f"invalid integration status: {status}")
    valid_modes = {"end_to_end_flow", "function_reverse_trace"}
    if coverage_mode and coverage_mode not in valid_modes:
        raise ValueError(f"invalid integration coverage_mode: {coverage_mode} (valid: {', '.join(sorted(valid_modes))})")
    if main_path_status and main_path_status not in ("passed", "failed", "not_run"):
        raise ValueError(f"invalid main_path_status: {main_path_status}")
    traces = list(function_traces or [])
    valid_trace_statuses = {"entrypoint", "connected", "intentionally_unused", "untraced", "disconnected"}
    for trace in traces:
        trace_status = str(trace.get("status") or "")
        if trace_status not in valid_trace_statuses:
            raise ValueError(f"invalid function trace status: {trace_status}")
        if trace_status == "intentionally_unused" and not str(trace.get("reason") or "").strip():
            raise ValueError("intentionally_unused function trace requires a reason")
    if status == "passed":
        missing = []
        if not coverage_mode:
            missing.append("coverage_mode (end_to_end_flow or function_reverse_trace)")
        if not main_path_status:
            missing.append("main_path_status")
        if missing:
            raise ValueError(
                "passed milestone integration requires coverage_mode and main_path_status: "
                + ", ".join(missing)
            )
        if main_path_status not in ("passed", "not_applicable"):
            missing.append(f"main_path_status={main_path_status} (expected passed or not_applicable)")
            raise ValueError(
                "passed milestone integration requires main_path_status=passed or not_applicable"
            )
        # function_reverse_trace mode: requires full trace inventory
        if coverage_mode == "function_reverse_trace":
            if not source_files:
                raise ValueError(
                    "function_reverse_trace requires --source-file. "
                    "Required by current milestone integration policy."
                )
            if not traces:
                raise ValueError(
                    "function_reverse_trace requires --function-trace. "
                    "Required by current milestone integration policy."
                )
            unresolved = [
                f"{t.get('file')}::{t.get('function')}"
                for t in traces if t.get("status") in ("untraced", "disconnected")
            ]
            if unresolved:
                raise ValueError(
                    "passed milestone integration has unresolved function traces: "
                    + ", ".join(unresolved[:10])
                )
            traced_files = {str(t.get("file") or "") for t in traces}
            covered_files = traced_files | set(accounted_files or [])
            missing_files = [path for path in source_files or [] if path not in covered_files]
            if missing_files:
                raise ValueError(
                    "passed milestone integration has unaccounted source files: "
                    + ", ".join(missing_files[:10])
                )
    data = load_milestones(base_dir)
    milestone = _find_milestone(data, milestone_id)
    if not milestone:
        raise ValueError(f"milestone not found: {milestone_id}")
    it = milestone.setdefault("integration_test", {})
    it["status"] = status
    it["commands"] = list(commands or [])
    it["summary"] = summary
    it["failed_integration_points"] = _unique(failed_points or [])
    it["coverage_mode"] = coverage_mode
    it["main_path_status"] = main_path_status or "not_run"
    it["source_files"] = _unique(source_files or [])
    it["accounted_files"] = _unique(accounted_files or [])
    it["function_traces"] = traces
    it["recorded_at"] = _now()
    _invalidate_user_acceptance(milestone)
    milestone["updated_at"] = _now()
    save_milestones(base_dir, data)

    # Auto-fill testing record on active verification task
    _auto_fill_verification_task_testing(base_dir, milestone_id, status, summary)

    return {"recorded": True, "milestone_id": milestone_id, "integration_test": it}


def record_milestone_arch_review(
    base_dir: str,
    milestone_id: str,
    status: str,
    interface_integrity: Optional[List[Dict[str, Any]]] = None,
    cross_goal_issues: Optional[List[Any]] = None,
    notes: str = "",
    resolution: str = "",
    resolution_evidence_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Record milestone-level architecture review — cross-Goal interface integrity."""
    if status not in ("intact", "issues_found"):
        raise ValueError(f"invalid arch review status: {status}")
    issues = []
    valid_severities = {"critical", "high", "medium", "low"}
    for raw_issue in cross_goal_issues or []:
        issue = dict(raw_issue) if isinstance(raw_issue, dict) else {
            "severity": "high",
            "description": str(raw_issue),
            "disposition": "open",
        }
        issue["severity"] = str(issue.get("severity") or "").lower()
        issue["description"] = str(issue.get("description") or "").strip()
        issue["disposition"] = str(issue.get("disposition") or "open")
        if issue["severity"] not in valid_severities:
            raise ValueError(f"invalid architecture issue severity: {issue['severity']}")
        if not issue["description"]:
            raise ValueError("architecture issue description is required")
        issues.append(issue)
    if status == "intact" and issues:
        raise ValueError("architecture review cannot be intact while issues are recorded")
    if status == "issues_found" and not issues:
        raise ValueError("issues_found architecture review requires at least one issue")
    data = load_milestones(base_dir)
    milestone = _find_milestone(data, milestone_id)
    if not milestone:
        raise ValueError(f"milestone not found: {milestone_id}")
    ar = milestone.setdefault("architecture_review", {})
    previous_status = str(ar.get("status") or "not_run")
    previous_recorded_at = str(ar.get("recorded_at") or "")
    if previous_status == "issues_found" and status == "intact":
        if not resolution.strip():
            raise ValueError(
                "architecture issues require a resolution summary before review can become intact"
            )
        integration_recorded_at = str(
            (milestone.get("integration_test", {}) or {}).get("recorded_at") or ""
        )
        if not integration_recorded_at or integration_recorded_at <= previous_recorded_at:
            raise ValueError(
                "architecture issues require milestone integration to be rerun after the finding"
            )
    history = ar.setdefault("review_history", [])
    if ar.get("status") and ar.get("status") != "not_run":
        history.append({
            "status": ar.get("status"),
            "interface_integrity": list(ar.get("interface_integrity", []) or []),
            "cross_goal_issues": list(ar.get("cross_goal_issues", []) or []),
            "notes": ar.get("notes", ""),
            "recorded_at": ar.get("recorded_at", ""),
        })
    ar["status"] = status
    ar["interface_integrity"] = list(interface_integrity or [])
    ar["cross_goal_issues"] = issues
    ar["notes"] = notes
    ar["resolution"] = resolution.strip()
    ar["resolution_evidence_ids"] = _unique(resolution_evidence_ids or [])
    ar["recorded_at"] = _now()
    _invalidate_user_acceptance(milestone)
    if status == "issues_found":
        milestone["status"] = "open"
        synthesis = milestone.setdefault(
            "stage_synthesis", _empty_milestone(milestone_id)["stage_synthesis"]
        )
        synthesis["status"] = "closed"
        synthesis["verdict"] = "REVISE"
        synthesis["summary"] = "Architecture review found unresolved milestone issues."
        synthesis["open_gaps"] = _unique([
            *list(synthesis.get("open_gaps", []) or []),
            *[issue["description"] for issue in issues],
        ])
        synthesis["recorded_at"] = _now()
    milestone["updated_at"] = _now()
    save_milestones(base_dir, data)
    return {"recorded": True, "milestone_id": milestone_id, "architecture_review": ar}


def check_milestone_activatable(base_dir: str, milestone_id: str) -> List[str]:
    """Return reasons a pending milestone cannot be activated. Empty = ready.

    Activation conditions:
    - Milestone status is 'pending'
    - Every covered_goal has at least one plan
    - Every plan for those goals has at least one task assigned

    Read-only. Used by status prompt to suggest activation.
    """
    data = load_milestones(base_dir)
    milestone = _find_milestone(data, milestone_id)
    if not milestone:
        return [f"milestone not found: {milestone_id}"]

    reasons = []

    if milestone.get("status") != "open":
        reasons.append(f"milestone status is '{milestone.get('status')}', not 'pending'")
        return reasons

    covered_goals = milestone.get("covered_goal_ids", []) or []
    if not covered_goals:
        reasons.append("milestone has no covered_goal_ids")
        return reasons

    try:
        from .plan_ops import load_plans

        plans_data = load_plans(base_dir)
        all_plans = plans_data.get("plans", []) or []

        for gid in covered_goals:
            gid_str = str(gid)
            goal_plans = [
                p for p in all_plans
                if str(p.get("goal_id") or p.get("target_goal_id") or "") == gid_str
            ]
            if not goal_plans:
                reasons.append(f"covered goal '{gid_str}' has no plan")
                continue
            for p in goal_plans:
                task_ids = p.get("task_ids", []) or []
                if not task_ids:
                    pid = p.get("plan_id") or p.get("id") or "?"
                    reasons.append(f"plan '{pid}' (goal '{gid_str}') has no tasks assigned")
    except Exception as e:
        reasons.append(f"activation check failed: {e}")

    return reasons


def check_milestone_technical_readiness(base_dir: str, milestone_id: str) -> List[str]:
    """Return technical blockers preventing milestone acceptance/close.

    Used by status prompt to determine if a milestone is ready for verification,
    and by confirmation/close as the technical gate logic.
    """
    data = load_milestones(base_dir)
    milestone = _find_milestone(data, milestone_id)
    if not milestone:
        return [f"milestone not found: {milestone_id}"]
    synthesis = milestone.get("stage_synthesis", {}) or {}
    blockers = []
    if synthesis.get("status") != "closed":
        blockers.append("milestone stage synthesis required before close")
    if synthesis.get("verdict") not in ("PASS", "PASS_WITH_RISK"):
        blockers.append("milestone verdict must be PASS or PASS_WITH_RISK")
    try:
        from .plan_ops import get_plan

        for plan_id in milestone.get("plan_ids", []) or []:
            plan = get_plan(base_dir, str(plan_id))
            if not plan:
                blockers.append(f"milestone plan missing: {plan_id}")
                continue
            remaining = plan.get("remaining_task_ids", []) or []
            if plan.get("status") != "closed" or remaining:
                blockers.append(
                    f"milestone plan not complete: {plan_id}"
                    + (f" (remaining: {', '.join(remaining[:5])})" if remaining else "")
                )
    except Exception as e:
        blockers.append(f"milestone plan completion check failed: {e}")
    try:
        from ..task_ledger import load_ledger

        tasks = load_ledger(base_dir).get("tasks", []) or []
        task_by_id = {str(t.get("id")): t for t in tasks if isinstance(t, dict) and t.get("id")}
        for task_id in milestone.get("task_ids", []) or []:
            task = task_by_id.get(str(task_id))
            if not task:
                blockers.append(f"milestone task missing: {task_id}")
                continue
            if task.get("status") not in ("closed", "rejected"):
                blockers.append(f"milestone task not terminal: {task_id} status={task.get('status')}")
    except Exception as e:
        blockers.append(f"milestone task completion check failed: {e}")
    # Covered goals: verify they exist (registered in goal tree).
    try:
        from .goal_tree_ops import goal_exists
        for gid in milestone.get("covered_goal_ids", []) or []:
            gid_str = str(gid)
            if not goal_exists(base_dir, gid_str):
                blockers.append(f"milestone covered goal not registered: {gid_str}")
    except Exception as e:
        blockers.append(f"milestone covered goal check failed: {e}")

    # Integration test: must pass before milestone can close.
    it = milestone.get("integration_test", {}) or {}
    if it.get("status") != "passed":
        blockers.append(
            "milestone integration test not passed. "
            "Run cross-Goal integration tests covering all covered_goals' "
            "integration_points, then: aiwf milestone integration-test <ID> --status passed"
        )
    else:
        coverage_mode = it.get("coverage_mode", "")
        if it.get("main_path_status") != "passed":
            blockers.append("milestone main path is not verified as passed")
        # function_reverse_trace: only checked when explicitly used or required by Milestone.md
        if coverage_mode == "function_reverse_trace":
            traces = it.get("function_traces", []) or []
            if not traces:
                blockers.append("milestone integration has no function trace inventory (required for function_reverse_trace mode)")
            unresolved = [
                f"{t.get('file')}::{t.get('function')}"
                for t in traces if t.get("status") in ("untraced", "disconnected")
            ]
            if unresolved:
                blockers.append(
                    "milestone integration has unresolved function traces: "
                    + ", ".join(unresolved[:10])
            )

    # Architecture review: must verify cross-Goal interface integrity.
    ar = milestone.get("architecture_review", {}) or {}
    if ar.get("status") == "issues_found":
        issues = ar.get("cross_goal_issues", []) or []
        labels = [
            f"{str(issue.get('severity') or 'high').upper()}: {issue.get('description', '')}"
            if isinstance(issue, dict) else str(issue)
            for issue in issues
        ]
        blockers.append(
            "milestone architecture review has unresolved issues; fix and rerun review: "
            + "; ".join(labels[:5])
        )
    elif ar.get("status") != "intact":
        blockers.append(
            "milestone architecture review not done. "
            "Verify cross-Goal interface integrity, then: aiwf milestone arch-review <ID> --status intact"
        )
    return blockers


def confirm_milestone_acceptance(
    base_dir: str,
    milestone_id: str,
    confirmed_by: str,
    summary: str,
) -> Dict[str, Any]:
    """Record explicit user acceptance after all technical gates pass."""
    data = load_milestones(base_dir)
    milestone = _find_milestone(data, milestone_id)
    if not milestone:
        return {"confirmed": False, "milestone": None, "blockers": [f"milestone not found: {milestone_id}"]}
    # V1: Documentation requirements come from Milestone.md Documentation Requirements,
    # verified by the milestone verification Task. No global architecture-doc gate.
    blockers = check_milestone_technical_readiness(base_dir, milestone_id)
    if blockers:
        return {"confirmed": False, "milestone": milestone, "blockers": blockers}
    synthesis = milestone.get("stage_synthesis", {}) or {}
    if synthesis.get("verdict") not in ("PASS", "PASS_WITH_RISK"):
        return {
            "confirmed": False,
            "milestone": milestone,
            "blockers": ["only PASS or PASS_WITH_RISK milestones can be accepted"],
        }
    if not str(confirmed_by or "").strip():
        return {"confirmed": False, "milestone": milestone, "blockers": ["confirmed_by is required"]}
    if not str(summary or "").strip():
        return {"confirmed": False, "milestone": milestone, "blockers": ["acceptance summary is required"]}
    acceptance = _ensure_user_acceptance(milestone)
    acceptance["required"] = True
    acceptance["status"] = "confirmed"
    acceptance["confirmed_by"] = str(confirmed_by).strip()
    acceptance["summary"] = str(summary).strip()
    acceptance["confirmed_at"] = _now()
    acceptance["assessment_recorded_at"] = str(synthesis.get("recorded_at") or "")
    milestone["updated_at"] = _now()
    save_milestones(base_dir, data)
    return {"confirmed": True, "milestone": milestone, "blockers": []}


def check_milestone_readiness(base_dir: str, milestone_id: str) -> List[str]:
    """Return all blockers preventing final milestone close."""
    # V1: Doc requirements come from Milestone.md, verified by verification Task.
    # No global architecture-doc gate on milestone close.
    blockers = check_milestone_technical_readiness(base_dir, milestone_id)
    if blockers:
        return blockers
    milestone = get_milestone(base_dir, milestone_id)
    acceptance = _ensure_user_acceptance(milestone)
    if acceptance.get("required") and acceptance.get("status") != "confirmed":
        blockers.append(
            "milestone is technically ready but user acceptance is required. "
            f"Present the stage summary and run: aiwf milestone confirm {milestone_id} "
            "--summary '<user acceptance>'"
        )
    return blockers


def _find_verification_task(base_dir: str, milestone_id: str) -> Optional[Dict[str, Any]]:
    """Find the milestone verification task, if one exists."""
    try:
        from ..task_ledger import load_ledger
        ledger = load_ledger(base_dir)
        for task in ledger.get("tasks", []) or []:
            if not isinstance(task, dict):
                continue
            if task.get("kind") == "milestone_verification" and task.get("milestone_id") == milestone_id:
                return task
    except Exception:
        pass
    return None


def close_milestone(base_dir: str, milestone_id: str) -> Dict[str, Any]:
    data = load_milestones(base_dir)
    milestone = _find_milestone(data, milestone_id)

    # V1: Milestone close requires a dedicated verification Task
    verify_task = _find_verification_task(base_dir, milestone_id)
    if not verify_task:
        return {
            "closed": False,
            "milestone": milestone,
            "blockers": [
                f"milestone verification Task required before closing {milestone_id}. "
                "Planner must create a Task with kind=milestone_verification and "
                f"milestone_id={milestone_id}, then close it after verification."
            ],
        }
    if verify_task.get("status") != "closed":
        return {
            "closed": False,
            "milestone": milestone,
            "blockers": [
                f"milestone verification Task {verify_task.get('id')} must be closed "
                f"before closing {milestone_id}. Current status: {verify_task.get('status')}."
            ],
        }
    milestone["verification_task_id"] = verify_task.get("id")

    blockers = check_milestone_readiness(base_dir, milestone_id)

    if blockers:
        return {"closed": False, "milestone": milestone, "blockers": blockers}

    # ── Auto-generate snapshot ──
    snapshot = milestone.setdefault("snapshot", {})
    try:
        from .goal_tree_ops import get_goal
        goals_snap = {}
        for gid in milestone.get("covered_goal_ids", []) or []:
            gid_str = str(gid)
            goal = get_goal(base_dir, gid_str) if goal_exists(base_dir, gid_str) else {}
            goals_snap[gid_str] = {
                "status": goal.get("status", "unknown") if goal else "unknown",
                "title": goal.get("title", "") if goal else "",
            }
        snapshot["goals"] = goals_snap
    except Exception:
        pass
    snapshot.setdefault("deferred", [])
    snapshot.setdefault("known_risks", [])
    snapshot.setdefault("next_milestone_focus", "")

    # ── Auto git tag ──
    tag_name = ""
    try:
        import subprocess
        tag_name = milestone_id.lower().replace(" ", "-") + "-" + _now()[:10]
        subprocess.run(
            ["git", "tag", tag_name, "-m", f"Milestone {milestone_id} snapshot"],
            capture_output=True, cwd=str(Path(base_dir)), timeout=10,
        )
    except Exception:
        pass

    milestone["status"] = "closed"
    milestone["closed_at"] = _now()
    milestone["updated_at"] = _now()
    milestone["git_tag"] = tag_name
    if data.get("active_milestone_id") == milestone_id:
        data["active_milestone_id"] = None
    save_milestones(base_dir, data)
    return {"closed": True, "milestone": milestone, "blockers": []}
