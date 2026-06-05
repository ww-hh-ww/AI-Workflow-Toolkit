"""AIWF Quality Policy Kernel — task-type × workflow-level → test/review/explore/cleanup/git strategy.

Planner selects: task_type + workflow_level + risk_flags → concrete quality plan.
Tester/reviewer follow the selected templates; they may request escalation, not unilaterally expand.
"""
from typing import Dict, List, Optional

# ── Task types ──
TASK_TYPES: Dict[str, Dict] = {
    "code_label_or_text_change": {
        "label": "Code label or text change",
        "typical_risks": ["typo in label", "wrong file edited"],
        "testing_focus": "targeted",
        "review_focus": "correctness + scope",
        "escalation_triggers": ["test failure", "file count > 2"],
    },
    "small_function": {
        "label": "Small function, 1-2 files",
        "typical_risks": ["edge case missed", "import broken"],
        "testing_focus": "happy + edge",
        "review_focus": "correctness + simplicity",
        "escalation_triggers": ["test failure", "cross-module import change", "file count > 3"],
    },
    "bug_fix": {
        "label": "Bug fix",
        "typical_risks": ["regression", "root cause misidentified"],
        "testing_focus": "regression + root cause",
        "review_focus": "correctness + regression risk",
        "escalation_triggers": ["test failure", "multiple modules affected", "fix changes API"],
    },
    "api_endpoint": {
        "label": "New or modified API endpoint",
        "typical_risks": ["breaking change", "auth bypass", "input validation gap"],
        "testing_focus": "boundary + adverse + auth",
        "review_focus": "correctness + security + compatibility",
        "escalation_triggers": ["auth/permission change", "breaking schema change", "test failure"],
    },
    "refactor": {
        "label": "Internal restructure, no API change",
        "typical_risks": ["behavior change", "performance regression", "import cycle"],
        "testing_focus": "regression + equivalence",
        "review_focus": "simplicity + equivalence + overengineering",
        "escalation_triggers": ["test failure", "public API change", "file count > 10"],
    },
    "numeric_semantics": {
        "label": "Change to numeric behavior or validation",
        "typical_risks": ["overflow", "precision loss", "boundary condition"],
        "testing_focus": "risk matrix + boundary + adversarial",
        "review_focus": "correctness + security + deferred risks",
        "escalation_triggers": ["test failure", "architecture impact", "security concern"],
    },
    "embedded_or_hardware": {
        "label": "Embedded or hardware-level change",
        "typical_risks": ["hardware damage", "timing issue", "resource exhaustion"],
        "testing_focus": "integration + hardware loop + resource",
        "review_focus": "safety + correctness + resource",
        "escalation_triggers": ["test failure", "unsafe operation", "hardware dependency change"],
    },
    "documentation": {
        "label": "Documentation-only change",
        "typical_risks": ["outdated info", "broken links"],
        "testing_focus": "targeted visual check",
        "review_focus": "accuracy + clarity",
        "escalation_triggers": [],
    },
    "security_sensitive": {
        "label": "Auth, encryption, data access",
        "typical_risks": ["data leak", "auth bypass", "crypto weakness"],
        "testing_focus": "adversarial + penetration + auth matrix",
        "review_focus": "security + correctness + data flow + escalation required",
        "escalation_triggers": ["any test failure", "unreviewed crypto", "data path change"],
    },
}

# ── Workflow level → quality depth ──
LEVEL_POLICY: Dict[str, Dict] = {
    "L0_direct": {
        "test_template": "targeted",
        "review_template": "review_lite",
        "exploration_budget": "no_broad_exploration",
        "exploration_max_files": 2,
        "asset_policy": "not_default",
        "cleanup_policy": "prepare_close_light",
        "git_policy": "no_auto_commit",
        "adversarial_review": False,
        "adversarial_test": False,
    },
    "L1_review_light": {
        "test_template": "targeted_plus_small_regression",
        "review_template": "reviewer_light",
        "exploration_budget": "target_file_plus_test_file",
        "exploration_max_files": 5,
        "asset_policy": "optional",
        "cleanup_policy": "prepare_close_light",
        "git_policy": "no_auto_commit",
        "adversarial_review": False,
        "adversarial_test": False,
    },
    "L2_standard_team": {
        "test_template": "regression_plus_boundary_adverse",
        "review_template": "standard_review",
        "exploration_budget": "asset_first_affected_files",
        "exploration_max_files": 15,
        "asset_policy": "asset_first_when_useful",
        "cleanup_policy": "reviewer_validates_cleanup",
        "git_policy": "reviewer_checks_diff_planner_suggests_commit",
        "adversarial_review": True,
        "adversarial_test": True,
    },
    "L3_full_power": {
        "test_template": "risk_matrix_plus_integration_adversarial",
        "review_template": "full_review_structure_cleanup_deferred_risks",
        "exploration_budget": "structured_exploration_packet",
        "exploration_max_files": 50,
        "asset_policy": "asset_first_required_if_fresh_else_verify_source",
        "cleanup_policy": "explicit_cleanup_phase_if_stale_state",
        "git_policy": "reviewer_checks_diff_planner_proposes_user_confirms",
        "adversarial_review": True,
        "adversarial_test": True,
    },
}




# ── Template contracts (compact) ──

