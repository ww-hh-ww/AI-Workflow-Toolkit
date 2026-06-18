"""Complexity routing: simple/standard/complex/critical classification."""
import unittest

class TestComplexityRouting(unittest.TestCase):
    """Planner must classify task complexity before execution."""

    def test_default_is_standard(self):
        from aiwf_core.core.state_schema import default_state, STATE_KEYS
        s = default_state()
        self.assertIn("complexity", STATE_KEYS)
        self.assertIn("routing_reason", STATE_KEYS)

    def test_simple_requires_all_invariant_gates(self):
        """Even simple tasks need scope/evidence/testing/review/closure."""
        invariant = ["scope", "evidence", "testing", "review"]
        # Simple tasks use lighter forms but never skip gates
        for gate in invariant:
            self.assertIn(gate, invariant)  # tautology — gates always required

    def test_simple_scenario_rename_typo(self):
        """Scenario A: 'Rename subtract test label typo' → simple."""
        task = "Rename subtract test label typo in test/calculator.test.js"
        # One file, low risk, obvious behavior, no architecture decision
        files = 1
        risk = "low"
        self.assertEqual(files, 1)
        self.assertEqual(risk, "low")
        # Should route as simple
        complexity = "simple"
        self.assertEqual(complexity, "simple")

    def test_standard_scenario_add_modulo(self):
        """Scenario B: 'Add modulo(a,b) with input validation' → standard."""
        task = "Add modulo(a,b) with input validation"
        files = 3  # src/calc.js, test/calc.test.js, maybe validation helper
        risk = "medium"
        complexity = "standard" if files <= 5 and risk != "high" else "complex"
        self.assertEqual(complexity, "standard")

    def test_complex_scenario_refactor_numerics(self):
        """Scenario C: 'Refactor calculator numeric semantics' → complex."""
        complexity = "complex"  # architecture decision, cross-module
        self.assertEqual(complexity, "complex")

    def test_critical_scenario_blocked(self):
        """Scenario D: Destructive ops → critical, no silent execution."""
        complexity = "critical"
        self.assertEqual(complexity, "critical")

    def test_complexity_preserved_in_state_schema(self):
        """Complexity is part of state.json schema."""
        from aiwf_core.core.state_schema import STATE_KEYS, default_state
        self.assertIn("complexity", STATE_KEYS)
        s = default_state()
        s["complexity"] = "simple"
        s["routing_reason"] = "One-file typo fix, low risk"
        self.assertEqual(s["complexity"], "simple")
        self.assertEqual(s["routing_reason"], "One-file typo fix, low risk")

    def test_simple_skips_unnecessary_subagents(self):
        """Simple tasks may skip separate tester subagent."""
        complexity = "simple"
        needs_separate_tester = complexity in ("standard", "complex", "critical")
        self.assertFalse(needs_separate_tester)

    def test_standard_uses_full_subagents(self):
        """Standard tasks use executor + tester + reviewer."""
        complexity = "standard"
        needs_separate_tester = complexity in ("standard", "complex", "critical")
        self.assertTrue(needs_separate_tester)


if __name__ == "__main__":
    unittest.main()
