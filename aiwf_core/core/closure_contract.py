"""Backend-neutral closure contract.

Defines closure gate conditions and how they are evaluated.
No Claude-specific logic.
"""
from __future__ import annotations

from typing import Any, Dict, List

def closure_conditions_met(
    state: Dict[str, Any],
    implementation: Dict[str, Any],
    testing: Dict[str, Any],
    review: Dict[str, Any],
    fix_loop: Dict[str, Any],
) -> Dict[str, Any]:
    """Keep Claude from stopping after review but before the active task closes."""
    closing_task = state.get("phase") == "closing" and bool(state.get("active_task_id"))
    blockers = []
    missing = []

    if closing_task:
        if fix_loop.get("status") == "open":
            blockers.append("fix-loop is open — resolve or escalate before closing")
            missing.append("fix-loop")
        blockers.append(
            "active task is in closing; run aiwf status --prompt and follow its route before stopping"
        )
        missing.append("task_close")

    if closing_task:
        if not implementation.get("implementation_ref") and not testing.get("based_on_ref"):
            blockers.append("implementation not recorded")
            missing.append("implementation")

        tstat = testing.get("status", "missing")
        if tstat == "missing":
            blockers.append("testing not recorded")
            missing.append("testing")
        elif tstat not in ("passed", "adequate"):
            blockers.append(f"testing status is '{tstat}', not passed/adequate")
            missing.append("testing")

        rstat = review.get("result", "unknown")
        if rstat == "unknown":
            blockers.append("review not recorded")
            missing.append("review")
        elif rstat != "accepted":
            blockers.append(f"review result is '{rstat}', not accepted")
            missing.append("review")

        if rstat == "accepted" and not review.get("closure_allowed", False):
            blockers.append("review closure_allowed is false")
            missing.append("review")

        tested_ref = str(testing.get("tested_ref") or "")
        reviewed_ref = str(review.get("reviewed_ref") or "")
        if not tested_ref:
            blockers.append("tested snapshot is missing")
            missing.append("testing")
        elif reviewed_ref != tested_ref:
            blockers.append("review does not match the tested snapshot")
            missing.append("review")

        pending = [
            item for item in review.get("adversarial_observations", []) or []
            if isinstance(item, dict) and item.get("disposition") == "pending"
        ]
        if pending:
            blockers.append(f"{len(pending)} reviewer observation(s) need Planner disposition")
            missing.append("review")

    if not closing_task and not blockers:
        return {"passed": False, "blockers": [], "missing": []}

    passed = not bool(blockers)

    return {
        "passed": passed,
        "blockers": blockers,
        "missing": missing,
    }
