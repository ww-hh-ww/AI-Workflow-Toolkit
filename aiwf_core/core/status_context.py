"""Shared change fingerprint for CLI acknowledgment and quiet host nudges."""
from .experiment_records import load_experiment
from .task_records import load_task_record
from .temporary_access import temporary_ai_writes_enabled


def problem(task, record):
    fix = record.get("fix_loop", {}) or {}
    if fix.get("status") == "open":
        return f"{task['id']} fix-loop routes to {fix.get('route') or 'planner'}"
    review = record.get("review", {}) or {}
    if review.get("result") == "accepted" and not review.get("closure_allowed", False):
        return f"{task['id']} accepted review lacks complete-story assertion"
    if review.get("result") in ("rejected", "needs_change", "needs_experiment", "scope_violation"):
        return f"{task['id']} review={review.get('result')}"
    return f"{task['id']} has a scope violation" if task.get("scope_violation") else ""


def fingerprint(control, tasks):
    rows, problems = [], []
    for task in tasks:
        record = load_task_record(control, str(task.get("id") or ""))
        review = record.get("review", {}) or {}
        issue = problem(task, record)
        if issue:
            problems.append(issue)
        experiment_ids = list(record.get("experiment_ids", []) or [])
        experiments = []
        for identity in experiment_ids:
            exp = load_experiment(control, identity)
            experiments.append({
                "id": identity, "status": exp.get("status"),
                "ref": exp.get("experiment_ref"),
                "disposition": exp.get("disposition"),
            })
        rows.append({
            "id": task.get("id", ""), "phase": task.get("phase", ""),
            "worktree": task.get("worktree_path", ""),
            "implementation": (record.get("implementation", {}) or {}).get("implementation_ref", ""),
            "experiments": experiment_ids, "experiment_states": experiments,
            "review": review.get("result", "unknown"),
            "review_story_complete": bool(review.get("closure_allowed", False)),
            "fix": (record.get("fix_loop", {}) or {}).get("status", "none"),
        })
    return {
        "tasks": sorted(rows, key=lambda row: str(row["id"])),
        "problems": sorted(problems),
        "temporary_ai_writes": temporary_ai_writes_enabled(control)
        and not any(task.get("status") == "active" for task in tasks),
    }
