"""Contract tests for Stage 4.7.4: Work Intent Discipline."""
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class TestWorkIntentValidation(unittest.TestCase):
    """Core validation of work_intent."""

    def test_all_allowed_work_intents_validate(self):
        from aiwf_core.core.work_intent_rules import VALID_WORK_INTENTS
        allowed = {"feature", "bugfix", "refactor", "cleanup", "migration",
                    "verification", "exploration", "documentation", "integration", "release"}
        self.assertEqual(allowed, VALID_WORK_INTENTS)

    def test_invalid_work_intent_rejected(self):
        from aiwf_core.core.work_intent_rules import get_work_intent_rules
        with self.assertRaises(ValueError):
            get_work_intent_rules("nonexistent")

    def test_valid_work_intent_returns_rules(self):
        from aiwf_core.core.work_intent_rules import get_work_intent_rules
        rules = get_work_intent_rules("bugfix")
        self.assertIn("default_constraints", rules)
        self.assertIn("default_forbidden_changes", rules)
        self.assertIn("default_expected_evidence", rules)
        self.assertIn("default_review_focus", rules)

    def test_default_work_intent_from_plan_kind(self):
        from aiwf_core.core.work_intent_rules import resolve_work_intent
        self.assertEqual("verification", resolve_work_intent("", "verification"))
        self.assertEqual("exploration", resolve_work_intent("", "exploration"))
        self.assertEqual("migration", resolve_work_intent("", "migration"))
        self.assertEqual("integration", resolve_work_intent("", "integration"))
        self.assertEqual("feature", resolve_work_intent("", "implementation"))
        self.assertEqual("feature", resolve_work_intent("", "structural"))

    def test_explicit_work_intent_wins_over_plan_kind(self):
        from aiwf_core.core.work_intent_rules import resolve_work_intent
        self.assertEqual("refactor", resolve_work_intent("refactor", "migration"))
        self.assertEqual("bugfix", resolve_work_intent("bugfix", "implementation"))

    def test_default_is_feature_when_nothing_specified(self):
        from aiwf_core.core.work_intent_rules import resolve_work_intent
        self.assertEqual("feature", resolve_work_intent("", ""))
        self.assertEqual("feature", resolve_work_intent("", "unknown"))


class TestWorkIntentRuleTable(unittest.TestCase):
    """Each intent has correct rule defaults."""

    def test_feature_has_acceptance_evidence(self):
        from aiwf_core.core.work_intent_rules import get_work_intent_rules
        r = get_work_intent_rules("feature")
        self.assertTrue(any("acceptance" in e for e in r["default_expected_evidence"]))

    def test_bugfix_requires_regression(self):
        from aiwf_core.core.work_intent_rules import get_work_intent_rules
        r = get_work_intent_rules("bugfix")
        self.assertTrue(r["regression_required"])
        self.assertTrue(any("regression" in e for e in r["default_expected_evidence"]))

    def test_refactor_preserves_behavior_and_compatibility(self):
        from aiwf_core.core.work_intent_rules import get_work_intent_rules
        r = get_work_intent_rules("refactor")
        self.assertTrue(r["preserve_behavior"])
        self.assertTrue(r["compatibility_required"])
        self.assertTrue(any("feature creep" in f for f in r["default_forbidden_changes"]))
        self.assertTrue(any("source-of-truth" in f for f in r["default_forbidden_changes"]))

    def test_cleanup_forbids_deleting_machine_truth(self):
        from aiwf_core.core.work_intent_rules import get_work_intent_rules
        r = get_work_intent_rules("cleanup")
        self.assertTrue(any("machine truth" in f for f in r["default_forbidden_changes"]))

    def test_migration_requires_mapping_and_compatibility(self):
        from aiwf_core.core.work_intent_rules import get_work_intent_rules
        r = get_work_intent_rules("migration")
        self.assertTrue(r["compatibility_required"])
        self.assertTrue(any("mapping" in e or "report" in e for e in r["default_expected_evidence"]))

    def test_verification_forbids_implementation_drift(self):
        from aiwf_core.core.work_intent_rules import get_work_intent_rules
        r = get_work_intent_rules("verification")
        self.assertTrue(any("implementation drift" in f for f in r["default_forbidden_changes"]))
        self.assertEqual(["tester", "reviewer"], r["preferred_dispatch"])

    def test_exploration_requires_isolation(self):
        from aiwf_core.core.work_intent_rules import get_work_intent_rules
        r = get_work_intent_rules("exploration")
        self.assertTrue(any("isolated" in c.lower() for c in r["default_constraints"]))
        self.assertTrue(any("graft" in e or "prune" in e for e in r["default_expected_evidence"]))

    def test_documentation_forbids_semantic_drift(self):
        from aiwf_core.core.work_intent_rules import get_work_intent_rules
        r = get_work_intent_rules("documentation")
        self.assertTrue(any("semantic" in f for f in r["default_forbidden_changes"]))
        self.assertFalse(r["regression_required"])

    def test_integration_requires_interface_consistency(self):
        from aiwf_core.core.work_intent_rules import get_work_intent_rules
        r = get_work_intent_rules("integration")
        self.assertTrue(any("interface" in e for e in r["default_expected_evidence"]))
        self.assertTrue(any("gaps" in e for e in r["default_expected_evidence"]))

    def test_release_requires_audit_and_hygiene(self):
        from aiwf_core.core.work_intent_rules import get_work_intent_rules
        r = get_work_intent_rules("release")
        self.assertTrue(any("audit" in e for e in r["default_expected_evidence"]))
        self.assertTrue(any("runtime" in f or "pycache" in f for f in r["default_forbidden_changes"]))


