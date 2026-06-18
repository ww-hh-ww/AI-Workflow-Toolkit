"""Resource-based workflow routing with L0–L3 levels and scoring.

V2-A adds topology dimensions (verification_need, execution_topology, review_need),
granular prior_fix_loop and semantic_change classification, machine_verifiable
detection, and a recorded downgrade/substitution protocol.
"""
from __future__ import annotations
from typing import Dict, List, Optional, Tuple


# ── workflow levels (V1, preserved) ──
# L0: executor only, self-test, minimal review, terse report
# L1: executor + reviewer-light (also does light testing), light gates, short report
# L2: executor + tester + reviewer, light cleanup/structure, normal report
# L3: full team + asset-first + full cleanup/structure + human decisions, full report

LEVELS = {
    "L0_direct": {
        "label": "L0 — Direct",
        "executor": True, "tester": False, "reviewer": False,
        "reviewer_light": False, "asset_first": False,
        "cleanup_depth": "none", "structure_depth": "none",
        "report_depth": "terse", "max_fix_loops": 0, "max_review_rounds": 1,
    },
    "L1_review_light": {
        "label": "L1 — Review-Light",
        "executor": True, "tester": False, "reviewer": False,
        "reviewer_light": True, "asset_first": False,
        "cleanup_depth": "light", "structure_depth": "light",
        "report_depth": "short", "max_fix_loops": 1, "max_review_rounds": 1,
    },
    "L2_standard_team": {
        "label": "L2 — Standard Team",
        "executor": True, "tester": True, "reviewer": True,
        "reviewer_light": False, "asset_first": False,
        "cleanup_depth": "light", "structure_depth": "light",
        "report_depth": "normal", "max_fix_loops": 2, "max_review_rounds": 2,
    },
    "L3_full_power": {
        "label": "L3 — Full Power",
        "executor": True, "tester": True, "reviewer": True,
        "reviewer_light": False, "asset_first": True,
        "cleanup_depth": "full", "structure_depth": "full",
        "report_depth": "full", "max_fix_loops": 3, "max_review_rounds": 4,
    },
}

INVARIANT_GATES = [
    "scope_before_code", "evidence_before_summary", "test_before_review",
    "review_before_close", "close_attempt_based_stop_gate",
]

# ── V2-A topology dimensions ──

VERIFICATION_NEEDS = [
    "deterministic",   # machine-verifiable: neg/pos validation, diff check
    "standard",        # normal testing: targeted + regression
    "broad",           # broad regression + boundary + adverse
    "adversarial",     # full adversarial matrix
]

EXECUTION_TOPOLOGIES = [
    "single_agent",                        # one agent does everything
    "single_agent_with_machine_evidence",  # one agent + machine-verifiable output
    "light_review",                        # executor + reviewer-light
    "standard_team",                       # executor + tester + reviewer
    "fanout_merge",                        # parallel agents + merge
]

# workflow_level → execution_topology: the canonical stored field is level.
# Topology is derived from level on every read — never stored independently.
LEVEL_TO_TOPOLOGY = {
    "L0_direct": "single_agent",
    "L1_review_light": "light_review",
    "L2_standard_team": "standard_team",
    "L3_full_power": "fanout_merge",
}

# topology → workflow_level: used by route downgrade to validate and map.
TOPOLOGY_TO_LEVEL = {
    "single_agent": "L0_direct",
    "single_agent_with_machine_evidence": "L1_review_light",
    "light_review": "L1_review_light",
    "standard_team": "L2_standard_team",
    "fanout_merge": "L3_full_power",
}

REVIEW_NEEDS = [
    "none",                    # self-review ok
    "optional_light_review",   # reviewer-light combines targeted testing + light review
    "required_review",         # independent review required
    "adversarial_review",      # adversarial multi-lens review required
]