TEST_CONTRACTS = {
    "targeted": {
        "purpose": "Verify exact changed behavior",
        "required": ["target behavior check", "existing cheap relevant check if available"],
        "not_required": ["full regression", "broad edge matrix", "adversarial matrix"],
        "escalation_if": ["unclear behavior", "failing related test", "wider impact discovered"],
    },
    "targeted_plus_small_regression": {
        "purpose": "Target behavior + small nearby regression",
        "required": ["target behavior", "nearby regression", "one cheap boundary if relevant"],
        "not_required": ["full risk matrix"],
        "escalation_if": ["shared helper/API touched", "prior fix-loop", "weak confidence"],
    },
    "regression_plus_boundary_adverse": {
        "purpose": "Protect changed behavior and nearby system behavior",
        "required": ["targeted validation", "full project regression disposition", "real user-facing entrypoint disposition",
                     "boundary", "adverse input/error path", "changed-file coverage"],
        "not_required": ["full architecture risk matrix unless risk found"],
        "escalation_if": ["security/data/hardware risk", "cross-module semantics"],
    },
    "risk_matrix_plus_integration_adversarial": {
        "purpose": "High-risk validation",
        "required": ["risk matrix", "targeted validation", "full project regression disposition",
                     "real user-facing entrypoint disposition", "integration path",
                     "adversarial/error path", "regression", "deferred risks"],
        "not_required": ["none; if not testable, document manual/deferred risk"],
        "escalation_if": ["user decision needed", "architecture decision unresolved"],
    },
}

REVIEW_CONTRACTS = {
    "review_lite": {
        "purpose": "Light review for trivial changes",
        "inspect": ["scope", "goal match", "basic evidence"],
        "do_not_expand_to": ["architecture review unless risk found"],
        "reject_if": ["scope drift", "no evidence", "goal mismatch"],
    },
    "reviewer_light": {
        "purpose": "Light review + test adequacy check",
        "inspect": ["scope", "goal", "evidence", "test adequacy", "overengineering"],
        "reject_if": ["no targeted test", "unnecessary abstraction", "unclear changed file"],
    },
    "standard_review": {
        "purpose": "Full correctness + structure review",
        "inspect": ["scope", "correctness", "test adequacy", "evidence", "simplicity", "structure impact"],
        "reject_if": ["missing boundary/adverse where required", "structure damage", "untracked risk"],
        "adversarial_observations": True,
    },
    "full_review_structure_cleanup_deferred_risks": {
        "purpose": "Complete review for high-risk/complex tasks",
        "inspect": ["scope", "correctness", "test adequacy", "evidence", "simplicity", "structure",
                     "architecture", "cleanup", "deferred risks", "git diff/scope"],
        "reject_if": ["unresolved risk", "stale state", "unreviewed decision", "insufficient risk matrix"],
        "adversarial_observations": True,
    },
}


def get_test_template_contract(template_key: str) -> dict:
    """Return compact test template contract. Returns targeted as default."""
    return TEST_CONTRACTS.get(template_key, TEST_CONTRACTS["targeted"])


def get_review_template_contract(template_key: str) -> dict:
    """Return compact review template contract. Returns review_lite as default."""
    return REVIEW_CONTRACTS.get(template_key, REVIEW_CONTRACTS["review_lite"])


def select_quality_policy(
    task_type: str,
    workflow_level: str,
    risk_flags: Optional[List[str]] = None,
    routing_reason: str = "",
) -> Dict:
    """Given task_type + workflow_level + optional risk_flags, return the quality policy.

    Security-sensitive tasks require full review, recommend L3_full_power, require user decision.
    """
    risk_flags = risk_flags or []
    task = TASK_TYPES.get(task_type, TASK_TYPES["small_function"])
    level = LEVEL_POLICY.get(workflow_level, LEVEL_POLICY["L1_review_light"])

    # Hard upgrades
    test_template = level["test_template"]
    review_template = level["review_template"]
    escalate = []

    if "security_sensitive" in (risk_flags + [task_type]):
        escalate.append("security: requires full review, recommends L3_full_power, requires user decision")
        review_template = max_review_depth(review_template, "full_review_structure_cleanup_deferred_risks")
        test_template = max_test_depth(test_template, "regression_plus_boundary_adverse")
        if workflow_level in ("L0_direct", "L1_review_light", "L2_standard_team"):
            escalate.append("security: current level below L3 — planner must escalate or explain")

    if "prior_fix_loop" in risk_flags:
        escalate.append("prior_fix_loop: requires regression testing")
        test_template = max_test_depth(test_template, "regression_plus_boundary_adverse")

    if "architecture_impact" in risk_flags:
        escalate.append("architecture_impact: requires structure review")
        review_template = max_review_depth(review_template, "standard_review")

    return {
        "task_type": task_type,
        "task_type_label": task["label"],
        "workflow_level": workflow_level,
        "routing_reason": routing_reason,
        "test_template": test_template,
        "review_template": review_template,
        "exploration_budget": level["exploration_budget"],
        "exploration_max_files": level["exploration_max_files"],
        "asset_policy": level["asset_policy"],
        "cleanup_policy": level["cleanup_policy"],
        "git_policy": level["git_policy"],
        "task_typical_risks": task["typical_risks"],
        "task_escalation_triggers": task["escalation_triggers"],
        "level_escalations_applied": escalate,
        "risk_flags": risk_flags,
        "recommended_minimum_level": "L3_full_power" if "security_sensitive" in (risk_flags + [task_type]) else workflow_level,
        "requires_user_decision": "security_sensitive" in (risk_flags + [task_type]),
    }


def max_test_depth(a: str, b: str) -> str:
    order = ["targeted", "targeted_plus_small_regression",
             "regression_plus_boundary_adverse", "risk_matrix_plus_integration_adversarial"]
    ai = order.index(a) if a in order else 0
    bi = order.index(b) if b in order else 0
    return order[max(ai, bi)]


def max_review_depth(a: str, b: str) -> str:
    order = ["review_lite", "reviewer_light", "standard_review",
             "full_review_structure_cleanup_deferred_risks"]
    ai = order.index(a) if a in order else 0
    bi = order.index(b) if b in order else 0
    return order[max(ai, bi)]
