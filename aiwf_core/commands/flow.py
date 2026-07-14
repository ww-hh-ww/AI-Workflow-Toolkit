"""Concise human and model status for the embedded workflow."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from ..constants import VERSION
from ..core.state.goal_ops import get_active_goal
from ..core.state.plan_ops import load_plans
from ..core.task_ledger import load_ledger, task_for_worktree
from ..core.task_records import load_task_record
from ..core.worktree_context import resolve_control_root, resolve_worktree_root


def _read_json(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else default
    except Exception:
        return default


def _task_next(task: Dict[str, Any], record: Dict[str, Any]) -> Tuple[str, str]:
    task_id = str(task.get("id") or "")
    fix_loop = record.get("fix_loop", {}) or {}
    if fix_loop.get("status") == "open":
        route = str(fix_loop.get("route") or "planner")
        if route == "executor":
            return "Executor fix", f"load /aiwf-implement and dispatch aiwf-executor for {task_id}"
        if route == "tester":
            return "Tester follow-up", f"load /aiwf-test and dispatch aiwf-tester for {task_id}"
        return "Planner decision", f"load /aiwf-planner and disposition the fix-loop for {task_id}"

    requirements = task.get("requirements", {}) or {}
    implementation = record.get("implementation", {}) or {}
    testing = record.get("testing", {}) or {}
    review = record.get("review", {}) or {}
    if not implementation.get("implementation_ref"):
        if requirements.get("executor_required", True):
            return "Executor", f"load /aiwf-implement and dispatch aiwf-executor for {task_id}"
        return "Inline implementation", f"load /aiwf-implement, implement {task_id} inline, and record it"
    if testing.get("status") not in ("adequate", "passed") or not testing.get("tested_ref"):
        if requirements.get("tester_required", True):
            return "Tester", f"load /aiwf-test and dispatch aiwf-tester for {task_id}"
        return "Inline testing", f"load /aiwf-test, test {task_id} inline, and record it"
    pending = [
        item for item in review.get("adversarial_observations", []) or []
        if isinstance(item, dict) and item.get("disposition") == "pending"
    ]
    if review.get("result") == "accepted" and pending:
        return (
            "Planner decision",
            f"load /aiwf-planner and disposition {len(pending)} Reviewer observation(s) for {task_id}",
        )
    if review.get("result") != "accepted" or not review.get("closure_allowed", False):
        if requirements.get("reviewer_required", True):
            return "Reviewer", f"load /aiwf-review and dispatch aiwf-reviewer for {task_id}"
        return "Inline review", f"load /aiwf-review, review {task_id} inline, and record it"
    return "Close", f"load /aiwf-close, calibrate Task.md if needed, then close {task_id}"


def _skill_for(next_role: str) -> str:
    return {
        "Executor": "/aiwf-implement",
        "Executor fix": "/aiwf-implement",
        "Inline implementation": "/aiwf-implement",
        "Tester": "/aiwf-test",
        "Tester follow-up": "/aiwf-test",
        "Inline testing": "/aiwf-test",
        "Reviewer": "/aiwf-review",
        "Inline review": "/aiwf-review",
        "Close": "/aiwf-close",
        "Planner calibration": "/aiwf-planner",
        "Planner decision": "/aiwf-planner",
    }.get(next_role, "/aiwf-planner")


def _active_rows(control: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for task in load_ledger(str(control)).get("tasks", []) or []:
        if not isinstance(task, dict) or task.get("status") != "active":
            continue
        record = load_task_record(control, str(task.get("id") or ""))
        next_role, action = _task_next(task, record)
        task_id = str(task.get("id") or "")
        calibration_missing = False
        if next_role == "Close":
            task_doc = control / ".aiwf/tasks" / f"{task_id}.md"
            if task_doc.exists():
                calibration_missing = "## Closure Calibration" not in task_doc.read_text(
                    encoding="utf-8", errors="ignore",
                )
            if calibration_missing:
                next_role = "Planner calibration"
                action = (
                    f"load /aiwf-planner and run aiwf task calibrate {task_id} with the actual result"
                )
        rows.append({
            "id": task_id,
            "plan_id": task.get("plan_id") or task.get("parent_plan") or "",
            "phase": task.get("phase", ""),
            "worktree_path": task.get("worktree_path", ""),
            "next_role": next_role,
            "action": action,
            "implementation_ref": (record.get("implementation", {}) or {}).get("implementation_ref", ""),
            "testing_status": (record.get("testing", {}) or {}).get("status", "missing"),
            "review_result": (record.get("review", {}) or {}).get("result", "unknown"),
            "fix_loop": (record.get("fix_loop", {}) or {}).get("status", "none"),
            "calibration_missing": calibration_missing,
        })
    return rows


def _plans_ready_to_integrate(control: Path) -> List[Dict[str, Any]]:
    ready = []
    for plan in load_plans(str(control), migrate=False).get("plans", []) or []:
        if not isinstance(plan, dict) or plan.get("status") != "open":
            continue
        statuses = plan.get("task_status", {}) or {}
        if statuses and all(value in ("closed", "cancelled") for value in statuses.values()):
            ready.append(plan)
    return ready


def _plans_between_tasks(control: Path) -> List[Dict[str, Any]]:
    plans = []
    for plan in load_plans(str(control), migrate=False).get("plans", []) or []:
        if not isinstance(plan, dict) or plan.get("status") != "open":
            continue
        statuses = plan.get("task_status", {}) or {}
        has_closed = any(value == "closed" for value in statuses.values())
        has_remaining = any(value not in ("closed", "cancelled") for value in statuses.values())
        if has_closed and has_remaining:
            plans.append(plan)
    return plans


def _installed(control: Path) -> bool:
    return (
        (control / ".aiwf/state/state.json").exists()
        and (
            (control / ".claude/settings.json").exists()
            or (control / ".reasonix/settings.json").exists()
        )
    )


def cmd_status(args) -> None:
    worktree = resolve_worktree_root(Path.cwd())
    control = resolve_control_root(worktree)
    if not _installed(control):
        print(f"AIWF V{VERSION}")
        print("No embedded AIWF installation found in this project.")
        print("Install with: aiwf install claude")
        return

    rows = _active_rows(control)
    current = task_for_worktree(str(worktree))
    plans_ready = _plans_ready_to_integrate(control)
    plans_between = _plans_between_tasks(control)
    if getattr(args, "debug", False):
        _print_debug(control, worktree, rows, current, plans_ready, plans_between)
    elif getattr(args, "prompt", False):
        _print_prompt(control, worktree, rows, current, plans_ready, plans_between)
    else:
        _print_human(control, worktree, rows, current, plans_ready, plans_between)


def _print_human(
    control: Path,
    worktree: Path,
    rows: List[Dict[str, Any]],
    current: Dict[str, Any] | None,
    plans_ready: List[Dict[str, Any]],
    plans_between: List[Dict[str, Any]],
) -> None:
    product = "Reasonix" if (control / ".reasonix/settings.json").exists() else "Claude Code"
    print(f"AIWF V{VERSION} - {product}")
    print(f"Control root: {control}")
    print(f"Current worktree: {worktree}")
    print(f"Active Tasks: {len(rows)}")
    for row in rows:
        marker = "*" if current and current.get("id") == row["id"] else " "
        print(
            f"{marker} {row['id']}  plan={row['plan_id'] or '-'}  phase={row['phase'] or '-'}  "
            f"next={row['next_role']}"
        )
        print(f"    worktree={row['worktree_path']}")
    for plan in plans_ready:
        print(f"Plan ready to integrate: {plan.get('plan_id') or plan.get('id')}")
    for plan in plans_between:
        print(f"Plan ready for next Task review: {plan.get('plan_id') or plan.get('id')}")
    if not rows and not plans_ready and not plans_between:
        goal = get_active_goal(str(control))
        print(f"Planning: {goal.get('current_goal') or goal.get('active_goal') or 'no active Goal'}")


def _print_prompt(
    control: Path,
    worktree: Path,
    rows: List[Dict[str, Any]],
    current: Dict[str, Any] | None,
    plans_ready: List[Dict[str, Any]],
    plans_between: List[Dict[str, Any]],
) -> None:
    memory_root = control / ".aiwf" / "memory"
    if current and len(rows) == 1 and not plans_ready:
        row = next(item for item in rows if item["id"] == current.get("id"))
        print(f"Do now: {row['action']}.")
        print(f"Required skills: {_skill_for(row['next_role'])}")
        print(f"Task: {row['id']}")
        print(f"Plan: {row['plan_id'] or '(none)'}")
        print(f"Worktree: {row['worktree_path']}")
        print("Dispatch: run the Agent in this worktree; the Agent must not call EnterWorktree.")
        print(f"Next role: {row['next_role']}")
        print(
            f"State: phase={row['phase'] or '-'}, testing={row['testing_status']}, "
            f"review={row['review_result']}, fix-loop={row['fix_loop']}"
        )
        if _skill_for(row["next_role"]) == "/aiwf-planner":
            print(f"Planner memory root: {memory_root}")
        return

    if plans_ready:
        plan_ids = ", ".join(str(plan.get("plan_id") or plan.get("id")) for plan in plans_ready)
        print(
            f"Do now: inspect the cumulative diff and integration behavior for {plan_ids}; "
            "merge in the planned order, verify the combined result, then close each Plan."
        )
        if rows:
            print("Other active Tasks:")
    elif rows:
        print(
            "Do now: manage the active Plan worktrees below. Dispatch each Task's next role with "
            "its Task ID and Agent cwd set to its worktree path."
        )
    elif plans_between:
        plan_ids = ", ".join(
            str(plan.get("plan_id") or plan.get("id")) for plan in plans_between
        )
        print(
            f"Do now: load /aiwf-planner. Before the next Task in {plan_ids}, compare the "
            "completed Task Calibration and proof with the Plan, correct changed assumptions, "
            "and maintain memory."
        )
        print("Required skills: /aiwf-planner")
        print(f"Planner memory root: {memory_root}")
        return
    else:
        print(
            "Do now: load /aiwf-planner. Discuss and investigate before creating or changing "
            "Mission, Goal, Plan, or Task documents."
        )
        print("Required skills: /aiwf-planner")
        print(f"Planner memory root: {memory_root}")
        return

    required = sorted({_skill_for(row["next_role"]) for row in rows})
    if plans_ready:
        required = sorted(set(required) | {"/aiwf-planner"})
    print("Required skills: " + ", ".join(required))

    current_id = str((current or {}).get("id") or "")
    display_rows = sorted(rows, key=lambda row: (row["id"] != current_id, row["id"]))
    for row in display_rows:
        marker = " [current]" if row["id"] == current_id else ""
        print(
            f"- {row['id']}{marker} | plan={row['plan_id'] or '-'} | "
            f"do={row['action']} | next={row['next_role']} | "
            f"skill={_skill_for(row['next_role'])} | worktree={row['worktree_path']}"
        )
    print(
        "Before starting another Plan in parallel, load /aiwf-planner and inspect the relevant "
        "code. Do not overlap the same file, responsibility, or shared mechanism. Check "
        "interfaces, state, runtime paths, dependencies, merge order, and combined proof."
    )
    if "/aiwf-planner" in required:
        print(f"Planner memory root: {memory_root}")


def _print_debug(
    control: Path,
    worktree: Path,
    rows: List[Dict[str, Any]],
    current: Dict[str, Any] | None,
    plans_ready: List[Dict[str, Any]],
    plans_between: List[Dict[str, Any]],
) -> None:
    state = _read_json(control / ".aiwf/state/state.json", {})
    plans = load_plans(str(control), migrate=False)
    ledger = load_ledger(str(control))
    records = {
        str(task.get("id")): load_task_record(control, str(task.get("id")))
        for task in ledger.get("tasks", []) or []
        if isinstance(task, dict) and task.get("id")
    }
    print(json.dumps({
        "version": VERSION,
        "control_root": str(control),
        "current_worktree": str(worktree),
        "current_task_id": (current or {}).get("id", ""),
        "active_tasks": rows,
        "plans_ready_to_integrate": [
            plan.get("plan_id") or plan.get("id") for plan in plans_ready
        ],
        "plans_between_tasks": [
            plan.get("plan_id") or plan.get("id") for plan in plans_between
        ],
        "state": state,
        "plans": plans,
        "tasks": ledger,
        "task_records": records,
    }, ensure_ascii=False, indent=2))