# ── routing factors ──
FACTORS = {
    "file_count_1_2": 0, "file_count_3_5": 1, "file_count_6_plus": 2,
    "cross_module": 2, "public_api_change": 2, "semantic_change": 2,
    "historical_deferred_risk": 1, "security_or_data_risk": 3,
    "test_matrix_complexity": 1, "user_decision_needed": 2,
    "architecture_impact": 2, "prior_fix_loop": 2,
    "destructive_command": 3, "publish_or_deploy": 3, "data_migration": 3,
}

# ── V2-A granular factors ──
# Prior fix-loop tiers (split from single "prior_fix_loop" = 2)
FIX_LOOP_FACTORS = {
    "prior_fix_loop_active": 3,          # current unresolved fix-loop — hard L2
    "prior_fix_loop_same_task": 3,       # resolved, same task — hard L2
    "prior_fix_loop_same_file": 2,       # resolved, same file touched — hard L2
    "prior_fix_loop_same_module": 1,     # resolved, same module — advisory +1
    "prior_fix_loop_history": 0,         # stale/unrelated — background only
}

# Semantic change tiers (split from single "semantic_change" = 2)
SEMANTIC_FACTORS = {
    "semantic_mechanical": 1,     # validator grep, template filler, sed fix
    "semantic_contract": 2,       # test contract, I/O contract, audit rules
    "semantic_core_gate": 3,      # close gate, scope guard, fix-loop, trust schema
}

# New detection factors
DETECTION_FACTORS = {
    "machine_verifiable": -1,     # reduces topology need when machine can verify
}

# Merge all factor weights
ALL_FACTORS_V2 = {}
ALL_FACTORS_V2.update(FACTORS)
ALL_FACTORS_V2.update(FIX_LOOP_FACTORS)
ALL_FACTORS_V2.update(SEMANTIC_FACTORS)
ALL_FACTORS_V2.update(DETECTION_FACTORS)

HARD_UPGRADES = {
    "destructive_command": "L3_full_power",
    "publish_or_deploy": "L3_full_power",
    "data_migration": "L3_full_power",
    "security_or_data_risk": "L3_full_power",
    "user_decision_needed": "L2_standard_team",
    "prior_fix_loop": "L2_standard_team",
    "cross_module_semantic": "L2_standard_team",
}

# V2-A hard upgrades (downgrade forbidden for these).
# prior_fix_loop_same_file is deliberately NOT a hard upgrade — it contributes
# +2 to the routing score but does not force L2. A file having been fixed in a
# prior task is a warning, not a gate. Mechanical changes (add config key, fix
# typo, add dict entry matching existing pattern) on hotspot files should stay
# at their natural level; the Planner can always escalate if needed.
HARD_UPGRADES_V2 = dict(HARD_UPGRADES)
HARD_UPGRADES_V2.update({
    "prior_fix_loop_active": "L2_standard_team",
    "prior_fix_loop_same_task": "L2_standard_team",
    "semantic_core_gate": "L2_standard_team",
})

# Factors that FORBID downgrade entirely.
# Only ACTIVE fix-loops and same-TASK recurrence forbid downgrade.
# prior_fix_loop_same_file is a warning signal (same file had issues in a
# prior task that was already resolved), not a hard constraint — Planner
# may accept the residual risk and proceed at current level.
DOWNGRADE_FORBIDDEN_FACTORS = {
    "security_or_data_risk",
    "destructive_command",
    "publish_or_deploy",
    "data_migration",
    "prior_fix_loop_active",
    "prior_fix_loop_same_task",
    "semantic_core_gate",
}

# Factors that ALLOW substitution (waive topology, keep verification)
SUBSTITUTION_ALLOWED_FACTORS = {
    "machine_verifiable",
    "prior_fix_loop_same_module",
    "prior_fix_loop_history",
    "semantic_mechanical",
}

# Downgrade fatigue: cumulative project-wide user-confirmed downgrades
# harden the gate. Each downgrade is a recorded bypass of system routing.
# After N prior confirmed downgrades, restrictions escalate until the
# project's downgrade quota is exhausted and the system-routed level
# becomes mandatory.
DOWNGRADE_FATIGUE = {
    "express_lane_blocked": 3,      # "mechanical change:" multi-step skip disabled
    "dispatch_plan_required": 5,    # reason must name subagent dispatch plan
    "quota_exhausted": 7,           # hard block — no further downgrades allowed
}