class TestWorkIntentMerge(unittest.TestCase):
    """Merging rule defaults into Work Packets."""

    def test_merge_adds_constraints_without_overwriting(self):
        from aiwf_core.core.work_intent_rules import merge_work_intent_defaults
        pkt = {"work_intent": "refactor", "constraints": ["custom rule"]}
        result = merge_work_intent_defaults(pkt)
        self.assertIn("custom rule", result["constraints"])
        self.assertTrue(len(result["constraints"]) > 1)

    def test_merge_adds_forbidden_changes(self):
        from aiwf_core.core.work_intent_rules import merge_work_intent_defaults
        pkt = {"work_intent": "migration"}
        result = merge_work_intent_defaults(pkt)
        self.assertTrue(len(result.get("forbidden_changes", [])) > 0)
        self.assertTrue(any("data loss" in f for f in result["forbidden_changes"]))

    def test_merge_adds_expected_evidence(self):
        from aiwf_core.core.work_intent_rules import merge_work_intent_defaults
        pkt = {"work_intent": "release"}
        result = merge_work_intent_defaults(pkt)
        self.assertTrue(any("audit" in e for e in result["expected_evidence"]))

    def test_merge_adds_review_focus(self):
        from aiwf_core.core.work_intent_rules import merge_work_intent_defaults
        pkt = {"work_intent": "bugfix"}
        result = merge_work_intent_defaults(pkt)
        self.assertTrue(any("root cause" in r for r in result["review_focus"]))

    def test_merge_preserves_explicit_fields(self):
        from aiwf_core.core.work_intent_rules import merge_work_intent_defaults
        pkt = {"work_intent": "feature", "expected_evidence": ["my_test"]}
        result = merge_work_intent_defaults(pkt)
        self.assertIn("my_test", result["expected_evidence"])

    def test_merge_injects_preserve_behavior_compatibility_regression(self):
        from aiwf_core.core.work_intent_rules import merge_work_intent_defaults
        pkt = {"work_intent": "refactor"}
        result = merge_work_intent_defaults(pkt)
        self.assertTrue(result["preserve_behavior"])
        self.assertTrue(result["compatibility_required"])
        self.assertTrue(result["regression_required"])

    def test_merge_unknown_intent_noop(self):
        from aiwf_core.core.work_intent_rules import merge_work_intent_defaults
        pkt = {"work_intent": ""}
        result = merge_work_intent_defaults(pkt)
        self.assertEqual(pkt, result)


