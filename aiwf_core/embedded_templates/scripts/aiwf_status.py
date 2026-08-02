#!/usr/bin/env python3
"""Quiet UserPromptSubmit nudge; full routing lives in aiwf status --prompt."""

import json
import os
import subprocess
import sys
from pathlib import Path


def _read_json(path, default):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else default
    except Exception:
        return default


def _emit(text):
    if os.environ.get("AIWF_HOOK_ENGINE", "").lower() == "reasonix":
        print(text)
        return
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": text,
    }}))


def _record(base, task_id):
    return _read_json(
        base / ".aiwf" / "records" / "tasks" / f"{task_id}.json",
        {},
    )


def _control_root(project_root):
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=str(project_root), capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            common = Path(result.stdout.strip())
            if not common.is_absolute():
                common = (project_root / common).resolve()
            primary = common.parent
            if (primary / ".aiwf/state/tasks.json").exists():
                return primary
    except Exception:
        pass
    return project_root


def _problem(task, record):
    fix_loop = record.get("fix_loop", {}) or {}
    if fix_loop.get("status") == "open":
        return f"{task['id']} fix-loop routes to {fix_loop.get('route') or 'planner'}"
    review = record.get("review", {}) or {}
    if review.get("result") in ("rejected", "needs_fix", "needs_more_testing", "scope_violation"):
        return f"{task['id']} review={review.get('result')}"
    if task.get("scope_violation"):
        return f"{task['id']} has a scope violation"
    return ""


def _evidence(record):
    implementation = record.get("implementation", {}) or {}
    testing = record.get("testing", {}) or {}
    review = record.get("review", {}) or {}
    bits = [
        "impl=" + ("recorded" if implementation.get("implementation_ref") else "missing"),
        "test=" + str(testing.get("status") or "missing"),
        "review=" + str(review.get("result") or "unknown"),
    ]
    if testing.get("status") in ("passed", "adequate") and not testing.get("tested_ref"):
        bits.append("tested_ref=missing")
    if review.get("result") == "accepted" and not review.get("closure_allowed"):
        bits.append("closure=blocked")
    return ", ".join(bits)


def _decision(task, record):
    task_id = str(task.get("id") or "")
    requirements = task.get("requirements", {}) or {}
    fix_loop = record.get("fix_loop", {}) or {}
    if task.get("status") == "suspended":
        return (
            "Planner",
            f"inspect why {task_id} is suspended, then reactivate or revise; do not continue project writes first",
        )
    if fix_loop.get("status") == "open":
        route = str(fix_loop.get("route") or "planner")
        if route == "executor":
            return "Executor repair", f"route the finding to aiwf-executor for {task_id}"
        if route == "tester":
            return "Tester follow-up", f"route missing verification to aiwf-tester for {task_id}"
        return "Planner", f"run aiwf fixloop status --task-id {task_id} and decide the repair route"

    implementation = record.get("implementation", {}) or {}
    testing = record.get("testing", {}) or {}
    review = record.get("review", {}) or {}
    if not implementation.get("implementation_ref"):
        if requirements.get("executor_required", True):
            return "Executor", f"dispatch or resume aiwf-executor for {task_id}"
        return "Inline implementation", f"implement {task_id} inline and record implementation"
    if testing.get("status") not in ("adequate", "passed"):
        if requirements.get("tester_required", True):
            return "Tester", f"dispatch or resume aiwf-tester for {task_id}; verify real behavior, not just form"
        return "Inline testing", f"test {task_id} inline and record concrete commands/results"
    if review.get("result") != "accepted" or not review.get("closure_allowed", False):
        if requirements.get("reviewer_required", True):
            return "Reviewer", f"dispatch or resume aiwf-reviewer for {task_id}"
        return "Inline review", f"review {task_id} inline and record findings"
    return "Close", f"calibrate Task.md if needed, then close {task_id}"


def _guardrail(role):
    if role in ("Executor", "Tester", "Reviewer", "Executor repair", "Tester follow-up"):
        return "use the native Agent/Task tool; do not role-play or self-fill missing independent evidence"
    if role.startswith("Inline"):
        return "inline is allowed by this Task; still record concrete evidence before close"
    if role == "Close":
        return "do not close over unresolved observations or unverified behavior"
    return "do not mutate project files until the planner decision is clear"


def _resume_packet(prefix, task, record):
    role, action = _decision(task, record)
    task_id = str(task.get("id") or "")
    phase = str(task.get("phase") or task.get("status") or "-")
    plan_id = str(task.get("plan_id") or task.get("parent_plan") or "-")
    worktree = str(task.get("worktree_path") or "-")
    return (
        f"[AIWF] {prefix}\n"
        f"Resume: task={task_id} plan={plan_id} phase={phase} worktree={worktree}\n"
        f"Evidence: {_evidence(record)}\n"
        f"Decision: {role} - {action}\n"
        f"Guardrail: {_guardrail(role)}\n"
        "Confirm: run `aiwf status --prompt` if anything looks stale before acting."
    )