# ── AIWF core gate file patterns ──
CORE_GATE_PATTERNS = [
    "aiwf_core/core/routing.py",
    "aiwf_core/core/task_ledger.py",
    "aiwf_core/core/state_schema.py",
    "aiwf_core/core/state/fixloop_ops.py",
    "aiwf_core/core/state/close_ops.py",
    "aiwf_core/core/quality_policy.py",
    "aiwf_core/core/process_contract.py",
    "aiwf_core/hooks/common/scope_checker.py",
    "aiwf_core/core/trust_schema.py",
]

# ── Contract file patterns (test contracts, I/O contracts, audit rules)
CONTRACT_PATTERNS = [
    "test_", "tests/",
    "release-audit",
    "validator",
    "Makefile",
    ".github/workflows",
    "aiwf_core/core/review_contract.py",
]


def score_to_level(score: int, hard_upgrades: Optional[List[str]] = None) -> str:
    """Map a routing score (and optional hard upgrades) to a workflow level."""
    level = "L0_direct"
    if score <= 1: level = "L0_direct"
    elif score <= 3: level = "L1_review_light"
    elif score <= 6: level = "L2_standard_team"
    else: level = "L3_full_power"

    # Hard upgrades override
    for hu in (hard_upgrades or []):
        mapped = HARD_UPGRADES_V2.get(hu)
        if mapped:
            # Only upgrade, never downgrade
            lvls = ["L0_direct", "L1_review_light", "L2_standard_team", "L3_full_power"]
            if lvls.index(mapped) > lvls.index(level):
                level = mapped
    return level


def classify_semantic_change(allowed_write: List[str]) -> str:
    """Classify the type of semantic change from allowed_write paths.

    Returns one of: 'semantic_core_gate', 'semantic_contract', 'semantic_mechanical', or ''.

    Only returns a V2 classification when confident. Regular code changes
    (most .py/.js/.ts etc. files) return '' and rely on the V1 semantic_change flag.
    """
    if not allowed_write:
        return ""
    paths_lower = [p.lower().replace("\\", "/") for p in allowed_write]

    # Tier 1: core gate files (AIWF state machine, close gates, trust schema)
    for pattern in CORE_GATE_PATTERNS:
        pattern_lower = pattern.lower()
        for p in paths_lower:
            if pattern_lower in p or p.endswith(pattern_lower.replace("aiwf_core/", "")):
                return "semantic_core_gate"

    # Tier 2: contract files (test infra, audit rules, review contracts, CI)
    _contract_indicators = [
        "release-audit", "validator", "Makefile", ".github/workflows",
        "review_contract", "test_contract",
    ]
    for indicator in _contract_indicators:
        for p in paths_lower:
            if indicator in p:
                return "semantic_contract"

    # Tier 3: mechanical files (grep patterns, templates, fixtures, mocks, __init__)
    _mechanical_indicators = [
        "grep", "sed ", ".template", "_template.", "fixture", "conftest",
        "__init__", ".txt", ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini",
    ]
    if all(
        any(ind in p for ind in _mechanical_indicators)
        for p in paths_lower
    ):
        return "semantic_mechanical"

    # Regular code change — no V2 semantic classification
    return ""


