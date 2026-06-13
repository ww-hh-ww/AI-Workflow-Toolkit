"""Work Intent Discipline — behavior rules for each work_intent value (Stage 4.7.4).

Each work_intent has default constraints, forbidden_changes, expected_evidence,
review_focus, and preferred dispatch targets. These defaults are merged into
Work Packets without overriding Planner's explicit fields.

plan_kind = structural role of the Plan
work_intent = behavioral discipline for the current work
They are orthogonal and can be combined.
"""

from __future__ import annotations

from typing import Any, Dict, List

VALID_WORK_INTENTS = {
    "feature", "bugfix", "refactor", "cleanup", "migration",
    "verification", "exploration", "documentation", "integration", "release",
}

# Default work_intent when plan_kind implies one but Planner didn't specify
PLAN_KIND_TO_DEFAULT_INTENT = {
    "verification": "verification",
    "exploration": "exploration",
    "migration": "migration",
    "integration": "integration",
}

# Fallback when neither plan_kind nor explicit intent provides one
DEFAULT_WORK_INTENT = "feature"

# ═══════════════════════════════════════════════════════════════════════════
# Rule table — one entry per work_intent
# ═══════════════════════════════════════════════════════════════════════════

_WORK_INTENT_RULES: Dict[str, Dict[str, Any]] = {
    "feature": {
        "label": "Feature",
        "summary": "New user-visible or system-visible capability.",
        "preserve_behavior": False,
        "compatibility_required": "if_existing_behavior_touched",
        "regression_required": True,
        "default_constraints": [
            "Keep implementation within the accepted Plan and Work Packet scope.",
            "Document new interfaces or user-visible behavior.",
            "Do not silently change unrelated behavior.",
        ],
        "default_forbidden_changes": [
            "unrelated refactor",
            "unapproved schema migration",
            "source-of-truth drift",
        ],
        "default_expected_evidence": [
            "acceptance_tests",
            "new_behavior_demonstration",
            "docs_or_usage_update_if_user_visible",
            "regression_tests",
        ],
        "default_review_focus": [
            "feature meets target Goal",
            "acceptance criteria pass",
            "interfaces are documented",
            "no unrelated behavior changed",
        ],
        "preferred_dispatch": ["executor", "tester", "reviewer"],
    },

    "bugfix": {
        "label": "Bug Fix",
        "summary": "Fix an error. Restore expected behavior.",
        "preserve_behavior": "restore_expected_behavior",
        "compatibility_required": True,
        "regression_required": True,
        "default_constraints": [
            "Minimize scope.",
            "Fix the root cause, not only the symptom.",
            "Preserve intended existing behavior.",
            "Add or update regression test covering the bug.",
        ],
        "default_forbidden_changes": [
            "feature creep",
            "large unrelated refactor",
            "silently changing expected behavior",
            "removing failing tests instead of fixing cause",
        ],
        "default_expected_evidence": [
            "bug_reproduction_or_failing_case",
            "fix_summary",
            "regression_test",
            "full_or_relevant_test_pass",
        ],
        "default_review_focus": [
            "root cause addressed",
            "regression coverage exists",
            "scope stayed local",
            "no unrelated behavior changed",
        ],
        "preferred_dispatch": ["executor", "tester", "reviewer"],
    },

    "refactor": {
        "label": "Refactor",
        "summary": "Restructure internals while preserving external behavior.",
        "preserve_behavior": True,
        "compatibility_required": True,
        "regression_required": True,
        "default_constraints": [
            "Preserve external behavior.",
            "Preserve machine truth semantics.",
            "Keep legacy read compatibility unless explicitly migrated.",
            "Do not introduce a new source of truth.",
            "Do not expand status --prompt.",
            "Do not add unrelated features.",
        ],
        "default_forbidden_changes": [
            "feature creep",
            "source-of-truth drift",
            "unrelated schema change",
            "prompt expansion",
            "breaking legacy read compatibility",
        ],
        "default_expected_evidence": [
            "before_after_structure_summary",
            "compatibility_test",
            "regression_test",
            "migration_or_fallback_story",
        ],
        "default_review_focus": [
            "external behavior preserved",
            "machine truth semantics unchanged",
            "legacy compatibility preserved",
            "no unrelated features added",
            "no new source of truth introduced",
        ],
        "preferred_dispatch": ["executor", "tester", "reviewer", "architect"],
    },

    "cleanup": {
        "label": "Cleanup",
        "summary": "Remove redundancy, pollution, cache, stale artifacts, or unused runtime content.",
        "preserve_behavior": True,
        "compatibility_required": False,
        "regression_required": "light",
        "default_constraints": [
            "Do not delete machine truth.",
            "Do not change registry semantics.",
            "Archive or report removed human artifacts.",
            "Keep cleanup scope local.",
            "Do not hide evidence needed for review/debug.",
        ],
        "default_forbidden_changes": [
            "deleting machine truth",
            "removing required artifacts without archive",
            "changing registry semantics",
            "removing evidence needed for review",
        ],
        "default_expected_evidence": [
            "removed_items_summary",
            "no_required_files_removed",
            "machine_truth_untouched",
        ],
        "default_review_focus": [
            "no required files removed",
            "machine truth untouched",
            "cleanup scope stayed local",
            "debug/review ability preserved",
        ],
        "preferred_dispatch": ["executor", "reviewer"],
    },

    "migration": {
        "label": "Migration",
        "summary": "Move old structure/paths/state/contracts to new structure while preserving compatibility.",
        "preserve_behavior": True,
        "compatibility_required": True,
        "regression_required": True,
        "default_constraints": [
            "Define old path/object and new path/object.",
            "Preserve existing data.",
            "Provide fallback or migration path.",
            "Do not change object truth semantics without explicit migration.",
            "Generate migration report.",
        ],
        "default_forbidden_changes": [
            "data loss",
            "silent schema drift",
            "breaking legacy projects",
            "duplicating object truth into artifacts",
        ],
        "default_expected_evidence": [
            "migration_mapping",
            "migration_report",
            "legacy_read_compatibility_test",
            "new_path_or_schema_test",
            "regression_test",
        ],
        "default_review_focus": [
            "old data preserved",
            "new structure is authoritative where intended",
            "fallback or migration story exists",
            "no double source of truth introduced",
        ],
        "preferred_dispatch": ["executor", "tester", "reviewer", "architect"],
    },

    "verification": {
        "label": "Verification",
        "summary": "Verify, review, prove. Do not change implementation unless explicitly assigned.",
        "preserve_behavior": True,
        "compatibility_required": False,
        "regression_required": False,
        "default_constraints": [
            "Do not change implementation unless explicitly assigned.",
            "Focus on evidence and correctness.",
            "State uncertainty clearly.",
            "Evidence must roll up to Plan/Goal.",
        ],
        "default_forbidden_changes": [
            "implementation drift",
            "unapproved code changes",
            "claiming pass without evidence",
        ],
        "default_expected_evidence": [
            "verification_result",
            "evidence_rollup",
            "limits_or_uncertainties",
        ],
        "default_review_focus": [
            "evidence supports target Plan/Goal",
            "no implementation drift",
            "uncertainties are explicit",
        ],
        "preferred_dispatch": ["tester", "reviewer"],
    },

    "exploration": {
        "label": "Exploration",
        "summary": "Explore an uncertain direction. Use Temporary Root or isolated scope.",
        "preserve_behavior": False,
        "compatibility_required": False,
        "regression_required": False,
        "default_constraints": [
            "Keep work isolated from stable structure.",
            "Use Temporary Root or clearly marked exploration scope.",
            "Do not mutate stable Goal Tree unless explicitly grafted.",
            "Record learnings and decision points.",
            "End with graft/prune/revise recommendation.",
        ],
        "default_forbidden_changes": [
            "polluting stable structure",
            "untracked prototype code",
            "silent graft into main tree",
            "presenting speculative result as stable",
        ],
        "default_expected_evidence": [
            "exploration_notes",
            "prototype_result_if_any",
            "graft_or_prune_recommendation",
            "risks_and_unknowns",
        ],
        "default_review_focus": [
            "exploration stayed isolated",
            "learning is captured",
            "next structural decision is clear",
        ],
        "preferred_dispatch": ["planner", "architect", "executor", "reviewer"],
    },

    "documentation": {
        "label": "Documentation",
        "summary": "Update docs, contracts, explanations. Do not change machine semantics.",
        "preserve_behavior": True,
        "compatibility_required": False,
        "regression_required": False,
        "default_constraints": [
            "Do not change machine semantics.",
            "Keep docs consistent with current source of truth.",
            "Do not document unimplemented behavior as complete.",
            "Clearly mark proposal vs implemented behavior.",
        ],
        "default_forbidden_changes": [
            "semantic drift",
            "claiming unimplemented features",
            "contradicting machine contract",
        ],
        "default_expected_evidence": [
            "docs_updated",
            "docs_match_current_behavior",
            "stale_docs_removed_or_marked",
        ],
        "default_review_focus": [
            "docs match implementation",
            "no overclaiming",
            "terminology consistent",
        ],
        "preferred_dispatch": ["executor", "reviewer"],
    },

    "integration": {
        "label": "Integration",
        "summary": "Integrate completed branches. Check interface consistency and convergence.",
        "preserve_behavior": True,
        "compatibility_required": True,
        "regression_required": True,
        "default_constraints": [
            "Integrate completed branches without redefining their Goals.",
            "Check interface compatibility.",
            "Resolve duplicate or conflicting concepts.",
            "Preserve source-of-truth boundaries.",
            "Identify remaining gaps and risks.",
        ],
        "default_forbidden_changes": [
            "silent interface change",
            "merging conflicting semantics without review",
            "duplicating truth sources",
            "hiding unresolved gaps",
        ],
        "default_expected_evidence": [
            "integration_summary",
            "interface_consistency_check",
            "conflict_resolution_notes",
            "regression_test",
            "remaining_gaps",
        ],
        "default_review_focus": [
            "integrated branches are coherent",
            "interfaces remain stable",
            "gaps are explicit",
            "downstream dependency is safe",
        ],
        "preferred_dispatch": ["architect", "reviewer", "tester"],
    },

    "release": {
        "label": "Release",
        "summary": "Package, archive, version-boundary, release hygiene, final delivery check.",
        "preserve_behavior": True,
        "compatibility_required": True,
        "regression_required": True,
        "default_constraints": [
            "Do not include runtime pollution.",
            "Do not include cache or generated junk.",
            "Ensure release package matches source-of-truth contracts.",
            "Run release hygiene checks.",
            "Generate release notes.",
        ],
        "default_forbidden_changes": [
            "shipping .aiwf runtime state unless intended",
            "shipping pycache or egg-info",
            "shipping stale docs as current",
            "changing behavior during packaging",
        ],
        "default_expected_evidence": [
            "release_audit_pass",
            "full_tests_pass",
            "package_contents_summary",
            "release_notes",
            "no_runtime_pollution",
        ],
        "default_review_focus": [
            "release package is clean",
            "version boundary is clear",
            "tests and audit pass",
            "docs and package match",
        ],
        "preferred_dispatch": ["tester", "reviewer", "executor"],
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════

def get_work_intent_rules(intent: str) -> Dict[str, Any]:
    """Return the full rule table entry for a work_intent value."""
    if intent not in VALID_WORK_INTENTS:
        raise ValueError(f"invalid work_intent: {intent}. Must be one of: {sorted(VALID_WORK_INTENTS)}")
    return dict(_WORK_INTENT_RULES[intent])


def resolve_work_intent(explicit_intent: str = "",
                          plan_kind: str = "") -> str:
    """Resolve work_intent: explicit > plan_kind default > 'feature'."""
    if explicit_intent and explicit_intent in VALID_WORK_INTENTS:
        return explicit_intent
    if plan_kind and plan_kind in PLAN_KIND_TO_DEFAULT_INTENT:
        return PLAN_KIND_TO_DEFAULT_INTENT[plan_kind]
    return DEFAULT_WORK_INTENT


def merge_work_intent_defaults(packet: Dict[str, Any]) -> Dict[str, Any]:
    """Merge work_intent rule defaults into a Work Packet without overwriting explicit fields.

    Reads packet['work_intent'], resolves the rule table, then appends missing
    constraints, forbidden_changes, expected_evidence, and review_focus.
    """
    intent = packet.get("work_intent", "") or ""
    if not intent or intent not in VALID_WORK_INTENTS:
        return packet

    rules = _WORK_INTENT_RULES[intent]

    # Constraints: append defaults not already present
    existing_c = [c.lower() for c in (packet.get("constraints", []) or [])]
    for c in rules.get("default_constraints", []):
        if c.lower() not in existing_c:
            packet.setdefault("constraints", []).append(c)

    # Forbidden changes
    existing_f = [f.lower() for f in (packet.get("forbidden_changes", []) or [])]
    for f in rules.get("default_forbidden_changes", []):
        if f.lower() not in existing_f:
            packet.setdefault("forbidden_changes", []).append(f)

    # Expected evidence
    existing_e = [e.lower() for e in (packet.get("expected_evidence", []) or [])]
    for e in rules.get("default_expected_evidence", []):
        if e.lower() not in existing_e:
            packet.setdefault("expected_evidence", []).append(e)

    # Review focus
    existing_r = [r.lower() for r in (packet.get("review_focus", []) or [])]
    for r in rules.get("default_review_focus", []):
        if r.lower() not in existing_r:
            packet.setdefault("review_focus", []).append(r)

    # Inject derived fields
    packet["preserve_behavior"] = rules.get("preserve_behavior")
    packet["compatibility_required"] = rules.get("compatibility_required")
    packet["regression_required"] = rules.get("regression_required")

    return packet
