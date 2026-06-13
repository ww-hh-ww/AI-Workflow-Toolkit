"""Execution Frontier — semantic dispatch validation and Work Packet preparation (Stage 4.7).

Stage 4.7.4: Work Intent Discipline integrated into frontier validation and Work Packet prep.

Read-only module. Never mutates state.

Planner decides frontier semantically.
AIWF validates frontier structurally.
AIWF prepares Work Packet.
Agents consume Work Packet.
No automatic scheduling. No automatic execution. No weight-based ranking.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List


def _resolve_work_intent(explicit: str, plan_kind: str) -> str:
    from .work_intent_rules import resolve_work_intent
    return resolve_work_intent(explicit, plan_kind)


# Allowed enumerations
VALID_FRONTIER_TYPES = {
    "execute_plan", "verify_plan", "review_plan",
    "integrate_goal", "architect_structure", "explore_temporary_root",
}
VALID_DISPATCH_TARGETS = {"executor", "tester", "reviewer", "architect", "planner"}
VALID_CONFIDENCE_LEVELS = {"low", "medium", "high"}
VALID_ACTIVE_PHASES = {"framing", "implementation", "integration", "seal"}
VALID_PLAN_KINDS = {"structural", "implementation", "verification", "migration", "exploration"}


def _read_json(file_path: Path) -> Dict[str, Any]:
    import json
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.loads(f.read())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _validate_goal_exists(base_dir: str, goal_id: str,
                          issues: List[str], warnings: List[str]) -> None:
    """Check that goal_id exists in goals.json."""
    data = _read_json(Path(base_dir) / ".aiwf" / "state" / "goals.json")
    goals = data.get("goals", [])
    if not goals:
        warnings.append(
            f"goals.json is empty; target_goal_id '{goal_id}' cannot be verified. "
            f"Create a root Goal first."
        )
        return
    goal_ids = {g.get("id", "") for g in goals}
    if goal_id not in goal_ids:
        # Special case: GOAL-001 is the bootstrap root id for a new goal registry.
        if goal_id == "GOAL-001" and not goals:
            warnings.append(
                "goals.json is empty; GOAL-001 will be created as the first root Goal."
            )
        else:
            issues.append(
                f"target_goal_id '{goal_id}' not found in goals.json. "
                f"Existing goals: {', '.join(sorted(goal_ids)) or '(none)'}"
            )


def _get_plan_kind_from_registry(base_dir: str, plan_id: str) -> str:
    """Read plan_kind from plans.json registry. Returns '' if not found."""
    data = _read_json(Path(base_dir) / ".aiwf" / "state" / "plans.json")
    for plan in data.get("plans", []):
        if plan.get("id") == plan_id:
            return plan.get("kind", plan.get("plan_kind", ""))
    return ""


def _get_plan_target_goal(base_dir: str, plan_id: str) -> str:
    """Read target_goal_id from plans.json. Returns '' if not found."""
    data = _read_json(Path(base_dir) / ".aiwf" / "state" / "plans.json")
    for plan in data.get("plans", []):
        if plan.get("id") == plan_id:
            return plan.get("target_goal_id", "")
    return ""


def _get_goal_title(base_dir: str, goal_id: str) -> str:
    """Read goal title from goals.json. Returns '' if not found."""
    data = _read_json(Path(base_dir) / ".aiwf" / "state" / "goals.json")
    for goal in data.get("goals", []):
        if goal.get("id") == goal_id:
            return goal.get("title", "")
    return ""


def _has_children_or_plans(base_dir: str, goal_id: str) -> bool:
    """Check if a Goal has child goals or attached plans."""
    data = _read_json(Path(base_dir) / ".aiwf" / "state" / "goals.json")
    for goal in data.get("goals", []):
        if goal.get("id") == goal_id:
            children = goal.get("child_goal_ids", []) or []
            plans = goal.get("attached_plan_ids", []) or []
            return bool(children) or bool(plans)
    return False


# ═══════════════════════════════════════════════════════════════════════════════
# Stage 4.7B: Frontier Decision Validation
# ═══════════════════════════════════════════════════════════════════════════════

def validate_frontier_decision(base_dir: str,
                                decision: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a Frontier Decision against structural constraints.

    MACHINE validator only — checks field presence, reference integrity,
    and constraint coherence. Makes NO semantic judgment about whether the
    frontier choice is "correct."

    Args:
        base_dir: Project root directory.
        decision: A dict matching the Frontier Decision schema.

    Returns:
        {valid: bool, issues: [...], warnings: [...]}
    """
    issues: List[str] = []
    warnings: List[str] = []

    ft = str(decision.get("frontier_type") or "")
    dt = str(decision.get("dispatch_to") or "")
    reason = str(decision.get("reason") or "")
    confidence = str(decision.get("confidence") or "medium")
    selected_plan_id = str(decision.get("selected_plan_id") or "")
    target_goal_id = str(decision.get("target_goal_id") or "")
    expected_evidence = decision.get("expected_evidence", []) or []
    review_focus = decision.get("review_focus", []) or []
    interfaces = decision.get("interfaces", []) or []
    constraints = decision.get("constraints", []) or []
    scope = str(decision.get("scope") or "")
    rollup_target = str(decision.get("rollup_target") or "")

    # ── Universal checks ──

    if ft not in VALID_FRONTIER_TYPES:
        issues.append(
            f"invalid frontier_type: '{ft}'. "
            f"Must be one of: {', '.join(sorted(VALID_FRONTIER_TYPES))}"
        )
        # Can't continue type-specific checks without valid type
        return {"valid": False, "issues": issues, "warnings": warnings}

    if confidence not in VALID_CONFIDENCE_LEVELS:
        issues.append(
            f"invalid confidence: '{confidence}'. Must be low/medium/high"
        )

    if not reason.strip():
        issues.append("reason is required for all frontier types")

    # dispatch_to is required for all frontier types
    if not dt:
        issues.append("dispatch_to is required for all frontier types")
    elif dt not in VALID_DISPATCH_TARGETS:
        issues.append(
            f"invalid dispatch_to: '{dt}'. "
            f"Must be one of: {', '.join(sorted(VALID_DISPATCH_TARGETS))}"
        )

    # Confidence = low should prompt human confirmation
    human_confirm = decision.get("needs_human_confirmation")
    if confidence == "low" and not human_confirm:
        warnings.append(
            "confidence=low but needs_human_confirmation is not true. "
            "Low-confidence frontier decisions should be confirmed by a human."
        )

    # Check that selected_plan_id exists in plans.json if provided
    if selected_plan_id:
        plans_data = _read_json(Path(base_dir) / ".aiwf" / "state" / "plans.json")
        plan_ids = {p.get("id", "") for p in plans_data.get("plans", [])}
        if not plan_ids:
            warnings.append(
                f"plans.json is empty; selected_plan_id '{selected_plan_id}' "
                f"cannot be verified."
            )
        elif selected_plan_id not in plan_ids:
            issues.append(
                f"selected_plan_id '{selected_plan_id}' not found in plans.json. "
                f"Existing plans: {', '.join(sorted(plan_ids)) or '(none)'}"
            )

    # Check target_goal_id exists if provided
    if target_goal_id:
        _validate_goal_exists(base_dir, target_goal_id, issues, warnings)

    # Plan's target_goal_id should match decision's target_goal_id
    if selected_plan_id and target_goal_id:
        plan_goal = _get_plan_target_goal(base_dir, selected_plan_id)
        if plan_goal and plan_goal != target_goal_id:
            warnings.append(
                f"Plan '{selected_plan_id}' has target_goal_id='{plan_goal}' "
                f"but frontier decision has target_goal_id='{target_goal_id}'. "
                f"If this is intentional, explain the mismatch in the reason."
            )

    # rollup_target should match target_goal_id if both provided
    if rollup_target and target_goal_id and rollup_target != target_goal_id:
        warnings.append(
            f"rollup_target '{rollup_target}' differs from target_goal_id "
            f"'{target_goal_id}'. Ensure evidence rolls up to the correct Goal."
        )

    # active_phase check
    active_phase = str(decision.get("active_phase") or "")
    if active_phase and active_phase not in VALID_ACTIVE_PHASES:
        issues.append(
            f"invalid active_phase: '{active_phase}'. "
            f"Must be one of: {', '.join(sorted(VALID_ACTIVE_PHASES))}"
        )

    # ── Stage 4.7.4: work_intent validation (rule-table-driven) ──
    work_intent = str(decision.get("work_intent") or "")
    if work_intent:
        from .work_intent_rules import VALID_WORK_INTENTS
        if work_intent not in VALID_WORK_INTENTS:
            issues.append(
                f"invalid work_intent: '{work_intent}'. "
                f"Must be one of: {', '.join(sorted(VALID_WORK_INTENTS))}"
            )
        else:
            ev_lower = [e.lower() for e in expected_evidence]
            fc_lower = [f.lower() for f in (decision.get("forbidden_changes", []) or [])]
            # refactor: preserve_behavior must not be false, evidence needs regression/compat/before-after (at least 2 of 3)
            if work_intent == "refactor":
                if decision.get("preserve_behavior") is False:
                    issues.append("refactor requires preserve_behavior=true")
                reg_count = sum(1 for kw in ("regression", "compatibility", "before") if any(kw in e for e in ev_lower))
                if reg_count < 2:
                    issues.append("refactor expected_evidence must include at least 2 of: regression, compatibility, before-after summary")
                if not any("feature creep" in f for f in fc_lower):
                    warnings.append("refactor should forbid feature creep in forbidden_changes")
            # migration: compatibility must not be false, evidence needs mapping or migration report
            elif work_intent == "migration":
                if decision.get("compatibility_required") is False:
                    issues.append("migration requires compatibility_required=true")
                has_mapping = any(kw in e for e in ev_lower for kw in ("mapping", "migration"))
                if not has_mapping:
                    issues.append("migration requires old-new mapping or migration report in expected_evidence")
            # verification: dispatch must be tester/reviewer, must forbid implementation drift
            elif work_intent == "verification":
                if dt and dt not in ("tester", "reviewer"):
                    issues.append(f"verification requires dispatch_to=tester or reviewer, got '{dt}'")
                if not any("implementation drift" in f for f in fc_lower):
                    warnings.append("verification should forbid implementation drift in forbidden_changes")
            # release: evidence needs at least 2 of: tests/audit/package hygiene
            elif work_intent == "release":
                rel_count = sum(1 for kw in ("test", "audit", "package") if any(kw in e for e in ev_lower))
                if rel_count < 2:
                    issues.append("release expected_evidence must include at least 2 of: tests, audit, package hygiene")
                if not any("runtime" in f or "pycache" in f or "junk" in f for f in fc_lower):
                    warnings.append("release should forbid shipping runtime pollution or generated junk")
            # documentation: must forbid semantic drift / changing machine semantics
            elif work_intent == "documentation":
                if not any("semantic" in f or "machine" in f for f in fc_lower):
                    issues.append("documentation must forbid changing machine semantics or semantic drift")
            # cleanup: must forbid deleting machine truth
            elif work_intent == "cleanup":
                if not any("deleting machine truth" in f for f in fc_lower):
                    warnings.append("cleanup should forbid deleting machine truth")
            # integration: dispatch prefers architect/reviewer/tester
            elif work_intent == "integration":
                if dt and dt not in ("architect", "reviewer", "tester"):
                    warnings.append(f"integration prefers dispatch_to=architect/reviewer/tester, got '{dt}'")
            # bugfix: evidence needs regression coverage
            elif work_intent == "bugfix":
                if not expected_evidence:
                    issues.append("bugfix requires expected_evidence with regression coverage")
                if not any("regression" in e for e in ev_lower):
                    warnings.append("bugfix should include regression evidence")
            # exploration: must have isolation
            elif work_intent == "exploration":
                has_isolation = decision.get("temporary_root_id") or \
                    any("isolated" in str(c).lower() or "temporary root" in str(c).lower()
                        for c in (decision.get("constraints", []) or []))
                if not has_isolation:
                    warnings.append("exploration should have isolation constraint or temporary root")
    else:
        # No explicit work_intent — derive from plan_kind or default
        plan_kind2 = _get_plan_kind_from_registry(base_dir, selected_plan_id) if selected_plan_id else ""
        derived = _resolve_work_intent("", plan_kind2)
        if derived != "feature":
            warnings.append(
                f"work_intent not specified; derived '{derived}' from plan_kind='{plan_kind2}'. "
                f"Consider specifying work_intent explicitly."
            )

    # ── Type-specific checks ──

    if ft == "execute_plan":
        if not selected_plan_id:
            issues.append("execute_plan requires selected_plan_id")
        if not target_goal_id:
            issues.append("execute_plan requires target_goal_id")
        if not scope.strip():
            issues.append("execute_plan requires scope")
        if not expected_evidence:
            issues.append("execute_plan requires expected_evidence (at least one item)")
        if not rollup_target:
            issues.append("execute_plan requires rollup_target")
        if dt != "executor":
            issues.append(f"execute_plan requires dispatch_to=executor, got '{dt}'")

        # If plan_kind is structural, warn about executor scope
        if selected_plan_id:
            plan_kind = _get_plan_kind_from_registry(base_dir, selected_plan_id)
            if plan_kind == "structural":
                warnings.append(
                    f"Plan '{selected_plan_id}' is structural. "
                    f"Executor work under a structural plan should be scoped "
                    f"to defining interfaces and boundaries, not implementation."
                )

    elif ft == "verify_plan":
        if not selected_plan_id:
            issues.append("verify_plan requires selected_plan_id")
        if not target_goal_id:
            issues.append("verify_plan requires target_goal_id")
        if not expected_evidence:
            issues.append("verify_plan requires expected_evidence (at least one item)")
        if dt != "tester":
            issues.append(f"verify_plan requires dispatch_to=tester, got '{dt}'")

    elif ft == "review_plan":
        if not selected_plan_id:
            issues.append("review_plan requires selected_plan_id")
        if dt != "reviewer":
            issues.append(f"review_plan requires dispatch_to=reviewer, got '{dt}'")
        if not review_focus and not expected_evidence:
            issues.append(
                "review_plan requires at least one of review_focus or expected_evidence"
            )

    elif ft == "integrate_goal":
        if not target_goal_id:
            issues.append("integrate_goal requires target_goal_id")
        if dt not in ("architect", "reviewer"):
            issues.append(
                f"integrate_goal requires dispatch_to=architect or reviewer, got '{dt}'"
            )
        if target_goal_id:
            if not _has_children_or_plans(base_dir, target_goal_id):
                warnings.append(
                    f"Goal '{target_goal_id}' has no attached plans or child goals. "
                    f"Integration with nothing to integrate may be premature."
                )

    elif ft == "architect_structure":
        if not target_goal_id:
            issues.append("architect_structure requires target_goal_id")
        if dt != "architect":
            issues.append(
                f"architect_structure requires dispatch_to=architect, got '{dt}'"
            )
        if not interfaces and not constraints:
            has_policy = bool(decision.get("child_goal_policy"))
            if not has_policy:
                issues.append(
                    "architect_structure requires at least one of: "
                    "interfaces, constraints, or child_goal_policy"
                )

    elif ft == "explore_temporary_root":
        if not target_goal_id and not decision.get("temporary_root_id") and not decision.get("new_temporary_root_title"):
            issues.append(
                "explore_temporary_root requires target_goal_id, "
                "temporary_root_id, or new_temporary_root_title"
            )
        if dt not in ("planner", "architect", "executor"):
            issues.append(
                f"explore_temporary_root requires dispatch_to=planner/architect/executor, "
                f"got '{dt}'"
            )
        warnings.append(
            "exploration that may enter the main tree will need subsequent "
            "graft or prune. Plan the exit strategy before exploration begins."
        )

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Stage 4.7C: Work Packet Preparation
# ═══════════════════════════════════════════════════════════════════════════════

