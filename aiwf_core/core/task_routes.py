"""Task-level mechanical eligibility; semantic dispatch stays in the main session."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .agent_runtime import resumable_agent
from .task_dispatch import _live_experiment_next, _post_construction_route
from .task_repair_routes import repair_route


def _task_next(
    task: Dict[str, Any],
    record: Dict[str, Any],
    control: Path | None = None,
    host: str = "",
) -> Tuple[str, str]:
    host = (host or os.environ.get("AIWF_HOST", "claude")).lower()
    task_id = str(task.get("id") or "")
    requirements = task.get("requirements", {}) or {}
    implementation = record.get("implementation", {}) or {}
    review = record.get("review", {}) or {}
    repair = repair_route(task, record, control, host)
    if repair:
        return repair

    if task.get("kind") == "milestone_verification":
        milestone_id = str(task.get("milestone_id") or "")
        from .state.milestone_ops import get_milestone

        milestone = get_milestone(str(control or Path.cwd()), milestone_id)
        synthesis = milestone.get("stage_synthesis", {}) or {}
        integration = milestone.get("integration_test", {}) or {}
        architecture = milestone.get("architecture_review", {}) or {}
        acceptance = milestone.get("user_acceptance", {}) or {}
        technically_passed = (
            synthesis.get("verdict") in ("PASS", "PASS_WITH_RISK")
            and integration.get("status") == "passed"
            and integration.get("main_path_status") == "passed"
            and architecture.get("status") == "intact"
        )
        if not technically_passed:
            return (
                "Milestone acceptance",
                f"load /aiwf-architect and dispatch an independent aiwf-architect for "
                f"{milestone_id} with the milestone-acceptance lens. Use "
                f"{control / '.aiwf/milestones' / (milestone_id + '.md') if control else 'Milestone.md'} "
                "as the acceptance contract, exercise its Pass Standard on the real path, "
                "and record integration, architecture, and assessment results. This status "
                "route does not dispatch the Agent itself",
            )
        if acceptance.get("status") != "confirmed":
            return (
                "Human acceptance",
                f"present the {milestone_id} assessment and residual risks to the user, then "
                f"ask whether they confirm this Milestone. Do not run aiwf milestone confirm "
                f"{milestone_id} until they explicitly approve",
            )
        return (
            "Planner calibration",
            f"load /aiwf-planner and calibrate {task_id} with the accepted Milestone outcome, "
            f"then load /aiwf-close and close the verification Task. After it closes, run "
            f"aiwf milestone close {milestone_id}",
        )
    if control:
        from .experiment_records import (
            list_experiments,
            pending_experiment_dispositions,
        )

        empirical_next = _live_experiment_next(control, task_id)
        if empirical_next:
            return empirical_next
        pending_dispositions = pending_experiment_dispositions(
            str(control), task_id=task_id,
        )
        if pending_dispositions:
            experiment_id = str(pending_dispositions[0].get("experiment_id") or "")
            return (
                "Planner decision",
                f"load /aiwf-planner, run aiwf experiment show {experiment_id}, then record "
                f"what the fact means with aiwf experiment disposition {experiment_id} "
                "--decision proceed|no_action|promote --reason '<why>'. If the fact invalidates "
                f"the contract, ask the user to interrupt {task_id} first, then record replan; "
                "do not edit active Task.md",
            )
        promotion = next((
            item for item in list_experiments(str(control), task_id=task_id)
            if (item.get("disposition", {}) or {}).get("decision") == "promote"
            and str((item.get("disposition", {}) or {}).get("recorded_at") or "")
            > str(implementation.get("recorded_at") or "")
        ), None)
        if promotion:
            return (
                "Executor",
                f"load /aiwf-implement and dispatch aiwf-executor for {task_id}; recreate the "
                f"approved promotion candidate from {promotion.get('experiment_id')} in stable "
                "reality, then record a fresh implementation and complete V evidence",
            )
    reviewed_ref = str(review.get("reviewed_ref") or "")
    if review.get("result") == "accepted" and reviewed_ref and control:
        try:
            from .git_snapshots import (
                ref_tree,
                worktree_changes_from_ref,
                worktree_matches_ref,
            )

            worktree = str(task.get("worktree_path") or control)
            review_stale = bool(ref_tree(worktree, reviewed_ref)) and (
                bool(worktree_changes_from_ref(worktree, reviewed_ref))
                if task.get("kind") == "integration"
                else not worktree_matches_ref(worktree, reviewed_ref)
            )
            if review_stale:
                return (
                    "Implementation repair",
                    f"load /aiwf-implement for {task_id}; project files changed after review. "
                    "Inspect the current diff, record the intended current implementation, "
                    "then rerun affected experiments and review. Do not interrupt only "
                    "because Git HEAD changed",
                )
        except Exception:
            pass
    if not implementation.get("implementation_ref"):
        if requirements.get("executor_required", True):
            previous = (
                resumable_agent(
                    control, task_id=task_id, subagent_type="aiwf-executor",
                )
                if control else None
            )
            if previous:
                if host == "opencode":
                    return (
                        "Executor",
                        f"load /aiwf-implement; continue the previous aiwf-executor child once "
                        f"with task_id {previous['agent_id']} and tell it to reread Task.md, "
                        "the current diff, and missing work; if continuation is unavailable, "
                        "dispatch a new aiwf-executor for the Task",
                    )
                return (
                    "Executor",
                    f"load /aiwf-implement; if available in this or the resumed original Claude "
                    f"session, try once to resume aiwf-executor {previous['agent_id']} "
                    f"with SendMessage: 'Resume {task_id}. Reread Task.md and the current "
                    "diff, finish any missing work, record implementation, and return'; "
                    "if unavailable or resume fails, dispatch a new aiwf-executor for the Task",
                )
            return "Executor", f"load /aiwf-implement and dispatch aiwf-executor for {task_id}"
        return "Inline implementation", f"load /aiwf-implement, implement {task_id} inline, and record it"
    proof_gaps: List[str] = []
    contract_blockers: List[str] = []
    if control:
        from .task_proof import (
            activation_proof_blockers,
            construction_proof_gaps,
            validate_implementation_against_task,
        )

        proof_validation = validate_implementation_against_task(str(control), task, implementation)
        contract_blockers = activation_proof_blockers(str(control), task)
        if implementation.get("implementation_ref"):
            proof_gaps = construction_proof_gaps(proof_validation)
    proof_contract_blockers = [
        item for item in contract_blockers
        if item.startswith("Verification")
        or "proof contract" in item.lower()
        or "Wired/Running" in item
    ]
    if proof_contract_blockers:
        blockers = "; ".join(proof_contract_blockers[:4])
        return (
            "Planner decision",
            f"load /aiwf-planner for {task_id}; Task.md proof contract is not dispatchable: "
            f"{blockers}. This is a contract defect, not missing construction evidence. Do not "
            "substitute paths. Because the active Task.md is frozen, "
            "ask the user to interrupt and revise the exact contract, sync, then reactivate "
            "the Task",
        )
    if proof_gaps:
        missing = ", ".join(proof_gaps[:5])
        return (
            "Executor",
            f"load /aiwf-implement and complete Executor-owned V evidence for {task_id}: {missing}",
        )
    if control and str(review.get("result") or "unknown") == "unknown":
        return _post_construction_route(
            task, implementation, control, host,
            requirements.get("reviewer_required", True),
        )
    if review.get("result") == "accepted" and not review.get("closure_allowed", False):
        previous = (
            resumable_agent(
                control, task_id=task_id, subagent_type="aiwf-reviewer",
            )
            if control else None
        )
        resume = (
            f"resume aiwf-reviewer {previous['agent_id']} once if available, otherwise "
            if previous else ""
        )
        return (
            "Reviewer reconciliation",
            f"load /aiwf-review; the recorded verdict says accepted but lacks the explicit "
            f"complete-story assertion. {resume}dispatch aiwf-reviewer for {task_id} to "
            "reconcile its REVIEW_REPORT and machine verdict. It must either record accepted "
            "with --story-complete because every required link actually holds, or record the "
            "appropriate non-accepted verdict. The main session must not supply this judgment",
        )
    pending = [
        item for item in review.get("adversarial_observations", []) or []
        if isinstance(item, dict) and item.get("disposition") == "pending"
    ]
    if review.get("result") == "accepted" and pending:
        return (
            "Planner decision",
            f"load /aiwf-planner and disposition {len(pending)} Reviewer observation(s) for {task_id}; "
            "fix an observation now when that is safe, bounded, and verifiable in this cycle; "
            "before choosing deferred, explain why it should wait and its return trigger, ask the "
            "user to agree, then write it into its downstream Task or "
            ".aiwf/memory/notes/deferred-findings.md",
        )
    if review.get("result") != "accepted" or not review.get("closure_allowed", False):
        if requirements.get("reviewer_required", True):
            previous = (
                resumable_agent(
                    control, task_id=task_id, subagent_type="aiwf-reviewer",
                )
                if control else None
            )
            if previous:
                if host == "opencode":
                    return (
                        "Reviewer",
                        f"load /aiwf-review; continue the previous aiwf-reviewer child once "
                        f"with task_id {previous['agent_id']} and tell it to reconcile Task.md, "
                        "the implementation snapshot, experiments, and its report; if continuation is unavailable, "
                        "dispatch a new aiwf-reviewer for the Task",
                    )
                return (
                    "Reviewer",
                    f"load /aiwf-review; if available in this or the resumed original Claude "
                    f"session, try once to resume aiwf-reviewer {previous['agent_id']} with "
                    f"SendMessage: 'Resume {task_id} review. Reconcile Task.md, the implementation "
                    "snapshot, and your report, record review, and return'; if unavailable or "
                    "resume fails, dispatch a new aiwf-reviewer for the Task",
                )
            return "Reviewer", f"load /aiwf-review and dispatch aiwf-reviewer for {task_id}"
        return "Inline review", f"load /aiwf-review, review {task_id} inline, and record it"
    integration_close_mode = ""
    if task.get("kind") == "integration" and reviewed_ref and control:
        try:
            from .git_workflow import integration_close_readiness

            worktree = str(task.get("worktree_path") or control)
            readiness = integration_close_readiness(
                worktree,
                task,
                str(task.get("git_origin_ref") or ""),
                reviewed_ref,
            )
            if readiness.get("status") != "ready":
                return (
                    "Planner decision",
                    f"load /aiwf-planner; {task_id} cannot close because "
                    f"{readiness.get('message')}. Inspect the Git state before changing "
                    "history or rerunning work",
                )
            integration_close_mode = str(readiness.get("mode") or "")
        except Exception as error:
            return (
                "Planner decision",
                f"load /aiwf-planner; {task_id} integration close preflight failed: {error}",
            )
    deferred = [
        item for item in review.get("adversarial_observations", []) or []
        if isinstance(item, dict) and item.get("disposition") == "deferred"
    ]
    if deferred:
        return (
            "Close",
            f"load /aiwf-close; confirm {len(deferred)} deferred Reviewer observation(s) "
            "are written in a downstream Task or .aiwf/memory/notes/deferred-findings.md, "
            f"calibrate Task.md if needed, then close {task_id}",
        )
    if integration_close_mode == "amend_merge":
        return (
            "Close",
            f"load /aiwf-close, calibrate Task.md if needed, then close {task_id}; "
            "close will add the reviewed staged project tree to the existing correct merge commit",
        )
    return "Close", f"load /aiwf-close, calibrate Task.md if needed, then close {task_id}"
