"""Fix-loop routing facts shared by all status consumers."""
from __future__ import annotations

from .agent_runtime import resumable_agent
from .task_dispatch import _live_experiment_next, _post_construction_route


def repair_route(task, record, control, host):
    task_id = str(task.get("id") or "")
    requirements = task.get("requirements", {}) or {}
    implementation = record.get("implementation", {}) or {}
    review = record.get("review", {}) or {}
    fix_loop = record.get("fix_loop", {}) or {}
    if fix_loop.get("status") == "open":
        if fix_loop.get("escalation_required"):
            return (
                "Planner decision",
                f"load /aiwf-planner and run aiwf fixloop status --task-id {task_id}; "
                "tell the user what failed and what still needs verification, then ask them to choose: "
                f"continue with aiwf fixloop continue --task-id {task_id}; pause and replan with "
                f"aiwf task interrupt {task_id}; or accept the unmet checks and close with "
                f"aiwf task force-close {task_id}. These commands are human-only. If they continue, "
                "run aiwf status --prompt again and follow its route",
            )
        route = str(fix_loop.get("route") or "planner")
        if route == "executor":
            previous = (
                resumable_agent(
                    control, task_id=task_id, subagent_type="aiwf-executor",
                )
                if control else None
            )
            if previous:
                if host == "opencode":
                    agent_route = (
                        f"otherwise continue the previous aiwf-executor child once with "
                        f"task_id {previous['agent_id']} and tell it to read aiwf task proof "
                        f"{task_id}; if continuation is unavailable, dispatch a new "
                        "aiwf-executor with the Task ID and current finding"
                    )
                else:
                    agent_route = (
                        f"otherwise, if available in this or the resumed original Claude session, "
                        f"try once to resume aiwf-executor {previous['agent_id']} with "
                        "SendMessage using the Task ID and a concise repair brief grounded in "
                        "the fix-loop context below; name the confirmed finding and source, "
                        "affected expected behavior, what remains valid, and focused proof, "
                        "without prescribing the implementation; if unavailable or resume "
                        "fails, dispatch a new aiwf-executor with the same repair brief"
                    )
            else:
                agent_route = (
                    "otherwise dispatch aiwf-executor with the Task ID and a concise "
                    "repair brief grounded in the fix-loop context below"
                )
            return (
                "Implementation repair",
                f"load /aiwf-implement for {task_id}; repair and record inline if tiny "
                f"and clear; {agent_route}",
            )
        if route == "reviewer":
            empirical_next = _live_experiment_next(control, task_id) if control else None
            if empirical_next:
                return empirical_next
            if (
                control
                and implementation.get("implementation_ref")
                and str(review.get("result") or "unknown") == "unknown"
            ):
                return _post_construction_route(
                    task, implementation, control, host,
                    requirements.get("reviewer_required", True),
                )
            previous = (
                resumable_agent(
                    control, task_id=task_id, subagent_type="aiwf-reviewer",
                )
                if control else None
            )
            if previous:
                if host == "opencode":
                    agent_route = (
                        f"otherwise continue the previous aiwf-reviewer child once with "
                        f"task_id {previous['agent_id']} and a concise judgment brief "
                        "grounded in the fix-loop context below; if continuation is unavailable, "
                        "dispatch a new aiwf-reviewer with the same brief"
                    )
                else:
                    agent_route = (
                        f"otherwise, if available, try once to resume aiwf-reviewer "
                        f"{previous['agent_id']} with the Task ID and the repaired candidate; "
                        "if unavailable, dispatch a new aiwf-reviewer"
                    )
            else:
                agent_route = (
                    "dispatch aiwf-reviewer with the Task ID and current repair context"
                )
            return (
                "Reviewer",
                f"load /aiwf-review for {task_id}; {agent_route}, then record judgment",
            )
        return (
            "Planner decision",
            f"load /aiwf-planner, run aiwf fixloop status --task-id {task_id}, "
            "then resolve the decided issue or reroute remaining work",
        )

    return None
