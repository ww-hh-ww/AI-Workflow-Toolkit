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
    status: str = "pending",
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
            "status": "pending",
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
        },
        "architecture_review": {
            "status": "not_run",        # not_run | intact | issues_found
            "interface_integrity": [],  # [{from_goal, to_goal, status: intact|broken}]
            "cross_goal_issues": [],
            "notes": "",
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
    status: str = "pending",
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
            status=status or "pending",
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
    if milestone.get("status") == "active":
        # Only one active milestone at a time — auto-deactivate any previously active
        for m in data.get("milestones", []) or []:
            if m is milestone:
                continue
            if m.get("status") == "active":
                m["status"] = "pending"
                m["updated_at"] = _now()
        data["active_milestone_id"] = milestone_id
    elif data.get("active_milestone_id") == milestone_id and milestone.get("status") != "active":
        data["active_milestone_id"] = None
    save_milestones(base_dir, data)
    return {"milestone": milestone, "milestones": data}


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
            if p.get("status") in ("complete", "completed"):
                closed += 1
            rollup = p.get("evidence_rollup", {}) or {}
            for gap in rollup.get("open_gaps", []) or []:
                if gap not in open_gaps:
                    open_gaps.append(gap)
    except Exception:
        closed = sum(1 for pid in plan_ids if pid == plan_id and plan.get("status") in ("complete", "completed"))
    if plan.get("status") in ("complete", "completed") and plan_id not in plan_ids:
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
        "status": "completed",
        "verdict": verdict,
        "summary": summary,
        "coherence_check": coherence_check,
        "interface_stability": "",
        "open_gaps": _unique(open_gaps or []),
        "residual_risks": _unique(residual_risks or []),
        "next_recommendation": next_recommendation,
        "recorded_at": _now(),
    }
    milestone["updated_at"] = _now()
    save_milestones(base_dir, data)
    return {"recorded": True, "milestone": milestone}


def record_milestone_integration(
    base_dir: str,
    milestone_id: str,
    status: str,
    commands: Optional[List[Dict[str, Any]]] = None,
    summary: str = "",
    failed_points: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Record milestone-level integration test results."""
    if status not in ("passed", "failed"):
        raise ValueError(f"invalid integration status: {status}")
    data = load_milestones(base_dir)
    milestone = _find_milestone(data, milestone_id)
    if not milestone:
        raise ValueError(f"milestone not found: {milestone_id}")
    it = milestone.setdefault("integration_test", {})
    it["status"] = status
    if commands:
        it["commands"] = commands
    if summary:
        it["summary"] = summary
    if failed_points:
        it["failed_integration_points"] = failed_points
    milestone["updated_at"] = _now()
    save_milestones(base_dir, data)
    return {"recorded": True, "milestone_id": milestone_id, "integration_test": it}


def record_milestone_arch_review(
    base_dir: str,
    milestone_id: str,
    status: str,
    interface_integrity: Optional[List[Dict[str, Any]]] = None,
    cross_goal_issues: Optional[List[str]] = None,
    notes: str = "",
) -> Dict[str, Any]:
    """Record milestone-level architecture review — cross-Goal interface integrity."""
    if status not in ("intact", "issues_found"):
        raise ValueError(f"invalid arch review status: {status}")
    data = load_milestones(base_dir)
    milestone = _find_milestone(data, milestone_id)
    if not milestone:
        raise ValueError(f"milestone not found: {milestone_id}")
    ar = milestone.setdefault("architecture_review", {})
    ar["status"] = status
    if interface_integrity:
        ar["interface_integrity"] = interface_integrity
    if cross_goal_issues:
        ar["cross_goal_issues"] = cross_goal_issues
    if notes:
        ar["notes"] = notes
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

    if milestone.get("status") != "pending":
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


def check_milestone_readiness(base_dir: str, milestone_id: str) -> List[str]:
    """Return blockers preventing milestone close. Read-only, no side effects.

    Used by status prompt to determine if a milestone is ready for verification,
    and by close_milestone as the gate logic.
    """
    data = load_milestones(base_dir)
    milestone = _find_milestone(data, milestone_id)
    if not milestone:
        return [f"milestone not found: {milestone_id}"]
    synthesis = milestone.get("stage_synthesis", {}) or {}
    blockers = []
    if synthesis.get("status") != "completed":
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
            if plan.get("status") not in ("complete", "completed") or remaining:
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

    # Architecture review: must verify cross-Goal interface integrity.
    ar = milestone.get("architecture_review", {}) or {}
    if ar.get("status") not in ("intact",):
        blockers.append(
            "milestone architecture review not done. "
            "Verify cross-Goal interface integrity, then: aiwf milestone arch-review <ID> --status intact"
        )
    return blockers


def close_milestone(base_dir: str, milestone_id: str) -> Dict[str, Any]:
    data = load_milestones(base_dir)
    milestone = _find_milestone(data, milestone_id)
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

    milestone["status"] = "completed"
    milestone["closed_at"] = _now()
    milestone["updated_at"] = _now()
    milestone["git_tag"] = tag_name
    if data.get("active_milestone_id") == milestone_id:
        data["active_milestone_id"] = None
    save_milestones(base_dir, data)
    return {"closed": True, "milestone": milestone, "blockers": []}