def _single_workflow_task(workflow_tasks):
    return workflow_tasks[0] if len(workflow_tasks) == 1 else None


def _changed_task_ids(previous, current):
    def indexed(fingerprint):
        return {
            str(task.get("id") or ""): task
            for task in fingerprint.get("tasks", []) or []
            if isinstance(task, dict) and task.get("id")
        }

    before = indexed(previous)
    after = indexed(current)
    return sorted(
        task_id for task_id in set(before) | set(after)
        if before.get(task_id) != after.get(task_id)
    )


def main():
    base = _control_root(Path(__file__).resolve().parent.parent)
    ledger_path = base / ".aiwf" / "state" / "tasks.json"
    if not ledger_path.exists():
        _emit("[AIWF] Not initialized. Run: aiwf install claude")
        return

    ledger = _read_json(ledger_path, {"tasks": []})
    workflow_tasks = [
        task for task in ledger.get("tasks", []) or []
        if isinstance(task, dict) and task.get("status") in ("active", "suspended")
    ]
    active = [task for task in workflow_tasks if task.get("status") == "active"]
    suspended = [task for task in workflow_tasks if task.get("status") == "suspended"]
    problems = []
    fingerprint_tasks = []
    for task in workflow_tasks:
        record = _record(base, str(task.get("id") or ""))
        problem = _problem(task, record)
        if problem:
            problems.append(problem)
        fingerprint_tasks.append({
            "id": task.get("id", ""),
            "phase": task.get("phase", ""),
            "worktree": task.get("worktree_path", ""),
            "testing": (record.get("testing", {}) or {}).get("status", "missing"),
            "review": (record.get("review", {}) or {}).get("result", "unknown"),
            "fix": (record.get("fix_loop", {}) or {}).get("status", "none"),
        })
    fingerprint_tasks.sort(key=lambda task: str(task.get("id") or ""))
    temporary_marker = _read_json(
        base / ".aiwf/runtime/internal/temporary-ai-writes.json", {}
    )
    temporary_ai_writes = temporary_marker.get("enabled") is True and not active
    fingerprint = {
        "tasks": fingerprint_tasks,
        "problems": sorted(problems),
        "temporary_ai_writes": temporary_ai_writes,
    }
    fp_path = base / ".aiwf/runtime/internal/status-hook-last.json"
    previous = _read_json(fp_path, {})
    if previous == fingerprint:
        return
    changed_task_ids = _changed_task_ids(previous, fingerprint)
    try:
        fp_path.parent.mkdir(parents=True, exist_ok=True)
        fp_path.write_text(json.dumps(fingerprint, indent=2) + "\n", encoding="utf-8")
    except Exception:
        pass

    route = "Run `aiwf status --prompt` and follow its route."
    if temporary_ai_writes:
        message = (
            "[AIWF] Human enabled temporary AI project writes. "
            "Complete the requested small operation directly; do not create a Task for it."
        )
    elif previous.get("temporary_ai_writes"):
        message = f"[AIWF] Temporary AI project writes are off. {route}"
    elif previous and len(changed_task_ids) == 1:
        task = next(
            (item for item in workflow_tasks if str(item.get("id") or "") == changed_task_ids[0]),
            None,
        )
        if task:
            message = _resume_packet(
                f"{changed_task_ids[0]} changed state.",
                task,
                _record(base, changed_task_ids[0]),
            )
        else:
            message = f"[AIWF] {changed_task_ids[0]} changed state. {route}"
    elif previous and changed_task_ids:
        message = f"[AIWF] Task state changed: {', '.join(changed_task_ids)}. {route}"
    elif previous and previous.get("problems", []) != fingerprint["problems"]:
        task = _single_workflow_task(workflow_tasks)
        if task:
            task_id = str(task.get("id") or "")
            message = _resume_packet(
                "AIWF problem state changed.",
                task,
                _record(base, task_id),
            )
        else:
            message = f"[AIWF] AIWF problem state changed. {route}"
    elif previous:
        task = _single_workflow_task(workflow_tasks)
        if task:
            task_id = str(task.get("id") or "")
            message = _resume_packet(
                "AIWF routing state changed.",
                task,
                _record(base, task_id),
            )
        else:
            message = f"[AIWF] AIWF routing state changed. {route}"
    elif len(active) == 1 and not suspended:
        task_id = str(active[0].get("id") or "")
        message = _resume_packet(
            f"{task_id} is active.",
            active[0],
            _record(base, task_id),
        )
    elif active:
        message = f"[AIWF] {len(active)} Tasks are active across Plan worktrees. {route}"
    elif len(suspended) == 1:
        task_id = str(suspended[0].get("id") or "")
        message = _resume_packet(
            f"{task_id} is suspended.",
            suspended[0],
            _record(base, task_id),
        )
    elif suspended:
        message = f"[AIWF] {len(suspended)} Tasks are suspended. {route}"
    else:
        message = f"[AIWF] Plan Before Work. {route}"
    if problems:
        message += " Attention: " + "; ".join(problems[:2]) + "."
    _emit(message)


if __name__ == "__main__":
    main()
