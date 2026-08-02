"""Verify, merge, and close one prepared Plan candidate."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from .git_snapshots import ref_tree
from .plan_integration_audit import integration_audit
from .plan_integration_checks import basic_blockers
from .plan_integration_closure import finish_plan_closure, plan_closure_summary
from .plan_integration_common import find_plan, now
from .plan_integration_git import (
    git_operation, is_ancestor, require_git, resolve_ref, run_git,
)
from .state._common import _governance_state_lock
from .state.plan_ops import load_plans, save_plans
from .worktree_context import resolve_control_root


def finish_plan_integration(
    base_dir: str,
    plan_id: str,
    status: str,
    commands: List[str],
    verification_results: List[Dict[str, Any]],
    summary: str,
    known_gaps: Optional[List[str]] = None,
    acceptance_reason: str = "",
) -> Dict[str, Any]:
    """Record proof, merge an accepted candidate, and close its Plan."""
    merge_statuses = {"passed", "accepted_with_gaps"}
    if status not in merge_statuses | {"failed"}:
        raise ValueError(
            "integration status must be passed, failed, or accepted_with_gaps"
        )
    if not commands:
        raise ValueError("integration proof requires at least one exact command")
    if len(verification_results) == len(commands):
        verification_results = [
            {**item, "command": command}
            for command, item in zip(commands, verification_results)
        ]
    normalized_gaps = list(dict.fromkeys(
        " ".join(str(gap).split())
        for gap in (known_gaps or [])
        if str(gap).strip()
    ))
    normalized_acceptance_reason = " ".join(str(acceptance_reason or "").split())
    normalized_commands = {" ".join(command.split()) for command in commands if command.strip()}
    matched_commands = {
        " ".join(str(item.get("command") or "").split())
        for item in verification_results
        if item.get("matched") and str(item.get("observed") or "").strip()
    }
    if status == "passed" and normalized_commands - matched_commands:
        raise ValueError(
            "passed integration requires a matched expected/observed result for every command"
        )
    observed_commands = {
        " ".join(str(item.get("command") or "").split())
        for item in verification_results
        if (
            str(item.get("observed") or "").strip()
            and isinstance(item.get("matched"), bool)
        )
    }
    if status == "accepted_with_gaps":
        if not normalized_gaps:
            raise ValueError("accepted_with_gaps requires at least one --known-gap")
        if not normalized_acceptance_reason:
            raise ValueError(
                "accepted_with_gaps requires --acceptance-reason from the explicit user decision"
            )
        if normalized_commands - observed_commands:
            raise ValueError(
                "accepted_with_gaps requires an observed verification result and "
                "match decision for every command"
            )

    control = resolve_control_root(base_dir)
    merge_commit = ""
    if status in merge_statuses:
        closure_summary = plan_closure_summary(control, plan_id)
    else:
        closure_summary = summary.strip()[:1000]
        if not closure_summary:
            raise ValueError("failed integration requires a concise failure summary")
    with _governance_state_lock(str(control)):
        data = load_plans(str(control))
        plan = find_plan(data, plan_id)
        if not plan:
            raise ValueError(f"Plan not found: {plan_id}")
        integration = plan.get("integration", {}) or {}
        if (
            status in merge_statuses
            and str(integration.get("status") or "") == "merged"
            and str(integration.get("merge_commit") or "")
        ):
            recorded_status = str(integration.get("verification_status") or "passed")
            if recorded_status != status:
                raise ValueError(
                    f"recorded Plan merge used {recorded_status}; rerun closure with that same status"
                )
            if status == "accepted_with_gaps":
                if (
                    list(integration.get("known_gaps", []) or []) != normalized_gaps
                    or str(integration.get("acceptance_reason") or "")
                    != normalized_acceptance_reason
                ):
                    raise ValueError(
                        "rerun accepted_with_gaps closure with the same known gaps "
                        "and acceptance reason recorded by the merge"
                    )
            merge_commit = str(integration["merge_commit"])
            base_branch = str(plan.get("git_base_branch") or "")
            if not is_ancestor(control, merge_commit, resolve_ref(control, base_branch)):
                raise ValueError("recorded Plan merge commit is not present on its base branch")
            closure_summary = str(
                ((plan.get("closure") or {}).get("summary"))
                or integration.get("summary") or closure_summary
            )
        else:
            blockers = basic_blockers(control, plan)
            if blockers:
                raise ValueError("; ".join(blockers))
            if integration.get("status") not in ("prepared", "failed"):
                raise ValueError("prepare this Plan with 'aiwf plan integrate' before recording proof")

            worktree = Path(str(plan["git_worktree_path"]))
            audit = integration_audit(control, worktree)
            if not audit["clean_for_candidate"]:
                raise ValueError(
                    "integration audit changed after candidate preparation: "
                    + "; ".join(audit["blocking"])
                    + ". Resolve it and run 'aiwf plan integrate' again"
                )
            candidate_ref = str(integration.get("candidate_ref") or "")
            base_ref = str(integration.get("base_ref") or "")
            current_base = resolve_ref(control, str(plan.get("git_base_branch") or ""))
            current_plan = resolve_ref(worktree, str(plan.get("git_branch") or ""))
            recovered_merge = False
            if current_base != base_ref:
                parents = require_git(control, "show", "-s", "--format=%P", current_base).split()
                recovered_merge = (
                    status in merge_statuses
                    and parents == [base_ref, candidate_ref]
                    and ref_tree(str(control), current_base)
                    == str(integration.get("candidate_tree") or "")
                )
                if not recovered_merge:
                    raise ValueError(
                        "base branch changed after preparation; run 'aiwf plan integrate' again"
                    )
            if current_plan != str(plan.get("git_head_ref") or ""):
                raise ValueError(
                    "Plan branch changed after preparation; the candidate is stale. "
                    "Run 'aiwf plan integrate' again before recording proof"
                )
            if not is_ancestor(control, str(integration.get("plan_ref") or ""), candidate_ref):
                raise ValueError("prepared candidate no longer contains the reviewed Plan result")

            integration.update({
                "status": status,
                "verification_status": status,
                "commands": list(dict.fromkeys(commands)),
                "verification_results": verification_results,
                "summary": closure_summary,
                "verified_at": now(),
            })
            if status == "accepted_with_gaps":
                integration["known_gaps"] = normalized_gaps
                integration["acceptance_reason"] = normalized_acceptance_reason
            else:
                integration.pop("known_gaps", None)
                integration.pop("acceptance_reason", None)
            plan["integration"] = integration
            plan["updated_at"] = now()
            if status == "failed":
                save_plans(str(control), data)
                return {"merged": False, "closed": False, "plan": plan, "integration": integration}

            if recovered_merge:
                merge_commit = current_base
            elif is_ancestor(control, candidate_ref, current_base):
                merge_commit = current_base
            else:
                merge = run_git(control, "merge", "--no-ff", "--no-commit", candidate_ref)
                if merge.returncode != 0:
                    if git_operation(control) == "merge":
                        run_git(control, "merge", "--abort")
                    raise ValueError(
                        merge.stderr.strip() or merge.stdout.strip() or "Plan merge failed"
                    )
                staged_tree = require_git(control, "write-tree")
                if staged_tree != str(integration.get("candidate_tree") or ""):
                    run_git(control, "merge", "--abort")
                    raise ValueError(
                        "base changed while integrating; the unverified merge was aborted"
                    )
                commit = run_git(
                    control, "commit", "-m",
                    f"Merge {plan_id}: {plan.get('title_cache') or plan.get('title') or plan_id}",
                )
                if commit.returncode != 0:
                    if git_operation(control) == "merge":
                        run_git(control, "merge", "--abort")
                    raise ValueError(
                        commit.stderr.strip() or commit.stdout.strip() or "Plan merge commit failed"
                    )
                merge_commit = require_git(control, "rev-parse", "HEAD")
            if ref_tree(str(control), merge_commit) != str(integration.get("candidate_tree") or ""):
                raise ValueError("merged base tree differs from the verified integration candidate")

            integration.update({
                "status": "merged", "merge_commit": merge_commit, "merged_at": now(),
            })
            plan["integration"] = integration
            plan["closure"] = {
                "mode": "accepted_with_gaps" if status == "accepted_with_gaps" else "normal",
                "accepted": True,
                "summary": closure_summary,
                "merged_commit": merge_commit,
                "merged_to_branch": str(plan.get("git_base_branch") or ""),
            }
            resolved_conflicts = list(integration.get("resolved_conflicts", []) or [])
            if resolved_conflicts:
                plan["closure"]["resolved_conflicts"] = resolved_conflicts
            if status == "accepted_with_gaps":
                plan["closure"]["known_gaps"] = normalized_gaps
                plan["closure"]["acceptance_reason"] = normalized_acceptance_reason
            plan["updated_at"] = now()
            save_plans(str(control), data)

    try:
        closed = finish_plan_closure(
            control, plan_id, closure_summary, merge_commit,
            verification_status=status,
            known_gaps=normalized_gaps,
            acceptance_reason=normalized_acceptance_reason,
            merged_to_branch=str(plan.get("git_base_branch") or ""),
            resolved_conflicts=list(integration.get("resolved_conflicts", []) or []),
        )
    except Exception as exc:
        raise ValueError(
            "Plan project merge succeeded but governance closure is incomplete. "
            f"Rerun the same 'aiwf plan integrate --status {status}' command to finish it: {exc}"
        ) from exc
    return {
        "merged": True,
        "closed": True,
        "plan": closed["plan"],
        "integration": closed["integration"],
        "governance_checkpoint": closed["governance_checkpoint"],
    }