class TestFrontierValidationWithIntent(unittest.TestCase):
    """Frontier validation checks work_intent."""

    def test_invalid_work_intent_in_frontier_fails(self):
        from aiwf_core.core.frontier_ops import validate_frontier_decision
        d = {
            "frontier_type": "execute_plan",
            "selected_plan_id": "",
            "target_goal_id": "",
            "dispatch_to": "executor",
            "reason": "test",
            "scope": "test",
            "expected_evidence": ["test"],
            "rollup_target": "GOAL-001",
            "work_intent": "bogus",
        }
        result = validate_frontier_decision("/tmp", d)
        self.assertFalse(result["valid"])
        self.assertTrue(any("work_intent" in i for i in result["issues"]))

    def test_valid_work_intent_in_frontier_passes(self):
        from aiwf_core.core.frontier_ops import validate_frontier_decision
        d = {
            "frontier_type": "explore_temporary_root",
            "dispatch_to": "planner",
            "reason": "Explore a new module structure.",
            "target_goal_id": "GOAL-001",
            "work_intent": "exploration",
        }
        result = validate_frontier_decision("/tmp", d)
        self.assertTrue(result["valid"], f"Should be valid: {result.get('issues')}")

    def test_refactor_with_preserve_behavior_false_fails(self):
        from aiwf_core.core.frontier_ops import validate_frontier_decision
        d = {
            "frontier_type": "execute_plan",
            "selected_plan_id": "",
            "target_goal_id": "",
            "dispatch_to": "executor",
            "reason": "test",
            "scope": "test",
            "expected_evidence": ["test"],
            "rollup_target": "GOAL-001",
            "work_intent": "refactor",
            "preserve_behavior": False,
        }
        result = validate_frontier_decision("/tmp", d)
        self.assertFalse(result["valid"])


class TestSkillWorkIntentAlignment(unittest.TestCase):
    """All skills mention work_intent or plan_kind vs work_intent."""

    @classmethod
    def _read_skill(cls, name):
        return (PROJECT_ROOT / "aiwf_core" / "embedded_templates" / "skills" / name / "SKILL.md").read_text()

    def test_planner_skill_mentions_work_intent(self):
        c = self._read_skill("aiwf-planner")
        self.assertIn("Work Intent Discipline", c)
        self.assertIn("plan_kind", c)
        self.assertIn("work_intent", c)

    def test_planner_skill_mentions_all_intent_values(self):
        c = self._read_skill("aiwf-planner")
        for intent in ["feature", "bugfix", "refactor", "cleanup", "migration",
                        "verification", "exploration", "documentation", "integration", "release"]:
            self.assertIn(intent, c, f"Planner skill missing work_intent: {intent}")

    def test_executor_skill_mentions_work_intent_discipline(self):
        c = self._read_skill("aiwf-implement")
        self.assertIn("Work Intent Discipline", c)
        for intent in ["feature", "bugfix", "refactor", "cleanup"]:
            self.assertIn(intent, c, f"Executor skill missing: {intent}")

    def test_tester_skill_mentions_work_intent(self):
        c = self._read_skill("aiwf-test")
        self.assertIn("Work Intent Discipline", c)
        self.assertIn("work_intent", c)

    def test_reviewer_skill_mentions_work_intent(self):
        c = self._read_skill("aiwf-review")
        self.assertIn("Work Intent Discipline", c)
        self.assertIn("work_intent", c)

    def test_architect_skill_mentions_work_intent(self):
        c = self._read_skill("aiwf-architect")
        self.assertIn("Work Intent Discipline", c)
        self.assertIn("work_intent", c)


