"""Record one independent Reviewer judgment."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ._common import BLOCKING_REVIEW_RESULTS


def invalidated_review(task_id: str, previous: Dict[str, Any]) -> Dict[str, Any]:
    """Invalidate the verdict while keeping observations available to Planner."""
    from ..state_schema import default_review

    review = default_review(task_id)
    review["adversarial_observations"] = [
        dict(item)
        for item in (previous.get("adversarial_observations", []) or [])
        if isinstance(item, dict)
    ]
    return review


def _merge_observations(
    previous: List[Dict[str, Any]], current: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    merged = [dict(item) for item in previous if isinstance(item, dict)]
    signatures = {
        (item.get("severity"), item.get("kind"), item.get("message"))
        for item in merged
    }
    next_id = max(
        [
            int(str(item.get("id") or "").removeprefix("ADV-"))
            for item in merged
            if str(item.get("id") or "").removeprefix("ADV-").isdigit()
        ]
        or [0]
    )
    for item in current:
        if not isinstance(item, dict):
            continue
        signature = (item.get("severity"), item.get("kind"), item.get("message"))
        if signature in signatures:
            continue
        next_id += 1
        added = dict(item)
        added["id"] = f"ADV-{next_id:03d}"
        added.setdefault("disposition", "pending")
        merged.append(added)
        signatures.add(signature)
    return merged


def record_review(
    base_dir: str,
    result: str,
    closure_allowed: bool = False,
    blockers: Optional[List[str]] = None,
    adversarial_observations: Optional[List[Dict[str, Any]]] = None,
    cleanup_status: str = "",
    structure_status: str = "",
    summary: str = "",
    experiment_request: Optional[Dict[str, Any]] = None,
    task_id: str = "",
) -> Dict[str, Any]:
    """Validate and replace one Task's review judgment."""
    from ..state_schema import VALID_REVIEW_RESULTS

    if result not in VALID_REVIEW_RESULTS or result == "unknown":
        raise ValueError(f"invalid review result: {result}")

    base = Path(base_dir)
    from ..task_ledger import load_ledger, resolve_active_task_id, update_task_runtime
    from ..task_records import load_task_record, update_task_record
    from ..worktree_context import resolve_control_root, resolve_worktree_root, same_path

    task_id = resolve_active_task_id(base_dir, task_id)
    task_record = load_task_record(base_dir, task_id) if task_id else {}
    implementation = task_record.get("implementation", {}) or {}
    implementation_ref = str(implementation.get("implementation_ref") or "")
    if not task_id:
        raise ValueError("review requires an active Task")
    if implementation.get("task_id") != task_id or not implementation_ref:
        raise ValueError("review requires a current implementation snapshot for the active Task")
    task = next(
        (
            item for item in load_ledger(base_dir).get("tasks", []) or []
            if isinstance(item, dict) and item.get("id") == task_id
        ),
        None,
    )
    if not task:
        raise ValueError(f"active Task not found: {task_id}")
    worktree = str(task.get("worktree_path") or "")
    if not worktree or not same_path(resolve_worktree_root(base), worktree):
        raise ValueError(f"run review in Task {task_id}'s assigned worktree")

    from ..git_snapshots import snapshot_binding

    binding = snapshot_binding(worktree, implementation_ref)
    binding_status = str(binding.get("candidate_tree_status") or "unavailable")
    if not binding.get("implementation_tree"):
        raise ValueError("review implementation_ref is unavailable or invalid")
    if binding_status == "changed":
        raise ValueError(
            "candidate project tree differs from implementation_ref; branch HEAD may "
            "differ from the AIWF hidden snapshot and does not need to be moved. Record "
            "implementation again only for an actual project-tree change"
        )
    if binding_status != "matched":
        from ..project_root import codex_dispatch_markers_advisory

        control = resolve_control_root(base)
        if not codex_dispatch_markers_advisory(control):
            detail = str(binding.get("candidate_tree_error") or "Git tree check failed")
            raise ValueError(
                "candidate freshness is unavailable; review requires a matched tree: "
                + detail
            )
        # A Codex child cannot elevate its fixed sandbox. The stable main Codex
        # task performs and supplies the exact-ref freshness preflight; only this
        # unavailable result is advisory. A detected tree change and an invalid
        # implementation ref remain hard failures above.
    from ..task_proof import construction_proof_gaps, validate_implementation_against_task

    proof = validate_implementation_against_task(base_dir, task, implementation)
    gaps = construction_proof_gaps(proof)
    if gaps:
        raise ValueError("review requires complete Executor V evidence: " + "; ".join(gaps[:8]))
    from ..experiment_records import live_experiments, pending_experiment_dispositions

    empirical_work = live_experiments(base_dir, task_id)
    if empirical_work:
        item = empirical_work[0]
        raise ValueError(
            "review requires empirical work to be recorded and disposed first: "
            f"{item.get('experiment_id')} is {item.get('status')}"
        )
    empirical_decisions = pending_experiment_dispositions(base_dir, task_id=task_id)
    if empirical_decisions:
        raise ValueError(
            "review requires Planner disposition of planning experiment: "
            f"{empirical_decisions[0].get('experiment_id')}"
        )
    if result == "accepted" and not closure_allowed:
        raise ValueError(
            "accepted requires an explicit complete-story assertion"
        )
    if result != "accepted" and closure_allowed:
        raise ValueError("only accepted review can assert a complete story")

    observations = _merge_observations(
        list((task_record.get("review", {}) or {}).get("adversarial_observations", []) or []),
        list(adversarial_observations or []),
    )
    unresolved_high = [
        item for item in observations
        if (
            isinstance(item, dict)
            and item.get("severity") in ("critical", "high")
            and item.get("disposition") != "resolved"
        )
    ]
    if result == "accepted" and unresolved_high:
        raise ValueError("critical/high observations cannot be accepted")

    experiment_payload: Dict[str, str] = {}
    if result == "needs_experiment":
        request = experiment_request or {}
        experiment_payload = {
            "experiment_id": str(request.get("experiment_id") or "").strip(),
            "question": " ".join(str(request.get("question") or "").split()),
            "hypothesis": " ".join(str(request.get("hypothesis") or "").split()),
        }
        from ..experiment_records import experiment_record_path

        experiment_path = experiment_record_path(
            base_dir, experiment_payload["experiment_id"],
        )
        if not experiment_payload["question"]:
            raise ValueError("needs_experiment requires an empirical question")
        if experiment_path.exists():
            raise ValueError(
                f"experiment already exists: {experiment_payload['experiment_id']}"
            )

    from ..index_ops import remove_narrative_section

    task_doc = resolve_control_root(base) / ".aiwf" / "tasks" / f"{task_id}.md"
    remove_narrative_section(task_doc, "Closure Calibration")

    review: Dict[str, Any] = {
        "task_id": task_id,
        "result": result,
        "closure_allowed": result == "accepted" and bool(closure_allowed),
        "blockers": list(blockers or []),
        "summary": summary.strip() or f"review result={result}",
        "reviewed_ref": implementation_ref,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    if observations:
        review["adversarial_observations"] = observations
    if result == "accepted":
        review["cleanup_status"] = cleanup_status or "fresh"
        review["structure_status"] = structure_status or "sound"
    else:
        if cleanup_status:
            review["cleanup_status"] = cleanup_status
        if structure_status:
            review["structure_status"] = structure_status
    def store(record: Dict[str, Any]) -> None:
        record["review"] = review
        fix_loop = record.get("fix_loop", {}) or {}
        if result == "accepted" and fix_loop.get("status") == "open" and fix_loop.get("route") == "reviewer":
            fix_loop["status"] = "resolved"
            fix_loop["resolution"] = review["summary"]
            fix_loop["source"] = "reviewer"
            record["fix_loop"] = fix_loop

    update_task_record(base_dir, task_id, store)
    update_task_runtime(base_dir, task_id, phase="closing")

    if result == "needs_experiment":
        from ..experiment_records import open_experiment

        open_experiment(
            base_dir,
            experiment_payload["experiment_id"],
            experiment_payload["question"],
            hypothesis=experiment_payload["hypothesis"],
            task_id=task_id,
            subject_ref=implementation_ref,
            timing="post_implementation",
        )
        update_task_runtime(base_dir, task_id, phase="reviewing")

    if result in BLOCKING_REVIEW_RESULTS:
        current = (load_task_record(base_dir, task_id).get("fix_loop", {}) or {})
        route = "executor" if result == "needs_change" else "planner"
        if not (current.get("status") == "open" and current.get("route") == route):
            from .fixloop_ops import open_fix_loop

            open_fix_loop(
                base_dir,
                route=route,
                reason=review["summary"],
                required_fixes=review["blockers"],
                source="reviewer",
                task_id=task_id,
            )
    return review
