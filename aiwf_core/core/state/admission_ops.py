"""Change Admission — lightweight entry judgment for new work (Stage 4).

Read-only advisory module. Never mutates state. Given a one-line summary,
recommends: attach_plan (under existing Goal), graft_goal (new Goal through
interface), or temporary_root (ownership unclear).

Pattern: follows impact_ops.py — one public function, defensive imports,
structured return dict, no side effects."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


# Priority-ordered signal categories. First match wins (checked in list order).
# Each entry: (admission, plan_kind, [keywords...])
# Keywords include both English and Chinese (Stage 4.2).
_ALL_SIGNAL_CATEGORIES = [
    # Skeleton change — graft_goal
    ("graft_goal", "structural", [
        # EN
        "new capability", "new feature", "new module", "new system",
        "new component", "structural change", "architecture", "redesign",
        "restructure", "interface change", "API change", "boundary change",
        "add support for", "introduce",
        # ZH
        "新能力", "新增能力", "新增", "新功能", "新模块", "新系统", "新组件",
        "架构", "重构", "重设计",
        "接口改变", "API改变", "边界改变",
        "嫁接", "功能骨架", "功能单元",
    ]),
    # Ownership unclear — temporary_root
    ("temporary_root", "", [
        # EN
        "experiment", "explore", "spike", "trial", "prototype",
        "unsure", "unclear", "investigate", "research",
        "maybe", "possibly", "could", "alternative",
        # ZH
        "探索", "实验", "试验", "原型", "试探",
        "不确定", "不清楚", "调研", "研究",
        "可能", "备选", "也许",
    ]),
    # Interface/structural change — graft_goal
    ("graft_goal", "structural", [
        # EN
        "interface", "API", "boundary", "contract", "skeleton",
        "functional unit", "capability surface",
        # ZH
        "接口", "边界", "契约", "骨架",
    ]),
    # Local improvement — attach_plan (implementation)
    ("attach_plan", "implementation", [
        # EN
        "fix", "patch", "update", "improve", "enhance", "refactor",
        "optimize", "cleanup", "bug", "typo", "error", "regression",
        "performance", "implement", "build", "add",
        # ZH
        "修复", "修改", "优化", "改进", "增强",
        "清理", "补丁", "错误", "回归",
        "性能", "实现", "构建", "添加",
    ]),
    # Verification — attach_plan (verification)
    ("attach_plan", "verification", [
        # EN
        "test", "verify", "validate", "coverage",
        # ZH
        "测试", "验证", "覆盖率",
    ]),
    # Migration — attach_plan (migration)
    ("attach_plan", "migration", [
        # EN
        "migrate", "migration", "upgrade", "convert",
        # ZH
        "迁移", "升级", "转换",
    ]),
]


def _detect_signals(summary_lower: str) -> Dict[str, Any]:
    """Scan summary for keyword signals and return the highest-priority match."""
    found_all: List[Dict[str, Any]] = []

    for category in _ALL_SIGNAL_CATEGORIES:
        admission, plan_kind, keywords = category
        for kw in keywords:
            if kw in summary_lower:
                found_all.append({
                    "admission": admission,
                    "plan_kind": plan_kind,
                    "keyword": kw,
                })

    if not found_all:
        # Default: local implementation
        return {"admission": "attach_plan", "plan_kind": "implementation",
                "keyword": "(default — no signals detected)"}

    # Highest priority signal wins (first in _ALL_SIGNAL_CATEGORIES order)
    return found_all[0]


def _find_best_goal(base_dir: str, summary_lower: str) -> Dict[str, Any]:
    """Find the best-matching existing Goal for this change.

    Returns {goal_id, title, match_score} or empty dict.
    """
    try:
        from .goal_tree_ops import list_goals
        goals = list_goals(base_dir)
    except Exception:
        return {}

    if not goals:
        return {}

    best = {}
    best_score = 0

    for g in goals:
        if not isinstance(g, dict):
            continue
        gid = g.get("id", "")
        title = str(g.get("title", "") or "").lower()
        intent = str(g.get("intent", "") or "").lower()
        if g.get("root_type") == "temporary":
            continue  # skip temporary roots for matching

        # Simple word overlap scoring
        goal_words = set(title.split() + intent.split())
        summary_words = set(summary_lower.split())
        overlap = len(goal_words & summary_words)
        # Bonus for words appearing in goal id
        id_bonus = 1 if any(w in gid.lower() for w in summary_words) else 0

        score = overlap + id_bonus
        if score > best_score:
            best_score = score
            best = {"goal_id": gid, "title": g.get("title", ""),
                    "match_score": score}

    return best


def _check_goals_empty(base_dir: str) -> bool:
    """Check if goals.json exists and has entries."""
    try:
        from .goal_tree_ops import load_goal_tree
        tree = load_goal_tree(base_dir, auto_create=False)
        return not bool(tree.get("goals"))
    except Exception:
        return True


def _build_next_commands(admission: str, target_goal_id: str,
                         plan_kind: str, summary: str) -> List[str]:
    """Generate suggested CLI commands based on admission result."""
    commands = []
    if admission == "attach_plan":
        kind_flag = f"--kind {plan_kind}" if plan_kind else ""
        commands.append(
            f"aiwf plan create PLAN-XXX "
            f"--target-goal {target_goal_id} {kind_flag} "
            f'--title "{summary[:80]}"'
        )
    elif admission == "graft_goal":
        commands.append(
            f"aiwf goal-tree init-root NEW-GOAL --type temporary "
            f'--title "{summary[:80]}"'
        )
        if target_goal_id:
            commands.append(
                f"aiwf goal-tree graft NEW-GOAL --target {target_goal_id} "
                f'--interface "..." --provides "..." --relation-to-parent "extends"'
            )
        commands.append(
            f"aiwf plan create PLAN-STRUCT --target-goal NEW-GOAL "
            f'--kind structural --title "Define: {summary[:60]}"'
        )
    elif admission == "temporary_root":
        commands.append(
            f"aiwf goal-tree init-root TMP-XXX --type temporary "
            f'--title "{summary[:80]}"'
        )
    return commands


def admit_change(base_dir: str, summary: str,
                 target_goal_hint: str = "") -> Dict[str, Any]:
    """Recommend a change admission path for a new work item.

    Args:
        base_dir: Project root directory.
        summary: One-line description of the proposed change.
        target_goal_hint: Optional preferred target goal ID.

    Returns:
        Dict with keys: admission, target_goal_id, target_goal_title,
        plan_kind, reason, impact, confidence, signals_found, notes,
        next_commands.
    """
    if not summary or not summary.strip():
        return {
            "admission": "unknown",
            "target_goal_id": "",
            "target_goal_title": "",
            "plan_kind": "",
            "reason": "empty summary — cannot judge admission path",
            "impact": "unknown",
            "confidence": "none",
            "signals_found": [],
            "notes": ["Provide a one-line summary describing the change."],
            "next_commands": [],
        }

    summary_lower = summary.strip().lower()
    notes: List[str] = []

    # Check if goals.json is empty — if so, suggest creating root first
    goals_empty = _check_goals_empty(base_dir)

    # Detect signals
    signal = _detect_signals(summary_lower)
    admission = signal["admission"]
    plan_kind = signal["plan_kind"]
    keyword = signal["keyword"]
    signals_found = [keyword]
    notes = []

    # Find best matching goal
    best_goal = _find_best_goal(base_dir, summary_lower)

    # Resolve target_goal_id
    if target_goal_hint:
        target_goal_id = target_goal_hint
        target_goal_title = ""
    elif best_goal:
        target_goal_id = best_goal["goal_id"]
        target_goal_title = best_goal["title"]
    else:
        target_goal_id = "GOAL-001"
        target_goal_title = ""

    # If goals.json is empty, add a note but keep the original admission.
    # Only force temporary_root when admission would be graft_goal (can't graft
    # into an empty tree — create main root first).
    if goals_empty:
        notes = [
            "goals.json is empty — create a root Goal first. "
            "See docs/DAY1_FOUNDATION_TREE.md for the Day-1 Foundation Tree process."
        ]
        target_goal_id = "GOAL-001"
        target_goal_title = ""
        if admission == "graft_goal":
            # Grafting into empty tree doesn't make sense; create root first
            admission = "attach_plan"
            plan_kind = "structural"
            notes.append(
                "Skeleton change detected but tree is empty. "
                "Create main root Goal first, then graft the new Goal."
            )

    # Fallback for empty goal matching
    if not target_goal_id and admission != "graft_goal":
        target_goal_id = "GOAL-001"

    # Override target_goal_id for graft_goal — needs a new goal
    if admission == "graft_goal":
        notes.append(
            "Create a new Goal and graft it through interface. "
            "Do NOT attach directly to an existing Goal without grafting."
        )

    # Build reason and impact strings
    if admission == "attach_plan":
        reason = f"signal '{keyword}' — modifies implementation under existing functional skeleton"
        impact = "local, no new Goal needed"
        confidence = "medium" if (best_goal or target_goal_hint) else "low"
        if not best_goal and not target_goal_hint:
            notes.append(
                "No matching Goal found in tree; target defaults to GOAL-001. "
                "Verify this is the correct parent Goal."
            )
    elif admission == "graft_goal":
        reason = f"signal '{keyword}' — changes the functional skeleton; new Goal must be grafted through interface"
        impact = "structural — adds/restructures a functional unit"
        confidence = "medium"
        notes.append(
            "Select a parent Goal that the new Goal extends. "
            "Declare: interface consumed, capability provided, relation to parent."
        )
    elif admission == "temporary_root":
        reason = f"signal '{keyword}' — ownership unclear; exploration needed before stable graft"
        impact = "exploratory — must be grafted or pruned before closure"
        confidence = "low"
        notes.append(
            "Temporary Roots are trial branches. "
            "They do not appear in status --prompt and must be grafted "
            "into the main tree or pruned when the exploration concludes."
        )

    # Downgrade: keyword heuristic is non-authoritative (Stage 4.2)
    notes.insert(0,
        "Heuristic recommendation only. Do not treat as authoritative. "
        "Use Admission Protocol for the final decision (see docs/CHANGE_ADMISSION.md)."
    )

    # Generate next commands
    next_commands = _build_next_commands(admission, target_goal_id, plan_kind, summary)

    return {
        "admission": admission,
        "target_goal_id": target_goal_id,
        "target_goal_title": target_goal_title,
        "plan_kind": plan_kind,
        "reason": reason,
        "impact": impact,
        "confidence": confidence,
        "signals_found": signals_found,
        "notes": notes,
        "next_commands": next_commands,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Stage 4.2: Semantic Admission Decision Validator
# ═══════════════════════════════════════════════════════════════════════════

VALID_ADMISSION_TYPES = {"attach_plan", "graft_goal", "temporary_root"}
VALID_PLAN_KINDS = {"structural", "implementation", "verification", "migration", "exploration"}
VALID_ACTIVE_PHASES = {"framing", "implementation", "integration", "seal"}
VALID_CONFIDENCE_LEVELS = {"low", "medium", "high"}


def validate_admission_decision(base_dir: str,
                                decision: Dict[str, Any]) -> Dict[str, Any]:
    """Validate an Admission Decision against structural constraints.

    This is a MACHINE validator — it checks field presence, reference
    integrity, and constraint coherence. It does NOT make semantic
    judgments about whether the admission_type is "correct."

    Args:
        base_dir: Project root directory.
        decision: A dict matching the Admission Decision schema.

    Returns:
        {valid: bool, issues: [...], warnings: [...]}
    """
    issues: List[str] = []
    warnings: List[str] = []

    at = str(decision.get("admission_type") or decision.get("admission") or "")
    if at not in VALID_ADMISSION_TYPES:
        issues.append(
            f"invalid admission_type: '{at}'. "
            f"Must be one of: {', '.join(sorted(VALID_ADMISSION_TYPES))}"
        )
        return {"valid": False, "issues": issues, "warnings": warnings}

    # ── Common fields ──
    reason = str(decision.get("reason") or "")
    if not reason:
        issues.append("reason is required for all admission types")

    confidence = str(decision.get("confidence") or "medium")
    if confidence not in VALID_CONFIDENCE_LEVELS:
        issues.append(f"invalid confidence: '{confidence}'. Must be low/medium/high")

    human_confirm = decision.get("needs_human_confirmation")
    if confidence == "low" and not human_confirm:
        warnings.append(
            "confidence=low but needs_human_confirmation is not true. "
            "Low-confidence decisions should be confirmed by a human."
        )

    plan_kind = str(decision.get("plan_kind") or "")

    # ── attach_plan validation ──
    if at == "attach_plan":
        tgid = str(decision.get("target_goal_id") or "")
        if not tgid:
            issues.append("attach_plan requires target_goal_id")
        else:
            _validate_goal_exists(base_dir, tgid, issues, warnings)

        tpid = str(decision.get("target_plan_id") or "")
        granularity = str(decision.get("action_granularity") or "plan")

        if granularity not in ("patch", "task", "plan"):
            issues.append(f"invalid action_granularity: '{granularity}'. Must be patch/task/plan")

        if granularity == "plan":
            # New Plan required — validate plan_kind
            if not plan_kind:
                issues.append("action_granularity=plan requires plan_kind")
            elif plan_kind not in VALID_PLAN_KINDS:
                issues.append(
                    f"invalid plan_kind: '{plan_kind}'. "
                    f"Must be one of: {', '.join(sorted(VALID_PLAN_KINDS))}"
                )
        elif granularity in ("patch", "task"):
            # Lightweight — must have target_plan_id or active_plan_id
            if not tpid:
                # Check if there's an active plan
                try:
                    from .plan_ops import load_plans
                    plans_data = load_plans(base_dir)
                    active_plan_id = plans_data.get("active_plan_id", "")
                    if not active_plan_id:
                        warnings.append(
                            f"action_granularity={granularity} but no target_plan_id "
                            f"and no active plan. Patch/task needs an existing Plan to attach to. "
                            f"Set target_plan_id or activate a plan first."
                        )
                except Exception:
                    warnings.append(
                        f"action_granularity={granularity} but no target_plan_id provided."
                    )

        active_phase = str(decision.get("active_phase") or "")
        if active_phase and active_phase not in VALID_ACTIVE_PHASES:
            issues.append(
                f"invalid active_phase: '{active_phase}'. "
                f"Must be one of: {', '.join(sorted(VALID_ACTIVE_PHASES))}"
            )

    # ── graft_goal validation ──
    if at == "graft_goal":
        tpid = str(decision.get("target_parent_goal_id") or "")
        if not tpid:
            issues.append("graft_goal requires target_parent_goal_id")
        else:
            _validate_goal_exists(base_dir, tpid, issues, warnings)

        ic = str(decision.get("interface_consumed") or "")
        if not ic:
            issues.append("graft_goal requires interface_consumed")

        cp = str(decision.get("capability_provided") or "")
        if not cp:
            issues.append("graft_goal requires capability_provided")

        rtp = str(decision.get("relation_to_parent") or "")
        if not rtp:
            issues.append("graft_goal requires relation_to_parent")

        if plan_kind and plan_kind not in VALID_PLAN_KINDS:
            issues.append(f"invalid plan_kind: '{plan_kind}'")

    # ── temporary_root validation ──
    if at == "temporary_root":
        ngt = str(decision.get("new_goal_title") or "")
        if not reason and not ngt:
            warnings.append(
                "temporary_root should have reason or new_goal_title"
            )

    # ── affected_plan_ids must exist ──
    affected = decision.get("affected_plan_ids") or []
    if affected:
        try:
            from .plan_ops import plan_exists
            for pid in affected:
                if not plan_exists(base_dir, str(pid)):
                    warnings.append(
                        f"affected_plan_id '{pid}' does not exist in plans.json"
                    )
        except Exception:
            pass

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
        "admission_type": at,
    }


def _validate_goal_exists(base_dir: str, goal_id: str,
                          issues: List[str], warnings: List[str]) -> None:
    """Check a goal_id exists in goals.json, with GOAL-001 fallback."""
    if goal_id == "GOAL-001":
        from .goal_tree_ops import load_goal_tree
        tree = load_goal_tree(base_dir, auto_create=False)
        if not tree.get("goals"):
            return  # Empty registry — GOAL-001 is valid fallback

    try:
        from .goal_tree_ops import goal_exists
        if not goal_exists(base_dir, goal_id):
            issues.append(
                f"target goal '{goal_id}' does not exist in goals.json"
            )
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# Stage 4.3: Admission-to-Action Plan — human action plan + operation plan
# ═══════════════════════════════════════════════════════════════════════════

_ENTRY_TITLES = {
    "attach_plan": "Attach Plan under existing Goal",
    "graft_goal": "Graft new Goal through interface",
    "temporary_root": "Temporary Root for exploration",
}

_ENTRY_SUMMARIES = {
    "attach_plan": "Add a Plan under an existing Goal without changing the functional skeleton.",
    "graft_goal": "Create a new Goal and graft it into the Goal Tree through a declared interface.",
    "temporary_root": "Create a trial branch outside the main tree until ownership is clear.",
}

_GRANULARITY_LABELS = {
    "patch": "Lightweight Patch — typo, wording, minor test assertion, one-line fix",
    "task": "Single Task — needs execution and verification, but not a new Plan",
    "plan": "New Plan — multi-step change with boundaries, acceptance, and review",
}

_GRANULARITY_SUMMARIES = {
    "patch": "Reuse existing Plan. Record as a lightweight patch under it.",
    "task": "Reuse existing Plan. Create a Task under it for independent verification.",
    "plan": "Requires a new Plan — the change has its own scope, boundaries, and acceptance.",
}

_PLAN_KIND_LABELS = {
    "structural": "Structure Plan — defines module boundaries, interfaces, and architecture",
    "implementation": "Implementation Plan — builds functionality under existing architecture",
    "verification": "Verification Plan — tests, validates, or audits existing work",
    "migration": "Migration Plan — moves data, schemas, or systems between states",
    "exploration": "Exploration Plan — investigates or prototypes without production commitment",
}

_PHASE_LABELS = {
    "framing": "Framing — define what this Plan changes and how",
    "implementation": "Implementation — build and test the change",
    "integration": "Integration — reconcile outputs, prepare for sealing",
    "seal": "Seal — close the Plan and roll up evidence to Goal",
}


def _build_graft_risk(decision: Dict[str, Any]) -> List[str]:
    risks = []
    if decision.get("whether_parent_meaning_changes"):
        risks.append("Changes parent Goal's meaning — structural review required.")
    if decision.get("affected_plan_ids"):
        plist = decision.get("affected_plan_ids", []) or []
        risks.append(f"Affects existing Plans: {', '.join(plist)} — check for conflicts.")
    if not risks:
        risks.append("Adds a new functional unit — verify interface contract with parent Goal.")
    return risks


def _build_attach_risk(decision: Dict[str, Any]) -> List[str]:
    risks = []
    pk = str(decision.get("plan_kind") or "")
    if pk == "structural":
        risks.append("Structural Plan — may redefine interface or boundary. Review before implementation.")
    if pk == "migration":
        risks.append("Migration Plan — may modify existing data or schemas. Checkpoint recommended.")
    if not risks:
        risks.append("Local scope — routine review is sufficient.")
    return risks


def _build_temp_risk(decision: Dict[str, Any]) -> List[str]:
    return [
        "Temporary Root — not yet integrated into the functional skeleton.",
        "Must be grafted or pruned before this work stream closes.",
        "Does not appear in status --prompt. Remember to revisit.",
    ]


def prepare_action_plan(base_dir: str, decision: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a validated Admission Decision into a reviewable Action Plan.

    Produces TWO layers:
    1. human_action_plan — structured prose for human review
    2. operation_plan — structured ops for machine/adapter consumption

    Neither layer contains raw shell commands by default.
    Does NOT mutate state.

    Returns:
        {valid, human_action_plan, operation_plan, warnings}
    """
    validation = validate_admission_decision(base_dir, decision)
    if not validation["valid"]:
        return {
            "valid": False,
            "admission_type": validation.get("admission_type", "unknown"),
            "validation_issues": validation["issues"],
            "human_action_plan": None,
            "operation_plan": None,
            "warnings": validation.get("warnings", []),
        }

    at = validation["admission_type"]
    reason = str(decision.get("reason") or "")
    impact = str(decision.get("impact_notes") or "")
    confidence = str(decision.get("confidence") or "medium")
    human_confirm = bool(decision.get("needs_human_confirmation"))
    requires_confirm = confidence == "low" or human_confirm

    warnings: List[str] = list(validation.get("warnings", []) or [])
    risks: List[str] = []
    ops: List[Dict[str, Any]] = []

    # ── Build human action plan ──
    title = _ENTRY_TITLES.get(at, at)
    summary = _ENTRY_SUMMARIES.get(at, "")

    # Resolve target goal info
    tgid = ""
    tpid = ""
    if at == "attach_plan":
        tgid = str(decision.get("target_goal_id") or "")
    elif at == "graft_goal":
        tpid = str(decision.get("target_parent_goal_id") or "")

    # Try to get goal titles
    tg_title = ""
    tp_title = ""
    try:
        from .goal_tree_ops import get_goal
        if tgid:
            g = get_goal(base_dir, tgid)
            tg_title = str(g.get("title", "") or "")
        if tpid:
            g = get_goal(base_dir, tpid)
            tp_title = str(g.get("title", "") or "")
    except Exception:
        pass

    ngt = str(decision.get("new_goal_title") or "")
    pk = str(decision.get("plan_kind") or "")
    phase = str(decision.get("active_phase") or "")
    pk_label = _PLAN_KIND_LABELS.get(pk, pk) if pk else ""
    phase_label = _PHASE_LABELS.get(phase, phase) if phase else ""

    # ── attach_plan ──
    if at == "attach_plan":
        granularity = str(decision.get("action_granularity") or "plan")
        target_plan_id = str(decision.get("target_plan_id") or "")

        if granularity == "patch":
            risks = [
                "Lightweight patch — local change, no new structure needed.",
                f"Belongs to existing Plan{f' {target_plan_id}' if target_plan_id else ''}.",
            ]
            ops.append({
                "op": "record_patch",
                "target_goal_id": tgid,
                "target_plan_id": target_plan_id,
                "reason": reason,
                "impact": "local — no new Plan or Task required",
            })
        elif granularity == "task":
            risks = [
                "Single task under existing Plan.",
                "Needs execution and verification but does not change Plan scope.",
            ]
            ops.append({
                "op": "create_task",
                "target_goal_id": tgid,
                "target_plan_id": target_plan_id,
                "reason": reason,
            })
        else:
            risks = _build_attach_risk(decision)
            ops.append({
                "op": "create_plan",
                "target_goal_id": tgid,
                "plan_kind": pk or "implementation",
                "active_phase": phase or "implementation",
                "reason": reason,
            })

    # ── graft_goal ──
    elif at == "graft_goal":
        risks = _build_graft_risk(decision)
        ic = str(decision.get("interface_consumed") or "")
        cp = str(decision.get("capability_provided") or "")
        rtp = str(decision.get("relation_to_parent") or "")
        existing_tmp = str(decision.get("existing_temporary_root_id") or "")

        if existing_tmp:
            ops.append({
                "op": "graft_goal",
                "source_goal_id": existing_tmp,
                "target_parent_goal_id": tpid,
                "interface_consumed": ic,
                "capability_provided": cp,
                "relation_to_parent": rtp,
                "reason": reason,
            })
        else:
            ops.append({
                "op": "create_temporary_root",
                "title": ngt,
                "reason": f"Trial root for: {ngt}",
            })
            ops.append({
                "op": "graft_goal",
                "source_goal_id": "TMP-XXX",
                "target_parent_goal_id": tpid,
                "interface_consumed": ic,
                "capability_provided": cp,
                "relation_to_parent": rtp,
                "reason": reason,
            })
        ops.append({
            "op": "create_plan",
            "target_goal_id": existing_tmp if existing_tmp else "TMP-XXX",
            "plan_kind": "structural",
            "active_phase": "framing",
            "reason": f"Frame new Goal: {ngt}",
        })

    # ── temporary_root ──
    elif at == "temporary_root":
        risks = _build_temp_risk(decision)
        ops.append({
            "op": "create_temporary_root",
            "title": ngt or "Exploration",
            "reason": reason or "Ownership unclear — trial growth needed",
        })

    # ── Situation warnings ──
    if confidence == "low":
        warnings.append("Confidence is low — human confirmation required before proceeding.")
    if human_confirm:
        warnings.append("needs_human_confirmation is true — confirm before proceeding.")
    pmc = decision.get("whether_parent_meaning_changes")
    if pmc is True or str(pmc or "").lower() in ("true", "yes", "1"):
        warnings.append("Parent meaning changes — structural review required.")
    affected = decision.get("affected_plan_ids") or []
    if affected:
        warnings.append(f"Affected Plans: {', '.join(affected)} — impact review recommended.")

    # ── Human action plan ──
    human = {
        "entry_type": at,
        "title": title,
        "summary": summary,
        "reason": reason,
        "impact_notes": impact,
        "risks": risks,
        "requires_confirmation": requires_confirm,
        "next_review_focus": "",
    }

    if at == "attach_plan":
        granularity = str(decision.get("action_granularity") or "plan")
        target_plan_id = str(decision.get("target_plan_id") or "")
        human["action_granularity"] = granularity
        human["granularity_label"] = _GRANULARITY_LABELS.get(granularity, "")
        human["granularity_summary"] = _GRANULARITY_SUMMARIES.get(granularity, "")
        if target_plan_id:
            human["target_plan_id"] = target_plan_id

        human["target_goal_id"] = tgid
        human["target_goal_title"] = tg_title

        if granularity == "plan":
            human["plan_kind"] = pk
            human["plan_kind_label"] = pk_label
            human["active_phase"] = phase or "implementation"
            human["active_phase_label"] = phase_label if phase else _PHASE_LABELS["implementation"]
            review_parts = [f"Plan kind: {pk_label}"]
            if pk == "structural":
                review_parts.append("Check that interface and boundary changes are explicit")
            human["next_review_focus"] = ". ".join(review_parts) + "."
        elif granularity == "patch":
            human["plan_kind"] = pk or ""
            review_parts = [
                f"Lightweight patch under existing Plan{f' {target_plan_id}' if target_plan_id else ''}.",
                "Verify the change is local and does not alter Plan scope or Goal meaning.",
            ]
            human["next_review_focus"] = " ".join(review_parts)
        elif granularity == "task":
            human["plan_kind"] = pk or ""
            review_parts = [
                f"Single task under existing Plan{f' {target_plan_id}' if target_plan_id else ''}.",
                "Verify task has independent acceptance criteria.",
            ]
            human["next_review_focus"] = " ".join(review_parts)

    elif at == "graft_goal":
        human["target_parent_goal_id"] = tpid
        human["target_parent_goal_title"] = tp_title
        human["new_goal_title"] = ngt
        human["interface_consumed"] = str(decision.get("interface_consumed") or "")
        human["capability_provided"] = str(decision.get("capability_provided") or "")
        human["relation_to_parent"] = str(decision.get("relation_to_parent") or "")
        human["next_review_focus"] = (
            f"Verify interface contract: {human['interface_consumed']} → {human['capability_provided']}. "
            f"Check that parent Goal {tpid} meaning is preserved."
        )

    elif at == "temporary_root":
        human["new_goal_title"] = ngt
        human["next_review_focus"] = (
            "What would clarify ownership? Set a criterion for graft-or-prune decision."
        )

    # ── Operation plan ──
    operation_plan = {
        "operation_plan_version": 1,
        "operations": ops,
        "mutates_state": False,
        "execution_requires_confirmation": requires_confirm,
    }

    return {
        "valid": True,
        "admission_type": at,
        "human_action_plan": human,
        "operation_plan": operation_plan,
        "warnings": warnings,
    }