def prepare_work_packet(base_dir: str,
                         decision: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a Frontier Decision and prepare a Work Packet.

    Runs validate_frontier_decision first. If valid, produces both
    human-readable and agent-structured Work Packet output.

    Args:
        base_dir: Project root directory.
        decision: A dict matching the Frontier Decision schema.

    Returns:
        {valid, validation_issues, warnings, human_work_packet, agent_work_packet}
    """
    validation = validate_frontier_decision(base_dir, decision)

    if not validation["valid"]:
        return {
            "valid": False,
            "validation_issues": validation["issues"],
            "warnings": validation.get("warnings", []),
            "human_work_packet": {},
            "agent_work_packet": {},
        }

    ft = str(decision.get("frontier_type") or "")
    dt = str(decision.get("dispatch_to") or "")
    target_goal_id = str(decision.get("target_goal_id") or "")
    selected_plan_id = str(decision.get("selected_plan_id") or "")

    # Read authoritative data from registries
    plan_kind = ""
    if selected_plan_id:
        plan_kind = _get_plan_kind_from_registry(base_dir, selected_plan_id)

    goal_title = ""
    if target_goal_id:
        goal_title = _get_goal_title(base_dir, target_goal_id)

    active_phase = str(decision.get("active_phase") or "")
    scope = str(decision.get("scope") or "")
    reason = str(decision.get("reason") or "")
    interfaces = decision.get("interfaces", []) or []
    constraints = decision.get("constraints", []) or []
    expected_evidence = decision.get("expected_evidence", []) or []
    forbidden_changes = decision.get("forbidden_changes", []) or []
    rollup_target = str(decision.get("rollup_target") or target_goal_id)
    review_focus = decision.get("review_focus", []) or []
    human_confirm = decision.get("needs_human_confirmation", False)

    # Work Intent (Stage 4.7.4)
    work_intent = str(decision.get("work_intent") or "")
    if not work_intent:
        from .work_intent_rules import resolve_work_intent
        work_intent = resolve_work_intent("", plan_kind or "")

    # ── Build base packet, merge work_intent defaults FIRST ──
    from .work_intent_rules import get_work_intent_rules, merge_work_intent_defaults

    base_packet: Dict[str, Any] = {
        "work_intent": work_intent,
        "constraints": list(constraints),
        "forbidden_changes": list(forbidden_changes),
        "expected_evidence": list(expected_evidence),
        "review_focus": list(review_focus),
    }
    merged = merge_work_intent_defaults(base_packet)
    merged_constraints = merged.get("constraints", constraints)
    merged_forbidden = merged.get("forbidden_changes", forbidden_changes)
    merged_evidence = merged.get("expected_evidence", expected_evidence)
    merged_review = merged.get("review_focus", review_focus)

    # ── Human Work Packet (text) — uses merged fields ──
    lines: List[str] = []
    lines.append("Work Packet Proposal")
    lines.append("=" * 18)
    lines.append("")
    lines.append(f"Dispatch: {dt.title()}")
    lines.append(f"Frontier: {ft.replace('_', ' ').title()}")
    lines.append("")

    if target_goal_id:
        goal_label = target_goal_id
        if goal_title:
            goal_label += f" — {goal_title}"
        lines.append(f"Target Goal:\n  {goal_label}")
        lines.append("")

    if selected_plan_id:
        plan_label = f"  {selected_plan_id}"
        if plan_kind:
            plan_label += f"\n  Kind: {plan_kind}"
        if active_phase:
            plan_label += f"\n  Phase: {active_phase}"
        if work_intent:
            plan_label += f"\n  Work Intent: {work_intent}"
        lines.append(f"Plan:\n{plan_label}")
        lines.append("")

    lines.append(f"Why this frontier:\n  {reason}")
    lines.append("")

    if work_intent:
        lines.append(f"Work Intent Discipline: {work_intent}")
        try:
            rules = get_work_intent_rules(work_intent)
            lines.append(f"  {rules.get('summary', '')}")
            pb = rules.get("preserve_behavior")
            if pb:
                lines.append(f"  Preserve Behavior: {pb}")
            rr = rules.get("regression_required")
            if rr:
                lines.append(f"  Regression: {'required' if rr is True else rr}")
        except Exception:
            pass
        lines.append("")

    if scope:
        lines.append(f"Scope:\n  {scope}")
        lines.append("")

    if interfaces:
        lines.append("Interfaces:")
        for i in interfaces:
            lines.append(f"  - {i}")
        lines.append("")

    if merged_constraints:
        lines.append("Constraints:")
        for c in merged_constraints:
            lines.append(f"  - {c}")
        lines.append("")

    if merged_evidence:
        lines.append("Expected Evidence:")
        for e in merged_evidence:
            lines.append(f"  - {e}")
        lines.append("")

    if merged_forbidden:
        lines.append("Forbidden Changes:")
        for f in merged_forbidden:
            lines.append(f"  - {f}")
        lines.append("")

    if rollup_target:
        lines.append(f"Rollup:\n  Evidence should roll up to {rollup_target}.")
        lines.append("")

    before_confirm = "Required" if human_confirm else "Not required."
    lines.append(f"Human Check:\n  {before_confirm}")
    lines.append("")

    if merged_review:
        lines.append("Review Focus:")
        for rf in merged_review:
            lines.append(f"  - {rf}")
        lines.append("")

    warnings = validation.get("warnings", [])
    if warnings:
        lines.append("Warnings:")
        for w in warnings:
            lines.append(f"  - {w}")
        lines.append("")

    lines.append("—")
    lines.append("This Work Packet is advisory. Review and confirm before dispatch.")
    lines.append("Use --json for the Agent Work Packet.")

    human_text = "\n".join(lines)

    # ── Agent Work Packet (JSON) — uses same merged fields ──
    agent_packet: Dict[str, Any] = {
        "work_packet_version": 1,
        "valid": True,
        "frontier_type": ft,
        "dispatch_to": dt,
        "target_goal_id": target_goal_id or None,
        "selected_plan_id": selected_plan_id or None,
        "plan_kind": plan_kind or None,
        "active_phase": active_phase or None,
        "work_intent": work_intent,
        "scope": scope or None,
        "interfaces": interfaces,
        "constraints": merged_constraints,
        "expected_evidence": merged_evidence,
        "forbidden_changes": merged_forbidden,
        "rollup_target": rollup_target or None,
        "review_focus": merged_review,
        "mutates_state": False,
        "preserve_behavior": merged.get("preserve_behavior"),
        "compatibility_required": merged.get("compatibility_required"),
        "regression_required": merged.get("regression_required"),
    }

    human_packet = {
        "title": f"{dt.title()} — {ft.replace('_', ' ').title()}",
        "dispatch": dt,
        "frontier_type": ft,
        "target_goal_id": target_goal_id or None,
        "target_goal_title": goal_title or None,
        "selected_plan_id": selected_plan_id or None,
        "plan_kind": plan_kind or None,
        "active_phase": active_phase or None,
        "work_intent": work_intent,
        "reason": reason,
        "scope": scope or None,
        "interfaces": interfaces,
        "constraints": merged_constraints,
        "expected_evidence": merged_evidence,
        "forbidden_changes": merged_forbidden,
        "rollup_target": rollup_target or None,
        "review_focus": merged_review,
        "requires_confirmation": human_confirm,
        "warnings": warnings,
        "text": human_text,
    }

    return {
        "valid": True,
        "validation_issues": [],
        "warnings": warnings,
        "human_work_packet": human_packet,
        "agent_work_packet": agent_packet,
    }
