"""Resource-based workflow routing with L0–L3 levels and scoring."""
from __future__ import annotations
from typing import Dict, List, Optional

# ── workflow levels ──
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

# ── routing factors ──
FACTORS = {
    "file_count_1_2": 0, "file_count_3_5": 1, "file_count_6_plus": 2,
    "cross_module": 2, "public_api_change": 2, "semantic_change": 2,
    "historical_deferred_risk": 1, "security_or_data_risk": 3,
    "test_matrix_complexity": 1, "user_decision_needed": 2,
    "architecture_impact": 2, "prior_fix_loop": 2,
    "destructive_command": 3, "publish_or_deploy": 3, "data_migration": 3,
}

HARD_UPGRADES = {
    "destructive_command": "L3_full_power",
    "publish_or_deploy": "L3_full_power",
    "data_migration": "L3_full_power",
    "security_or_data_risk": "L3_full_power",
    "user_decision_needed": "L2_standard_team",
    "prior_fix_loop": "L2_standard_team",
    "cross_module_semantic": "L2_standard_team",
}


def score_to_level(score: int, hard_upgrades: Optional[List[str]] = None) -> str:
    """Map a routing score (and optional hard upgrades) to a workflow level."""
    level = "L0_direct"
    if score <= 1: level = "L0_direct"
    elif score <= 3: level = "L1_review_light"
    elif score <= 6: level = "L2_standard_team"
    else: level = "L3_full_power"

    # Hard upgrades override
    for hu in (hard_upgrades or []):
        mapped = HARD_UPGRADES.get(hu)
        if mapped:
            # Only upgrade, never downgrade
            lvls = ["L0_direct", "L1_review_light", "L2_standard_team", "L3_full_power"]
            if lvls.index(mapped) > lvls.index(level):
                level = mapped
    return level


def compute_routing_score(factors: Dict[str, bool], file_count: int = 1) -> Dict:
    """Compute routing score from factor flags and return full routing decision."""
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
        if flag and factor in FACTORS:
            score += FACTORS[factor]
            matched.append(factor)
            if factor in HARD_UPGRADES:
                hard.append(factor)

    # Special: cross_module + semantic_change -> hard upgrade
    if factors.get("cross_module") and factors.get("semantic_change"):
        hard.append("cross_module_semantic")

    level = score_to_level(score, hard)
    level_info = LEVELS.get(level, LEVELS["L0_direct"])

    return {
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
