"""Phase-gate field checks. Every transition requires key fields filled.

Enum fields: must not be empty (some valid value selected).
Q&A fields: must have at least one non-empty entry.

Does NOT check content quality — Reviewer handles that.
Each blocker returns a human-readable message + the fix command.
"""

from __future__ import annotations

import json

from .state.goal_ops import get_active_goal
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _read(path: Path, default: Dict[str, Any] = None) -> Dict[str, Any]:
    if default is None:
        default = {}
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _empty(val: Any) -> bool:
    """True if the value is effectively empty."""
    if val is None:
        return True
    if isinstance(val, str):
        return not val.strip()
    if isinstance(val, list):
        return len(val) == 0 or all(not str(v).strip() for v in val)
    if isinstance(val, dict):
        return len(val) == 0
    return False


def _blocker(field: str, question: str, fix: str) -> str:
    """Format a blocker message."""
    return f"[{field}] {question} — fix: {fix}"


# ── planned → implementing ──

def planned_to_implementing_gates(base_dir: str, task_plan_id: str = "") -> List[str]:
    """Fields that must be filled before task activation.

    Tiered by workflow level:
    - L0: enum fields only (plan_kind, work_intent)
    - L1: enum + key Q&A (purpose, allowed_write, acceptance_criteria, non_goals)
    - L2/L3: everything including evaluation contract and architecture brief
    """
    root = Path(base_dir)
    state = _read(root / ".aiwf" / "state" / "state.json")
    level = state.get("workflow_level", "L1_review_light")
    blockers: List[str] = []

    # ── Plan fields ──
    plans_data = _read(root / ".aiwf" / "state" / "plans.json")
    active_plan_id = state.get("active_plan_id", "") or task_plan_id
    plan = None
    if active_plan_id:
        for p in plans_data.get("plans", []) or []:
            if isinstance(p, dict) and p.get("id") == active_plan_id:
                plan = p
                break

    # Only check Plan fields when a plan is actively registered.
    # plan_kind and work_intent are enum fields — must be filled.
    if plan:
        # Enum: plan_kind (all levels)
        if _empty(plan.get("plan_kind")):
            blockers.append(_blocker(
                "plan.plan_kind",
                "What kind of Plan is this?",
                "aiwf plan create PLAN-ID --kind structural|implementation|verification|migration|exploration",
            ))
        # Enum: work_intent (L1+)
        if level != "L0_direct" and _empty(plan.get("work_intent")):
            blockers.append(_blocker(
                "plan.work_intent",
                "What is the behavioral discipline?",
                "aiwf plan update --task-id <ID> --section goal --content 'work_intent: feature|bugfix|refactor|cleanup|migration|verification|exploration|documentation|integration|release'",
            ))

    # ── Q&A: target_goal_id (L1+) ──
    if level != "L0_direct" and plan and _empty(plan.get("target_goal_id")):
        blockers.append(_blocker(
            "plan.target_goal_id",
            "Which Goal does this Plan serve?",
            "aiwf plan create PLAN-ID --target-goal <GOAL-ID> --kind <KIND>",
        ))
    elif level != "L0_direct" and plan and plan.get("target_goal_id"):
        # Validate the referenced Goal exists and is not archived/superseded
        tgid = plan["target_goal_id"]
        try:
            from .state.goal_tree_ops import goal_exists, get_goal
            if goal_exists(base_dir, tgid):
                goal = get_goal(base_dir, tgid)
                gs = goal.get("status", "")
                if gs in ("archived", "superseded"):
                    blockers.append(_blocker(
                        "goal.status",
                        f"Goal '{tgid}' is {gs} — cannot activate Plan for archived/superseded Goal",
                        f"aiwf goal-tree show {tgid} — check status, or use a different Goal",
                    ))
            elif tgid == "GOAL-001":
                # Legacy GOAL-001: check goal.json exists as fallback.
                # goals.json is the tree registry; goal.json is the legacy singleton.
                # If neither exists, the project state is incomplete.
                legacy = get_active_goal(base_dir)
                if not legacy.get("title") and not legacy.get("quality_brief"):
                    blockers.append(_blocker(
                        "plan.target_goal_id",
                        "Legacy GOAL-001 has no goal data — project state may be incomplete",
                        "aiwf goal-tree init-root GOAL-001 --type main --title '...'",
                    ))
            else:
                blockers.append(_blocker(
                    "plan.target_goal_id",
                    f"Goal '{tgid}' does not exist in the Goal Tree",
                    f"aiwf goal-tree init-root {tgid} --type main --title '...'  or  aiwf goal-tree show",
                ))
        except Exception:
            pass

    # ── Plan scope (L1+) ──
    # Plan is recommended but not required. Task.md is the execution contract.
    # allowed_write is no longer a gate — blacklist (forbidden_write) is the
    # safety boundary. Only check Plan purpose when a Plan is attached.
    if level != "L0_direct" and plan:
        if not plan.get("purpose"):
            blockers.append(_blocker(
                "plan.purpose",
                "What is this Plan meant to achieve?",
                "aiwf plan create PLAN-ID --purpose '...'",
            ))

    # ── Contract fields (L1+) ──
    # Only check when quality_brief has been started (any field filled).
    # If everything is default-empty, Planner hasn't begun contracts — skip.
    if level != "L0_direct":
        goal = get_active_goal(base_dir)
        brief = goal.get("quality_brief", {}) or {}
        evaluation = brief.get("evaluation_contract", {}) or {}
        architecture = brief.get("architecture_brief", {}) or {}
        surface_types = brief.get("surface_types", []) or []

        # Only check when Planner has started filling contracts
        contracts_started = bool(
            evaluation.get("acceptance_criteria") or evaluation.get("user_visible_outcome")
            or evaluation.get("test_obligations") or evaluation.get("review_obligations")
            or brief.get("non_goals") or surface_types
            or any(architecture.get(k) for k in (
                "target_structure", "module_boundaries", "architecture_invariants",
            ) if architecture.get(k))
        )
        if contracts_started:
            if _empty(evaluation.get("acceptance_criteria")):
                blockers.append(_blocker(
                    "contract.acceptance_criteria",
                    "How will we know this is done?",
                    "aiwf state record-quality-brief --acceptance-criterion '...'",
                ))

            # non_goals: all levels (L1+)
            if _empty(brief.get("non_goals")):
                blockers.append(_blocker(
                    "contract.non_goals",
                    "What is explicitly NOT in scope?",
                    "aiwf state record-quality-brief --non-goal '...'",
                ))

            # L2/L3 extra
            if level in ("L2_standard_team", "L3_full_power"):
                if _empty(evaluation.get("user_visible_outcome")):
                    blockers.append(_blocker(
                        "contract.user_visible_outcome",
                        "What will the user see after this is done?",
                        "aiwf state record-quality-brief --user-visible-outcome '...'",
                    ))
                if _empty(evaluation.get("test_obligations")):
                    blockers.append(_blocker(
                        "contract.test_obligations",
                        "What must be tested?",
                        "aiwf state record-quality-brief --test-obligation '...'",
                    ))
                if _empty(evaluation.get("review_obligations")):
                    blockers.append(_blocker(
                        "contract.review_obligations",
                        "What must Reviewer check?",
                        "aiwf state record-quality-brief --review-obligation '...'",
                    ))
                if not any(architecture.get(k) for k in (
                    "target_structure", "module_boundaries", "architecture_invariants",
                    "forbidden_restructures", "integration_points",
                )):
                    blockers.append(_blocker(
                        "architecture_brief",
                        "What are the structural boundaries?",
                        "aiwf state record-quality-brief --target-structure '...' --module-boundary '...'",
                    ))

    return blockers


