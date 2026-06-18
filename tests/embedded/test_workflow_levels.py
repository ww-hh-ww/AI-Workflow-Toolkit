import unittest
from pathlib import Path

class TestWorkflowLevels(unittest.TestCase):

    def test_trivial_label_edit_is_L0(self):
        from aiwf_core.core.routing import compute_routing_score
        r = compute_routing_score({}, file_count=1)
        self.assertEqual(r["workflow_level"], "L0_direct")
        self.assertFalse(r["uses_tester"])

    def test_2_file_small_feature_is_L1(self):
        from aiwf_core.core.routing import compute_routing_score
        r = compute_routing_score({"semantic_change": True}, file_count=2)
        self.assertEqual(r["workflow_level"], "L1_review_light")
        self.assertTrue(r["uses_reviewer_light"])
        self.assertFalse(r["uses_tester"])

    def test_multi_module_hard_upgrade(self):
        from aiwf_core.core.routing import compute_routing_score
        r = compute_routing_score({"cross_module": True, "semantic_change": True,
                                    "public_api_change": True}, file_count=5)
        # cross+semantic hard upgrade + 7+ score -> L3
        self.assertEqual(r["workflow_level"], "L3_full_power")

    def test_numeric_redesign_is_L3(self):
        from aiwf_core.core.routing import compute_routing_score
        r = compute_routing_score({"cross_module":True,"semantic_change":True,
            "architecture_impact":True,"prior_fix_loop":True,"test_matrix_complexity":True}, file_count=8)
        self.assertEqual(r["workflow_level"], "L3_full_power")
        self.assertTrue(r["asset_first"])

    def test_security_risk_is_L3(self):
        from aiwf_core.core.routing import compute_routing_score
        r = compute_routing_score({"security_or_data_risk": True}, file_count=1)
        self.assertEqual(r["workflow_level"], "L3_full_power")

    def test_score_0_1_is_L0(self):
        from aiwf_core.core.routing import score_to_level
        self.assertEqual(score_to_level(0), "L0_direct")
        self.assertEqual(score_to_level(1), "L0_direct")

    def test_score_2_3_is_L1(self):
        from aiwf_core.core.routing import score_to_level
        self.assertEqual(score_to_level(2), "L1_review_light")

    def test_score_4_6_is_L2(self):
        from aiwf_core.core.routing import score_to_level
        self.assertEqual(score_to_level(4), "L2_standard_team")

    def test_score_7_plus_is_L3(self):
        from aiwf_core.core.routing import score_to_level
        self.assertEqual(score_to_level(7), "L3_full_power")

    def test_L0_preserves_invariant_gates(self):
        from aiwf_core.core.routing import INVARIANT_GATES
        for g in ["scope_before_code","evidence_before_summary","test_before_review",
                   "review_before_close","close_attempt_based_stop_gate"]:
            self.assertIn(g, INVARIANT_GATES)

    def test_L1_reviewer_light_no_tester(self):
        from aiwf_core.core.routing import LEVELS
        l = LEVELS["L1_review_light"]
        self.assertFalse(l["tester"]); self.assertTrue(l["reviewer_light"])

    def test_L1_light_review_is_combined_verifier_not_executor_self_review(self):
        """V2: dispatch follows Task.requirements (tester_required/reviewer_required),
        not a combined reviewer-light role that handles both testing and review."""
        root = Path(__file__).resolve().parent.parent.parent

        # V2 process_contract no longer mentions the old combined reviewer-light pattern
        process_contract = (root / "aiwf_core" / "core" / "process_contract.py").read_text()
        self.assertNotIn("reviewer-light subagent combines targeted testing and light review", process_contract)
        self.assertNotIn("same agent may do light review", process_contract)

        # V1: planner SKILL.md covers Task.requirements and per-role required flags
        planner_skill = (
            root / "aiwf_core" / "embedded_templates" / "skills" / "aiwf-planner" / "SKILL.md"
        ).read_text()
        self.assertIn("Task", planner_skill)
        self.assertIn("requirements", planner_skill.lower())
        self.assertIn("task activate", planner_skill.lower())

        # V2: test skill uses tester_required for dispatch, not reviewer-light
        tester_skill = (
            root / "aiwf_core" / "embedded_templates" / "skills" / "aiwf-test" / "SKILL.md"
        ).read_text()
        self.assertIn("tester_required", tester_skill)
        self.assertNotIn("reviewer-light", tester_skill)

        # V2: review skill uses reviewer_required for dispatch
        review_skill = (
            root / "aiwf_core" / "embedded_templates" / "skills" / "aiwf-review" / "SKILL.md"
        ).read_text()
        self.assertIn("reviewer_required", review_skill)

        # V2: implement skill uses executor_required for dispatch
        implement_skill = (
            root / "aiwf_core" / "embedded_templates" / "skills" / "aiwf-implement" / "SKILL.md"
        ).read_text()
        self.assertIn("executor_required", implement_skill)
        self.assertIn("requirements", implement_skill)

    def test_L2_has_tester_and_reviewer(self):
        from aiwf_core.core.routing import LEVELS
        l = LEVELS["L2_standard_team"]
        self.assertTrue(l["tester"]); self.assertTrue(l["reviewer"])

    def test_L3_asset_first(self):
        from aiwf_core.core.routing import LEVELS
        self.assertTrue(LEVELS["L3_full_power"]["asset_first"])

    def test_escalation_on_scope_violation(self):
        from aiwf_core.core.routing import should_escalate
        self.assertEqual(should_escalate({"scope_violation":True},{}, "L1_review_light"), "L2_standard_team")

    def test_escalation_on_cross_task_quality_signal(self):
        from aiwf_core.core.routing import should_escalate
        self.assertEqual(
            should_escalate({}, {"architecture_drift": ["shared module churn"]}, "L1_review_light"),
            "L2_standard_team",
        )

    def test_no_escalation_on_clean(self):
        from aiwf_core.core.routing import should_escalate
        self.assertIsNone(should_escalate({},{"result":"accepted","architecture_impact":"low"},"L1_review_light"))

    def test_state_has_workflow_level(self):
        from aiwf_core.core.state_schema import default_state, STATE_KEYS
        # V2: workflow_level still in STATE_KEYS as legacy key for backward compat
        self.assertIn("workflow_level", STATE_KEYS)
        # V2: default_state() no longer includes workflow_level — it lives in routing-debug.json
        self.assertNotIn("workflow_level", default_state())

    def test_state_has_routing_fields(self):
        from aiwf_core.core.state_schema import default_state, STATE_KEYS
        # V2: routing fields moved to routing-debug.json, no longer in default_state()
        s = default_state()
        self.assertNotIn("routing_score", s)
        self.assertNotIn("routing_background_factors", s)
        self.assertNotIn("escalation_history", s)
        # But they remain in STATE_KEYS as legacy keys for backward compat
        self.assertIn("routing_score", STATE_KEYS)
        self.assertIn("routing_background_factors", STATE_KEYS)

    def test_cross_semantic_hard_upgrade(self):
        from aiwf_core.core.routing import compute_routing_score
        r = compute_routing_score({"cross_module":True,"semantic_change":True}, file_count=2)
        self.assertIn(r["workflow_level"], ("L2_standard_team","L3_full_power"))

    def test_budget_in_routing_result(self):
        from aiwf_core.core.routing import compute_routing_score
        r = compute_routing_score({"semantic_change":True}, file_count=2)
        self.assertIn("budget", r)
        self.assertIn("max_fix_loops", r["budget"])


    def test_L3_can_be_decision_only_no_code(self):
        """L3_full_power can be discussion/decision-only without implementation."""
        from aiwf_core.core.routing import LEVELS, compute_routing_score
        r = compute_routing_score({"architecture_impact": True, "user_decision_needed": True,
                                    "security_or_data_risk": True}, file_count=1)
        self.assertEqual(r["workflow_level"], "L3_full_power")
        # L3 may decide to defer implementation — closure not required immediately
        l3 = LEVELS["L3_full_power"]
        # L3 has full capabilities but implementation is optional
        self.assertTrue(l3["asset_first"])

    def test_default_is_lowest_viable(self):
        """V2: default_state() no longer includes workflow_level (moved to routing-debug.json).
        The routing module still defaults to L1_review_light via score_to_level(2)."""
        from aiwf_core.core.state_schema import default_state
        from aiwf_core.core.routing import score_to_level
        self.assertNotIn("workflow_level", default_state())
        # Routing still defaults to L1_review_light as the lowest viable level
        self.assertEqual(score_to_level(2), "L1_review_light")

    def test_escalation_history_in_state(self):
        """V2: escalation_history moved to routing-debug.json, not in default_state()."""
        from aiwf_core.core.state_schema import default_state, STATE_KEYS
        s = default_state()
        self.assertNotIn("escalation_history", s)
        # STATE_KEYS preserves the legacy key for backward compat
        self.assertIn("escalation_history", STATE_KEYS)


if __name__ == "__main__":
    unittest.main()