def classify_fix_loop(fix_loop: Dict, task_id: str, allowed_write: List[str],
                       prior_task_fix_loops: Optional[List[Dict]] = None) -> Tuple[str, List[str]]:
    """Classify prior fix-loop into granular tiers.

    Returns (primary_factor, [background_factors]).
    """
    background: List[str] = []
    attempt_count = fix_loop.get("attempt_count", 0) or 0
    status = fix_loop.get("status", "none")

    if status == "open":
        return "prior_fix_loop_active", background

    if attempt_count <= 0:
        return "", background

    # Resolved fix-loop: classify by proximity
    source_task = fix_loop.get("source", "") or ""
    if source_task and source_task == task_id:
        return "prior_fix_loop_same_task", background

    # Check same-file proximity
    fix_required = fix_loop.get("required_fixes", []) or []
    fix_files = set()
    for item in fix_required:
        if isinstance(item, dict):
            fp = item.get("file", "") or item.get("path", "")
            if fp:
                fix_files.add(fp.replace("\\", "/").lower())
        elif isinstance(item, str):
            fix_files.add(item.replace("\\", "/").lower())

    allowed_lower = {p.replace("\\", "/").lower() for p in allowed_write}
    if fix_files and allowed_lower:
        if fix_files & allowed_lower:
            return "prior_fix_loop_same_file", background

    # Check same-module proximity
    fix_modules = {f.split("/")[0] for f in fix_files if "/" in f}
    allowed_modules = {p.split("/")[0] for p in allowed_lower if "/" in p}
    if fix_modules and allowed_modules and (fix_modules & allowed_modules):
        return "prior_fix_loop_same_module", background

    # Check prior task fix-loops
    if prior_task_fix_loops:
        for pfl in prior_task_fix_loops:
            pfl_files = set()
            for item in (pfl.get("required_fixes", []) or []):
                if isinstance(item, dict):
                    fp = item.get("file", "") or item.get("path", "")
                    if fp:
                        pfl_files.add(fp.replace("\\", "/").lower())
                elif isinstance(item, str):
                    pfl_files.add(item.replace("\\", "/").lower())
            if pfl_files and allowed_lower and (pfl_files & allowed_lower):
                return "prior_fix_loop_same_file", background
            pfl_modules = {f.split("/")[0] for f in pfl_files if "/" in f}
            if pfl_modules and allowed_modules and (pfl_modules & allowed_modules):
                return "prior_fix_loop_same_module", background

    background.append("prior_fix_loop_history")
    return "", background


def detect_machine_verifiable(allowed_write: List[str], semantic_type: str) -> bool:
    """Determine if a change can be machine-verified.

    Machine-verifiable changes are those where deterministic commands
    (grep, diff, test suite) can conclusively prove correctness.
    """
    if not semantic_type:
        return False  # regular code change — needs human review
    if semantic_type == "semantic_core_gate":
        return False  # gate changes need human review
    if semantic_type == "semantic_contract":
        # Contract changes may be machine-verifiable if they're mechanical
        paths_lower = [p.lower().replace("\\", "/") for p in allowed_write]
        mechanical_indicators = ["validator", "grep", "sed ", "template", "fixture", "mock"]
        return any(
            any(ind in p for ind in mechanical_indicators)
            for p in paths_lower
        )
    # semantic_mechanical: always machine-verifiable by definition
    if semantic_type == "semantic_mechanical":
        return True
    return False


def compute_routing_score(factors: Dict[str, bool], file_count: int = 1) -> Dict:
    """Compute routing score from factor flags and return full routing decision.

    Backward-compatible: always returns workflow_level and budget fields.
    V2-A also populates topology dimensions when V2 factors are present.
    """
    score = 0
    matched = []
    hard: List[str] = []

    if file_count <= 2:
        score += FACTORS["file_count_1_2"]; matched.append("file_count_1_2")
    elif file_count <= 5:
        score += FACTORS["file_count_3_5"]; matched.append("file_count_3_5")
    else:
        score += FACTORS["file_count_6_plus"]; matched.append("file_count_6_plus")

    for factor, flag in factors.items():
        if not flag:
            continue
        weight = ALL_FACTORS_V2.get(factor, FACTORS.get(factor, 0))
        if weight:
            score += weight
        if factor in ALL_FACTORS_V2 or factor in FACTORS:
            matched.append(factor)
        if factor in HARD_UPGRADES_V2:
            hard.append(factor)

    # Special: cross_module + semantic_change -> hard upgrade
    if factors.get("cross_module") and factors.get("semantic_change"):
        hard.append("cross_module_semantic")

    level = score_to_level(score, hard)
    level_info = LEVELS.get(level, LEVELS["L0_direct"])

    result = {
        "workflow_level": level,
        "label": level_info["label"],
        "routing_score": score,
        "routing_factors": matched,
        "hard_upgrades": hard,
        "budget": {
            k: v for k, v in level_info.items()
            if k in ("max_fix_loops", "max_review_rounds", "report_depth",
                      "cleanup_depth", "structure_depth")
        },
        "uses_tester": level_info["tester"],
        "uses_reviewer": level_info["reviewer"],
        "uses_reviewer_light": level_info["reviewer_light"],
        "asset_first": level_info["asset_first"],
        # V2-A topology dimensions
        "verification_need": _derive_verification_need(level, factors, hard),
        "execution_topology": _derive_execution_topology(level, factors, hard),
        "review_need": _derive_review_need(level, factors, hard),
        "downgrade_allowed": _downgrade_allowed(level, factors, hard),
        "substitution_allowed": _substitution_allowed(level, factors, hard),
        "hard_constraints": sorted(set(
            hu for hu in hard
            if hu in DOWNGRADE_FORBIDDEN_FACTORS
        )),
    }
    return result


