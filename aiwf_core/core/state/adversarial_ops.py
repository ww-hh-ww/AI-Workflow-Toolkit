"""Adversarial observation disposition."""
from __future__ import annotations

from typing import Any, Dict

from ..task_ledger import resolve_active_task_id
from ..task_records import load_task_record, update_task_record

def disposition_adversarial_observation(
    base_dir: str,
    adv_id: str,
    disposition: str,
    reason: str = "",
    disposed_by: str = "planner",
    task_id: str = "",
) -> Dict[str, Any]:
    """Update disposition on a single adversarial observation. Prefer this over direct edit."""
    valid_dispositions = {"accepted", "deferred", "dismissed", "resolved"}
    if disposition not in valid_dispositions:
        raise ValueError(f"invalid disposition: {disposition}. Valid: {', '.join(sorted(valid_dispositions))}")
    if not reason or not reason.strip():
        raise ValueError("disposition reason is required")
    effective_task = resolve_active_task_id(base_dir, task_id)
    if not effective_task:
        raise ValueError("disposition requires an active Task ID or assigned Task worktree")
    review = load_task_record(base_dir, effective_task)["review"]
    obs_list = review.get("adversarial_observations", [])
    if not isinstance(obs_list, list):
        obs_list = []
    found = False
    for obs in obs_list:
        if isinstance(obs, dict) and obs.get("id") == adv_id:
            if obs.get("severity") in ("critical", "high") and disposition != "resolved":
                raise ValueError("CRITICAL/HIGH observations can only be dispositioned as resolved")
            obs["disposition"] = disposition
            obs["disposition_reason"] = reason.strip()
            obs["disposed_by"] = disposed_by
            found = True
            break
    if not found:
        raise ValueError(f"adversarial observation not found: {adv_id}")
    review["adversarial_observations"] = obs_list
    update_task_record(base_dir, effective_task, lambda record: record.update({"review": review}))
    return {"id": adv_id, "disposition": disposition, "found": True}
