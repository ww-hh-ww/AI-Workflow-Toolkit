"""Quality policy: task_type × workflow_level → test/review/explore/cleanup/git strategy."""
import unittest

class TestQualityPolicy(unittest.TestCase):

    def test_L0_label_change_targeted_review_lite(self):
        from aiwf_core.core.quality_policy import select_quality_policy
        p = select_quality_policy("code_label_or_text_change", "L0_direct")
        self.assertEqual(p["test_template"], "targeted")
        self.assertEqual(p["review_template"], "review_lite")
        self.assertEqual(p["exploration_budget"], "no_broad_exploration")
        self.assertEqual(p["git_policy"], "no_auto_commit")
        p = select_quality_policy("code_label_or_text_change", "L0_direct")
        self.assertEqual(p["review_template"], "review_lite")
        self.assertEqual(p["exploration_budget"], "no_broad_exploration")
        self.assertEqual(p["git_policy"], "no_auto_commit")

    def test_L1_small_function_regression_reviewer_light(self):
        from aiwf_core.core.quality_policy import select_quality_policy
        p = select_quality_policy("small_function", "L1_review_light")
        self.assertEqual(p["test_template"], "targeted_plus_small_regression")
        self.assertEqual(p["review_template"], "reviewer_light")
        self.assertEqual(p["exploration_max_files"], 5)

    def test_L2_api_endpoint_boundary_standard_review(self):
        from aiwf_core.core.quality_policy import select_quality_policy
        p = select_quality_policy("api_endpoint", "L2_standard_team")
        self.assertEqual(p["test_template"], "regression_plus_boundary_adverse")
        self.assertEqual(p["review_template"], "standard_review")
        self.assertEqual(p["asset_policy"], "asset_first_when_useful")
        self.assertEqual(p["exploration_max_files"], 15)

    def test_L3_numeric_semantics_risk_matrix_full_review(self):
        from aiwf_core.core.quality_policy import select_quality_policy
        p = select_quality_policy("numeric_semantics", "L3_full_power")
        self.assertEqual(p["test_template"], "risk_matrix_plus_integration_adversarial")
        self.assertEqual(p["review_template"], "full_review_structure_cleanup_deferred_risks")
        self.assertEqual(p["asset_policy"], "asset_first_required_if_fresh_else_verify_source")
        self.assertEqual(p["exploration_max_files"], 50)

    def test_security_sensitive_requires_full_review_and_user_decision(self):
        from aiwf_core.core.quality_policy import select_quality_policy
        p = select_quality_policy("security_sensitive", "L0_direct")
        # Security-sensitive hard-upgrades review even at L0
        self.assertIn("full_review", p["review_template"])
        self.assertIn("security", str(p["level_escalations_applied"]).lower())

    def test_security_sensitive_recommends_L3_minimum(self):
        from aiwf_core.core.quality_policy import select_quality_policy
        p = select_quality_policy("security_sensitive", "L0_direct")
        self.assertTrue(p["requires_user_decision"])
        self.assertEqual(p["recommended_minimum_level"], "L3_full_power")
        self.assertIn("full_review", p["review_template"])

    def test_policy_contains_escalation_triggers(self):
        from aiwf_core.core.quality_policy import select_quality_policy
        p = select_quality_policy("bug_fix", "L1_review_light")
        self.assertTrue(len(p["task_escalation_triggers"]) > 0)
        self.assertTrue(len(p["task_escalation_triggers"]) > 0)

    def test_all_task_types_have_required_fields(self):
        from aiwf_core.core.quality_policy import TASK_TYPES
        for tt, info in TASK_TYPES.items():
            for field in ["typical_risks", "testing_focus", "review_focus", "escalation_triggers"]:
                self.assertIn(field, info, f"{tt} missing {field}")

    def test_all_levels_have_required_fields(self):
        from aiwf_core.core.quality_policy import LEVEL_POLICY
        for lv, info in LEVEL_POLICY.items():
            for field in ["test_template", "review_template", "exploration_budget",
                          "asset_policy", "cleanup_policy", "git_policy"]:
                self.assertIn(field, info, f"{lv} missing {field}")

    def test_git_policy_no_auto_commit_L0(self):
        from aiwf_core.core.quality_policy import select_quality_policy
        for lv in ["L0_direct", "L1_review_light"]:
            p = select_quality_policy("small_function", lv)
            self.assertEqual(p["git_policy"], "no_auto_commit", f"{lv} git policy")

    def test_prior_fix_loop_risk_upgrades_test(self):
        from aiwf_core.core.quality_policy import select_quality_policy
        p = select_quality_policy("small_function", "L1_review_light",
                                   risk_flags=["prior_fix_loop"])
        self.assertEqual(p["test_template"], "regression_plus_boundary_adverse")

    def test_architecture_impact_upgrades_to_standard(self):
        from aiwf_core.core.quality_policy import select_quality_policy
        p = select_quality_policy("refactor", "L1_review_light",
                                   risk_flags=["architecture_impact"])
        self.assertEqual(p["review_template"], "standard_review")



    def test_prompt_cache_compliance_state_keys_only(self):
        """State records template keys, never full template text."""
        from aiwf_core.core.state_schema import default_state, STATE_KEYS
        s = default_state()
        # All string fields should be short keys, not full text
        for k, v in s.items():
            if isinstance(v, str):
                self.assertLess(len(v), 200, f"state.{k} is {len(v)} chars; should be a key, not full text")
        # Verify template-relevant fields are valid state keys (may not be populated in default_state)
        for field in ["workflow_level", "complexity"]:
            self.assertIn(field, STATE_KEYS)

    def test_prompt_cache_compliance_no_dynamic_claude_md(self):
        """Quality policy does not reference dynamic CLAUDE.md modification."""
        import inspect
        from aiwf_core.core import quality_policy
        src = inspect.getsource(quality_policy)
        self.assertNotIn("CLAUDE.md", src)
        self.assertNotIn("settings.json", src)

    def test_state_no_template_fulltext(self):
        """quality_policy returns keys, state stores keys, not full template text."""
        from aiwf_core.core.quality_policy import select_quality_policy
        p = select_quality_policy("small_function", "L1_review_light")
        # test_template is a key like "targeted_plus_small_regression", not full instructions
        self.assertIsInstance(p["test_template"], str)
        self.assertLess(len(p["test_template"]), 60)
        self.assertIsInstance(p["review_template"], str)
        self.assertLess(len(p["review_template"]), 60)


if __name__ == "__main__":
    unittest.main()
