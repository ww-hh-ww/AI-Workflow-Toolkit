"""Planner-facing workflow explanation derived from machine-readable state."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def _read(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def planner_process_guidance(base_dir: str) -> Dict[str, Any]:
    """Explain current gates, why they apply, and what Planner should do next."""
    root = Path(base_dir)
    state = _read(root / ".aiwf" / "state" / "state.json", {})
    goal = _read(root / ".aiwf" / "state" / "goal.json", {})
    testing = _read(root / ".aiwf" / "quality" / "testing.json", {})
    review = _read(root / ".aiwf" / "quality" / "review.json", {})
    fix_loop = _read(root / ".aiwf" / "state" / "fix-loop.json", {})
    ledger = _read(root / ".aiwf" / "history" / "task-ledger.json", {"tasks": []})
    level = state.get("workflow_level", "L1_review_light")
    active_task = state.get("active_task_id")
    brief = goal.get("quality_brief", {}) or {}
    evaluation = brief.get("evaluation_contract", {}) or {}
    architecture = brief.get("architecture_brief", {}) or {}
    required: List[str] = []
    conditional: List[str] = []
    advisory: List[str] = []

    if state.get("scope_violation"):
        events = [
            event for event in (review.get("scope_violation_events", []) or [])
            if isinstance(event, dict) and event.get("status", "recorded") != "resolved_reverted"
        ]
        paths = ", ".join(str(event.get("path")) for event in events[:3] if event.get("path"))
        required.append(
            "Scope recovery: revert the originally violating files"
            + (f" ({paths})" if paths else "")
            + ", then run aiwf fix-loop resolve --resolution '<what was reverted>'; "
              "context widening cannot legalize past writes"
        )
    if not active_task:
        required.append("Plan and activate one task before project writes: aiwf task plan ...; aiwf task activate <TASK-ID>")
    if level in ("L2_standard_team", "L3_full_power"):
        missing_eval = [
            key for key in ("user_visible_outcome", "acceptance_criteria", "test_obligations", "review_obligations")
            if not evaluation.get(key)
        ]
        if missing_eval:
            required.append("Complete Evaluation Contract before activation: " + ", ".join(missing_eval))
        if not any(architecture.get(k) for k in (
            "target_structure", "module_boundaries", "architecture_invariants",
            "forbidden_restructures", "integration_points",
        )):
            required.append("Record a structural Architecture Brief before activation")
        if active_task and testing.get("status") not in ("adequate", "passed"):
            required.append(f"Dispatch independent Tester using {state.get('test_template') or 'selected test template'}")
        if active_task and (
            testing.get("full_suite_status", "not_run") == "not_run"
            or testing.get("real_usage_status", "not_run") == "not_run"
        ):
            required.append(
                "Tester must disposition the full project suite and an actual user-facing entrypoint; "
                "unit tests alone are insufficient"
            )
        if testing.get("status") in ("adequate", "passed") and not review.get("cleanup_verified_at"):
            required.append("Verify cleanup before dispatching Reviewer: aiwf cleanup check; aiwf state mark-cleanup-fresh")
        if review.get("cleanup_verified_at") and review.get("result") != "accepted":
            required.append(f"Dispatch independent Reviewer using {state.get('review_template') or 'selected review template'}")
        if review.get("result") == "accepted":
            pending = [
                o for o in (review.get("adversarial_observations", []) or [])
                if isinstance(o, dict) and o.get("disposition") == "pending"
            ]
            if pending:
                required.append(f"Planner meta-critique: disposition {len(pending)} adversarial observation(s)")
            else:
                required.append("Record Planner meta-critique, close the active task, then prepare-close")

    if fix_loop.get("status") == "open":
        fixes = "; ".join(map(str, (fix_loop.get("required_fixes", []) or [])[:2]))
        verification = "; ".join(map(str, (fix_loop.get("required_verification", []) or [])[:2]))
        detail = []
        if fixes: detail.append(f"fixes={fixes}")
        if verification: detail.append(f"verification={verification}")
        if fix_loop.get("escalation_required"): detail.append("escalation requires user/independent decision")
        required.insert(
            0,
            f"Resolve fix-loop via route={fix_loop.get('route') or 'planner'} before continuing"
            + (f" ({'; '.join(detail)})" if detail else "")
        )
    if level == "L3_full_power":
        ckpt = root / ".aiwf" / "checkpoints"
        if not (ckpt.exists() and any(ckpt.iterdir())):
            conditional.append("L3 requires checkpoint before task completion, unless Planner records an explicit skip decision")

    try:
        from .task_gravity import should_trigger_architecture_review, task_gravity
        gravity = task_gravity(base_dir)
        arch = should_trigger_architecture_review(base_dir)
        for constraint in gravity.get("hard_constraints", [])[:3]:
            required.append(
                f"Gravity gate [{constraint.get('kind', '?')}]: {constraint.get('message', '')}"
            )
        if arch.get("should_trigger"):
            conditional.append("Periodic Architect is due before the next ordinary task: " + "; ".join(arch.get("reasons", [])[:2]))
    except Exception:
        pass

    try:
        from ..assets.schema import asset_status
        assets = asset_status(base_dir)
        if assets.get("overall") == "stale":
            stale = ", ".join(assets.get("stale_files", [])[:3])
            conditional.append(
                "Tier 1 assets are stale; verify source directly and refresh assets"
                + (f": {stale}" if stale else "")
            )
    except Exception:
        pass

    if not (root / ".aiwf" / "assets" / "environment.json").exists():
        conditional.append("Environment profile is missing; it will be mechanically scanned at context start")
    if not (root / ".aiwf" / "assets" / "capabilities.json").exists():
        conditional.append("Capability registry is missing; scan before relying on external skills/hooks")

    advisory.extend([
        "Use Explorer when pre-planning research needs broad read-only discovery",
        "Use Curator after closure only when lessons or negative patterns will change future behavior",
        "Use memory suggest when prior lessons may affect this task; suggestions never override current contracts",
        "Mechanical signals select minimum depth; Planner must explain semantic risk and may increase depth or breadth",
    ])
    return {
        "workflow_level": level,
        "complexity": state.get("complexity", "standard"),
        "routing_score": state.get("routing_score", 0),
        "routing_factors": state.get("routing_factors", []) or [],
        "test_template": state.get("test_template", ""),
        "review_template": state.get("review_template", ""),
        "exploration_budget": state.get("exploration_budget", ""),
        "required_now": required,
        "conditional": conditional,
        "advisory": advisory,
        "active_task_id": active_task,
        "ledger_task_count": len(ledger.get("tasks", []) or []),
        "contract_freeze_reasons": _contract_freeze_reasons(base_dir, state),
    }


def _contract_freeze_reasons(base_dir: str, state: Dict[str, Any]) -> List[str]:
    try:
        from .state_ops import execution_contract_freeze_reasons
        return execution_contract_freeze_reasons(base_dir, state)
    except Exception:
        return []
