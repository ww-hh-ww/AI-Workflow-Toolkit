"""Task ledger and per-worktree execution-window checks.

Many Plans may execute at once. Each worktree still owns only one active Task.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .state.goal_ops import get_active_goal
from .state._common import _atomic_write, _exclusive_operation_lock, _read_json
from .task_records import default_task_record, load_task_record, save_task_record
from .worktree_context import resolve_control_root, resolve_worktree_root, same_path

VALID_TASK_STATUSES = {"candidate", "ready", "active", "blocked", "suspended", "closed", "cancelled"}
TERMINAL_TASK_STATUSES = {"closed", "cancelled"}
REQUIRED_ACTIVATION_CRITIQUES = 2

# Task granularity: titles that smell like actions, not deliverables.
# Tasks must be verifiable outcome units, not single-step actions.
_ACTION_SMELL_PREFIXES = [
    "check ", "look at ", "read ", "run ", "view ", "find ", "search ",
    "open ", "test ", "debug ", "investigate ", "try ", "explore ",
]
_ACTION_SMELL_PHRASES = [
    "change one line", "fix typo", "add comment", "update readme",
    "跑一下", "看看", "检查一下", "试一下",
]

def _detect_action_smell(title: str) -> List[str]:
    """Return warnings if a task title looks like an action, not a deliverable.

    A task should describe a verifiable outcome, e.g.:
      "route CLI is reachable from entry point with smoke test"
    Not an action step, e.g.:
      "check pipeline.py"
      "run tests"
      "update README"
    """
    warnings = []
    tl = title.strip().lower()
    for prefix in _ACTION_SMELL_PREFIXES:
        if tl.startswith(prefix):
            warnings.append(
                f"Task title starts with '{prefix.strip()}' — tasks should describe "
                f"verifiable outcomes, not actions. Consider merging into a larger deliverable task."
            )
            break
    for phrase in _ACTION_SMELL_PHRASES:
        if phrase in tl:
            warnings.append(
                f"Task title contains '{phrase}' — this smells like an action step. "
                f"Tasks should be deliverable units with a verifiable outcome."
            )
            break
    return warnings

def _read(path: Path, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return _read_json(path, default)

def _write(path: Path, data: Dict[str, Any]) -> None:
    _atomic_write(path, data)

def ledger_path(base_dir: str) -> Path:
    return resolve_control_root(base_dir) / ".aiwf" / "state" / "tasks.json"

def _migrate_ledger_if_needed(base_dir: str) -> None:
    new_path = ledger_path(base_dir)
    control = resolve_control_root(base_dir)
    old_path = control / ".aiwf" / "runtime" / "history" / "task-ledger.json"
    if old_path.exists() and not new_path.exists():
        new_path.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.move(str(old_path), str(new_path))

def default_ledger() -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "tasks": [],
    }

def load_ledger(base_dir: str) -> Dict[str, Any]:
    _migrate_ledger_if_needed(base_dir)
    ledger = _read(ledger_path(base_dir), default_ledger())
    migrated = False
    if not isinstance(ledger.get("tasks"), list):
        ledger["tasks"] = []
    if "default_max_active" in ledger:
        ledger.pop("default_max_active", None)
        migrated = True
    for task in ledger["tasks"]:
        if isinstance(task, dict) and "parallel_safe" in task:
            task.pop("parallel_safe", None)
            migrated = True
    state = _read(resolve_control_root(base_dir) / ".aiwf" / "state" / "state.json", {})
    legacy_active = str(state.get("active_task_id") or "")
    for task in ledger["tasks"]:
        if not isinstance(task, dict):
            continue
        if task.get("status") == "active" and not task.get("phase"):
            task["phase"] = str(state.get("phase") or "implementing")
            migrated = True
        if task.get("status") == "active" and not task.get("worktree_path"):
            task["worktree_path"] = str(resolve_worktree_root(base_dir))
            migrated = True
        if (
            task.get("id") == legacy_active
            and task.get("status") not in ("active", *TERMINAL_TASK_STATUSES)
        ):
            task["status"] = "active"
            task["phase"] = str(state.get("phase") or "implementing")
            task["worktree_path"] = str(resolve_worktree_root(base_dir))
            migrated = True
    active_by_worktree: Dict[str, List[Dict[str, Any]]] = {}
    for task in ledger["tasks"]:
        if not isinstance(task, dict) or task.get("status") != "active":
            continue
        worktree = str(task.get("worktree_path") or resolve_worktree_root(base_dir))
        task["worktree_path"] = worktree
        key = str(Path(worktree).expanduser().resolve())
        active_by_worktree.setdefault(key, []).append(task)
    for worktree_tasks in active_by_worktree.values():
        if len(worktree_tasks) < 2:
            continue
        keep = next(
            (task for task in worktree_tasks if task.get("id") == legacy_active),
            worktree_tasks[0],
        )
        for task in worktree_tasks:
            if task is keep:
                continue
            task["status"] = "suspended"
            task["suspended_phase"] = task.get("phase") or "implementing"
            task["phase"] = "suspended"
            task["interruption"] = {
                "reason": "recovered conflicting active Tasks in one worktree",
                "unsatisfied_checks": [],
            }
            migrated = True
    ledger.setdefault("schema_version", 1)
    legacy_state_changed = any(
        key in state for key in ("active_task_id", "active_plan_id", "phase", "git_origin_ref")
    )
    for key in ("active_task_id", "active_plan_id", "phase", "git_origin_ref"):
        state.pop(key, None)
    if migrated:
        save_ledger(base_dir, ledger)
    if legacy_state_changed:
        _write(resolve_control_root(base_dir) / ".aiwf" / "state" / "state.json", state)
    return ledger

def save_ledger(base_dir: str, ledger: Dict[str, Any]) -> None:
    _write(ledger_path(base_dir), ledger)

def _mark_task_doc_contract_status(
    base_dir: str,
    task: Dict[str, Any],
    status: str,
) -> Optional[str]:
    """Keep Task.md frontmatter aligned with the machine task status."""
    doc_path = str(task.get("doc_path") or "").strip()
    task_id = str(task.get("id") or task.get("task_id") or "").strip()
    if not doc_path and task_id:
        doc_path = f".aiwf/tasks/{task_id}.md"
    if not doc_path:
        return None
    doc = resolve_control_root(base_dir) / doc_path
    if not doc.exists():
        return None
    try:
        from .index_ops import parse_md, write_narrative_doc

        fm, body = parse_md(doc)
        if fm is None:
            return f"Task.md frontmatter missing or invalid; sync may not see closed status: {doc_path}"
        if fm.get("contract_status") != status:
            fm["contract_status"] = status
            write_narrative_doc(doc, fm, body)
    except Exception as e:
        return f"Task.md frontmatter status update failed for {doc_path}: {e}"
    return None

def _mark_task_doc_closed(base_dir: str, task: Dict[str, Any]) -> Optional[str]:
    return _mark_task_doc_contract_status(base_dir, task, "closed")

def _task_unsatisfied_checks(base_dir: str, task: Dict[str, Any]) -> List[str]:
    """Collect gate failures for human override/interruption records."""
    unsatisfied: List[str] = []
    record = load_task_record(base_dir, str(task.get("id") or ""))
    if (record.get("fix_loop", {}) or {}).get("status") == "open":
        unsatisfied.append("fix-loop is open")
    reqs = task.get("requirements", {})
    if reqs.get("executor_required"):
        implementation = record.get("implementation", {}) or {}
        if implementation.get("task_id") != task.get("id") or not implementation.get("implementation_ref"):
            unsatisfied.append("executor_required but no implementation recorded")
    if reqs.get("tester_required"):
        testing = record.get("testing", {}) or {"status": "missing"}
        if testing.get("status") not in ("adequate", "passed"):
            unsatisfied.append(f"tester_required but testing status={testing.get('status', 'missing')}")
    if reqs.get("reviewer_required"):
        review = record.get("review", {}) or {"result": "unknown"}
        if review.get("result") != "accepted":
            unsatisfied.append(f"reviewer_required but review result={review.get('result', 'unknown')}")
        if review.get("blockers"):
            unsatisfied.append(f"review blockers: {review['blockers']}")
    return unsatisfied

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _find(tasks: List[Dict[str, Any]], task_id: str) -> Optional[Dict[str, Any]]:
    for task in tasks:
        if task.get("id") == task_id:
            return task
    return None


def active_tasks(base_dir: str) -> List[Dict[str, Any]]:
    return [
        task for task in load_ledger(base_dir).get("tasks", [])
        if isinstance(task, dict) and task.get("status") == "active"
    ]


def task_for_worktree(base_dir: str, task_id: str = "") -> Optional[Dict[str, Any]]:
    """Resolve one active Task from an explicit ID or the current worktree."""
    tasks = load_ledger(base_dir).get("tasks", [])
    if task_id:
        task = _find(tasks, task_id)
        return task if task and task.get("status") == "active" else None
    current = resolve_worktree_root(base_dir)
    matches = [
        task for task in tasks
        if task.get("status") == "active"
        and task.get("worktree_path")
        and same_path(task["worktree_path"], current)
    ]
    return matches[0] if len(matches) == 1 else None


def resolve_active_task_id(base_dir: str, task_id: str = "") -> str:
    task = task_for_worktree(base_dir, task_id)
    return str((task or {}).get("id") or "")


def update_task_runtime(base_dir: str, task_id: str, **changes: Any) -> Dict[str, Any]:
    """Atomically update runtime fields for one Task."""
    control = resolve_control_root(base_dir)
    with _exclusive_operation_lock(str(control), "task-ledger"):
        ledger = load_ledger(base_dir)
        task = _find(ledger.get("tasks", []), task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")
        for key, value in changes.items():
            if value is None:
                task.pop(key, None)
            else:
                task[key] = value
        task["updated_at"] = _now()
        save_ledger(base_dir, ledger)
        return task

def upsert_task(
    base_dir: str,
    task_id: str,
    title: str = "",
    status: str = "candidate",
    dependencies: Optional[List[str]] = None,
    allowed_write: Optional[List[str]] = None,   # DEPRECATED: ignored; scope lives on Plan
    notes: Optional[List[str]] = None,
    parent_goal: str = "",
    parent_plan: str = "",
    goal_id: str = "",
    plan_id: str = "",
    milestone: str = "",
    milestone_id: str = "",
    kind: str = "",
) -> Dict[str, Any]:
    """Create/update a task without activating execution.

    parent_goal/goal_id: the GOAL-ID this task serves (task is execution unit, not goal unit).
    parent_plan/plan_id: the PLAN-ID this task belongs to.
    milestone: the milestone this task advances.
    """
    if status not in VALID_TASK_STATUSES:
        raise ValueError(f"invalid task status: {status}")
    effective_goal = goal_id or parent_goal
    effective_plan = plan_id or parent_plan
    if effective_plan:
        from .state.plan_ops import get_plan

        linked_plan = get_plan(base_dir, effective_plan, migrate=False)
        if linked_plan and str(linked_plan.get("status") or "open") == "closed":
            raise ValueError(
                f"plan {effective_plan} is closed; cannot link a Task. "
                "Create a new Plan for new work."
            )
    ledger = load_ledger(base_dir)
    tasks = ledger["tasks"]
    task = _find(tasks, task_id)
    if task and task.get("status") == "active":
        contract_changes = []
        if status != "active": contract_changes.append("status")
        if dependencies is not None and dependencies != (task.get("dependencies", []) or []):
            contract_changes.append("dependencies")
        if contract_changes:
            raise ValueError(
                "active task contract is frozen; cannot change " + ", ".join(contract_changes)
                + "; this prevents retrospective scope/status changes. "
                "Allowed now: add notes and complete the current contract. "
                "To stop this execution window, the human can run aiwf task interrupt; "
                "then Planner can revise, cancel, or activate follow-up work."
            )
    if not task:
        task = {
            "id": task_id,
            "type": "task",
            "title": title or task_id,
            "status": status,
            "title_cache": title or task_id,
            "summary_cache": "",
            "doc_path": "",
            "requirements": {
                "executor_required": False if kind == "milestone_verification" else True,
                "tester_required": True,
                "reviewer_required": True,
            },
            "report_policy": "ask",
            "dependencies": [],
            "notes": [],
            "created_at": _now(),
            "updated_at": _now(),
            "parent_goal": "",
            "parent_plan": "",
            "goal_id": "",
            "plan_id": "",
            "milestone": "",
            "milestone_id": "",
            "kind": "",
        }
        tasks.append(task)
    if title:
        task["title"] = title
    task["status"] = status
    if dependencies is not None:
        task["dependencies"] = dependencies
    if notes:
        task.setdefault("notes", []).extend(notes)
    if effective_goal:
        task["goal_id"] = effective_goal
    if effective_plan:
        task["plan_id"] = effective_plan
    if milestone:
        task["milestone"] = milestone
    if milestone_id:
        task["milestone_id"] = milestone_id
    if kind:
        task["kind"] = kind
    task["updated_at"] = _now()
    save_ledger(base_dir, ledger)
    if effective_plan:
        try:
            from .state.plan_ops import attach_task_to_plan, plan_exists
            if plan_exists(base_dir, effective_plan):
                attach_task_to_plan(base_dir, effective_plan, task_id)
        except Exception:
            pass
    granularity = _detect_action_smell(task.get("title", ""))
    return {"task": task, "ledger": ledger, "granularity_warnings": granularity}

def task_activation_critique_count(task: Dict[str, Any]) -> int:
    try:
        return int(task.get("activation_critique_count") or 0)
    except Exception:
        return 0

def task_activation_critique_blockers(base_dir: str, task_id: str) -> List[str]:
    task = _find(load_ledger(base_dir).get("tasks", []), task_id)
    if not task:
        return [f"task not found: {task_id}"]
    count = task_activation_critique_count(task)
    if count >= REQUIRED_ACTIVATION_CRITIQUES:
        return []
    return [
        f"activation critique count {count}/{REQUIRED_ACTIVATION_CRITIQUES}; "
        "load /aiwf-planner, read references/activation-critique.md, run the critique, "
        f"then record it with: aiwf task critique {task_id}"
    ]

def record_task_activation_critique(base_dir: str, task_id: str) -> Dict[str, Any]:
    ledger = load_ledger(base_dir)
    task = _find(ledger.get("tasks", []), task_id)
    if not task:
        return {"recorded": False, "blockers": [f"task not found: {task_id}"], "task": None}
    if task.get("status") == "active":
        return {"recorded": False, "blockers": ["task is already active"], "task": task}
    if task.get("status") in TERMINAL_TASK_STATUSES:
        return {"recorded": False, "blockers": [f"task is {task.get('status')}"], "task": task}
    count = task_activation_critique_count(task) + 1
    task["activation_critique_count"] = count
    task["activation_critique_updated_at"] = _now()
    task["updated_at"] = _now()
    save_ledger(base_dir, ledger)
    return {
        "recorded": True,
        "blockers": [],
        "task": task,
        "count": count,
        "required": REQUIRED_ACTIVATION_CRITIQUES,
        "ready": count >= REQUIRED_ACTIVATION_CRITIQUES,
    }

def activation_blockers(base_dir: str, task_id: str) -> List[str]:
    """Task activation minimal gates.

    Task.md is the execution contract. Plan is not a gate.
    Only checks: task exists, status valid, dependencies, one Task in the target
    worktree, Task-local findings, activation proof, and Git readiness.
    """
    ledger = load_ledger(base_dir)
    tasks = ledger.get("tasks", [])
    task = _find(tasks, task_id)
    blockers: List[str] = []
    if not task:
        return [f"task not found: {task_id}"]
    if task.get("status") not in ("candidate", "ready", "suspended", "blocked"):
        blockers.append(f"task status cannot activate: {task.get('status')}")

    for dep in task.get("dependencies", []) or []:
        dep_task = _find(tasks, dep)
        if not dep_task or dep_task.get("status") != "closed":
            blockers.append(f"dependency not closed: {dep}")

    plan = {}
    plan_id = str(task.get("plan_id") or task.get("parent_plan") or "")
    if plan_id:
        from .state.plan_ops import get_plan
        plan = get_plan(base_dir, plan_id, migrate=False)
    target_worktree = str(plan.get("git_worktree_path") or resolve_worktree_root(base_dir))
    occupied = {
        str(item.get("id"))
        for item in tasks
        if item.get("status") == "active"
        and item.get("id") != task_id
        and item.get("worktree_path")
        and same_path(item["worktree_path"], target_worktree)
    }
    if occupied:
        blockers.append(
            "target worktree already has active Task " + ", ".join(sorted(occupied))
        )
    record = load_task_record(base_dir, task_id)
    if task.get("scope_violation"):
        blockers.append(
            "scope violation remains recorded; revert the violating files, then run "
            "aiwf fix-loop resolve --resolution '<what was reverted>' before activating another task"
        )
    if task.get("phase") == "closing":
        blockers.append("this Task still needs to close")
    fix_loop = record.get("fix_loop", {}) or {}
    if fix_loop.get("status") == "open":
        required = fix_loop.get("required_verification", []) or []
        suffix = f"; required verification: {', '.join(map(str, required[:3]))}" if required else ""
        blockers.append(
            "fix-loop is open; complete required fixes/verification and run aiwf fix-loop resolve"
            + suffix
        )
    try:
        from .task_proof import activation_proof_blockers
        blockers.extend(activation_proof_blockers(base_dir, task))
    except Exception as e:
        blockers.append(f"Task proof contract check failed: {e}")
    blockers.extend(_active_plan_blockers(base_dir, task))
    plan_needs_worktree = bool(plan_id and plan and not plan.get("git_worktree_path"))
    if not plan_needs_worktree:
        try:
            from .git_workflow import task_activation_git_blockers
            blockers.extend(task_activation_git_blockers(
                target_worktree,
                plan,
                allow_dirty=task.get("status") == "suspended",
                expected_head=str(task.get("git_origin_ref") or "") if task.get("status") == "suspended" else "",
            ))
        except Exception as e:
            blockers.append(f"Git activation check failed: {e}")
    return blockers

def _active_plan_blockers(base_dir: str, task: Dict[str, Any]) -> List[str]:
    """Plan is optional. Task.md is the execution contract.

    When a Plan is attached, only verify it exists and its index binding is healthy.
    Semantic fields (allowed_write, purpose, work_intent, etc.) live in Plan.md and
    are checked by Reviewer — NOT by the activation gate.
    """
    plan_id = str(task.get("plan_id") or "")
    if not plan_id:
        return []

    blockers: List[str] = []
    try:
        from .state.plan_ops import get_plan, plan_exists
        if not plan_exists(base_dir, plan_id):
            blockers.append(f"[plan] Plan '{plan_id}' not found in plans.json")
            return blockers
        plan = get_plan(base_dir, plan_id, migrate=False)
        if not plan:
            blockers.append(f"[plan] Plan '{plan_id}' entry is empty")
            return blockers
        if not plan.get("git_worktree_path"):
            blockers.append(
                f"[plan] Plan '{plan_id}' has no worktree. Run from the control root: "
                f"aiwf plan bind-worktree {plan_id} --create"
            )
        # Check Plan.md exists if doc_path is set
        doc_path = plan.get("doc_path", "")
        if doc_path:
            from pathlib import Path as _Path
            if not (resolve_control_root(base_dir) / doc_path).exists():
                blockers.append(
                    f"[plan] Plan.md missing at {doc_path} — "
                    f"create it with: aiwf plan create {plan_id} --narrative"
                )
        # Check dependencies if plan has them
        from .state.plan_ops import plan_dependency_blockers
        dep_blockers = plan_dependency_blockers(base_dir, plan_id)
        if dep_blockers:
            blockers.extend(dep_blockers)
    except Exception as e:
        blockers.append(f"[plan] Plan check failed: {e}")

    return blockers

def activate_task(base_dir: str, task_id: str) -> Dict[str, Any]:
    """Activate a planned task if execution-window gates pass."""
    try:
        with _exclusive_operation_lock(str(resolve_control_root(base_dir)), "task-ledger"):
            return _activate_task_locked(base_dir, task_id)
    except TimeoutError as exc:
        return {
            "activated": False,
            "task": None,
            "ledger": load_ledger(base_dir),
            "blockers": [str(exc)],
        }


def _activate_task_locked(base_dir: str, task_id: str) -> Dict[str, Any]:
    ledger = load_ledger(base_dir)
    task = _find(ledger["tasks"], task_id)
    blockers = activation_blockers(base_dir, task_id)
    if blockers:
        return {"activated": False, "task": task, "ledger": ledger, "blockers": blockers}
    from .temporary_access import disable_temporary_ai_writes

    disable_temporary_ai_writes(base_dir)
    resuming = task.get("status") == "suspended"
    task["status"] = "active"
    task["phase"] = str(task.pop("suspended_phase", "") or "implementing")
    task["activation_critique_count"] = 0
    task.pop("activation_critique_updated_at", None)
    task["activated_at"] = _now()
    task["updated_at"] = _now()
    worktree = resolve_worktree_root(base_dir)
    # Bind the Plan to its worktree on its first Task.
    if task.get("plan_id"):
        from .git_workflow import bind_plan_worktree
        from .state.plan_ops import load_plans, save_plans

        plans = load_plans(base_dir)
        for p in plans.get("plans", []) or []:
            if p.get("plan_id", p.get("id")) == task["plan_id"]:
                target = p.get("git_worktree_path") or worktree
                bind_plan_worktree(base_dir, p, target)
                worktree = resolve_worktree_root(target)
                p.setdefault("task_status", {})[task_id] = "active"
                save_plans(base_dir, plans)
                break
    if task.get("plan_id"):
        try:
            from .state.plan_ops import get_plan
            plan = get_plan(base_dir, task["plan_id"], migrate=False)
            plan_goal = plan.get("target_goal_id") or plan.get("goal_id")
            if plan_goal and not task.get("goal_id"):
                task["goal_id"] = plan_goal
                task["parent_goal"] = plan_goal
            if plan.get("milestone_id") and not task.get("milestone_id"):
                task["milestone_id"] = plan["milestone_id"]
        except Exception:
            pass
    from .git_workflow import repository_info

    if not resuming or not task.get("git_origin_ref"):
        git_info = repository_info(str(worktree))
        ref = git_info["head"]
        task["git_origin_ref"] = ref
        task["git_branch"] = git_info["branch"]
        save_task_record(base_dir, default_task_record(task_id))
    task["worktree_path"] = str(worktree)
    save_ledger(base_dir, ledger)
    return {"activated": True, "task": task, "ledger": ledger, "blockers": []}

def interrupt_task(base_dir: str, reason: str = "", task_id: str = "") -> Dict[str, Any]:
    try:
        with _exclusive_operation_lock(str(resolve_control_root(base_dir)), "task-ledger"):
            return _interrupt_task_locked(base_dir, reason=reason, task_id=task_id)
    except TimeoutError as exc:
        return {
            "interrupted": False, "task": None, "ledger": load_ledger(base_dir),
            "blockers": [str(exc)],
        }


def _interrupt_task_locked(base_dir: str, reason: str = "", task_id: str = "") -> Dict[str, Any]:
    """Human-only interruption of one active Task.

    This releases the execution window without marking the task complete.
    Use cancel for work that should be abandoned, and force-close only when a
    human explicitly accepts an incomplete gate state as finished.
    """
    task_id = resolve_active_task_id(base_dir, task_id)
    if not task_id:
        return {"interrupted": False, "task": None, "ledger": load_ledger(base_dir),
                "blockers": ["no active task to interrupt"]}

    ledger = load_ledger(base_dir)
    task = _find(ledger.get("tasks", []), task_id)
    if not task:
        return {"interrupted": False, "task": None, "ledger": ledger,
                "blockers": [f"active task not found in ledger: {task_id}"]}
    if task.get("status") in TERMINAL_TASK_STATUSES:
        return {"interrupted": False, "task": task, "ledger": ledger,
                "blockers": [f"cannot interrupt terminal task: {task.get('status')}"]}

    task["status"] = "suspended"
    task["updated_at"] = _now()
    task["interruption"] = {
        "reason": reason.strip() or None,
        "unsatisfied_checks": _task_unsatisfied_checks(base_dir, task),
    }
    task["suspended_phase"] = task.get("phase")
    task["phase"] = "suspended"
    if reason.strip():
        task.setdefault("notes", []).append(f"INTERRUPTED by human: {reason.strip()}")
    warning = _mark_task_doc_contract_status(base_dir, task, "suspended")
    if warning:
        task.setdefault("close_warnings", []).append(warning)

    save_ledger(base_dir, ledger)
    return {"interrupted": True, "task": task, "ledger": ledger, "blockers": []}

def close_task(base_dir: str, task_id: str = "", note: str = "") -> Dict[str, Any]:
    try:
        with _exclusive_operation_lock(str(resolve_control_root(base_dir)), "task-ledger"):
            return _close_task_locked(base_dir, task_id=task_id, note=note)
    except TimeoutError as exc:
        return {
            "closed": False, "task": None, "ledger": load_ledger(base_dir),
            "blockers": [str(exc)],
        }


def _close_task_locked(base_dir: str, task_id: str = "", note: str = "") -> Dict[str, Any]:
    """Mark one active Task closed.

    Returns goal progress: task is an execution unit, not a goal unit.
    Close output must show: task closed, goal complete status, next task.
    """
    task_id = str(task_id or "") or resolve_active_task_id(base_dir)
    if not task_id:
        return {"closed": False, "task": None, "ledger": load_ledger(base_dir),
                "blockers": ["no active task to close"]}
    ledger = load_ledger(base_dir)
    task = _find(ledger["tasks"], task_id)
    if not task:
        return {"closed": False, "task": None, "ledger": ledger, "blockers": [f"task not found: {task_id}"]}
    if task.get("status") == "closed":
        warning = _mark_task_doc_closed(base_dir, task)
        if warning:
            task.setdefault("close_warnings", []).append(warning)
            save_ledger(base_dir, ledger)
        return {"closed": True, "task": task, "ledger": ledger, "blockers": []}
    if task.get("status") != "active":
        return {
            "closed": False,
            "task": task,
            "ledger": ledger,
            "blockers": [f"task status is '{task.get('status')}', not active; activate the task before close"],
        }
    if task.get("status") == "active":
        blockers: List[str] = []
        record = load_task_record(base_dir, task_id)
        fix_loop = record.get("fix_loop", {}) or {}
        implementation = record.get("implementation", {}) or {}
        testing = record.get("testing", {}) or {"status": "missing"}
        review = record.get("review", {}) or {"result": "unknown"}
        reqs = task.get("requirements", {})

        if fix_loop.get("status") == "open":
            blockers.append("open fix-loop blocks task close")
        if task.get("scope_violation"):
            blockers.append("unresolved Forbidden Write violation blocks task close")

        if reqs.get("executor_required"):
            if (
                implementation.get("task_id") != task_id
                or not implementation.get("implementation_ref")
            ):
                blockers.append("executor_required but no current implementation record exists")

        if reqs.get("tester_required"):
            test_status = testing.get("status")
            if testing.get("task_id") != task_id or not testing.get("tested_ref"):
                blockers.append("tester_required but no current tested snapshot exists")
            if test_status not in ("adequate", "passed"):
                blockers.append("tester_required but testing status is not adequate/passed")
            elif test_status == "passed":
                from .task_proof import validate_testing_against_task

                proof = validate_testing_against_task(base_dir, task, testing)
                for key, label in (
                    ("missing_commands", "missing Verification Command"),
                    ("missing_verification_results", "missing expected/observed result"),
                    ("mismatched_results", "mismatched observable result"),
                    ("empty_observed_results", "empty observed result"),
                ):
                    values = proof.get(key, []) or []
                    if proof.get("strict") and values:
                        blockers.append(f"{label}: {', '.join(map(str, values[:5]))}")

        if reqs.get("reviewer_required"):
            if review.get("result") != "accepted" or not review.get("closure_allowed", False):
                blockers.append("reviewer_required but review not accepted for closure")
            if review.get("blockers"):
                blockers.append(f"review has blockers: {review['blockers']}")
            pending = [
                item for item in (review.get("adversarial_observations", []) or [])
                if isinstance(item, dict) and item.get("disposition") == "pending"
            ]
            if pending:
                blockers.append(f"{len(pending)} Reviewer observation(s) still need Planner disposition")

        tested_ref = str(testing.get("tested_ref") or "")
        reviewed_ref = str(review.get("reviewed_ref") or "")
        worktree = str(task.get("worktree_path") or resolve_worktree_root(base_dir))
        if tested_ref and reviewed_ref != tested_ref:
            blockers.append("Reviewer did not accept the current tested snapshot")
        if reviewed_ref:
            try:
                from .git_snapshots import worktree_matches_ref
                if not worktree_matches_ref(worktree, reviewed_ref):
                    from .git_workflow import reviewed_snapshot_mismatch_message
                    blockers.append(reviewed_snapshot_mismatch_message(worktree, reviewed_ref))
            except Exception as e:
                blockers.append(f"reviewed snapshot check failed: {e}")

        if blockers:
            return {"closed": False, "task": task, "ledger": ledger, "blockers": blockers}
        reviewed_ref = str(review.get("reviewed_ref") or "")
        git_commit = ""
        if reviewed_ref:
            try:
                from .git_workflow import create_task_commit

                git_commit = create_task_commit(
                    worktree,
                    task,
                    str(task.get("git_origin_ref") or ""),
                    reviewed_ref,
                )
            except ValueError as e:
                return {"closed": False, "task": task, "ledger": ledger, "blockers": [f"Git close blocked: {e}"]}
        else:
            from .git_workflow import changed_project_files
            if changed_project_files(worktree):
                return {
                    "closed": False, "task": task, "ledger": ledger,
                    "blockers": ["Git close blocked: project changes exist without a reviewed snapshot"],
                }
    task["status"] = "closed"
    task["phase"] = "closed"
    task["closed_at"] = _now()
    task["updated_at"] = _now()
    task["closure"] = {
        "mode": "normal",
        "accepted": True,
        "summary": note or "",
        "git_commit": git_commit,
        "implementation_ref": implementation.get("implementation_ref", ""),
        "tested_ref": testing.get("tested_ref", ""),
        "reviewed_ref": review.get("reviewed_ref", ""),
    }
    if note:
        task.setdefault("notes", []).append(note)
    warning = _mark_task_doc_closed(base_dir, task)
    if warning:
        task.setdefault("close_warnings", []).append(warning)
    # Goal progress: find sibling tasks under the same parent goal
    parent_goal = task.get("goal_id") or task.get("parent_goal", "") or ""
    parent_plan = task.get("plan_id") or task.get("parent_plan", "") or ""
    goal_tasks = []
    if parent_goal:
        goal_tasks = [
            t for t in ledger.get("tasks", [])
            if (t.get("goal_id") or t.get("parent_goal")) == parent_goal and t.get("id") != task_id
        ]
    elif parent_plan:
        goal_tasks = [
            t for t in ledger.get("tasks", [])
            if (t.get("plan_id") or t.get("parent_plan")) == parent_plan and t.get("id") != task_id
        ]

    closed_count = sum(1 for t in goal_tasks if t.get("status") == "closed") + 1  # +1 for this task
    total_count = len(goal_tasks) + 1
    remaining = [t.get("id", "") for t in goal_tasks if t.get("status") not in TERMINAL_TASK_STATUSES]
    goal_complete = len(remaining) == 0

    save_ledger(base_dir, ledger)
    plan_progress = {}
    try:
        from .state.plan_ops import reconcile_task_to_plan
        plan_progress = reconcile_task_to_plan(base_dir, task)
    except Exception:
        plan_progress = {"reconciled": False, "reason": "plan reconcile failed"}
    # Granularity: task without parent goal is an orphan.
    # Tasks are execution units, not goal units.
    # Milestone verification tasks bind to milestone_id, not parent_goal.
    task_kind = task.get("kind", "")
    task_milestone_id = task.get("milestone_id", "")
    granularity_warnings = []
    if not parent_goal and not parent_plan:
        if task_kind == "milestone_verification" and task_milestone_id:
            pass  # milestone verification tasks bind to milestone_id, not parent_goal
        else:
            granularity_warnings.append(
                "No parent_goal set — task was not linked to a larger goal. "
                "Use --parent-goal GOAL-xxx when planning tasks to prevent goal drift."
            )

    return {
        "closed": True,
        "task": task,
        "ledger": ledger,
        "blockers": [],
        "goal_progress": {
            "parent_goal": parent_goal,
            "parent_plan": parent_plan,
            "closed_count": closed_count,
            "total_count": total_count,
            "goal_complete": goal_complete,
            "remaining_tasks": remaining,
        },
        "plan_progress": plan_progress,
        "granularity_warnings": granularity_warnings,
    }

def force_close_task(base_dir: str, reason: str = "", task_id: str = "") -> Dict[str, Any]:
    try:
        with _exclusive_operation_lock(str(resolve_control_root(base_dir)), "task-ledger"):
            return _force_close_task_locked(base_dir, reason=reason, task_id=task_id)
    except TimeoutError as exc:
        return {
            "closed": False, "task": None, "ledger": load_ledger(base_dir),
            "blockers": [str(exc)],
        }


def _force_close_task_locked(base_dir: str, reason: str = "", task_id: str = "") -> Dict[str, Any]:
    """Human-only emergency close of one active Task.
    Bypasses ALL gates — no hash check, no evidence, no testing, no review.

    AI is mechanically blocked from calling this by command-policy.json.
    """
    task_id = str(task_id or "") or resolve_active_task_id(base_dir)
    if not task_id:
        return {"closed": False, "task": None, "ledger": load_ledger(base_dir),
                "blockers": ["no active task to force-close"]}

    ledger = load_ledger(base_dir)
    task = _find(ledger.get("tasks", []), task_id)
    if not task:
        return {"closed": False, "task": None, "ledger": ledger,
                "blockers": [f"active task not found in ledger: {task_id}"]}
    if task.get("status") == "closed":
        warning = _mark_task_doc_closed(base_dir, task)
        if warning:
            task.setdefault("close_warnings", []).append(warning)
            save_ledger(base_dir, ledger)
        return {"closed": True, "task": task, "ledger": ledger, "blockers": []}
    if task.get("status") != "active":
        return {
            "closed": False, "task": task, "ledger": ledger,
            "blockers": [f"task status is '{task.get('status')}', not active"],
        }

    unsatisfied = _task_unsatisfied_checks(base_dir, task)

    task["status"] = "closed"
    task["phase"] = "closed"
    task["closed_at"] = _now()
    task["updated_at"] = _now()
    task["closure"] = {
        "mode": "human_force",
        "reason": reason.strip() or None,
        "unsatisfied_checks": unsatisfied,
    }
    if reason.strip():
        task.setdefault("notes", []).append(f"FORCE-CLOSED by human: {reason.strip()}")
    warning = _mark_task_doc_closed(base_dir, task)
    if warning:
        task.setdefault("close_warnings", []).append(warning)

    save_ledger(base_dir, ledger)

    try:
        from .state.plan_ops import reconcile_task_to_plan
        reconcile_task_to_plan(base_dir, task)
    except Exception:
        pass

    return {"closed": True, "task": task, "ledger": ledger, "blockers": []}

def ledger_summary(base_dir: str) -> Dict[str, Any]:
    ledger = load_ledger(base_dir)
    tasks = ledger.get("tasks", [])
    counts: Dict[str, int] = {}
    for task in tasks:
        status = task.get("status", "unknown")
        counts[status] = counts.get(status, 0) + 1
    active_ids = [t.get("id") for t in tasks if t.get("status") == "active" and t.get("id")]
    return {
        "tasks": tasks,
        "counts": counts,
        "active_task_ids": active_ids,
        "active_tasks": [t for t in tasks if t.get("status") == "active"],
    }
