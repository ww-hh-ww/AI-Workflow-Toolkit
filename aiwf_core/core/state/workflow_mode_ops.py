"""Workflow mode operations — record_quality_policy."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ._common import _execution_contract_frozen, _freeze_explanation, _read, _write

def record_quality_policy(
    base_dir: str,
    task_type: str,
    workflow_level: str,
    risk_flags: Optional[List[str]] = None,
    routing_reason: str = "",
) -> Dict[str, Any]:
    """Select quality policy and write short keys to state.json. No template fulltext."""
    base = Path(base_dir)
    state_path = base / ".aiwf" / "state" / "state.json"

    state = _read(state_path)
    current_level = state.get("workflow_level", "L1_review_light")
    protected_cycle = _execution_contract_frozen(base, state)
    if (
        protected_cycle
        and current_level in WORKFLOW_LEVELS
        and workflow_level in WORKFLOW_LEVELS
        and WORKFLOW_LEVELS.index(workflow_level) < WORKFLOW_LEVELS.index(current_level)
    ):
        raise ValueError(
            f"cannot lower workflow level from {current_level} to {workflow_level}; "
            f"{_freeze_explanation(base, state)}"
        )

    from ..quality_policy import select_quality_policy
    policy = select_quality_policy(task_type, workflow_level, risk_flags, routing_reason)

    state["task_type"] = task_type
    state["workflow_level"] = workflow_level
    state["risk_flags"] = risk_flags or []
    state["test_template"] = policy["test_template"]
    state["review_template"] = policy["review_template"]
    state["exploration_budget"] = policy["exploration_budget"]
    state["asset_policy"] = policy["asset_policy"]
    state["cleanup_policy"] = policy["cleanup_policy"]
    state["git_policy"] = policy["git_policy"]
    state["quality_policy_reason"] = routing_reason
    state["recommended_minimum_level"] = policy.get("recommended_minimum_level", "")
    state["requires_user_decision"] = policy.get("requires_user_decision", False)
    # Detect escalation: recommended level higher than current
    levels = ["L0_direct", "L1_review_light", "L2_standard_team", "L3_full_power"]
    rec_idx = levels.index(policy["recommended_minimum_level"]) if policy.get("recommended_minimum_level") in levels else -1
    cur_idx = levels.index(workflow_level) if workflow_level in levels else 0
    esc_required = (rec_idx > cur_idx)
    # Hard safety net: destructive/migration/deploy tasks cannot stay below L3.
    # security_sensitive -> adversarial review forced, but does NOT force L3.
    if task_type == "security_sensitive" or "security_sensitive" in (risk_flags or []):
        state["adversarial_mode"] = True
        if state.get("review_template") in ("review_lite", "reviewer_light", ""):
            state["review_template"] = "standard_review"
    hard_l3_types = {"data_migration", "destructive_command", "publish_or_deploy"}
    hard_l3_flags = set(risk_flags or []) & hard_l3_types
    # Auto-detect destructive intent from goal text (crude but effective)
    goal_data = _read(base / ".aiwf" / "state" / "goal.json")
    goal_text = (goal_data.get("current_goal") or goal_data.get("active_goal") or "").lower()
    destructive_keywords = [
        "purge", "delete all", "wipe", "clear all", "drop all",
        "remove all", "truncate", "destroy", "nuke"
    ]
    # Auto-detect crypto from goal text (must be after goal_text is read)
    crypto_keywords = ["encrypt", "decrypt", "crypto", "cipher", "AES", "password manager", "key derivation", "Argon2", "Fernet"]
    if any(kw.lower() in goal_text for kw in crypto_keywords):
        state["adversarial_mode"] = True
        if state.get("review_template") in ("review_lite", "reviewer_light", ""):
            state["review_template"] = "standard_review"
    if any(kw in goal_text for kw in destructive_keywords):
        hard_l3_flags.add("destructive_command")
    if (task_type in hard_l3_types or hard_l3_flags) and workflow_level != "L3_full_power":
        esc_required = True
        trigger = task_type if task_type in hard_l3_types else ", ".join(hard_l3_flags)
        state["quality_escalation_required"] = True
        state["quality_escalation_reason"] = f"safety net: {trigger} requires L3_full_power"
        state["recommended_minimum_level"] = "L3_full_power"
        rec_idx = levels.index("L3_full_power")

    # L0 guard: multi-file or complex task types require at least L1
    if workflow_level == "L0_direct" and not esc_required:
        l0_escalations = []
        if task_type in ("refactor", "api_endpoint", "bug_fix", "numeric_semantics"):
            l0_escalations.append(f"task_type '{task_type}' requires at least L1_review_light")
        if risk_flags:
            l0_escalations.append(f"risk flags present: {risk_flags}")
        if l0_escalations:
            esc_required = True
            state["quality_escalation_required"] = True
            state["quality_escalation_reason"] = "; ".join(l0_escalations)
            state["recommended_minimum_level"] = "L1_review_light"
    state["quality_escalation_required"] = esc_required
    policy_reason = "; ".join(policy.get("level_escalations_applied", [])[:3])
    if policy_reason and not state.get("quality_escalation_reason"):
        state["quality_escalation_reason"] = policy_reason
    if policy.get("level_escalations_applied"):
        hist = state.get("escalation_history", []) or []
        for e in policy["level_escalations_applied"]:
            if e not in hist: hist.append(e)
        state["escalation_history"] = hist

    # Gravity escalation: pure read + explicit state mutation at this write boundary.
    try:
        from ..task_gravity import apply_gravity_to_state
        state = apply_gravity_to_state(base_dir, state)
    except Exception:
        pass

    _write(state_path, state)
    return policy