def _derive_verification_need(level: str, factors: Dict[str, bool],
                               hard: List[str]) -> str:
    """Derive verification_need from risk level and factors."""
    if factors.get("security_or_data_risk") or "security_or_data_risk" in hard:
        return "adversarial"
    if factors.get("semantic_core_gate") or "semantic_core_gate" in hard:
        return "broad"
    if factors.get("machine_verifiable"):
        return "deterministic"
    if level in ("L3_full_power",):
        return "adversarial"
    if level in ("L2_standard_team",):
        return "broad"
    if level == "L1_review_light":
        return "standard"
    return "standard"


def _derive_execution_topology(level: str, factors: Dict[str, bool],
                                hard: List[str]) -> str:
    """Derive execution_topology from risk level and factors."""
    if factors.get("security_or_data_risk") or "security_or_data_risk" in hard:
        return "fanout_merge"
    if factors.get("semantic_core_gate") or "semantic_core_gate" in hard:
        return "standard_team"

    # Machine-verifiable changes can use lighter topology
    if factors.get("machine_verifiable"):
        if level in ("L0_direct", "L1_review_light"):
            return "single_agent_with_machine_evidence"
        if level == "L2_standard_team":
            return "light_review"

    if level == "L0_direct":
        return "single_agent"
    if level == "L1_review_light":
        return "light_review"
    if level in ("L2_standard_team",):
        return "standard_team"
    if level in ("L3_full_power",):
        return "fanout_merge"
    return "light_review"


def _derive_review_need(level: str, factors: Dict[str, bool],
                         hard: List[str]) -> str:
    """Derive review_need from risk level and factors."""
    if factors.get("security_or_data_risk") or "security_or_data_risk" in hard:
        return "adversarial_review"
    if factors.get("semantic_core_gate") or "semantic_core_gate" in hard:
        return "required_review"

    if factors.get("machine_verifiable"):
        if level in ("L0_direct", "L1_review_light"):
            return "optional_light_review"
        if level == "L2_standard_team":
            return "required_review"

    if level == "L0_direct":
        return "none"
    if level == "L1_review_light":
        return "optional_light_review"
    if level in ("L2_standard_team",):
        return "required_review"
    if level in ("L3_full_power",):
        return "adversarial_review"
    return "optional_light_review"


def _downgrade_allowed(level: str, factors: Dict[str, bool],
                        hard: List[str]) -> bool:
    """Check if downgrade from current level is allowed.

    Downgrade is FORBIDDEN when any hard constraint factor is present
    that is in DOWNGRADE_FORBIDDEN_FACTORS.
    """
    for hu in hard:
        if hu in DOWNGRADE_FORBIDDEN_FACTORS:
            return False
    for factor, flag in factors.items():
        if flag and factor in DOWNGRADE_FORBIDDEN_FACTORS:
            return False
    return True


