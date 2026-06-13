"""Day-1 Foundation Tree — Planner bootstrap validation (Stage 4.5).

Validates a Foundation Tree proposal against structural rules.
Read-only advisory. Never mutates state. Never creates goals/plans/tasks.

Planner proposes → machine validates → human reviews → then manually create structure."""

from __future__ import annotations

from typing import Any, Dict, List


VALID_RELATIONS = {"extends", "implements", "decomposes"}
MAX_FIRST_LEVEL = 7
MIN_FIRST_LEVEL = 1


def validate_foundation_tree(foundation: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a Day-1 Foundation Tree proposal.

    Checks structural rules only — does NOT check whether referenced IDs
    actually exist in goals.json/plans.json (since this is pre-creation).

    Returns: {valid, issues, warnings, foundation_summary}
    """
    issues: List[str] = []
    warnings: List[str] = []

    # ── Root Goal ──
    root = foundation.get("root_goal") or {}
    if not root or not isinstance(root, dict):
        issues.append("root_goal is required")
    else:
        if not root.get("id"):
            issues.append("root_goal.id is required")
        if not root.get("title"):
            issues.append("root_goal.title is required")
        if not root.get("intent"):
            warnings.append("root_goal.intent is empty — root should have a clear purpose")

    # ── First-level Goals ──
    fl_goals = foundation.get("first_level_goals") or []
    if not isinstance(fl_goals, list):
        issues.append("first_level_goals must be a list")
        fl_goals = []

    fl_count = len(fl_goals)
    if fl_count == 0:
        issues.append("first_level_goals must have at least 1 entry")
    elif fl_count == 1:
        warnings.append("first_level_goals has only 1 entry — minimal decomposition. Verify the tree is sufficiently differentiated.")
    elif 2 <= fl_count <= 5:
        pass  # healthy range
    elif 6 <= fl_count <= 7:
        warnings.append(f"first_level_goals has {fl_count} entries — at the upper end. Ensure each goal is a distinct functional domain.")
    elif fl_count > 7:
        warnings.append(
            f"first_level_goals has {fl_count} entries (max recommended: 7). "
            f"Too many first-level goals suggest the tree is over-decomposed."
        )

    fl_ids = set()
    for i, g in enumerate(fl_goals):
        gid = g.get("id", "")
        if not gid:
            issues.append(f"first_level_goals[{i}]: id is required")
        elif gid in fl_ids:
            issues.append(f"first_level_goals[{i}]: duplicate id '{gid}'")
        else:
            fl_ids.add(gid)
        if not g.get("title"):
            issues.append(f"first_level_goals[{i}] '{gid}': title is required")
        if not g.get("intent"):
            warnings.append(f"first_level_goals[{i}] '{gid}': intent is empty")
        rel = g.get("relation_to_root", "")
        if rel and rel not in VALID_RELATIONS:
            issues.append(
                f"first_level_goals[{i}] '{gid}': invalid relation_to_root '{rel}'. "
                f"Must be one of: {', '.join(sorted(VALID_RELATIONS))}"
            )

    # Collect all declared IDs for active_path validation
    all_declared_ids = {"GOAL-ROOT"}
    if root and root.get("id"):
        all_declared_ids.add(root["id"])
    all_declared_ids.update(fl_ids)

    # ── Structural Plan ──
    s_plan = foundation.get("structural_plan") or {}
    if not s_plan or not isinstance(s_plan, dict):
        issues.append("structural_plan is required")
    else:
        spid = s_plan.get("plan_id", "")
        if not spid:
            issues.append("structural_plan.plan_id is required")
        else:
            all_declared_ids.add(spid)

        if s_plan.get("plan_kind") != "structural":
            issues.append("structural_plan.plan_kind must be 'structural'")
        ap = s_plan.get("active_phase", "")
        if ap not in ("framing", "implementation"):
            issues.append(
                f"structural_plan.active_phase must be 'framing' or 'implementation', got '{ap}'"
            )
        if not s_plan.get("purpose"):
            warnings.append("structural_plan.purpose is empty")

        # target_goal_id must reference a declared goal (root or first-level)
        sp_tgid = s_plan.get("target_goal_id", "")
        if sp_tgid:
            if sp_tgid not in all_declared_ids:
                issues.append(
                    f"structural_plan.target_goal_id '{sp_tgid}' references "
                    f"an undeclared goal. Declared: {sorted(all_declared_ids)}"
                )

        # Interfaces
        interfaces = s_plan.get("interfaces") or []
        if not isinstance(interfaces, list) or len(interfaces) == 0:
            issues.append("structural_plan must have at least 1 interface")
        else:
            for j, iface in enumerate(interfaces):
                if not iface.get("owner"):
                    issues.append(f"structural_plan.interfaces[{j}]: owner is required")
                if not iface.get("description"):
                    issues.append(f"structural_plan.interfaces[{j}]: description is required")
                consumers = iface.get("consumers") or []
                for c in consumers:
                    if c not in all_declared_ids:
                        warnings.append(
                            f"structural_plan.interfaces[{j}].consumers references "
                            f"'{c}' which is not a declared goal/plan ID"
                        )

    # ── Active Path ──
    active_path = foundation.get("active_path") or {}
    if not active_path or not isinstance(active_path, dict):
        issues.append("active_path is required")
    else:
        seq = active_path.get("sequence") or []
        if not seq:
            issues.append("active_path.sequence must have at least 1 entry")
        else:
            for k, ref_id in enumerate(seq):
                if ref_id not in all_declared_ids:
                    issues.append(
                        f"active_path.sequence[{k}] '{ref_id}' references "
                        f"an undeclared goal/plan. Declared IDs: {sorted(all_declared_ids)}"
                    )

        if not active_path.get("reason"):
            warnings.append("active_path.reason is empty — why start here?")

    # ── Temporary Roots ──
    tmp_roots = foundation.get("temporary_roots") or []
    if isinstance(tmp_roots, list):
        for i, tr in enumerate(tmp_roots):
            if not tr.get("title"):
                issues.append(f"temporary_roots[{i}]: title is required")
            if not tr.get("reason"):
                warnings.append(f"temporary_roots[{i}] '{tr.get('title','')}': reason is empty")
            if not tr.get("resolution_criterion"):
                warnings.append(
                    f"temporary_roots[{i}] '{tr.get('title','')}': "
                    f"no resolution_criterion — what would clarify ownership?"
                )

    # ── Evidence Rollup Policy ──
    erp = foundation.get("evidence_rollup_policy") or {}
    if not erp or not isinstance(erp, dict):
        issues.append("evidence_rollup_policy is required")
    else:
        if not erp.get("task_to_plan"):
            issues.append("evidence_rollup_policy.task_to_plan is required")
        if not erp.get("plan_to_goal"):
            issues.append("evidence_rollup_policy.plan_to_goal is required")

    # ── Initial Milestone (optional) ──
    ms = foundation.get("initial_milestone") or {}
    if ms and isinstance(ms, dict):
        if not ms.get("title"):
            warnings.append("initial_milestone.title is empty")
        ac = ms.get("acceptance_criteria") or []
        if not ac:
            warnings.append("initial_milestone has no acceptance_criteria")
        covers = ms.get("covers") or []
        for ref in covers:
            if ref not in all_declared_ids:
                warnings.append(
                    f"initial_milestone.covers references '{ref}' which is not "
                    f"a declared goal/plan ID"
                )

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
        "summary": _build_foundation_summary(foundation, issues, warnings),
    }


def _build_foundation_summary(foundation: Dict[str, Any],
                               issues: List[str],
                               warnings: List[str]) -> Dict[str, Any]:
    """Build a structural summary of the foundation tree for review."""
    root = foundation.get("root_goal") or {}
    fl_goals = foundation.get("first_level_goals") or []
    s_plan = foundation.get("structural_plan") or {}
    active_path = foundation.get("active_path") or {}
    tmp_roots = foundation.get("temporary_roots") or []
    erp = foundation.get("evidence_rollup_policy") or {}
    ms = foundation.get("initial_milestone") or {}

    return {
        "project_title": foundation.get("project_title", ""),
        "root_goal_id": root.get("id", ""),
        "root_goal_title": root.get("title", ""),
        "first_level_count": len(fl_goals),
        "first_level_ids": [g.get("id", "") for g in fl_goals],
        "has_structural_plan": bool(s_plan and s_plan.get("plan_id")),
        "structural_plan_id": s_plan.get("plan_id", ""),
        "structural_plan_phase": s_plan.get("active_phase", ""),
        "interface_count": len(s_plan.get("interfaces", []) or []),
        "active_path_length": len(active_path.get("sequence", []) or []),
        "temporary_root_count": len(tmp_roots),
        "has_evidence_policy": bool(erp and erp.get("task_to_plan")),
        "has_milestone": bool(ms and ms.get("title")),
        "issue_count": len(issues),
        "warning_count": len(warnings),
    }
