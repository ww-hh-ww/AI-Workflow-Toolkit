"""Plan narrative and governance closure after a project merge."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from .plan_integration_common import find_plan, now
from .state._common import _governance_state_lock
from .state.plan_ops import load_plans, save_plans


def write_plan_closure_doc(control: Path, plan_id: str, summary: str) -> bool:
    from .index_ops import parse_md, sync_index, write_narrative_doc

    doc = control / ".aiwf" / "plans" / f"{plan_id}.md"
    if not doc.exists():
        return False
    frontmatter, body = parse_md(doc)
    if frontmatter is None:
        raise ValueError(f"cannot read Plan document frontmatter: {doc}")
    if (
        str(frontmatter.get("status") or "") == "closed"
        and str(frontmatter.get("closure_summary") or "") == summary
    ):
        return False
    frontmatter["status"] = "closed"
    frontmatter["closure_summary"] = summary
    write_narrative_doc(doc, frontmatter, body)
    sync_index(str(control))
    return True


def plan_closure_summary(control: Path, plan_id: str) -> str:
    from .index_ops import parse_md, read_markdown_section

    doc = control / ".aiwf" / "plans" / f"{plan_id}.md"
    if not doc.exists():
        raise ValueError(f"Plan document not found: {doc}")
    frontmatter, body = parse_md(doc)
    if frontmatter is None:
        raise ValueError(f"cannot read Plan document frontmatter: {doc}")
    calibration = read_markdown_section(body, "Closure Calibration")
    if not calibration:
        raise ValueError(
            "Plan.md needs a non-empty '## Closure Calibration' before an accepted merge"
        )
    summary = " ".join(calibration.split("\n\n", 1)[0].split())
    if not summary:
        raise ValueError("Plan.md Closure Calibration needs a concise outcome paragraph")
    return summary[:1000]


def finish_plan_closure(
    control: Path,
    plan_id: str,
    summary: str,
    merge_commit: str,
    verification_status: str = "passed",
    known_gaps: Optional[List[str]] = None,
    acceptance_reason: str = "",
    merged_to_branch: str = "",
    resolved_conflicts: Optional[List[str]] = None,
) -> Dict[str, Any]:
    write_plan_closure_doc(control, plan_id, summary)
    closure = {
        "mode": "accepted_with_gaps" if verification_status == "accepted_with_gaps" else "normal",
        "accepted": True,
        "summary": summary,
        "merged_commit": merge_commit,
        "merged_to_branch": merged_to_branch,
    }
    if resolved_conflicts:
        closure["resolved_conflicts"] = list(resolved_conflicts)
    if verification_status == "accepted_with_gaps":
        closure["known_gaps"] = list(known_gaps or [])
        closure["acceptance_reason"] = acceptance_reason

    with _governance_state_lock(str(control)):
        data = load_plans(str(control))
        plan = find_plan(data, plan_id)
        if not plan:
            raise ValueError(f"Plan not found while finishing closure: {plan_id}")
        integration = plan.get("integration", {}) or {}
        if (
            str(integration.get("status") or "") != "merged"
            or str(integration.get("merge_commit") or "") != merge_commit
        ):
            raise ValueError("Plan integration record changed before closure finished")
        if plan.get("status") != "closed" or plan.get("closure") != closure:
            plan["status"] = "closed"
            plan.pop("integration_hold_ref", None)
            plan["closure"] = closure
            plan["updated_at"] = now()
            save_plans(str(control), data)

    try:
        from .governance_git import checkpoint_governance

        checkpoint = checkpoint_governance(
            control, reason=f"after Plan integration and close: {plan_id}",
        )
    except ValueError as exc:
        checkpoint = {
            "committed": False, "commit": "", "paths": [], "warning": str(exc),
        }
    return {"plan": plan, "integration": integration, "governance_checkpoint": checkpoint}
