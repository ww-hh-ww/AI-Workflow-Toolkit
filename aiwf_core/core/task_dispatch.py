"""Expose eligible post-construction paths without selecting the semantic branch."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Tuple

from ..adapters.candidate_freshness import _codex_freshness_preflight, freshness_packet


def _live_experiment_next(control: Path, task_id: str) -> Tuple[str, str] | None:
    from .experiment_records import live_experiments

    empirical_work = live_experiments(str(control), task_id)
    if not empirical_work:
        return None
    experiment = empirical_work[0]
    experiment_id = str(experiment.get("experiment_id") or "")
    state = str(experiment.get("status") or "open")
    action = (
        f"run aiwf experiment start {experiment_id}, then dispatch aiwf-experimenter "
        f"for {experiment_id}"
        if state == "open"
        else f"run aiwf experiment finish {experiment_id}, then rerun aiwf status --prompt"
        if state == "recorded"
        else f"dispatch or resume aiwf-experimenter for {experiment_id}"
    )
    return ("Experiment cleanup" if state == "recorded" else "Experimenter"), action


def _post_construction_next(
    task_id: str, reviewer_required: bool, codex_binding: Dict[str, Any] | None = None,
) -> Tuple[str, str]:
    review_action = (
        f"dispatch aiwf-reviewer for {task_id}"
        if reviewer_required
        else f"review {task_id} inline and record it"
    )
    freshness = ""
    if codex_binding:
        freshness = (
            " If it selects review, copy this exact Codex main-session freshness packet "
            "into the Reviewer dispatch: "
            + freshness_packet(codex_binding) + "\n"
        )
    return (
        "Main-session dispatch",
        f"run aiwf task proof {task_id}, read Task.md Dispatch Decisions, and use the "
        "recorded implementation and experiment evidence to choose the declared next path "
        "in this main session. If it selects Experimenter, open and start the declared "
        "post-implementation EXP against the current implementation_ref, load "
        f"/aiwf-experiment, and dispatch aiwf-experimenter with its EXP ID. If it selects "
        f"review, load /aiwf-review and {review_action}.{freshness} Do not delegate this route choice "
        "to a child Agent or infer a universal experiment rule outside Task.md",
    )


def _post_construction_route(
    task: Dict[str, Any], implementation: Dict[str, Any], control: Path,
    host: str, reviewer_required: bool,
) -> Tuple[str, str]:
    if host == "codex":
        freshness = _codex_freshness_preflight(task, implementation, control)
        if isinstance(freshness, tuple):
            return freshness
        return _post_construction_next(
            str(task.get("id") or ""), reviewer_required, freshness,
        )
    return _post_construction_next(
        str(task.get("id") or ""), reviewer_required,
    )
