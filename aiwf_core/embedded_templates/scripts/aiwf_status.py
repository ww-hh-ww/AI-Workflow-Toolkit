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
    active = [
        task for task in ledger.get("tasks", []) or []
        if isinstance(task, dict) and task.get("status") == "active"
    ]
    problems = []
    fingerprint_tasks = []
    for task in active:
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
        message = f"[AIWF] {changed_task_ids[0]} changed state. {route}"
    elif previous and changed_task_ids:
        message = f"[AIWF] Task state changed: {', '.join(changed_task_ids)}. {route}"
    elif previous and previous.get("problems", []) != fingerprint["problems"]:
        message = f"[AIWF] AIWF problem state changed. {route}"
    elif previous:
        message = f"[AIWF] AIWF routing state changed. {route}"
    elif len(active) == 1:
        message = f"[AIWF] {active[0]['id']} is active. {route}"
    elif active:
        message = f"[AIWF] {len(active)} Tasks are active across Plan worktrees. {route}"
    else:
        message = f"[AIWF] Plan Before Work. {route}"
    if problems:
        message += " Attention: " + "; ".join(problems[:2]) + "."
    _emit(message)


if __name__ == "__main__":
    main()
