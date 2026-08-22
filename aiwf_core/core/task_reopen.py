"""Safely invalidate an unconsumed closed Task without rewriting history."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

from .index_ops import (
    parse_md,
    remove_narrative_section,
    replace_markdown_section,
    write_narrative_doc,
)
from .state._common import _governance_locked
from .state.plan_ops import load_plans, save_plans
from .task_reopen_checks import reopen_blockers
from .task_ledger import (
    _mark_task_doc_contract_status,
    load_ledger,
    save_ledger,
)
from .task_records import default_task_record, load_task_record, save_task_record
from .worktree_context import resolve_control_root


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _find(items: List[Dict[str, Any]], item_id: str) -> Optional[Dict[str, Any]]:
    return next((item for item in items if item.get("id") == item_id), None)


def _mark_task_doc_reopened(base_dir: str, task: Dict[str, Any]) -> Optional[str]:
    warning = _mark_task_doc_contract_status(base_dir, task, "ready")
    doc_path = str(task.get("doc_path") or f".aiwf/tasks/{task.get('id', '')}.md")
    doc = resolve_control_root(base_dir) / doc_path
    if not doc.exists():
        return warning
    try:
        remove_narrative_section(doc, "Closure Calibration")
        frontmatter, body = parse_md(doc)
        if frontmatter is None:
            return f"Task.md frontmatter missing or invalid after reopen: {doc_path}"
        body = re.sub(r"^> \*\*CLOSED\*\*[^\n]*\n?", "", body, flags=re.MULTILINE)
        entries = []
        for item in task.get("reopen_history", []) or []:
            closure = item.get("previous_closure", {}) or {}
            commit = str(closure.get("git_commit") or "")[:12] or "no-commit"
            reason = " ".join(str(item.get("reason") or "").split())
            entries.append(
                f"- {item.get('reopened_at')}: invalidated close `{commit}` - {reason}"
            )
        body = replace_markdown_section(body, "Reopen History", "\n".join(entries))
        write_narrative_doc(doc, frontmatter, body)
    except Exception as exc:
        return f"Task.md reopen update failed for {doc_path}: {exc}"
    return warning


def _reopen_parent_plan(base_dir: str, task: Dict[str, Any]) -> Optional[str]:
    plan_id = str(task.get("plan_id") or task.get("parent_plan") or "")
    if not plan_id:
        return None
    try:
        plans = load_plans(base_dir)
        plan = next(
            (
                item for item in plans.get("plans", []) or []
                if isinstance(item, dict)
                and str(item.get("plan_id") or item.get("id") or "") == plan_id
            ),
            None,
        )
        if not plan:
            return f"parent Plan not found while reopening Task: {plan_id}"

        invalidated = {}
        if plan.get("integration"):
            invalidated["integration"] = deepcopy(plan["integration"])
        if plan.get("integration_hold_ref"):
            invalidated["integration_hold_ref"] = plan["integration_hold_ref"]
        if invalidated:
            plan.setdefault("integration_history", []).append({
                "status": "invalidated_by_task_reopen",
                "task_id": task.get("id"),
                "invalidated_at": _now(),
                **invalidated,
            })
        plan.pop("integration", None)
        plan.pop("integration_hold_ref", None)

        task_ids = plan.setdefault("task_ids", [])
        if task.get("id") not in task_ids:
            task_ids.append(task.get("id"))
        task_status = plan.setdefault("task_status", {})
        task_status[task["id"]] = "ready"
        closed = [tid for tid in task_ids if task_status.get(tid) == "closed"]
        remaining = [tid for tid in task_ids if task_status.get(tid) not in ("closed", "cancelled")]
        task_by_id = {
            str(item.get("id") or ""): item
            for item in load_ledger(base_dir).get("tasks", []) or []
            if isinstance(item, dict)
        }
        commits = [
            str(((task_by_id.get(tid, {}).get("closure") or {}).get("git_commit")) or "")
            for tid in closed
        ]
        plan["closed_task_ids"] = closed
        plan["remaining_task_ids"] = remaining
        plan["task_rollup"] = {
            "summary": f"{len(closed)}/{len(task_ids)} plan tasks closed",
            "closed_count": len(closed),
            "total_count": len(task_ids),
            "remaining_task_ids": remaining,
            "git_commits": [commit for commit in commits if commit],
        }
        plan["updated_at"] = _now()
        save_plans(base_dir, plans)

        doc_path = str(plan.get("doc_path") or f".aiwf/plans/{plan_id}.md")
        remove_narrative_section(resolve_control_root(base_dir) / doc_path, "Closure Calibration")
    except Exception as exc:
        return f"parent Plan reopen update failed: {exc}"
    return None


@_governance_locked
def reopen_closed_task(base_dir: str, task_id: str, reason: str = "") -> Dict[str, Any]:
    reason = " ".join(str(reason or "").split())
    ledger = load_ledger(base_dir)
    task = _find(ledger.get("tasks", []), task_id)
    if not reason:
        return {"reopened": False, "task": task, "ledger": ledger,
                "blockers": ["reopen reason is required"]}
    if not task:
        return {"reopened": False, "task": None, "ledger": ledger,
                "blockers": [f"task not found: {task_id}"]}
    if task.get("status") != "closed":
        return {"reopened": False, "task": task, "ledger": ledger,
                "blockers": [f"task status is '{task.get('status')}', not closed"]}

    blockers = reopen_blockers(base_dir, task, ledger)
    if blockers:
        return {"reopened": False, "task": task, "ledger": ledger, "blockers": blockers}

    now = _now()
    previous_closure = deepcopy(task.get("closure", {}) or {})
    record = load_task_record(base_dir, task_id)
    attempt_history = deepcopy(record.get("attempt_history", []) or [])
    attempt_history.append({
        "attempt": len(attempt_history) + 1,
        "status": "closed_invalidated",
        "closed_at": task.get("closed_at") or "",
        "closure": previous_closure,
        "proof": {
            key: deepcopy(record.get(key))
            for key in ("implementation", "testing", "review", "fix_loop", "role_agents")
        },
        "reopened_at": now,
        "reopen_reason": reason,
    })
    fresh_record = default_task_record(task_id)
    fresh_record["attempt_history"] = attempt_history
    fresh_record["reopen_context"] = {
        "reopened_at": now, "reason": reason, "previous_closure": previous_closure,
    }
    save_task_record(base_dir, fresh_record)

    task.setdefault("reopen_history", []).append({
        "reopened_at": now,
        "reason": reason,
        "previous_closed_at": task.get("closed_at") or "",
        "previous_closure": previous_closure,
    })
    task.update({
        "status": "ready",
        "phase": "planning",
        "activation_critique_count": 0,
        "updated_at": now,
        "last_reopen": {"reopened_at": now, "reason": reason},
    })
    for key in (
        "closed_at", "closure", "activated_at", "git_origin_ref", "interruption",
        "suspended_phase", "close_warnings",
    ):
        task.pop(key, None)
    task.setdefault("notes", []).append(f"REOPENED by human: {reason}")
    save_ledger(base_dir, ledger)

    warnings = [
        warning for warning in (
            _mark_task_doc_reopened(base_dir, task),
            _reopen_parent_plan(base_dir, task),
        ) if warning
    ]
    if warnings:
        task.setdefault("close_warnings", []).extend(warnings)
        save_ledger(base_dir, ledger)
    return {
        "reopened": True,
        "task": task,
        "ledger": ledger,
        "blockers": [],
        "warnings": warnings,
        "archived_attempt": attempt_history[-1],
    }
