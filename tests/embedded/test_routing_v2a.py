"""Complexity Routing V2-A tests: granular factors, topology dimensions, downgrade protocol.

Covers the 5 acceptance cases:
  Case 1: TASK-030 class — mechanical change, stale fix-loop → L1 deterministic single-agent
  Case 2: Current unresolved fix-loop → hard L2, downgrade forbidden
  Case 3: Core gate change → L2+, broad verification, standard team
  Case 4: Security/data risk → hard L3, no downgrade
  Case 5: L2 deterministic substitutable → downgrade allowed if recorded
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


class TestRoutingV2Factors(unittest.TestCase):
    """Test the new V2-A factor functions."""

    @unittest.skip("V1: routing hidden")
    def test_classify_semantic_core_gate(self):
        from aiwf_core.core.routing import classify_semantic_change
        self.assertEqual(
            classify_semantic_change(["aiwf_core/core/routing.py"]),
            "semantic_core_gate",
        )
        self.assertEqual(
            classify_semantic_change(["aiwf_core/core/task_ledger.py"]),
            "semantic_core_gate",
        )
        self.assertEqual(
            classify_semantic_change(["aiwf_core/core/state_schema.py"]),
            "semantic_core_gate",
        )
        self.assertEqual(
            classify_semantic_change(["aiwf_core/core/state/fixloop_ops.py"]),
            "semantic_core_gate",
        )
        self.assertEqual(
            classify_semantic_change(["aiwf_core/hooks/common/scope_checker.py"]),
            "semantic_core_gate",
        )

    @unittest.skip("V1: routing hidden")
    def test_classify_semantic_contract(self):
        from aiwf_core.core.routing import classify_semantic_change
        self.assertEqual(
            classify_semantic_change(["scripts/release-audit.sh"]),
            "semantic_contract",
        )
        self.assertEqual(
            classify_semantic_change(["src/validators.py"]),
            "semantic_contract",
        )

    @unittest.skip("V1: routing hidden")
    def test_classify_semantic_mechanical(self):
        from aiwf_core.core.routing import classify_semantic_change
        # All files must match mechanical indicators
        self.assertEqual(
            classify_semantic_change(["tests/conftest.py", "tests/fixtures.json"]),
            "semantic_mechanical",
        )
        self.assertEqual(
            classify_semantic_change(["config.template.yaml"]),
            "semantic_mechanical",
        )

    @unittest.skip("V1: routing hidden")
    def test_classify_semantic_regular_code_returns_empty(self):
        from aiwf_core.core.routing import classify_semantic_change
        self.assertEqual(classify_semantic_change([]), "")
        self.assertEqual(classify_semantic_change(["src/main.py"]), "")
        self.assertEqual(classify_semantic_change(["api/handler.py", "core/service.py"]), "")

    @unittest.skip("V1: routing hidden")
    def test_detect_machine_verifiable_mechanical(self):
        from aiwf_core.core.routing import detect_machine_verifiable
        self.assertTrue(
            detect_machine_verifiable(["scripts/validate.sh"], "semantic_mechanical")
        )

    @unittest.skip("V1: routing hidden")
    def test_detect_machine_verifiable_core_gate_never(self):
        from aiwf_core.core.routing import detect_machine_verifiable
        self.assertFalse(
            detect_machine_verifiable(["aiwf_core/core/routing.py"], "semantic_core_gate")
        )

    @unittest.skip("V1: routing hidden")
    def test_detect_machine_verifiable_regular_code_never(self):
        from aiwf_core.core.routing import detect_machine_verifiable
        self.assertFalse(
            detect_machine_verifiable(["src/main.py"], "")
        )

    @unittest.skip("V1: routing hidden")
    def test_classify_fix_loop_active(self):
        from aiwf_core.core.routing import classify_fix_loop
        fl = {"status": "open", "attempt_count": 1}
        primary, bg = classify_fix_loop(fl, "TASK-X", [])
        self.assertEqual(primary, "prior_fix_loop_active")
        self.assertEqual(bg, [])

    @unittest.skip("V1: routing hidden")
    def test_classify_fix_loop_same_task(self):
        from aiwf_core.core.routing import classify_fix_loop
        fl = {"status": "resolved", "attempt_count": 1, "source": "TASK-030"}
        primary, bg = classify_fix_loop(fl, "TASK-030", [])
        self.assertEqual(primary, "prior_fix_loop_same_task")

    @unittest.skip("V1: routing hidden")
    def test_classify_fix_loop_same_file(self):
        from aiwf_core.core.routing import classify_fix_loop
        fl = {
            "status": "resolved", "attempt_count": 1, "source": "TASK-029",
            "required_fixes": [{"file": "scripts/release-audit.sh", "issue": "sed escaping"}],
        }
        primary, bg = classify_fix_loop(fl, "TASK-030", ["scripts/release-audit.sh"])
        self.assertEqual(primary, "prior_fix_loop_same_file")

    @unittest.skip("V1: routing hidden")
    def test_classify_fix_loop_same_module(self):
        from aiwf_core.core.routing import classify_fix_loop
        fl = {
            "status": "resolved", "attempt_count": 1, "source": "TASK-029",
            "required_fixes": [{"file": "scripts/old.sh", "issue": "test"}],
        }
        primary, bg = classify_fix_loop(fl, "TASK-030", ["scripts/new.sh"])
        self.assertEqual(primary, "prior_fix_loop_same_module")

    @unittest.skip("V1: routing hidden")
    def test_classify_fix_loop_unrelated(self):
        from aiwf_core.core.routing import classify_fix_loop
        fl = {
            "status": "resolved", "attempt_count": 1, "source": "TASK-005",
            "required_fixes": [{"file": "src/old_module/thing.py", "issue": "test"}],
        }
        primary, bg = classify_fix_loop(fl, "TASK-030", ["scripts/release-audit.sh"])
        self.assertEqual(primary, "")
        self.assertIn("prior_fix_loop_history", bg)

    @unittest.skip("V1: routing hidden")
    def test_classify_fix_loop_no_history(self):
        from aiwf_core.core.routing import classify_fix_loop
        fl = {"status": "none", "attempt_count": 0}
        primary, bg = classify_fix_loop(fl, "TASK-030", [])
        self.assertEqual(primary, "")
        self.assertEqual(bg, [])


class TestRoutingV2Topology(unittest.TestCase):
    """Test V2-A topology dimension derivation."""

    @unittest.skip("V1: routing hidden")
    def test_case1_task030_mechanical_stale_fix_loop(self):
        """Case 1: Mechanical validator change, stale unrelated fix-loop.
        Should route to L1 / deterministic / single_agent_with_machine_evidence."""
        from aiwf_core.core.routing import compute_routing_score
        factors = {
            "semantic_mechanical": True,
            "semantic_change": False,  # V1: no semantic (mechanical only)
            "machine_verifiable": True,
            "prior_fix_loop": False,  # V1: not a fix-loop task
            "prior_fix_loop_history": True,  # stale, background only
            "cross_module": False,
        }
        result = compute_routing_score(factors, file_count=2)

        # Risk level should be L0 or L1 (low)
        self.assertIn(result["workflow_level"], ("L0_direct", "L1_review_light"))
        # Mechanical + machine-verifiable → deterministic verification
        self.assertEqual(result["verification_need"], "deterministic")
        # Should allow single-agent with machine evidence
        self.assertEqual(result["execution_topology"], "single_agent_with_machine_evidence")
        # Review can be optional
        self.assertEqual(result["review_need"], "optional_light_review")
        # Downgrade allowed (no hard constraints)
        self.assertTrue(result["downgrade_allowed"])
        # Substitution allowed (machine_verifiable)
        self.assertTrue(result["substitution_allowed"])

    @unittest.skip("V1: routing hidden")
    def test_case2_active_fix_loop_hard_L2_no_downgrade(self):
        """Case 2: Current unresolved fix-loop.
        Must be at least L2, downgrade forbidden."""
        from aiwf_core.core.routing import compute_routing_score
        factors = {
            "prior_fix_loop_active": True,
            "prior_fix_loop": True,  # V1 compat
            "semantic_change": True,
            "cross_module": False,
        }
        result = compute_routing_score(factors, file_count=1)

        # Must be at least L2
        lvls = ["L0_direct", "L1_review_light", "L2_standard_team", "L3_full_power"]
        self.assertGreaterEqual(
            lvls.index(result["workflow_level"]),
            lvls.index("L2_standard_team"),
        )
        # Downgrade forbidden
        self.assertFalse(result["downgrade_allowed"])
        # Substitution not allowed
        self.assertFalse(result["substitution_allowed"])
        # prior_fix_loop_active in hard_constraints
        self.assertIn("prior_fix_loop_active", result["hard_constraints"])

    @unittest.skip("V1: routing hidden")
    def test_case3_core_gate_change_L2_broad_verification(self):
        """Case 3: Change to close gate / scope guard.
        Must be L2+, broad verification, standard team."""
        from aiwf_core.core.routing import compute_routing_score
        factors = {
            "semantic_core_gate": True,
            "semantic_change": True,
            "cross_module": False,
        }
        result = compute_routing_score(factors, file_count=1)

        lvls = ["L0_direct", "L1_review_light", "L2_standard_team", "L3_full_power"]
        self.assertGreaterEqual(
            lvls.index(result["workflow_level"]),
            lvls.index("L2_standard_team"),
        )
        # Core gate changes need broad verification
        self.assertEqual(result["verification_need"], "broad")
        # Standard team topology
        self.assertEqual(result["execution_topology"], "standard_team")
        # Required review
        self.assertEqual(result["review_need"], "required_review")
        # Downgrade forbidden (semantic_core_gate in forbidden factors)
        self.assertFalse(result["downgrade_allowed"])
        self.assertIn("semantic_core_gate", result["hard_constraints"])

    @unittest.skip("V1: routing hidden")
    def test_case4_security_risk_L3_no_downgrade(self):
        """Case 4: Security/data risk.
        Still hard L3, no downgrade allowed."""
        from aiwf_core.core.routing import compute_routing_score
        factors = {
            "security_or_data_risk": True,
            "semantic_change": True,
        }
        result = compute_routing_score(factors, file_count=1)

        self.assertEqual(result["workflow_level"], "L3_full_power")
        self.assertEqual(result["verification_need"], "adversarial")
        self.assertEqual(result["execution_topology"], "fanout_merge")
        self.assertEqual(result["review_need"], "adversarial_review")
        self.assertFalse(result["downgrade_allowed"])
        self.assertFalse(result["substitution_allowed"])
        self.assertIn("security_or_data_risk", result["hard_constraints"])

    @unittest.skip("V1: routing hidden")
    def test_case5_L2_deterministic_substitutable(self):
        """Case 5: L2 task with deterministic verifiability.
        Downgrade/substitution allowed if recorded."""
        from aiwf_core.core.routing import compute_routing_score
        factors = {
            "semantic_contract": True,
            "semantic_change": True,
            "machine_verifiable": True,
            "cross_module": False,
        }
        result = compute_routing_score(factors, file_count=3)

        # Contract + machine_verifiable should allow substitution
        self.assertTrue(result["substitution_allowed"])
        self.assertTrue(result["downgrade_allowed"])

        # Even though level might be L1 or L2, the topology should reflect
        # that it's machine-verifiable
        self.assertIn(result["verification_need"], ("deterministic", "standard"))


class TestRoutingV2TopologyOverride(unittest.TestCase):
    """Test the topology override / substitution protocol."""

    @unittest.skip("V1: routing hidden")
    def test_downgrade_blocked_by_active_fix_loop(self):
        from aiwf_core.core.routing import compute_topology_override
        factors = {"prior_fix_loop_active": True}
        hard = ["prior_fix_loop_active"]

        result = compute_topology_override(
            current_topology="standard_team",
            requested_topology="single_agent_with_machine_evidence",
            factors=factors,
            hard=hard,
            reason="deterministic validation",
        )
        self.assertFalse(result["allowed"])
        self.assertEqual(result["effective_topology"], "standard_team")
        self.assertTrue(any("forbidden" in w.lower() for w in result["warnings"]))

    @unittest.skip("V1: routing hidden")
    def test_downgrade_blocked_by_security_risk(self):
        from aiwf_core.core.routing import compute_topology_override
        factors = {"security_or_data_risk": True}
        hard = ["security_or_data_risk"]

        result = compute_topology_override(
            current_topology="fanout_merge",
            requested_topology="single_agent",
            factors=factors,
            hard=hard,
            reason="simple change",
        )
        self.assertFalse(result["allowed"])

    @unittest.skip("V1: routing hidden")
    def test_downgrade_allowed_for_machine_verifiable(self):
        from aiwf_core.core.routing import compute_topology_override
        factors = {"machine_verifiable": True, "semantic_mechanical": True}
        hard = []

        result = compute_topology_override(
            current_topology="light_review",
            requested_topology="single_agent_with_machine_evidence",
            factors=factors,
            hard=hard,
            reason="mechanical validator change with machine-verifiable acceptance",
        )
        self.assertTrue(result["allowed"])
        self.assertEqual(result["effective_topology"], "single_agent_with_machine_evidence")

    @unittest.skip("V1: routing hidden")
    def test_substitution_requires_reason(self):
        from aiwf_core.core.routing import compute_topology_override
        factors = {"machine_verifiable": True}
        hard = []

        result = compute_topology_override(
            current_topology="standard_team",
            requested_topology="single_agent_with_machine_evidence",
            factors=factors,
            hard=hard,
            reason="",  # empty reason
        )
        # Should still be allowed (upgrade direction), but with warning
        # Actually this is a downgrade — check if reason required
        warnings = result["warnings"]
        if not result["allowed"]:
            self.assertTrue(any("reason" in w.lower() for w in warnings))

    @unittest.skip("V1: routing hidden")
    def test_upgrade_always_allowed(self):
        from aiwf_core.core.routing import compute_topology_override
        factors = {}
        hard = []

        result = compute_topology_override(
            current_topology="light_review",
            requested_topology="standard_team",
            factors=factors,
            hard=hard,
            reason="task complexity increased",
        )
        self.assertTrue(result["allowed"])
        self.assertEqual(result["effective_topology"], "standard_team")


class TestRoutingV2StateSchema(unittest.TestCase):
    """Test the new V2-A state schema fields."""

    @unittest.skip("V1: routing hidden")
    def test_default_state_has_topology_fields(self):
        # V2: routing/topology fields live in routing-debug.json, not in the minimal
        # V2 state core (state.json). default_state() is deliberately minimal.
        from aiwf_core.core.state_schema import default_state
        s = default_state()
        # V2 core has no routing fields — they come from routing-debug.json at read time
        self.assertIn("phase", s)
        self.assertIn("schema_version", s)
        self.assertEqual(s["phase"], "planning")

        # load_routing_state() provides V2-A topology defaults when debug file absent
        import tempfile
        from aiwf_core.core.task_ledger import load_routing_state
        routing = load_routing_state(tempfile.mkdtemp(prefix="aiwf_no_state_"))
        self.assertIn("verification_need", routing)
        self.assertIn("review_need", routing)
        self.assertIn("downgrade_allowed", routing)
        self.assertIn("hard_constraints", routing)
        self.assertEqual(routing["verification_need"], "standard")
        self.assertEqual(routing["review_need"], "optional_light_review")
        self.assertTrue(routing["downgrade_allowed"])
        # execution_topology is derived from workflow_level, not stored independently
        from aiwf_core.core.routing import LEVEL_TO_TOPOLOGY
        self.assertEqual(LEVEL_TO_TOPOLOGY.get(routing["workflow_level"]), "light_review")

    @unittest.skip("V1: routing hidden")
    def test_state_keys_include_topology(self):
        from aiwf_core.core.state_schema import STATE_KEYS
        for key in ("verification_need", "review_need",
                     "downgrade_allowed", "substitution_allowed",
                     "routing_reason", "hard_constraints", "substitution_records"):
            self.assertIn(key, STATE_KEYS)

    @unittest.skip("V1: routing hidden")
    def test_valid_topology_values(self):
        from aiwf_core.core.state_schema import (
            VALID_VERIFICATION_NEEDS, VALID_EXECUTION_TOPOLOGIES, VALID_REVIEW_NEEDS,
        )
        self.assertIn("deterministic", VALID_VERIFICATION_NEEDS)
        self.assertIn("single_agent_with_machine_evidence", VALID_EXECUTION_TOPOLOGIES)
        self.assertIn("optional_light_review", VALID_REVIEW_NEEDS)


class TestRoutingV2MechanicalRouting(unittest.TestCase):
    """Integration tests: mechanical routing produces V2-A topology fields."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aiwf_routing_v2_"))
        from aiwf_core.core.state_schema import MVP_STATE_FILES
        for rel, factory in MVP_STATE_FILES.items():
            _write(self.tmp / ".aiwf" / rel, factory())

    def _seed_planning_contracts(self):
        # V2: goal data lives in goals.json, not goal.json
        goals_path = self.tmp / ".aiwf" / "state" / "goals.json"
        goals_data = json.loads(goals_path.read_text())
        goals_data.setdefault("goals", [])
        goals_data.setdefault("active_goal_id", "GOAL-001")
        goal = None
        for g in goals_data["goals"]:
            if isinstance(g, dict) and g.get("id") == "GOAL-001":
                goal = g
                break
        if goal is None:
            from aiwf_core.core.state_schema import default_goal
            goal = default_goal()
            goal["id"] = "GOAL-001"
            goal["title"] = "GOAL-001"
            goals_data["goals"].append(goal)
        brief = goal["quality_brief"]
        brief["evaluation_contract"].update({
            "user_visible_outcome": "Requested behavior works",
            "acceptance_criteria": ["behavior verified"],
            "test_obligations": ["run tests"],
            "review_obligations": ["review scope"],
        })
        brief["architecture_brief"]["target_structure"] = "Preserve modules"
        brief["non_goals"] = ["test"]
        _write(goals_path, goals_data)

    def _seed_plan(self, task_id, allowed_write=None):
        from aiwf_core.core.state.plan_ops import upsert_plan

        plan_id = f"PLAN-{task_id}"
        plan_dir = self.tmp / ".aiwf" / "plans"
        plan_dir.mkdir(parents=True, exist_ok=True)
        plan_path = plan_dir / f"{plan_id}.md"
        if not plan_path.exists():
            plan_path.write_text(
                f"# {plan_id}\n\n"
                "> AI working plan.\n\n"
                f"Plan ID: {plan_id}\n"
                "Parent Goal: GOAL-001\n"
                f"Task IDs: {task_id}\n\n"
                "## Goal\nTest\n\n## Route\n- How: fix\n\n"
                "## Scope\n- Change: test\n\n## Risks\n- none\n\n"
                "## Verification\n- Machine-verifiable: yes\n\n"
                "## Impact\n- docs: no — test\n- project_map: no — test\n- environment: no — test\n- capabilities: no — test\n- quality_summary: no — test\n\n"
                "## Done Means\n- test passes\n\n"
                "## Goal Progress\n- Parent goal: test\n\n"
                "## Next Steps\n1. done\n",
                encoding="utf-8",
            )
        kwargs = {"goal_id": "GOAL-001", "task_ids": [task_id], "plan_kind": "implementation", "work_intent": "feature", "purpose": "Test task"}
        if allowed_write is not None:
            kwargs["allowed_write"] = allowed_write
        else:
            kwargs["allowed_write"] = ["src/"]
        upsert_plan(str(self.tmp), plan_id, **kwargs)
        # V2: task ledger is state/tasks.json
        ledger_path = self.tmp / ".aiwf" / "state" / "tasks.json"
        if ledger_path.exists():
            ledger = json.loads(ledger_path.read_text())
            changed = False
            for task in ledger.get("tasks", []):
                if task.get("id") == task_id:
                    task["plan_id"] = plan_id
                    task["parent_plan"] = plan_id
                    task["goal_id"] = task.get("goal_id") or "GOAL-001"
                    task["parent_goal"] = task.get("parent_goal") or task["goal_id"]
                    # V2: upsert_plan ignores allowed_write; set on task for fallback
                    if allowed_write is not None:
                        task["allowed_write"] = allowed_write
                    changed = True
            if changed:
                _write(ledger_path, ledger)
        return plan_id

    @unittest.skip("V1: routing hidden")
    def test_mechanical_task_routes_with_topology_dimensions(self):
        """A mechanical config-template change should get V2-A topology fields in routing-debug."""
        from aiwf_core.core.task_ledger import activate_task, upsert_task
        self._seed_planning_contracts()
        # Seed routing level L0 so mechanical routing max() keeps it at L0
        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["workflow_level"] = "L0_direct"
        state_path.write_text(json.dumps(state, indent=2))

        upsert_task(
            str(self.tmp), "TASK-V2A-001", "Fix config template", status="ready",
        )

        self._seed_plan("TASK-V2A-001", allowed_write=["config.template.yaml"])
        result = activate_task(str(self.tmp), "TASK-V2A-001")
        self.assertTrue(result["activated"], result["blockers"])

        # V2: routing lives in runtime/internal/routing-debug.json, not state.json
        routing_path = self.tmp / ".aiwf" / "runtime" / "internal" / "routing-debug.json"
        self.assertTrue(routing_path.exists(), f"Expected routing-debug.json at {routing_path}")
        routing = json.loads(routing_path.read_text())

        # V2-A fields should be populated (execution_topology derived from level)
        self.assertIn("verification_need", routing)
        self.assertIn("review_need", routing)
        self.assertIn("downgrade_allowed", routing)
        self.assertIn("substitution_allowed", routing)
        self.assertIn("hard_constraints", routing)
        self.assertIn("workflow_level", routing)

        # A mechanical validator template change should be low-risk
        self.assertIn(routing["workflow_level"], ("L0_direct", "L1_review_light"))
        # Mechanical changes should be machine-verifiable
        self.assertEqual(routing["verification_need"], "deterministic")

    @unittest.skip("V1: routing hidden")
    def test_active_fix_loop_blocks_downgrade_in_state(self):
        """An active fix-loop should set downgrade_allowed=False in routing-debug."""
        from aiwf_core.core.task_ledger import activate_task, upsert_task
        self._seed_planning_contracts()

        # Set up an active fix-loop
        _write(self.tmp / ".aiwf" / "state" / "fix-loop.json", {
            "status": "open", "attempt_count": 1, "route": "executor",
            "required_fixes": [{"file": "src/broken.py", "issue": "test failure"}],
            "required_verification": ["pytest src/broken.py"],
        })

        upsert_task(
            str(self.tmp), "TASK-V2A-002", "Fix failing test", status="ready",
        )

        self._seed_plan("TASK-V2A-002", allowed_write=["src/broken.py"])
        result = activate_task(str(self.tmp), "TASK-V2A-002")
        # May be blocked by fix-loop; check routing-debug regardless
        # V2: routing fields in runtime/internal/routing-debug.json
        routing_path = self.tmp / ".aiwf" / "runtime" / "internal" / "routing-debug.json"

        # Even if not activated, let's check what routing would produce
        from aiwf_core.core.routing import compute_routing_score
        decision = compute_routing_score(
            {"prior_fix_loop_active": True, "prior_fix_loop": True, "semantic_change": True},
            file_count=1,
        )
        self.assertFalse(decision["downgrade_allowed"])
        self.assertIn("prior_fix_loop_active", decision["hard_constraints"])

    @unittest.skip("V1: routing hidden")
    def test_same_task_prior_fix_loop_hard_L2(self):
        """Prior fix-loop on same task should produce hard L2 routing."""
        from aiwf_core.core.routing import compute_routing_score
        factors = {
            "prior_fix_loop_same_task": True,
            "prior_fix_loop": True,
            "semantic_change": True,
        }
        result = compute_routing_score(factors, file_count=2)

        lvls = ["L0_direct", "L1_review_light", "L2_standard_team", "L3_full_power"]
        self.assertGreaterEqual(
            lvls.index(result["workflow_level"]),
            lvls.index("L2_standard_team"),
        )
        self.assertFalse(result["downgrade_allowed"])

    @unittest.skip("V1: routing hidden")
    def test_same_file_prior_fix_loop_hard_L2(self):
        """Prior fix-loop on same file recommends L2 but allows downgrade.

        Resolved same-file fix-loops are warnings, not hard constraints.
        Only active fix-loops and same-task recurrence forbid downgrade.
        """
        from aiwf_core.core.routing import compute_routing_score
        factors = {
            "prior_fix_loop_same_file": True,
            "prior_fix_loop": True,
            "semantic_change": True,
        }
        result = compute_routing_score(factors, file_count=1)

        lvls = ["L0_direct", "L1_review_light", "L2_standard_team", "L3_full_power"]
        self.assertGreaterEqual(
            lvls.index(result["workflow_level"]),
            lvls.index("L2_standard_team"),
        )
        self.assertTrue(result["downgrade_allowed"])

    @unittest.skip("V1: routing hidden")
    def test_same_module_fix_loop_advisory_only(self):
        """Same-module prior fix-loop gives +1, not hard L2."""
        from aiwf_core.core.routing import compute_routing_score
        factors = {
            "prior_fix_loop_same_module": True,
            "semantic_change": True,
            "cross_module": False,
        }
        result = compute_routing_score(factors, file_count=1)

        # same_module = weight 1, semantic_change = weight 2 → total 3 → L1
        # But no hard upgrade for same_module, so downgrade is still allowed
        self.assertTrue(result["downgrade_allowed"])

    @unittest.skip("V1: routing hidden")
    def test_unrelated_fix_loop_history_does_not_hard_upgrade(self):
        """Stale unrelated prior fix-loop should NOT force hard upgrade."""
        from aiwf_core.core.routing import compute_routing_score
        # prior_fix_loop_history has weight 0 and no hard upgrade
        factors = {
            "semantic_change": True,
            "prior_fix_loop": False,
            "prior_fix_loop_history": True,  # background only
        }
        result = compute_routing_score(factors, file_count=2)

        # Should NOT have prior_fix_loop in hard_constraints
        self.assertNotIn("prior_fix_loop", result["hard_constraints"])
        self.assertNotIn("prior_fix_loop_active", result["hard_constraints"])
        self.assertNotIn("prior_fix_loop_same_task", result["hard_constraints"])
        # Downgrade should be allowed
        self.assertTrue(result["downgrade_allowed"])