class TestWorkIntentDocExists(unittest.TestCase):
    """The discipline doc exists and covers key concepts."""

    def test_work_intent_doc_exists(self):
        self.assertTrue((PROJECT_ROOT / "docs" / "WORK_INTENT_DISCIPLINE.md").exists())

    def test_work_intent_doc_says_not_a_node(self):
        text = (PROJECT_ROOT / "docs" / "WORK_INTENT_DISCIPLINE.md").read_text()
        self.assertIn("NOT a node", text)

    def test_work_intent_doc_says_orthogonal(self):
        text = (PROJECT_ROOT / "docs" / "WORK_INTENT_DISCIPLINE.md").read_text()
        self.assertIn("orthogonal", text.lower())

    def test_work_intent_doc_has_all_values(self):
        text = (PROJECT_ROOT / "docs" / "WORK_INTENT_DISCIPLINE.md").read_text()
        for intent in ["feature", "bugfix", "refactor", "cleanup", "migration",
                        "verification", "exploration", "documentation", "integration", "release"]:
            self.assertIn(intent, text, f"Doc missing: {intent}")


class TestWorkIntentPlanLayer(unittest.TestCase):
    """Stage 4.7.4b: Plan registry stores work_intent."""

    def test_empty_plan_has_work_intent(self):
        from aiwf_core.core.state.plan_ops import _empty_plan
        plan = _empty_plan("PLAN-TEST", work_intent="refactor")
        self.assertEqual("refactor", plan.get("work_intent"))

    def test_empty_plan_invalid_work_intent_raises(self):
        from aiwf_core.core.state.plan_ops import _empty_plan
        with self.assertRaises(ValueError):
            _empty_plan("PLAN-TEST", work_intent="bogus")

    def test_empty_plan_work_intent_none_ok(self):
        from aiwf_core.core.state.plan_ops import _empty_plan
        plan = _empty_plan("PLAN-TEST", work_intent="")
        self.assertIsNone(plan.get("work_intent"))

    def test_plan_artifact_has_work_intent(self):
        from aiwf_core.core.task_plan import _default_plan
        text = _default_plan("PLAN-FOO", work_intent="refactor")
        self.assertIn("Work Intent: refactor", text)

    def test_plan_artifact_no_work_intent_when_empty(self):
        from aiwf_core.core.task_plan import _default_plan
        text = _default_plan("PLAN-BAR")
        self.assertNotIn("Work Intent:", text)


