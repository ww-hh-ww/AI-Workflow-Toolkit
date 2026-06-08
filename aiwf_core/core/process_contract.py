"""Planner-facing workflow explanation derived from machine-readable state."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def _read(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _base_recovery() -> Dict[str, Any]:
    return {
        "state": "clear",
        "category": "",
        "owner": "planner",
        "primary": "",
        "legal_options": [],
        "forbidden": [],
        "user_decision_required": False,
        "why": "",
    }


def _blocked(
    category: str,
    owner: str,
    primary: str,
    why: str,
    legal_options: List[str],
    forbidden: Optional[List[str]] = None,
    user_decision_required: bool = False,
) -> Dict[str, Any]:
    return {
        "state": "blocked",
        "category": category,
        "owner": owner,
        "primary": primary,
        "legal_options": legal_options,
        "forbidden": forbidden or [],
        "user_decision_required": user_decision_required,
        "why": why,
    }


def _recovery_guidance(
    base_dir: str,
    state: Dict[str, Any],
    goal: Dict[str, Any],
    testing: Dict[str, Any],
    review: Dict[str, Any],
    fix_loop: Dict[str, Any],
) -> Dict[str, Any]:
    """Return the primary recovery path without collapsing normal workflow topology."""
    root = Path(base_dir)
    level = state.get("workflow_level", "L1_review_light")
    request_mode = state.get("request_mode", "execution")
    active_task = state.get("active_task_id")

    if fix_loop.get("status") == "open":
        route = fix_loop.get("route") or "planner"
        needs_user = route == "planner" or bool(fix_loop.get("escalation_required"))
        return _blocked(
            "fix_loop",
            "user" if needs_user else route,
            f"resolve fix-loop via route={route}",
            "An open fix-loop freezes forward progress until its required fixes and verification are satisfied.",
            [
                "follow required_fixes and required_verification, then run aiwf fixloop resolve --resolution '...'",
                "if route=planner or escalation_required=true, ask the user for the decision before more work",
            ],
            [
                "do not start unrelated implementation",
                "do not edit fix-loop.json by hand",
                "do not lower workflow level to escape the fix-loop",
            ],
            user_decision_required=needs_user,
        )

    if state.get("scope_violation"):
        events = [
            event for event in (review.get("scope_violation_events", []) or [])
            if isinstance(event, dict) and event.get("status", "recorded") != "resolved_reverted"
        ]
        paths = ", ".join(str(event.get("path")) for event in events[:3] if event.get("path"))
        return _blocked(
            "scope",
            "planner",
            "recover scope violation",
            "Past out-of-scope writes cannot be legalized by widening context after the fact.",
            [
                "revert the originally violating files" + (f": {paths}" if paths else ""),
                "run aiwf fixloop resolve --resolution '<what was reverted>' after mechanical verification passes",
                "ask the user whether the desired extra work should become a new scoped task",
            ],
            [
                "do not widen allowed_write retrospectively",
                "do not close while scope_violation=true",
                "do not hand-edit review/state JSON to clear the violation",
            ],
            user_decision_required=not paths,
        )

    if request_mode in ("discussion", "clarification", "research"):
        return {
            "state": "open",
            "category": request_mode,
            "owner": "planner",
            "primary": f"continue {request_mode}",
            "legal_options": [
                f"continue {request_mode} without project writes",
                "ask the user to confirm when ready to switch request_mode=execution",
            ],
            "forbidden": ["do not activate implementation while request_mode is non-execution"],
            "user_decision_required": request_mode != "discussion",
            "why": "Non-execution request modes intentionally keep topology open while blocking implementation.",
        }

    if request_mode == "spike" or state.get("workflow_pattern") == "spike_first":
        return {
            "state": "open",
            "category": "spike",
            "owner": "planner",
            "primary": "finish spike and record findings",
            "legal_options": [
                "record spike findings",
                "ask the user to confirm execution after feasibility is known",
            ],
            "forbidden": ["do not treat spike output as final implementation closure"],
            "user_decision_required": False,
            "why": "Spike topology permits exploration before the final execution contract.",
        }

    if state.get("external_research_required") and request_mode == "execution":
        try:
            from .external_research import research_requirement_blocker
            if research_requirement_blocker(base_dir):
                return _blocked(
                    "user_decision",
                    "planner",
                    "resolve external research requirement",
                    "Execution requires promoted external research or an explicit Planner/user skip decision.",
                    [
                        "promote a relevant research record with aiwf research promote <ID> --decision '...'",
                        "ask the user whether to skip external research, then run aiwf research skip --reason '...'",
                    ],
                    [
                        "do not start implementation",
                        "do not silently clear external_research_required",
                    ],
                    user_decision_required=True,
                )
        except Exception:
            pass

    try:
        from .capabilities import capability_use_blockers
        cap_blockers = capability_use_blockers(base_dir)
        if cap_blockers:
            return _blocked(
                "user_decision",
                "planner",
                "resolve planned external capability decision",
                cap_blockers[0],
                [
                    "record a decision with aiwf capability decide <ID> --decision '...'",
                    "ask the user whether to use, avoid, or replace the overlapping capability",
                ],
                [
                    "do not use lifecycle-overlap external capabilities without an explicit decision",
                    "do not delete capability registry entries to bypass the gate",
                ],
                user_decision_required=True,
            )
    except Exception:
        pass

    if not active_task:
        active_plan = state.get("active_plan_id")
        if active_plan and request_mode == "execution":
            return _blocked(
                "plan_only_drift",
                "planner",
                f"freeze execution contract and activate planned task {active_plan}",
                "A human-readable plan exists, but no active task/context execution contract is running.",
                [
                    "record quality policy and Architecture/Evaluation Brief for the plan",
                    "start a scoped context with allowed_write and forbidden_write",
                    f"run aiwf task plan {active_plan} --title '...' --allowed-write '...'",
                    f"run aiwf task activate {active_plan}",
                    "or switch request_mode to discussion/research/spike if execution is not confirmed",
                ],
                [
                    "do not keep rewriting the plan as progress",
                    "do not dispatch implementation without task activation",
                    "do not treat plan.md as evidence or mechanical truth",
                ],
            )
        return _blocked(
            "missing_step",
            "planner",
            "plan and activate one scoped task",
            "Project writes need an active task with context boundaries and mechanical routing.",
            [
                "run aiwf task plan <TASK-ID> --title '...' --allowed-write '...'",
                "run aiwf task activate <TASK-ID>",
                "run aiwf status after activation and explain current/background routing signals",
            ],
            [
                "do not edit project files before task activation",
                "do not rely on plan.md as mechanical truth",
            ],
        )

    if level in ("L2_standard_team", "L3_full_power"):
        brief = goal.get("quality_brief", {}) or {}
        evaluation = brief.get("evaluation_contract", {}) or {}
        missing_eval = [
            key for key in ("user_visible_outcome", "acceptance_criteria", "test_obligations", "review_obligations")
            if not evaluation.get(key)
        ]
        if missing_eval:
            return _blocked(
                "missing_contract",
                "planner",
                "complete Evaluation Contract",
                "L2/L3 work requires explicit acceptance, test, and review obligations before execution can proceed.",
                [
                    "record the missing Evaluation Contract fields: " + ", ".join(missing_eval),
                    "ask the user to clarify acceptance criteria if they are not knowable from context",
                ],
                ["do not dispatch implementation until the contract is machine-readable"],
                user_decision_required=True,
            )
        architecture = brief.get("architecture_brief", {}) or {}
        if not any(architecture.get(k) for k in (
            "target_structure", "module_boundaries", "architecture_invariants",
            "forbidden_restructures", "integration_points",
        )):
            return _blocked(
                "missing_contract",
                "planner",
                "record structural Architecture Brief",
                "L2/L3 review and testing need declared structural boundaries.",
                [
                    "run aiwf state record-quality-brief with structural fields",
                    "ask the user for architecture boundaries only when source inspection cannot determine them",
                ],
                ["do not proceed with vague architecture obligations"],
                user_decision_required=False,
            )
        if testing.get("status") not in ("adequate", "passed"):
            return _blocked(
                "missing_step",
                "tester",
                "dispatch independent Tester",
                "L2/L3 requires distinct testing evidence before cleanup/review.",
                [
                    "dispatch aiwf-tester as a separate subagent/session",
                    "record testing only after real tester evidence and commands exist",
                ],
                [
                    "do not let planner-main roleplay Tester",
                    "do not dispatch Reviewer before testing is adequate",
                    "do not hand-edit testing.json as proof",
                ],
            )
        if testing.get("full_suite_status", "not_run") == "not_run" or testing.get("real_usage_status", "not_run") == "not_run":
            return _blocked(
                "quality_gap",
                "tester",
                "disposition full suite and real usage validation",
                "For L2/L3, unit tests alone are insufficient without full-suite and user-facing entrypoint disposition.",
                [
                    "run or explicitly disposition the full project suite",
                    "run or explicitly disposition an actual user-facing entrypoint",
                    "if impossible, record the reason and ask the user before accepting residual risk",
                ],
                ["do not proceed to review with undispositioned validation layers"],
                user_decision_required=True,
            )
        if not review.get("cleanup_verified_at"):
            return _blocked(
                "wrong_order",
                "planner",
                "verify cleanup before Reviewer",
                "Review must critique the cleaned implementation, not stale/generated leftovers.",
                [
                    "run cleanup checks",
                    "run aiwf state mark-cleanup-fresh after cleanup is verified",
                    "then dispatch independent Reviewer",
                ],
                ["do not dispatch Reviewer before cleanup is verified"],
            )
        if review.get("result") != "accepted":
            return _blocked(
                "missing_step",
                "reviewer",
                "dispatch independent Reviewer",
                "L2/L3 requires adversarial review after testing and cleanup.",
                [
                    "dispatch aiwf-reviewer as a separate subagent/session",
                    "record accepted review only after evidence-first contract critique",
                ],
                [
                    "do not let planner-main roleplay Reviewer",
                    "do not close without accepted review",
                ],
            )
        pending = [
            o for o in (review.get("adversarial_observations", []) or [])
            if isinstance(o, dict) and o.get("disposition") == "pending"
        ]
        if pending:
            return _blocked(
                "missing_step",
                "planner",
                "disposition adversarial observations",
                "Planner meta-critique must accept, reject, defer, or convert review observations before close.",
                [
                    "record structured dispositions for pending adversarial observations",
                    "turn accepted follow-ups into scoped tasks or explicit deferrals",
                ],
                ["do not prepare-close while adversarial observations are pending"],
            )
        return {
            "state": "ready",
            "category": "close",
            "owner": "planner",
            "primary": "close task and prepare-close",
            "legal_options": [
                "run aiwf task close <TASK-ID>",
                "run aiwf state prepare-close",
            ],
            "forbidden": ["do not skip task close before prepare-close"],
            "user_decision_required": False,
            "why": "Testing, cleanup, and review are complete for the active task.",
        }

    return _base_recovery()


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
    request_mode = state.get("request_mode", "execution")
    workflow_pattern = state.get("workflow_pattern", "linear")
    active_task = state.get("active_task_id")
    brief = goal.get("quality_brief", {}) or {}
    evaluation = brief.get("evaluation_contract", {}) or {}
    architecture = brief.get("architecture_brief", {}) or {}
    required: List[str] = []
    conditional: List[str] = []
    advisory: List[str] = []

    try:
        from .workflow_patterns import guidance_for_state, mode_activation_blocker
        mode_hint = guidance_for_state(state)
        mode_blocker = mode_activation_blocker(state)
        if mode_hint:
            advisory.append(mode_hint)
        if mode_blocker:
            required.append(mode_blocker)
    except Exception:
        pass

    if state.get("external_research_required") and request_mode in ("research", "execution"):
        conditional.append(
            "External research is marked required; record low-trust findings with aiwf research record and promote only Planner-approved claims"
        )
        if request_mode == "execution":
            try:
                from .external_research import research_requirement_blocker
                blocker = research_requirement_blocker(base_dir)
                if blocker:
                    required.append(blocker)
            except Exception:
                required.append("External research requirement could not be verified")

    try:
        from .capabilities import capability_use_blockers
        blockers = capability_use_blockers(base_dir)
        required.extend(blockers)
    except Exception:
        pass

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
    if not active_task and request_mode not in ("discussion", "clarification", "research"):
        active_plan = state.get("active_plan_id")
        if active_plan and request_mode == "execution":
            required.append(
                f"Plan-only drift: active plan {active_plan} exists without an active task; "
                "freeze quality/architecture/context contracts, then run "
                f"aiwf task plan {active_plan} ... and aiwf task activate {active_plan}"
            )
        else:
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
        "Use aiwf recipe recommend to choose an advisory workflow template; recipes never override .aiwf JSON gates",
        "Use aiwf plan create/update for human-readable plan.md continuity; the plan artifact is not mechanical truth",
        "Use Curator after closure only when lessons or negative patterns will change future behavior",
        "Use memory suggest when prior lessons may affect this task; suggestions never override current contracts",
        "Treat external community workflows and plugins as capabilities to classify, not as lifecycle replacements",
        "Mechanical signals select minimum depth; Planner must explain semantic risk and may increase depth or breadth",
    ])
    recovery = _recovery_guidance(base_dir, state, goal, testing, review, fix_loop)
    return {
        "workflow_level": level,
        "complexity": state.get("complexity", "standard"),
        "request_mode": request_mode,
        "workflow_pattern": workflow_pattern,
        "pattern_reason": state.get("pattern_reason", ""),
        "external_research_required": bool(state.get("external_research_required")),
        "active_plan_id": state.get("active_plan_id", ""),
        "routing_score": state.get("routing_score", 0),
        "routing_factors": state.get("routing_factors", []) or [],
        "routing_background_factors": state.get("routing_background_factors", []) or [],
        "test_template": state.get("test_template", ""),
        "review_template": state.get("review_template", ""),
        "exploration_budget": state.get("exploration_budget", ""),
        "required_now": required,
        "recovery": recovery,
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
