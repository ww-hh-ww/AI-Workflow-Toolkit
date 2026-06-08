"""Lightweight workflow recipes: guidance, not execution runtime."""
from __future__ import annotations

from typing import Dict, List


RECIPES: Dict[str, Dict[str, object]] = {
    "requirements_grill": {
        "description": "Clarify fuzzy requirements before freezing an execution contract.",
        "request_mode": "clarification",
        "workflow_pattern": "clarification_first",
        "minimum_level": "L1_review_light",
        "required_contract_fields": ["acceptance_criteria", "non_goals", "open_questions"],
        "test_focus": ["turn clarified outcomes into acceptance coverage"],
        "review_focus": ["check whether hidden assumptions were resolved"],
        "escalation_triggers": ["unanswered user decision", "scope ambiguity", "conflicting constraints"],
    },
    "tdd_vertical_slice": {
        "description": "Use one behavior-focused failing test before implementation.",
        "request_mode": "execution",
        "workflow_pattern": "linear",
        "minimum_level": "L1_review_light",
        "required_contract_fields": ["acceptance_criteria", "test_obligations"],
        "test_focus": ["public behavior first", "one slice at a time"],
        "review_focus": ["tests describe behavior rather than implementation details"],
        "escalation_triggers": ["no public interface", "test cannot observe behavior"],
    },
    "bug_fix": {
        "description": "Reproduce, fix, verify, and prevent recurrence.",
        "request_mode": "execution",
        "workflow_pattern": "linear",
        "minimum_level": "L1_review_light",
        "required_contract_fields": ["failure_summary", "acceptance_criteria", "required_verification"],
        "test_focus": ["reproduction before fix", "regression coverage"],
        "review_focus": ["route cause correctly and avoid scope creep"],
        "escalation_triggers": ["unclear failure route", "prior fix-loop", "cross-module blast radius"],
    },
    "architecture_health_check": {
        "description": "Periodic architecture synthesis from reviewer signals and project drift.",
        "request_mode": "research",
        "workflow_pattern": "adversarial_early",
        "minimum_level": "L2_standard_team",
        "required_contract_fields": ["architecture_brief", "deferred_risks"],
        "test_focus": ["not applicable unless a follow-up task is created"],
        "review_focus": ["PROJECT-MAP drift", "hotspots", "boundary decay"],
        "escalation_triggers": ["gravity >= 0.5", "PROJECT-MAP stale", "3+ drift signals"],
    },
    "architecture_migration": {
        "description": "Migrate a repository from an old architecture/mainline to a new one without leaving double-track behavior.",
        "request_mode": "execution",
        "workflow_pattern": "adversarial_early",
        "minimum_level": "L2_standard_team",
        "required_contract_fields": [
            "architecture_brief.migration_source_of_truth",
            "architecture_brief.legacy_paths",
            "architecture_brief.legacy_terms",
            "architecture_brief.default_entrypoints",
            "architecture_brief.validators",
        ],
        "test_focus": ["legacy sweep", "default entrypoint dry-run", "validator/CI dry-run", "sample output alignment"],
        "review_focus": ["single source of truth", "old entrypoints removed/redirected/isolated", "docs/scripts/prompts/tests agree"],
        "escalation_triggers": ["old default entrypoint still active", "validator checks old structure", "README and behavior disagree"],
    },
    "release_verification": {
        "description": "Verify release readiness without auto-publishing.",
        "request_mode": "execution",
        "workflow_pattern": "adversarial_early",
        "minimum_level": "L3_full_power",
        "required_contract_fields": ["release_scope", "rollback_plan", "required_verification"],
        "test_focus": ["full regression", "real usage", "packaging/install path"],
        "review_focus": ["no auto deploy", "diff clarity", "rollback readiness"],
        "escalation_triggers": ["publish/deploy", "security/data risk", "missing rollback"],
    },
    "external_research_decision": {
        "description": "Use external research as low-trust input before Planner decision.",
        "request_mode": "research",
        "workflow_pattern": "research_first",
        "minimum_level": "L1_review_light",
        "required_contract_fields": ["research_question", "decision_needed"],
        "test_focus": ["not applicable until decision becomes execution contract"],
        "review_focus": ["source freshness", "claim confidence", "decision trace"],
        "escalation_triggers": ["unstable library/API", "high-cost choice", "conflicting evidence"],
    },
    "exploratory_spike": {
        "description": "Bounded experiment to reduce uncertainty before formal implementation.",
        "request_mode": "spike",
        "workflow_pattern": "spike_first",
        "minimum_level": "L1_review_light",
        "required_contract_fields": ["spike_question", "timebox", "throwaway_boundaries"],
        "test_focus": ["prove feasibility only"],
        "review_focus": ["do not treat spike as final implementation"],
        "escalation_triggers": ["prototype touches production path", "scope expands", "decision remains unclear"],
    },
    "flaky_test_hunt": {
        "description": "Isolate nondeterministic test behavior before blaming implementation.",
        "request_mode": "execution",
        "workflow_pattern": "research_first",
        "minimum_level": "L2_standard_team",
        "required_contract_fields": ["failure_summary", "environment_profile", "required_verification"],
        "test_focus": ["repeatability", "environment route", "minimal reproduction"],
        "review_focus": ["route to environment/tester/executor correctly"],
        "escalation_triggers": ["CI-only failure", "time/network dependency", "shared fixture hotspot"],
    },
}


def list_recipes() -> List[str]:
    return sorted(RECIPES)


def get_recipe(name: str) -> Dict[str, object]:
    if name not in RECIPES:
        raise ValueError(f"unknown recipe: {name}")
    return RECIPES[name]


def recommend_recipes(task_type: str = "", risk_flags: List[str] | None = None) -> List[Dict[str, object]]:
    flags = set(risk_flags or [])
    task_type = task_type or ""
    names: List[str] = []
    if task_type in {"bug_fix"}:
        names.append("bug_fix")
    if "architecture_migration" in flags or "legacy_migration" in flags:
        names.append("architecture_migration")
    if task_type in {"refactor"} or "architecture_impact" in flags:
        names.append("architecture_health_check")
    if task_type in {"api_endpoint", "small_function"}:
        names.append("tdd_vertical_slice")
    if flags & {"publish_or_deploy", "destructive_command"}:
        names.append("release_verification")
    if flags & {"external_research", "unstable_dependency"}:
        names.append("external_research_decision")
    if flags & {"flaky", "flaky_test", "nondeterministic", "ci_only"}:
        names.append("flaky_test_hunt")
    if not names:
        names.append("requirements_grill")
    return [{"name": n, **RECIPES[n]} for n in names]