class TestWorkIntentValidationDeepened(unittest.TestCase):
    """Stage 4.7.4b: Deepened work_intent validation."""

    def _validate(self, d):
        from aiwf_core.core.frontier_ops import validate_frontier_decision
        return validate_frontier_decision("/tmp", d)

    def test_refactor_missing_regression_and_compat_fails(self):
        d = {
            "frontier_type": "execute_plan",
            "selected_plan_id": "", "target_goal_id": "", "dispatch_to": "executor",
            "reason": "test", "scope": "test",
            "expected_evidence": ["refactor_done"],
            "rollup_target": "GOAL-001",
            "work_intent": "refactor",
        }
        result = self._validate(d)
        self.assertFalse(result["valid"])
        self.assertTrue(any("regression" in i or "compatibility" in i for i in result["issues"]))

    def test_migration_missing_mapping_fails(self):
        d = {
            "frontier_type": "execute_plan",
            "selected_plan_id": "", "target_goal_id": "", "dispatch_to": "executor",
            "reason": "test", "scope": "test",
            "expected_evidence": ["data_moved"],
            "rollup_target": "GOAL-001",
            "work_intent": "migration",
        }
        result = self._validate(d)
        self.assertFalse(result["valid"])
        self.assertTrue(any("mapping" in i or "fallback" in i or "migration" in i for i in result["issues"]))

    def test_release_missing_audit_and_tests_fails(self):
        d = {
            "frontier_type": "execute_plan",
            "selected_plan_id": "", "target_goal_id": "", "dispatch_to": "executor",
            "reason": "test", "scope": "test",
            "expected_evidence": ["done"],
            "rollup_target": "GOAL-001",
            "work_intent": "release",
        }
        result = self._validate(d)
        self.assertFalse(result["valid"])
        self.assertTrue(any("test" in i or "audit" in i or "package" in i for i in result["issues"]))

    def test_documentation_missing_semantic_drift_guard_fails(self):
        d = {
            "frontier_type": "execute_plan",
            "selected_plan_id": "", "target_goal_id": "", "dispatch_to": "executor",
            "reason": "test", "scope": "test",
            "expected_evidence": ["docs updated"],
            "rollup_target": "GOAL-001",
            "work_intent": "documentation",
        }
        result = self._validate(d)
        self.assertFalse(result["valid"])
        self.assertTrue(any("semantic" in i or "machine" in i for i in result["issues"]))

    def test_refactor_with_regression_and_compat_passes(self):
        d = {
            "frontier_type": "explore_temporary_root",
            "target_goal_id": "GOAL-001", "dispatch_to": "planner",
            "reason": "test",
            "expected_evidence": ["regression_test", "compatibility_test", "before_after_summary"],
            "work_intent": "refactor",
        }
        result = self._validate(d)
        self.assertTrue(result["valid"], f"Issues: {result['issues']}")

    def test_migration_with_mapping_passes(self):
        d = {
            "frontier_type": "explore_temporary_root",
            "target_goal_id": "GOAL-001", "dispatch_to": "planner",
            "reason": "test",
            "expected_evidence": ["migration_mapping", "migration_report", "regression_test"],
            "work_intent": "migration",
        }
        result = self._validate(d)
        self.assertTrue(result["valid"], f"Issues: {result['issues']}")

    def test_release_with_audit_and_tests_passes(self):
        d = {
            "frontier_type": "explore_temporary_root",
            "target_goal_id": "GOAL-001", "dispatch_to": "planner",
            "reason": "test",
            "expected_evidence": ["full_tests_pass", "release_audit_pass", "package_contents"],
            "work_intent": "release",
        }
        result = self._validate(d)
        self.assertTrue(result["valid"], f"Issues: {result['issues']}")


class TestHumanWorkPacketMerged(unittest.TestCase):
    """Human and Agent Work Packets agree on merged work_intent defaults."""

    def test_human_and_agent_packet_constraints_agree(self):
        from aiwf_core.core.frontier_ops import prepare_work_packet
        d = {
            "frontier_type": "execute_plan",
            "selected_plan_id": "", "target_goal_id": "", "dispatch_to": "executor",
            "reason": "test", "scope": "test",
            "expected_evidence": ["test"], "rollup_target": "GOAL-001",
            "work_intent": "refactor",
        }
        result = prepare_work_packet("/tmp", d)
        h_c = result["human_work_packet"].get("constraints", [])
        a_c = result["agent_work_packet"].get("constraints", [])
        self.assertEqual(h_c, a_c, f"Human={h_c} vs Agent={a_c}")

    def test_human_and_agent_packet_evidence_agree(self):
        from aiwf_core.core.frontier_ops import prepare_work_packet
        d = {
            "frontier_type": "execute_plan",
            "selected_plan_id": "", "target_goal_id": "", "dispatch_to": "executor",
            "reason": "test", "scope": "test",
            "expected_evidence": ["test"], "rollup_target": "GOAL-001",
            "work_intent": "refactor",
        }
        result = prepare_work_packet("/tmp", d)
        h_e = result["human_work_packet"].get("expected_evidence", [])
        a_e = result["agent_work_packet"].get("expected_evidence", [])
        self.assertEqual(h_e, a_e)

    def test_human_text_contains_refactor_defaults(self):
        from aiwf_core.core.frontier_ops import prepare_work_packet
        d = {
            "frontier_type": "explore_temporary_root",
            "target_goal_id": "GOAL-001", "dispatch_to": "planner",
            "reason": "test",
            "expected_evidence": ["regression_test", "compatibility_test", "before_after"],
            "work_intent": "refactor",
        }
        result = prepare_work_packet("/tmp", d)
        text = result["human_work_packet"].get("text", "")
        self.assertIn("preserve", text.lower())


if __name__ == "__main__":
    unittest.main()