# ── implementing → testing ──

def implementing_to_testing_gates(base_dir: str) -> List[str]:
    """Before recording testing as adequate/passed, verify evidence exists.
    Only checks when there's an active task (real workflow context)."""
    root = Path(base_dir)
    blockers: List[str] = []
    state = _read(root / ".aiwf" / "state" / "state.json")

    # Skip if no active task (e.g., unit tests calling record_testing directly)
    if not state.get("active_task_id"):
        return blockers

    evidence = _read(root / ".aiwf" / "records" / "evidence.json")
    records = evidence.get("records", []) or []

    if not records:
        blockers.append(_blocker(
            "evidence",
            "No evidence records — implementation must produce evidence before testing",
            "aiwf state record-role-evidence --role executor --summary '...' --changed-file <path> --scan-git",
        ))

    return blockers


# ── testing → reviewing ──

def testing_to_reviewing_gates(base_dir: str) -> List[str]:
    """Before recording review, verify testing passed and cleanup is fresh.
    Only checks when there's an active task (real workflow context)."""
    root = Path(base_dir)
    blockers: List[str] = []
    state = _read(root / ".aiwf" / "state" / "state.json")

    # Skip if no active task (e.g., unit tests calling record_review directly)
    if not state.get("active_task_id"):
        return blockers

    level = state.get("workflow_level", "L1_review_light")

    testing = _read(root / ".aiwf" / "records" / "testing.json")
    tstat = testing.get("status", "missing")

    if tstat not in ("adequate", "passed"):
        blockers.append(_blocker(
            "testing.status",
            f"Testing status is '{tstat}', must be adequate or passed before review",
            "aiwf state record-testing --status adequate --supports-plan <PLAN-ID> --supports-goal <GOAL-ID> --command '...'",
        ))

    # L1+: cleanup must be verified before review
    if level != "L0_direct":
        review = _read(root / ".aiwf" / "records" / "review.json")
        if _empty(review.get("cleanup_verified_at")):
            blockers.append(_blocker(
                "cleanup",
                "Cleanup must be verified before Reviewer is dispatched",
                "aiwf cleanup check && aiwf state mark-cleanup-fresh",
            ))

        # L2/L3: tree-internal consistency before independent review.
        # Task/Plan attachment is already enforced at activation; here we
        # check graft interface integrity and cross-parent relation transparency
        # — structural drift that activation gates don't see.
        try:
            from .state.goal_tree_ops import list_goals, load_goal_tree
            # Graft interface: child Goals must declare their interface to parent
            for g in list_goals(base_dir):
                if not isinstance(g, dict):
                    continue
                gid = g.get("id", "")
                parent = g.get("parent_goal_id")
                if parent and not g.get("graft_interface") and not g.get("graft_history"):
                    blockers.append(_blocker(
                        "goal.graft_interface",
                        f"Goal '{gid}' has parent '{parent}' but no graft_interface — "
                        "interface declaration is required for structural traceability",
                        f"aiwf goal-tree graft {gid} --target {parent} --interface-consumed '...' --capability-provided '...'",
                    ))
            # Cross-parent relations must carry a reason
            tree = load_goal_tree(base_dir, auto_create=False)
            for rel in (tree.get("relations", []) or []):
                if not isinstance(rel, dict):
                    continue
                if rel.get("cross_parent") and not rel.get("reason"):
                    src = rel.get("source_id", "")
                    tgt = rel.get("target_id", "")
                    blockers.append(_blocker(
                        "relation.reason",
                        f"Cross-parent relation {src}--[{rel.get('type', '')}]-->{tgt} has no reason — "
                        "cross-tree links without justification obscure the functional skeleton",
                        f"aiwf relation add {src} {tgt} --type {rel.get('type', '')} --cross --reason '...'",
                    ))
        except Exception:
            pass

    return blockers