def _substitution_allowed(level: str, factors: Dict[str, bool],
                           hard: List[str]) -> bool:
    """Check if topology substitution is allowed.

    Substitution (waiving topology while keeping verification) is allowed
    when at least one SUBSTITUTION_ALLOWED_FACTORS factor is present
    AND no DOWNGRADE_FORBIDDEN_FACTORS factor is present.
    """
    if not _downgrade_allowed(level, factors, hard):
        return False
    for factor, flag in factors.items():
        if flag and factor in SUBSTITUTION_ALLOWED_FACTORS:
            return True
    return False


def compute_topology_override(
    current_topology: str,
    requested_topology: str,
    factors: Dict[str, bool],
    hard: List[str],
    reason: str,
    downgrade_history_count: int = 0,
) -> Dict:
    """Validate and record a topology override request.

    downgrade_history_count: number of prior user-confirmed downgrades/substitutions
    already recorded in this project. Used to enforce escalating fatigue gates.

    Returns a dict with 'allowed', 'effective_topology', 'reason', 'warnings'.
    """
    warnings: List[str] = []
    allowed = True

    for hu in hard:
        if hu in DOWNGRADE_FORBIDDEN_FACTORS:
            allowed = False
            warnings.append(
                f"Topology override forbidden: hard constraint '{hu}' "
                f"prohibits downgrade/substitution"
            )

    for factor, flag in factors.items():
        if flag and factor in DOWNGRADE_FORBIDDEN_FACTORS:
            allowed = False
            warnings.append(
                f"Topology override forbidden: factor '{factor}' "
                f"prohibits downgrade/substitution"
            )

    if not allowed:
        return {
            "allowed": False,
            "effective_topology": current_topology,
            "reason": reason,
            "warnings": warnings,
        }

    # Validate that the requested topology is appropriate for the risk level
    topo_order = {
        "single_agent": 0,
        "single_agent_with_machine_evidence": 1,
        "light_review": 2,
        "standard_team": 3,
        "fanout_merge": 4,
    }
    current_order = topo_order.get(current_topology, 0)
    requested_order = topo_order.get(requested_topology, 0)

    if requested_order > current_order:
        warnings.append(
            f"Requested topology '{requested_topology}' is higher than "
            f"current '{current_topology}'; upgrade is always allowed"
        )

    # Check substitution validity
    if requested_order < current_order:
        is_mechanical = reason.strip().lower().startswith("mechanical change")
        next_count = downgrade_history_count + 1  # this request would be the Nth

        # ── Downgrade fatigue: cumulative project downgrades harden the gate ──
        if next_count >= DOWNGRADE_FATIGUE["quota_exhausted"]:
            allowed = False
            warnings.append(
                f"DOWNGRADE QUOTA EXHAUSTED: {downgrade_history_count} prior "
                f"user-confirmed downgrades recorded in this project. "
                f"System-routed level '{current_topology}' is now mandatory. "
                f"Dispatch subagents per the routing topology — do not inline."
            )
        elif next_count >= DOWNGRADE_FATIGUE["dispatch_plan_required"]:
            reason_lower = reason.lower()
            has_dispatch_plan = any(
                keyword in reason_lower
                for keyword in ("dispatch", "subagent", "子agent", "executor",
                                "tester", "reviewer", "delegate")
            )
            if not has_dispatch_plan:
                allowed = False
                warnings.append(
                    f"DOWNGRADE #{next_count}: {downgrade_history_count} prior "
                    f"user-confirmed downgrades recorded. Reason MUST include an "
                    f"explicit subagent dispatch plan — name who will execute, "
                    f"test, and review. E.g.: 'dispatch Executor subagent for "
                    f"build.ps1, Tester for CI verification, Reviewer for gate check.'"
                )
        elif next_count >= DOWNGRADE_FATIGUE["express_lane_blocked"]:
            if is_mechanical and current_order - requested_order > 1:
                allowed = False
                warnings.append(
                    f"DOWNGRADE #{next_count}: 'mechanical change:' express lane "
                    f"disabled after {downgrade_history_count} prior user-confirmed "
                    f"downgrades. Downgrade ONE level at a time "
                    f"(from '{current_topology}' to the next level down, "
                    f"not directly to '{requested_topology}')."
                )

        # Single-step limit: downgrade one level at a time, unless the
        # downgrade is for a mechanical change (explicitly scoped by Planner).
        if current_order - requested_order > 1 and not is_mechanical:
            allowed = False
            warnings.append(
                f"Topology downgrade from '{current_topology}' to "
                f"'{requested_topology}' skips {current_order - requested_order} levels. "
                "Downgrade ONE level at a time, or prefix reason with "
                "'mechanical change:' for trivial changes that don't need the routed level."
            )
        has_substitution_grounds = any(
            flag and factor in SUBSTITUTION_ALLOWED_FACTORS
            for factor, flag in factors.items()
        )
        if not has_substitution_grounds and not is_mechanical:
            warnings.append(
                f"Topology downgrade from '{current_topology}' to "
                f"'{requested_topology}' requires at least one substitution-grounds "
                f"factor: {', '.join(sorted(SUBSTITUTION_ALLOWED_FACTORS))}"
            )
        if not reason.strip():
            allowed = False
            warnings.append("Topology substitution requires a recorded reason")

    return {
        "allowed": allowed or requested_order >= current_order,
        "effective_topology": requested_topology if (allowed or requested_order >= current_order) else current_topology,
        "reason": reason,
        "warnings": warnings,
        "is_downgrade": requested_order < current_order,
    }


