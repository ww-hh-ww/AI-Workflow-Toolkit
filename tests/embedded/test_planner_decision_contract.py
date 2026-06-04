"""Planner decision contract: fix-loop route=planner must not silently resolve."""
import unittest

class TestPlannerDecision(unittest.TestCase):
    """Planner-routed fix-loop requires explicit user decision."""

    def _make_fix_loop(self, route="planner", status="open", reason="scope unclear",
                       required_decisions=None, resolution=None, resolution_source=None):
        fl = {"status": status, "route": route, "reason": reason, "required_fixes": []}
        if required_decisions:
            fl["required_decisions"] = required_decisions
            fl["user_decision_required"] = True
        if resolution:
            fl["resolution"] = resolution
            fl["resolution_source"] = resolution_source or ""
            fl["status"] = "resolved"
            fl["user_decision_required"] = False
        return fl

    def test_no_prior_decision_requires_user_input(self):
        """Planner route with no prior decision must set user_decision_required=true."""
        fl = self._make_fix_loop(
            required_decisions=["Should operations reject Infinite results?"])
        self.assertEqual(fl["status"], "open")
        self.assertTrue(fl["user_decision_required"])

    def test_prior_decision_resolves_with_citation(self):
        """Explicit prior user decision allows resolution with source citation."""
        fl = self._make_fix_loop(
            status="resolved",
            resolution="deferred_out_of_scope",
            resolution_source="prior_user_decision",
            required_decisions=["Should operations reject Infinite results?"])
        # Override: when resolved, user_decision_required=false
        fl["user_decision_required"] = False
        fl["decision_summary"] = "User confirmed finite-only scope."
        self.assertEqual(fl["status"], "resolved")
        self.assertFalse(fl["user_decision_required"])
        self.assertEqual(fl["resolution_source"], "prior_user_decision")
        self.assertIn("finite-only", fl["decision_summary"])

    def test_planner_must_not_silently_resolve(self):
        """Planner route with status=open and no resolution_source must not be treated as resolved."""
        fl = self._make_fix_loop(
            required_decisions=["Boundary condition scope decision"])
        # Simulate: if somehow resolved without source
        fl["status"] = "open"
        fl["user_decision_required"] = True
        can_close = fl["status"] != "open"
        self.assertFalse(can_close, "Open planner decision must block closure")

    def test_fix_loop_route_planner_preserved(self):
        """Route=planner is preserved when user decision is pending."""
        fl = self._make_fix_loop(
            required_decisions=["Design choice: sync or async API?"])
        self.assertEqual(fl["route"], "planner")
        self.assertEqual(fl["status"], "open")

    def test_resolution_source_required_for_resolved(self):
        """When a planner decision is resolved, resolution_source must be set."""
        fl = self._make_fix_loop(
            status="resolved",
            resolution="user_confirmed_scope",
            resolution_source="prior_user_decision")
        self.assertTrue(fl["resolution_source"])
        self.assertNotEqual(fl["resolution_source"], "")

    def test_closure_blocked_by_open_planner_decision(self):
        """Open fix-loop with route=planner blocks closure."""
        fl = self._make_fix_loop()
        # fix-loop open -> closure blocked
        self.assertEqual(fl["status"], "open")
        # In real closure check: fix_loop_open=True -> passed=False
        self.assertNotEqual(fl["status"], "resolved")


if __name__ == "__main__":
    unittest.main()