# ── reviewing → closing ──

def reviewing_to_closing_gates(base_dir: str) -> List[str]:
    """Before prepare-close, verify review verdict is recorded and observations disposed."""
    root = Path(base_dir)
    blockers: List[str] = []

    review = _read(root / ".aiwf" / "records" / "review.json")
    verdict = review.get("verdict", "pending")

    # Only check if review has been started (result or verdict explicitly set)
    review_started = bool(
        review.get("verdict") or review.get("result") != "unknown"
        or review.get("cleanup_status") or review.get("structure_status")
        or review.get("accepted_evidence_ids") or review.get("quality_dimensions")
    )
    if review_started and verdict == "pending":
        blockers.append(_blocker(
            "review.verdict",
            "Review verdict is pending — Reviewer must record a verdict",
            "aiwf state record-review --verdict PASS|PASS_WITH_RISK|REVISE|REJECT --accepted-evidence-id <ID>",
        ))

    # Q&A: Planner meta-critique (L2+; skip if goals.json not set up)
    state = _read(root / ".aiwf" / "state" / "state.json")
    level = state.get("workflow_level", "L1_review_light")
    if level in ("L2_standard_team", "L3_full_power"):
        goal = get_active_goal(base_dir)
        meta = goal.get("meta_critique", {}) or {}
        if _empty(meta.get("summary")):
            blockers.append(_blocker(
                "meta_critique.summary",
                "Planner must record meta-critique after reviewing adversarial observations",
                "aiwf state record-meta-critique --summary '...'",
            ))

    # Enum: adversarial observations must be disposed
    observations = review.get("adversarial_observations", []) or []
    pending_obs = [o for o in observations if isinstance(o, dict) and o.get("disposition") == "pending"]
    if pending_obs:
        blockers.append(_blocker(
            "adversarial_observations",
            f"{len(pending_obs)} adversarial observation(s) pending disposition",
            "aiwf state disposition-adversarial --id <ADV-ID> --disposition ignored|accepted|deferred|brief_updated --reason '...'",
        ))

    return blockers