def should_escalate(state: Dict, review: Dict, current_level: str, file_count_delta: int = 0) -> Optional[str]:
    """Check if current execution should escalate to a higher level."""
    lvls = ["L0_direct", "L1_review_light", "L2_standard_team", "L3_full_power"]
    current_idx = lvls.index(current_level) if current_level in lvls else 0

    if state.get("scope_violation"): return lvls[min(current_idx + 1, 3)]
    if review.get("result") in ("needs_fix", "scope_violation", "rejected"):
        return lvls[min(current_idx + 1, 3)]
    if review.get("architecture_impact") in ("medium", "high"):
        return lvls[min(current_idx + 1, 3)]
    if review.get("architecture_drift") or review.get("cross_task_risks") or review.get("testing_debt"):
        return lvls[max(current_idx + 1, lvls.index("L2_standard_team")) if current_idx < 2 else min(current_idx + 1, 3)]
    if state.get("cross_task_quality_escalation_required"):
        return lvls[max(current_idx + 1, lvls.index("L2_standard_team")) if current_idx < 2 else min(current_idx + 1, 3)]
    if file_count_delta > 3: return lvls[min(current_idx + 1, 3)]
    if current_level == "L1_review_light" and review.get("result") == "needs_more_testing":
        return "L2_standard_team"
    return None


# ── Routing explanation for human/agent consumption ──

def explain_routing(decision: Dict) -> str:
    """Produce a human-readable routing explanation."""
    level = decision.get("workflow_level", "L1_review_light")
    label = decision.get("label", "")
    topo = decision.get("execution_topology", "light_review")
    verif = decision.get("verification_need", "standard")
    review = decision.get("review_need", "optional_light_review")
    factors = decision.get("routing_factors", [])
    hard = decision.get("hard_upgrades", [])
    downgrade_ok = decision.get("downgrade_allowed", True)
    sub_ok = decision.get("substitution_allowed", False)

    lines = [
        f"Routing: {level} / {verif} / {topo}",
        f"Review: {review}",
    ]
    if factors:
        lines.append(f"Factors: {', '.join(factors[:8])}")
    if hard:
        lines.append(f"Hard constraints: {', '.join(hard)}")
    lines.append(f"Downgrade: {'allowed' if downgrade_ok else 'forbidden'}")
    if sub_ok:
        lines.append("Substitution: allowed (topology may be waived with recorded reason)")
    else:
        lines.append("Substitution: not applicable")

    return "\n".join(lines)
