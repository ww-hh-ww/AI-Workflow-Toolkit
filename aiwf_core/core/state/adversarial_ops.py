"""Adversarial observation disposition."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ._common import _execution_contract_frozen, _freeze_explanation, _read, _write

def disposition_adversarial_observation(
    base_dir: str,
    adv_id: str,
    disposition: str,
    reason: str = "",
    disposed_by: str = "planner",
) -> Dict[str, Any]:
    """Update disposition on a single adversarial observation. Prefer this over direct edit."""
    valid_dispositions = {"ignored", "accepted", "deferred", "brief_updated"}
    if disposition not in valid_dispositions:
        raise ValueError(f"invalid disposition: {disposition}. Valid: {', '.join(sorted(valid_dispositions))}")
    if not reason or not reason.strip():
        raise ValueError("disposition reason is required")
    base = Path(base_dir)
    review_path = base / ".aiwf" / "artifacts" / "quality" / "review.json"
    review = _read(review_path)
    obs_list = review.get("adversarial_observations", [])
    if not isinstance(obs_list, list):
        obs_list = []
    found = False
    for obs in obs_list:
        if isinstance(obs, dict) and obs.get("id") == adv_id:
            obs["disposition"] = disposition
            obs["disposition_reason"] = reason.strip()
            obs["disposed_by"] = disposed_by
            found = True
            break
    if not found:
        raise ValueError(f"adversarial observation not found: {adv_id}")
    review["adversarial_observations"] = obs_list
    _write(review_path, review)
    return {"id": adv_id, "disposition": disposition, "found": True}

