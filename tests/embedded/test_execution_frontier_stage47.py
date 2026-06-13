"""Contract tests for Stage 4.7: Semantic Execution Frontier + Work Packet."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _install(cwd):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    subprocess.run(
        [sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
        capture_output=True, text=True, cwd=str(cwd), env=env, timeout=20,
    )


def _setup_goals(base_dir):
    """Create goals.json with a root Goal for reference checks."""
    goals = {
        "schema_version": 1,
        "active_goal_id": "GOAL-001",
        "roots": ["GOAL-001"],
        "goals": [
            {
                "id": "GOAL-001",
                "title": "Root Goal",
                "root_type": "main",
                "parent_goal_id": None,
                "child_goal_ids": ["GOAL-002"],
                "children_order": ["GOAL-002"],
                "intent": "Root functional goal",
                "acceptance_boundary": "",
                "attached_plan_ids": ["PLAN-001"],
                "status": "active",
                "visibility": "default",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            },
            {
                "id": "GOAL-002",
                "title": "Child Goal",
                "root_type": "",
                "parent_goal_id": "GOAL-001",
                "child_goal_ids": [],
                "children_order": [],
                "intent": "Child goal for testing",
                "acceptance_boundary": "",
                "attached_plan_ids": [],
                "status": "active",
                "visibility": "default",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            },
        ],
        "relations": [],
    }
    os.makedirs(os.path.join(base_dir, ".aiwf", "state"), exist_ok=True)
    with open(os.path.join(base_dir, ".aiwf", "state", "goals.json"), "w", encoding="utf-8") as f:
        json.dump(goals, f)


def _setup_plans(base_dir):
    """Create plans.json with test plans."""
    plans = {
        "schema_version": 1,
        "active_plan_id": "PLAN-001",
        "plans": [
            {
                "id": "PLAN-001",
                "title": "Implementation Plan",
                "target_goal_id": "GOAL-001",
                "kind": "implementation",
                "active_phase": "implementation",
                "status": "active",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            },
            {
                "id": "PLAN-002",
                "title": "Structural Plan",
                "target_goal_id": "GOAL-001",
                "kind": "structural",
                "active_phase": "framing",
                "status": "active",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            },
            {
                "id": "PLAN-003",
                "title": "Mismatch Plan",
                "target_goal_id": "GOAL-002",
                "kind": "implementation",
                "active_phase": "implementation",
                "status": "active",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            },
        ],
    }
    with open(os.path.join(base_dir, ".aiwf", "state", "plans.json"), "w", encoding="utf-8") as f:
        json.dump(plans, f)


def _make_valid_execute_plan():
    return {
        "frontier_type": "execute_plan",
        "selected_plan_id": "PLAN-001",
        "target_goal_id": "GOAL-001",
        "dispatch_to": "executor",
        "reason": "Implementation plan is ready for execution.",
        "active_phase": "implementation",
        "work_intent": "feature",
        "scope": "Implement the goal tree registry module.",
        "interfaces": [],
        "constraints": ["Do not change task activation."],
        "expected_evidence": [
            "goals.json is created during init.",
            "Root goal can be upserted.",
        ],
        "forbidden_changes": [],
        "rollup_target": "GOAL-001",
        "review_focus": [],
        "confidence": "high",
        "needs_human_confirmation": False,
    }


class TestFrontierValidation(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awf47v_"))
        _install(cls.tmp)
        _setup_goals(str(cls.tmp))
        _setup_plans(str(cls.tmp))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _validate(self, decision):
        from aiwf_core.core.frontier_ops import validate_frontier_decision
        return validate_frontier_decision(str(self.tmp), decision)

    # ── Universal checks ──

    def test_valid_execute_plan_passes(self):
        decision = _make_valid_execute_plan()
        result = self._validate(decision)
        self.assertTrue(result["valid"], f"Should be valid, got: {result.get('issues')}")
        self.assertEqual([], result["issues"])

    def test_invalid_frontier_type_rejected(self):
        decision = {**_make_valid_execute_plan(), "frontier_type": "nonexistent"}
        result = self._validate(decision)
        self.assertFalse(result["valid"])
        self.assertTrue(any("frontier_type" in i for i in result["issues"]))

    def test_invalid_dispatch_to_rejected(self):
        decision = {**_make_valid_execute_plan(), "dispatch_to": "janitor"}
        result = self._validate(decision)
        self.assertFalse(result["valid"])
        self.assertTrue(any("dispatch_to" in i for i in result["issues"]))

    def test_missing_reason_fails(self):
        decision = {**_make_valid_execute_plan(), "reason": ""}
        result = self._validate(decision)
        self.assertFalse(result["valid"])
        self.assertTrue(any("reason" in i for i in result["issues"]))

    def test_invalid_confidence_rejected(self):
        decision = {**_make_valid_execute_plan(), "confidence": "absolute"}
        result = self._validate(decision)
        self.assertFalse(result["valid"])

    def test_invalid_active_phase_rejected(self):
        decision = {**_make_valid_execute_plan(), "active_phase": "destroying"}
        result = self._validate(decision)
        self.assertFalse(result["valid"])

    # ── execute_plan checks ──

    def test_execute_plan_missing_selected_plan_id_fails(self):
        decision = _make_valid_execute_plan()
        del decision["selected_plan_id"]
        result = self._validate(decision)
        self.assertFalse(result["valid"])
        self.assertTrue(any("selected_plan_id" in i for i in result["issues"]))

    def test_execute_plan_missing_expected_evidence_fails(self):
        decision = _make_valid_execute_plan()
        decision["expected_evidence"] = []
        result = self._validate(decision)
        self.assertFalse(result["valid"])
        self.assertTrue(any("expected_evidence" in i for i in result["issues"]))

    def test_execute_plan_missing_scope_fails(self):
        decision = _make_valid_execute_plan()
        decision["scope"] = ""
        result = self._validate(decision)
        self.assertFalse(result["valid"])
        self.assertTrue(any("scope" in i for i in result["issues"]))

    def test_execute_plan_missing_target_goal_id_fails(self):
        decision = _make_valid_execute_plan()
        del decision["target_goal_id"]
        result = self._validate(decision)
        self.assertFalse(result["valid"])
        self.assertTrue(any("target_goal_id" in i for i in result["issues"]))

    def test_execute_plan_missing_rollup_target_fails(self):
        decision = _make_valid_execute_plan()
        decision["rollup_target"] = ""
        result = self._validate(decision)
        self.assertFalse(result["valid"])
        self.assertTrue(any("rollup_target" in i for i in result["issues"]))

    def test_execute_plan_wrong_dispatch_to_fails(self):
        decision = {**_make_valid_execute_plan(), "dispatch_to": "tester"}
        result = self._validate(decision)
        self.assertFalse(result["valid"])

    def test_execute_plan_nonexistent_plan_id_fails(self):
        decision = {**_make_valid_execute_plan(), "selected_plan_id": "PLAN-999"}
        result = self._validate(decision)
        self.assertFalse(result["valid"])
        self.assertTrue(any("PLAN-999" in i for i in result["issues"]))

    def test_execute_plan_nonexistent_target_goal_fails(self):
        decision = {**_make_valid_execute_plan(), "target_goal_id": "GOAL-999"}
        result = self._validate(decision)
        self.assertFalse(result["valid"])
        self.assertTrue(any("GOAL-999" in i for i in result["issues"]))

    def test_structural_plan_execute_warns(self):
        decision = {
            **_make_valid_execute_plan(),
            "selected_plan_id": "PLAN-002",
            "target_goal_id": "GOAL-001",
        }
        result = self._validate(decision)
        self.assertTrue(result["valid"], f"Should be valid, got issues: {result.get('issues')}")
        self.assertTrue(
            any("structural" in w.lower() for w in result.get("warnings", [])),
            f"Should warn about structural plan, got: {result.get('warnings')}",
        )

    # ── verify_plan checks ──

    def test_verify_plan_valid(self):
        decision = {
            "frontier_type": "verify_plan",
            "selected_plan_id": "PLAN-001",
            "target_goal_id": "GOAL-001",
            "dispatch_to": "tester",
            "reason": "Verify the implementation.",
            "expected_evidence": ["Tests pass"],
            "confidence": "high",
        }
        result = self._validate(decision)
        self.assertTrue(result["valid"], f"Should be valid, got: {result.get('issues')}")

    def test_verify_plan_missing_expected_evidence_fails(self):
        decision = {
            "frontier_type": "verify_plan",
            "selected_plan_id": "PLAN-001",
            "target_goal_id": "GOAL-001",
            "dispatch_to": "tester",
            "reason": "Verify the implementation.",
            "expected_evidence": [],
            "confidence": "high",
        }
        result = self._validate(decision)
        self.assertFalse(result["valid"])

    def test_verify_plan_wrong_dispatch_to_fails(self):
        decision = {
            "frontier_type": "verify_plan",
            "selected_plan_id": "PLAN-001",
            "target_goal_id": "GOAL-001",
            "dispatch_to": "executor",
            "reason": "Verify the implementation.",
            "expected_evidence": ["Tests pass"],
            "confidence": "high",
        }
        result = self._validate(decision)
        self.assertFalse(result["valid"])

    # ── review_plan checks ──

    def test_review_plan_valid_with_review_focus(self):
        decision = {
            "frontier_type": "review_plan",
            "selected_plan_id": "PLAN-001",
            "dispatch_to": "reviewer",
            "reason": "Review the completed implementation.",
            "review_focus": ["Check scope boundaries.", "Verify evidence rollup."],
            "confidence": "high",
        }
        result = self._validate(decision)
        self.assertTrue(result["valid"], f"Should be valid, got: {result.get('issues')}")

    def test_review_plan_missing_review_focus_and_evidence_fails(self):
        decision = {
            "frontier_type": "review_plan",
            "selected_plan_id": "PLAN-001",
            "dispatch_to": "reviewer",
            "reason": "Review the completed implementation.",
            "review_focus": [],
            "expected_evidence": [],
            "confidence": "high",
        }
        result = self._validate(decision)
        self.assertFalse(result["valid"])

    def test_review_plan_wrong_dispatch_to_fails(self):
        decision = {
            "frontier_type": "review_plan",
            "selected_plan_id": "PLAN-001",
            "dispatch_to": "tester",
            "reason": "Review the completed implementation.",
            "review_focus": ["Check scope."],
            "confidence": "high",
        }
        result = self._validate(decision)
        self.assertFalse(result["valid"])

    # ── integrate_goal checks ──

    def test_integrate_goal_valid(self):
        decision = {
            "frontier_type": "integrate_goal",
            "target_goal_id": "GOAL-001",
            "dispatch_to": "architect",
            "reason": "Integrate child goals before sealing.",
            "confidence": "high",
        }
        result = self._validate(decision)
        self.assertTrue(result["valid"], f"Should be valid, got: {result.get('issues')}")

    def test_integrate_goal_missing_target_goal_id_fails(self):
        decision = {
            "frontier_type": "integrate_goal",
            "dispatch_to": "architect",
            "reason": "Integrate child goals.",
            "confidence": "high",
        }
        result = self._validate(decision)
        self.assertFalse(result["valid"])

    def test_integrate_goal_no_children_warns(self):
        decision = {
            "frontier_type": "integrate_goal",
            "target_goal_id": "GOAL-002",
            "dispatch_to": "architect",
            "reason": "Integrate this goal.",
            "confidence": "high",
        }
        result = self._validate(decision)
        self.assertTrue(result["valid"], f"Should be valid, got: {result.get('issues')}")
        self.assertTrue(
            any("no attached plans" in w.lower() or "child goals" in w.lower()
                for w in result.get("warnings", [])),
            f"Should warn about no children/plans, got: {result.get('warnings')}",
        )

    # ── architect_structure checks ──

    def test_architect_structure_valid_with_interfaces(self):
        decision = {
            "frontier_type": "architect_structure",
            "target_goal_id": "GOAL-001",
            "dispatch_to": "architect",
            "reason": "Define the architecture skeleton.",
            "interfaces": ["goal_tree_ops.py"],
            "confidence": "high",
        }
        result = self._validate(decision)
        self.assertTrue(result["valid"], f"Should be valid, got: {result.get('issues')}")

    def test_architect_structure_missing_interfaces_constraints_fails(self):
        decision = {
            "frontier_type": "architect_structure",
            "target_goal_id": "GOAL-001",
            "dispatch_to": "architect",
            "reason": "Define the architecture.",
            "interfaces": [],
            "constraints": [],
            "confidence": "high",
        }
        result = self._validate(decision)
        self.assertFalse(result["valid"])
        self.assertTrue(any("interfaces" in i for i in result["issues"]))

    # ── explore_temporary_root checks ──

    def test_explore_temporary_root_valid(self):
        decision = {
            "frontier_type": "explore_temporary_root",
            "target_goal_id": "GOAL-001",
            "dispatch_to": "architect",
            "reason": "Explore potential new module structure.",
            "confidence": "low",
            "needs_human_confirmation": True,
        }
        result = self._validate(decision)
        self.assertTrue(result["valid"], f"Should be valid, got: {result.get('issues')}")
        self.assertTrue(
            any("graft" in w.lower() or "prune" in w.lower()
                for w in result.get("warnings", [])),
            f"Should warn about graft/prune, got: {result.get('warnings')}",
        )

    # ── dispatch_to required (4.7.1 precision) ──

    def test_missing_dispatch_to_fails(self):
        decision = _make_valid_execute_plan()
        del decision["dispatch_to"]
        result = self._validate(decision)
        self.assertFalse(result["valid"])
        self.assertTrue(any("dispatch_to" in i for i in result["issues"]))

    def test_verify_plan_missing_target_goal_id_fails(self):
        decision = {
            "frontier_type": "verify_plan",
            "selected_plan_id": "PLAN-001",
            "dispatch_to": "tester",
            "reason": "Verify the implementation.",
            "expected_evidence": ["Tests pass"],
            "confidence": "high",
        }
        result = self._validate(decision)
        self.assertFalse(result["valid"])
        self.assertTrue(any("target_goal_id" in i for i in result["issues"]))

    def test_execute_plan_missing_dispatch_to_fails_with_clear_message(self):
        decision = _make_valid_execute_plan()
        del decision["dispatch_to"]
        result = self._validate(decision)
        self.assertIn("dispatch_to is required", str(result["issues"]))

    def test_integrate_goal_missing_dispatch_to_fails(self):
        decision = {
            "frontier_type": "integrate_goal",
            "target_goal_id": "GOAL-001",
            "reason": "Integrate child goals.",
            "confidence": "high",
        }
        result = self._validate(decision)
        self.assertFalse(result["valid"])
        self.assertTrue(any("dispatch_to" in i for i in result["issues"]))

    def test_architect_structure_missing_dispatch_to_fails(self):
        decision = {
            "frontier_type": "architect_structure",
            "target_goal_id": "GOAL-001",
            "reason": "Define the architecture.",
            "interfaces": ["goal_tree_ops.py"],
            "confidence": "high",
        }
        result = self._validate(decision)
        self.assertFalse(result["valid"])
        self.assertTrue(any("dispatch_to" in i for i in result["issues"]))

    # ── confidence checks ──

    def test_low_confidence_without_human_confirmation_warns(self):
        decision = {
            **_make_valid_execute_plan(),
            "confidence": "low",
            "needs_human_confirmation": False,
        }
        result = self._validate(decision)
        self.assertTrue(result["valid"], f"Should be valid, got issues: {result.get('issues')}")
        self.assertTrue(
            any("human" in w.lower() and "confirmation" in w.lower()
                for w in result.get("warnings", [])),
            f"Should warn about human confirmation, got: {result.get('warnings')}",
        )

    # ── plan target_goal_id mismatch ──

    def test_plan_target_goal_mismatch_warns(self):
        """PLAN-003 has target_goal_id=GOAL-002 but decision says GOAL-001."""
        decision = {
            **_make_valid_execute_plan(),
            "selected_plan_id": "PLAN-003",
            "target_goal_id": "GOAL-001",
        }
        result = self._validate(decision)
        self.assertTrue(result["valid"], f"Should be valid with warning, got: {result.get('issues')}")
        self.assertTrue(
            any("mismatch" in w.lower() or "plan" in w.lower()
                for w in result.get("warnings", [])),
            f"Should warn about plan/goal mismatch, got: {result.get('warnings')}",
        )


class TestFrontierPrepare(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awf47p_"))
        _install(cls.tmp)
        _setup_goals(str(cls.tmp))
        _setup_plans(str(cls.tmp))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _prepare(self, decision):
        from aiwf_core.core.frontier_ops import prepare_work_packet
        return prepare_work_packet(str(self.tmp), decision)

    def test_prepare_valid_returns_human_packet(self):
        decision = _make_valid_execute_plan()
        result = self._prepare(decision)
        self.assertTrue(result["valid"])
        human = result.get("human_work_packet", {})
        self.assertIn("text", human)
        self.assertTrue(len(human["text"]) > 0)
        self.assertIn("Work Packet Proposal", human["text"])

    def test_prepare_human_packet_has_no_shell_commands(self):
        decision = _make_valid_execute_plan()
        result = self._prepare(decision)
        text = result.get("human_work_packet", {}).get("text", "")
        self.assertNotIn("aiwf ", text)
        self.assertNotIn("```bash", text)
        self.assertNotIn("Next:", text)

    def test_prepare_invalid_returns_issues(self):
        decision = {**_make_valid_execute_plan(), "selected_plan_id": ""}
        result = self._prepare(decision)
        self.assertFalse(result["valid"])
        self.assertTrue(len(result.get("validation_issues", [])) > 0)

    def test_prepare_agent_packet_has_work_packet_version(self):
        decision = _make_valid_execute_plan()
        result = self._prepare(decision)
        agent = result.get("agent_work_packet", {})
        self.assertEqual(1, agent.get("work_packet_version"))
        self.assertTrue(agent.get("valid"))

    def test_prepare_agent_packet_has_plan_kind_from_registry(self):
        decision = _make_valid_execute_plan()
        result = self._prepare(decision)
        agent = result.get("agent_work_packet", {})
        self.assertEqual("implementation", agent.get("plan_kind"))

    def test_prepare_agent_packet_mutates_state_false(self):
        decision = _make_valid_execute_plan()
        result = self._prepare(decision)
        agent = result.get("agent_work_packet", {})
        self.assertFalse(agent.get("mutates_state"))

    def test_prepare_does_not_mutate_state_files(self):
        # Snapshot state before
        goals_before = (self.tmp / ".aiwf" / "state" / "goals.json").read_text()
        plans_before = (self.tmp / ".aiwf" / "state" / "plans.json").read_text()

        decision = _make_valid_execute_plan()
        self._prepare(decision)

        goals_after = (self.tmp / ".aiwf" / "state" / "goals.json").read_text()
        plans_after = (self.tmp / ".aiwf" / "state" / "plans.json").read_text()

        self.assertEqual(goals_before, goals_after)
        self.assertEqual(plans_before, plans_after)

    def test_prepare_rollup_target_in_agent_packet(self):
        decision = _make_valid_execute_plan()
        result = self._prepare(decision)
        agent = result.get("agent_work_packet", {})
        self.assertEqual("GOAL-001", agent.get("rollup_target"))

    def test_prepare_forbidden_changes_preserved(self):
        decision = {
            **_make_valid_execute_plan(),
            "forbidden_changes": ["Do not touch task activation."],
        }
        result = self._prepare(decision)
        agent = result.get("agent_work_packet", {})
        self.assertIn("Do not touch task activation.", agent.get("forbidden_changes", []))

    def test_prepare_review_focus_preserved(self):
        decision = {
            **_make_valid_execute_plan(),
            "review_focus": ["Check plan boundary.", "Verify evidence rollup."],
        }
        result = self._prepare(decision)
        agent = result.get("agent_work_packet", {})
        self.assertIn("Check plan boundary.", agent.get("review_focus", []))


class TestFrontierCLI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awf47c_"))
        _install(cls.tmp)
        _setup_goals(str(cls.tmp))
        _setup_plans(str(cls.tmp))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _run(self, *args):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", *args],
            capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=15,
        )

    def _write_frontier_json(self, filename, decision):
        path = self.tmp / filename
        path.write_text(json.dumps(decision), encoding="utf-8")
        return str(path)

    def test_cli_validate_valid_passes(self):
        decision = _make_valid_execute_plan()
        fpath = self._write_frontier_json("valid_frontier.json", decision)
        r = self._run("frontier", "validate", "--file", fpath)
        self.assertEqual(0, r.returncode, f"stdout: {r.stdout}\nstderr: {r.stderr}")
        self.assertIn("valid", r.stdout.lower())

    def test_cli_validate_invalid_fails(self):
        decision = {**_make_valid_execute_plan(), "frontier_type": "bogus"}
        fpath = self._write_frontier_json("invalid_frontier.json", decision)
        r = self._run("frontier", "validate", "--file", fpath)
        self.assertNotEqual(0, r.returncode)
        self.assertIn("invalid", r.stdout.lower())

    def test_cli_prepare_human_output(self):
        decision = _make_valid_execute_plan()
        fpath = self._write_frontier_json("prep_frontier.json", decision)
        r = self._run("frontier", "prepare", "--file", fpath)
        self.assertEqual(0, r.returncode, f"stderr: {r.stderr}")
        self.assertIn("Work Packet Proposal", r.stdout)
        self.assertNotIn("aiwf ", r.stdout)

    def test_cli_prepare_json_output(self):
        decision = _make_valid_execute_plan()
        fpath = self._write_frontier_json("prep_json_frontier.json", decision)
        r = self._run("frontier", "prepare", "--file", fpath, "--json")
        self.assertEqual(0, r.returncode, f"stderr: {r.stderr}")
        data = json.loads(r.stdout)
        self.assertEqual(1, data.get("work_packet_version"))
        self.assertFalse(data.get("mutates_state"))

    def test_cli_prepare_invalid_fails(self):
        decision = {**_make_valid_execute_plan(), "scope": ""}
        fpath = self._write_frontier_json("bad_prep_frontier.json", decision)
        r = self._run("frontier", "prepare", "--file", fpath)
        self.assertNotEqual(0, r.returncode)

    def test_cli_help(self):
        r = self._run("frontier")
        self.assertEqual(0, r.returncode)
        self.assertIn("Planner decides", r.stdout)


class TestFrontierSkillAlignment(unittest.TestCase):

    """Verify skills mention Stage 4.7 frontier/work-packet concepts."""

    @classmethod
    def _read_skill(cls, name):
        return (PROJECT_ROOT / "aiwf_core" / "embedded_templates" / "skills" / name / "SKILL.md").read_text()

    def test_planner_skill_has_dispatch_protocol(self):
        c = self._read_skill("aiwf-planner")
        self.assertIn("Dispatch Protocol", c)
        self.assertIn("Frontier Decision", c)
        self.assertIn("frontier validate", c)
        self.assertIn("Plan + Context freeze", c)

    def test_planner_skill_distinguishes_three_decisions(self):
        c = self._read_skill("aiwf-planner")
        self.assertIn("Admission Decision", c)
        self.assertIn("Frontier Decision", c)
        self.assertIn("What should be worked on now?", c)

    def test_planner_skill_no_tree_traversal_default(self):
        c = self._read_skill("aiwf-planner")
        self.assertIn("tree traversal", c.lower())

    def test_executor_skill_has_pull_based_before_starting(self):
        c = self._read_skill("aiwf-implement")
        self.assertIn("Before Starting (pull what you need)", c)
        self.assertIn("goals.json", c)
        self.assertIn("plans.json", c)
        self.assertIn("work_intent", c.lower())

    def test_tester_skill_has_pull_based_before_testing(self):
        c = self._read_skill("aiwf-test")
        self.assertIn("Before testing, pull from the tree", c)
        self.assertIn("goals.json", c)
        self.assertIn("plans.json", c)

    def test_reviewer_skill_has_pull_based_before_reviewing(self):
        c = self._read_skill("aiwf-review")
        self.assertIn("Before reviewing, verify", c)
        self.assertIn("Read the active context", c)


class TestAgentWrapperAlignment(unittest.TestCase):
    """Agent wrappers use pull-based dispatch — roles read from Plan/Goal/Context directly."""

    @classmethod
    def _read_agent(cls, name):
        return (PROJECT_ROOT / "aiwf_core" / "embedded_templates" / "agents" / f"{name}.md").read_text()

    def test_executor_wrapper_has_pull_based_context(self):
        c = self._read_agent("aiwf-executor")
        self.assertIn("Before starting (pull what you need)", c)
        self.assertIn("goals.json", c)
        self.assertIn("plans.json", c)

    def test_executor_wrapper_mentions_goal_tree_boundaries(self):
        c = self._read_agent("aiwf-executor")
        self.assertIn("Do not modify the Goal Tree", c)

    def test_tester_wrapper_has_pull_based_context(self):
        c = self._read_agent("aiwf-tester")
        self.assertIn("Before starting (pull what you need)", c)
        self.assertIn("goals.json", c)
        self.assertIn("plans.json", c)

    def test_reviewer_wrapper_has_pull_based_context(self):
        c = self._read_agent("aiwf-reviewer")
        self.assertIn("Before reviewing (pull what you need)", c)
        self.assertIn("goals.json", c)
        self.assertIn("plans.json", c)
        self.assertIn("orphan patch", c.lower())

    def test_reviewer_wrapper_mentions_evidence_rollup(self):
        c = self._read_agent("aiwf-reviewer")
        self.assertIn("rolls up", c.lower())
        self.assertIn("Plan/Goal", c)

    def test_architect_skill_mentions_structural_judgments(self):
        c = (PROJECT_ROOT / "aiwf_core" / "embedded_templates" / "skills" / "aiwf-architect" / "SKILL.md").read_text()
        self.assertIn("Structural Judgments", c)
        self.assertIn("architect_structure", c)
        self.assertIn("integrate_goal", c)

    def test_architect_skill_mentions_graft_prune_seal(self):
        c = (PROJECT_ROOT / "aiwf_core" / "embedded_templates" / "skills" / "aiwf-architect" / "SKILL.md").read_text()
        self.assertIn("graft", c.lower())
        self.assertIn("prune", c.lower())
        self.assertIn("seal", c.lower())

    def test_architect_skill_mentions_structural_plan_phases(self):
        c = (PROJECT_ROOT / "aiwf_core" / "embedded_templates" / "skills" / "aiwf-architect" / "SKILL.md").read_text()
        self.assertIn("framing", c)
        self.assertIn("integration", c)
        self.assertIn("interface", c.lower())


class TestChangeAdmitNoShellCommands(unittest.TestCase):
    """Stage 4.7.1: change admit default output must not expose raw shell commands."""

    def test_change_admit_notes_have_no_shell_command(self):
        from aiwf_core.core.state.admission_ops import admit_change
        # Test with empty goals scenario
        with tempfile.TemporaryDirectory() as tmp:
            # No goals.json — simulate empty state
            os.makedirs(os.path.join(tmp, ".aiwf", "state"), exist_ok=True)
            result = admit_change(str(tmp), summary="fix typo in README", target_goal_hint="")
            notes = result.get("notes", [])
            notes_text = " ".join(str(n) for n in notes)
            self.assertNotIn("aiwf ", notes_text)
            self.assertNotIn("init-root", notes_text)

    def test_change_admit_with_matching_goal_no_shell_commands_in_notes(self):
        from aiwf_core.core.state.admission_ops import admit_change
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, ".aiwf", "state"), exist_ok=True)
            # Set up a goal so we don't trigger the empty-goals path
            goals = {
                "schema_version": 1, "active_goal_id": "GOAL-001",
                "roots": ["GOAL-001"],
                "goals": [{
                    "id": "GOAL-001", "title": "Root", "root_type": "main",
                    "parent_goal_id": None, "child_goal_ids": [],
                    "children_order": [], "intent": "", "acceptance_boundary": "",
                    "attached_plan_ids": [], "status": "active", "visibility": "default",
                    "created_at": "", "updated_at": "",
                }],
                "relations": [],
            }
            with open(os.path.join(tmp, ".aiwf", "state", "goals.json"), "w") as f:
                json.dump(goals, f)
            result = admit_change(str(tmp), summary="fix typo in README", target_goal_hint="")
            notes = result.get("notes", [])
            notes_text = " ".join(str(n) for n in notes)
            self.assertNotIn("aiwf ", notes_text)


class TestStatusPromptRegression(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awf47s_"))
        _install(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_status_prompt_within_budget(self):
        """status --prompt should stay under 800 characters."""
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", "status", "--prompt"],
            capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=15,
        )
        self.assertEqual(0, r.returncode, f"stderr: {r.stderr}")
        self.assertLess(len(r.stdout), 800, f"status --prompt is {len(r.stdout)} chars")


if __name__ == "__main__":
    unittest.main()