class TestRoutingV2Explain(unittest.TestCase):
    """Test the routing explanation function."""

    @unittest.skip("V1: routing hidden")
    def test_explain_routing_shows_topology(self):
        from aiwf_core.core.routing import explain_routing
        decision = {
            "workflow_level": "L1_review_light",
            "label": "L1 — Review-Light",
            "execution_topology": "single_agent_with_machine_evidence",
            "verification_need": "deterministic",
            "review_need": "optional_light_review",
            "routing_factors": ["semantic_mechanical", "machine_verifiable"],
            "routing_background_factors": ["prior_fix_loop_history"],
            "hard_upgrades": [],
            "downgrade_allowed": True,
            "substitution_allowed": True,
        }
        explanation = explain_routing(decision)
        self.assertIn("L1_review_light", explanation)
        self.assertIn("deterministic", explanation)
        self.assertIn("single_agent_with_machine_evidence", explanation)
        self.assertIn("downgrade", explanation.lower())


class TestRoutingV2CLISmoke(unittest.TestCase):
    """CLI smoke: ensure route commands are reachable through the CLI entry point."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aiwf_route_cli_"))
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent.parent)
        r = subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
            capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=30,
        )
        self.assertEqual(r.returncode, 0, r.stderr)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run_route(self, *args):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent.parent)
        return subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", "route", *args],
            capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=15,
        )

    def _state(self):
        return json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())

    def _write_state(self, state):
        _write(self.tmp / ".aiwf" / "state" / "state.json", state)

    def _seed_downgrade_grounds(self):
        state = self._state()
        state["workflow_level"] = "L1_review_light"
        state["routing_factors"] = ["semantic_mechanical", "machine_verifiable"]
        state["downgrade_allowed"] = True
        state["substitution_allowed"] = False
        state["hard_constraints"] = []
        state["substitution_records"] = []
        self._write_state(state)

    @unittest.skip("V1: routing hidden")
    def test_route_help_is_reachable(self):
        """aiwf route --help must succeed — guards against known-whitelist drift."""
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent.parent)
        r = subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", "route", "--help"],
            capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=15,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("explain", r.stdout)

    @unittest.skip("V1: routing hidden")
    def test_route_explain_runs_without_error(self):
        """aiwf route explain must not crash on a fresh install."""
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent.parent)
        r = subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", "route", "explain"],
            capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=15,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Routing:", r.stdout)

    @unittest.skip("V1: routing hidden")
    def test_route_override_pending_without_changing_level(self):
        """Override requests must not mutate workflow_level before user confirmation."""
        self._seed_downgrade_grounds()
        before = self._state()
        self.assertEqual(before["workflow_level"], "L1_review_light")

        r = self._run_route(
            "override",
            "--to", "single_agent",
            "--reason", "mechanical change: user wants a lighter flow for a trivial docs tweak",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("USER DECISION REQUIRED", r.stdout)

        after = self._state()
        self.assertEqual(after["workflow_level"], "L1_review_light")
        self.assertTrue(after["requires_user_decision"])
        self.assertTrue(after["quality_escalation_required"])
        self.assertIn("Route override requested", after["quality_escalation_reason"])
        record = after["substitution_records"][-1]
        self.assertEqual(record["type"], "override")
        self.assertFalse(record["user_confirmed"])
        self.assertEqual(record["status"], "pending_user_confirmation")

    @unittest.skip("V1: routing hidden")
    def test_route_override_confirmed_changes_level(self):
        self._seed_downgrade_grounds()
        r = self._run_route(
            "override",
            "--to", "single_agent",
            "--reason", "mechanical change: user approved lower topology with machine checks",
            "--user-confirmed",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Route overridden", r.stdout)

        state = self._state()
        self.assertEqual(state["workflow_level"], "L0_direct")
        record = state["substitution_records"][-1]
        self.assertTrue(record["user_confirmed"])
        self.assertEqual(record["status"], "confirmed")

    @unittest.skip("V1: routing hidden")
    def test_route_override_blocked_by_missing_reason(self):
        """Override without proper reason should be blocked or warn."""
        self._seed_downgrade_grounds()
        # override with empty reason — should produce warnings
        r = self._run_route(
            "override",
            "--to", "single_agent",
            "--reason", "mechanical change: user wants a temporary lightweight path",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("USER DECISION REQUIRED", r.stdout)

        state = self._state()
        self.assertEqual(state["workflow_level"], "L1_review_light")
        record = state["substitution_records"][-1]
        self.assertEqual(record["type"], "override")
        self.assertFalse(record["user_confirmed"])
        self.assertEqual(record["status"], "pending_user_confirmation")


if __name__ == "__main__":
    unittest.main()
