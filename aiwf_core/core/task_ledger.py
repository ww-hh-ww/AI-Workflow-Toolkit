"""Flexible task ledger and execution-window checks.

The ledger is advisory for planning shape, but mechanical for active execution:
Planner may keep many candidate/ready tasks, while activation enforces dependency
and active-window discipline.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .state.goal_ops import get_active_goal

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
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else (default or {})
    except Exception:
        return default or {}

def _write(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def ledger_path(base_dir: str) -> Path:
    return Path(base_dir) / ".aiwf" / "state" / "tasks.json"

def _migrate_ledger_if_needed(base_dir: str) -> None:
    new_path = ledger_path(base_dir)
    old_path = Path(base_dir) / ".aiwf" / "runtime" / "history" / "task-ledger.json"
    if old_path.exists() and not new_path.exists():
        new_path.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.move(str(old_path), str(new_path))

def default_ledger() -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "default_max_active": 1,
        "tasks": [],
    }

def load_ledger(base_dir: str) -> Dict[str, Any]:
    _migrate_ledger_if_needed(base_dir)
    ledger = _read(ledger_path(base_dir), default_ledger())
    if not isinstance(ledger.get("tasks"), list):
        ledger["tasks"] = []
    ledger.setdefault("default_max_active", 1)
    ledger.setdefault("schema_version", 1)
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
    doc = Path(base_dir) / doc_path
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
    if _read(Path(base_dir) / ".aiwf" / "state" / "fix-loop.json", {}).get("status") == "open":
        unsatisfied.append("fix-loop is open")
    reqs = task.get("requirements", {})
    if reqs.get("executor_required"):
        implementation = _read(Path(base_dir) / ".aiwf/records/implementation.json", {})
        if implementation.get("task_id") != task.get("id") or not implementation.get("implementation_ref"):
            unsatisfied.append("executor_required but no implementation recorded")
    if reqs.get("tester_required"):
        testing = _read(Path(base_dir) / ".aiwf" / "records" / "testing.json", {"status": "missing"})
        if testing.get("status") not in ("adequate", "passed"):
            unsatisfied.append(f"tester_required but testing status={testing.get('status', 'missing')}")
    if reqs.get("reviewer_required"):
        review = _read(Path(base_dir) / ".aiwf" / "records" / "review.json", {"result": "unknown"})
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

def upsert_task(
    base_dir: str,
    task_id: str,
    title: str = "",
    status: str = "candidate",
    dependencies: Optional[List[str]] = None,
    allowed_write: Optional[List[str]] = None,   # DEPRECATED: ignored; scope lives on Plan
    parallel_safe: bool = False,
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
        if bool(parallel_safe) != bool(task.get("parallel_safe", False)):
            contract_changes.append("parallel_safe")
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
            "parallel_safe": False,
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
    task["parallel_safe"] = bool(parallel_safe)
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
    _sync_active_ids(ledger)
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

def _sync_active_ids(ledger: Dict[str, Any]) -> None:
    """No-op in V2. state.json.active_task_id is the single active pointer."""
    pass

def _overlap(a: List[str], b: List[str]) -> List[str]:
    return sorted(set(a or []) & set(b or []))

def _task_plan_scope(base_dir: str, task: Dict[str, Any]) -> List[str]:
    """Read the task's scope boundary — Plan is authoritative, task is legacy fallback."""
    plan_id = str(task.get("plan_id") or task.get("parent_plan") or "")
    if plan_id:
        try:
            from .state.plan_ops import get_plan
            plan = get_plan(base_dir, plan_id, migrate=False)
            plan_scope = plan.get("allowed_write", []) or []
            if plan_scope:
                return list(plan_scope)
        except Exception:
            pass
    # Legacy fallback: task-level allowed_write (deprecated, will be removed)
    return list(task.get("allowed_write", []) or [])

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
    Only checks: task exists, status valid, deps closed, no other active,
    no fix_loop, no scope_violation, and activation proof.
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

    active = [t for t in tasks if t.get("status") == "active" and t.get("id") != task_id]
    max_active = int(ledger.get("default_max_active", 1) or 1)
    if active and not task.get("parallel_safe"):
        blockers.append("active execution window occupied")
    if len(active) >= max_active and not task.get("parallel_safe"):
        blockers.append(f"default active task limit reached: {max_active}")
    if task.get("parallel_safe"):
        for other in active:
            overlap = _overlap(_task_plan_scope(base_dir, task), _task_plan_scope(base_dir, other))
            if overlap:
                blockers.append(f"parallel write boundary conflict with {other.get('id')}: {', '.join(overlap[:5])}")

    state = _read(Path(base_dir) / ".aiwf" / "state" / "state.json", {})
    if state.get("scope_violation"):
        blockers.append(
            "scope violation remains recorded; revert the violating files, then run "
            "aiwf fix-loop resolve --resolution '<what was reverted>' before activating another task"
        )
    if state.get("phase") == "closing":
        blockers.append("the current task still needs to close")
    fix_loop = _read(Path(base_dir) / ".aiwf" / "state" / "fix-loop.json", {})
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
    try:
        from .git_workflow import task_activation_git_blockers
        from .state.plan_ops import get_plan

        plan_id = str(task.get("plan_id") or task.get("parent_plan") or "")
        plan = get_plan(base_dir, plan_id, migrate=False) if plan_id else {}
        blockers.extend(task_activation_git_blockers(
            base_dir,
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
        # Check Plan.md exists if doc_path is set
        doc_path = plan.get("doc_path", "")
        if doc_path:
            from pathlib import Path as _Path
            if not (_Path(base_dir) / doc_path).exists():
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
    ledger = load_ledger(base_dir)
    task = _find(ledger["tasks"], task_id)
    blockers = activation_blockers(base_dir, task_id)
    if blockers:
        return {"activated": False, "task": task, "ledger": ledger, "blockers": blockers}
    resuming = task.get("status") == "suspended"
    task["status"] = "active"
    task["activation_critique_count"] = 0
    task.pop("activation_critique_updated_at", None)
    task["activated_at"] = _now()
    task["updated_at"] = _now()
    # Bind the Plan to the current feature branch on its first Task.
    if task.get("plan_id"):
        from .git_workflow import bind_plan_branch
        from .state.plan_ops import load_plans, save_plans

        plans = load_plans(base_dir)
        for p in plans.get("plans", []) or []:
            if p.get("plan_id", p.get("id")) == task["plan_id"]:
                bind_plan_branch(base_dir, p)
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
    _sync_active_ids(ledger)
    state_path = Path(base_dir) / ".aiwf" / "state" / "state.json"
    state = _read(state_path, {})
    from .git_workflow import repository_info
    from .state_schema import default_implementation, default_review, default_testing

    if not resuming or not task.get("git_origin_ref"):
        git_info = repository_info(base_dir)
        ref = git_info["head"]
        task["git_origin_ref"] = ref
        task["git_branch"] = git_info["branch"]
        _write(Path(base_dir) / ".aiwf/records/implementation.json", default_implementation(task_id))
        _write(Path(base_dir) / ".aiwf/records/testing.json", default_testing(task_id))
        _write(Path(base_dir) / ".aiwf/records/review.json", default_review(task_id))
    state["git_origin_ref"] = task["git_origin_ref"]
    if task.get("suspended_context"):
        for key, value in task["suspended_context"].items():
            state[key] = value
    state["active_task_id"] = task_id
    if task.get("plan_id"):
        state["active_plan_id"] = task["plan_id"]
    if state.get("phase") not in ("testing", "reviewing", "closing", "closed"):
        state["phase"] = "executing"
    _write(state_path, state)
    save_ledger(base_dir, ledger)
    return {"activated": True, "task": task, "ledger": ledger, "blockers": []}

def interrupt_task(base_dir: str, reason: str = "") -> Dict[str, Any]:
    """Human-only interruption of the current active task.

    This releases the execution window without marking the task complete.
    Use cancel for work that should be abandoned, and force-close only when a
    human explicitly accepts an incomplete gate state as finished.
    """
    state_path = Path(base_dir) / ".aiwf" / "state" / "state.json"
    state = _read(state_path, {})
    task_id = state.get("active_task_id", "")
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
    snapshot_keys = ["phase", "active_task_id", "active_plan_id"]
    task["suspended_context"] = {k: state.get(k) for k in snapshot_keys if k in state}
    if reason.strip():
        task.setdefault("notes", []).append(f"INTERRUPTED by human: {reason.strip()}")
    warning = _mark_task_doc_contract_status(base_dir, task, "suspended")
    if warning:
        task.setdefault("close_warnings", []).append(warning)

    if state.get("active_task_id") == task_id:
        state["active_task_id"] = None
    if state.get("phase") in ("executing", "testing", "reviewing", "closing"):
        state["phase"] = "planning"
    _write(state_path, state)

    _sync_active_ids(ledger)
    save_ledger(base_dir, ledger)
    return {"interrupted": True, "task": task, "ledger": ledger, "blockers": []}

def close_task(base_dir: str, task_id: str = "", note: str = "") -> Dict[str, Any]:
    """Mark the active task closed. Defaults to state.json's active_task_id.

    Returns goal progress: task is an execution unit, not a goal unit.
    Close output must show: task closed, goal complete status, next task.
    """
    if not task_id:
        state_path = Path(base_dir) / ".aiwf" / "state" / "state.json"
        state = _read(state_path, {})
        task_id = state.get("active_task_id", "")
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
        state = _read(Path(base_dir) / ".aiwf/state/state.json", {})
        fix_loop = _read(Path(base_dir) / ".aiwf/state/fix-loop.json", {})
        implementation = _read(Path(base_dir) / ".aiwf/records/implementation.json", {})
        testing = _read(Path(base_dir) / ".aiwf/records/testing.json", {"status": "missing"})
        review = _read(Path(base_dir) / ".aiwf/records/review.json", {"result": "unknown"})
        reqs = task.get("requirements", {})

        if fix_loop.get("status") == "open":
            blockers.append("open fix-loop blocks task close")
        if state.get("scope_violation"):
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
        if tested_ref and reviewed_ref != tested_ref:
            blockers.append("Reviewer did not accept the current tested snapshot")
        if reviewed_ref:
            try:
                from .git_snapshots import worktree_matches_ref
                if not worktree_matches_ref(base_dir, reviewed_ref):
                    blockers.append("project files changed after review; run Tester and Reviewer again")
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
                    base_dir,
                    task,
                    str(task.get("git_origin_ref") or ""),
                    reviewed_ref,
                )
            except ValueError as e:
                return {"closed": False, "task": task, "ledger": ledger, "blockers": [f"Git close blocked: {e}"]}
        else:
            from .git_workflow import changed_project_files
            if changed_project_files(base_dir):
                return {
                    "closed": False, "task": task, "ledger": ledger,
                    "blockers": ["Git close blocked: project changes exist without a reviewed snapshot"],
                }
    task["status"] = "closed"
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
    _sync_active_ids(ledger)

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

    state_path = Path(base_dir) / ".aiwf" / "state" / "state.json"
    state = _read(state_path, {})
    if state.get("active_task_id") == task_id:
        state["active_task_id"] = None
    if state.get("phase") in ("executing", "testing", "reviewing", "closing"):
        state["phase"] = "planning"
    _write(state_path, state)
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

def force_close_task(base_dir: str, reason: str = "") -> Dict[str, Any]:
    """Human-only emergency close of the current active task.
    Bypasses ALL gates — no hash check, no evidence, no testing, no review.

    AI is mechanically blocked from calling this by command-policy.json.
    Operates on active_task_id from state.json — no TASK-ID parameter.
    """
    state_path = Path(base_dir) / ".aiwf" / "state" / "state.json"
    state = _read(state_path, {})
    task_id = state.get("active_task_id", "")
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

    unsatisfied = _task_unsatisfied_checks(base_dir, task)

    task["status"] = "closed"
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

    state["active_task_id"] = None
    if state.get("phase") in ("executing", "testing", "reviewing", "closing"):
        state["phase"] = "planning"
    _write(state_path, state)

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
    }
