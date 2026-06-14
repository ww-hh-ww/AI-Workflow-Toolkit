"""Stage 1 plan registry: plan decoupling without hard-gating old flows."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 15


class TestPlanRegistryStage1(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aiwf_plan_registry_"))
        from aiwf_core.core.state_schema import MVP_STATE_FILES
        for rel, factory in MVP_STATE_FILES.items():
            path = self.tmp / ".aiwf" / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(factory(), indent=2) + "\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, *args):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", *args],
            cwd=str(self.tmp),
            env=env,
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )

    def _seed_plan_markdown(self, plan_id):
        plan_dir = self.tmp / ".aiwf" / "artifacts" / "plans"
        plan_dir.mkdir(parents=True, exist_ok=True)
        (plan_dir / f"{plan_id}.md").write_text(
            f"# {plan_id}\n\n"
            "## Goal\nTest\n\n"
            "## Route\n- How: direct\n\n"
            "## Scope\n- Change: x\n\n"
            "## Verification\n- Machine-verifiable: yes\n\n"
            "## Impact\n"
            "- docs: no — test\n"
            "- project_map: no — test\n"
            "- environment: no — test\n"
            "- capabilities: no — test\n"
            "- quality_summary: no — test\n",
            encoding="utf-8",
        )

    def _mark_prepare_close_passed(self, task_id):
        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["phase"] = "closed"
        state["closure_allowed"] = True
        state["active_task_id"] = task_id
        state["close_prepared_task_id"] = task_id
        state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    def test_default_plans_file_is_part_of_mvp_state(self):
        path = self.tmp / ".aiwf" / "state" / "plans.json"
        self.assertTrue(path.exists())
        data = json.loads(path.read_text())
        self.assertEqual(data["legacy_goal_id"], "GOAL-001")
        self.assertEqual(data["plans"], [])

    def test_legacy_markdown_does_not_create_machine_plan(self):
        from aiwf_core.core.state.plan_ops import load_plans

        self._seed_plan_markdown("TASK-001")
        data = load_plans(str(self.tmp))

        self.assertEqual(data["plans"], [])
        self.assertTrue((self.tmp / ".aiwf" / "artifacts" / "plans" / "TASK-001.md").exists())

    def test_task_references_plan_and_goal_with_aliases(self):
        from aiwf_core.core.task_ledger import upsert_task
        from aiwf_core.core.state.plan_ops import get_plan, upsert_plan

        upsert_plan(str(self.tmp), "PLAN-001", goal_id="GOAL-001", plan_kind="implementation", work_intent="feature", allowed_write=["src/"], purpose="Test task")

        result = upsert_task(
            str(self.tmp), "TASK-001", "Feature", status="ready",
            plan_id="PLAN-001", goal_id="GOAL-001",
        )

        task = result["task"]
        self.assertEqual(task["plan_id"], "PLAN-001")
        self.assertEqual(task["parent_plan"], "PLAN-001")
        self.assertEqual(task["goal_id"], "GOAL-001")
        self.assertEqual(task["parent_goal"], "GOAL-001")
        self.assertIn("TASK-001", get_plan(str(self.tmp), "PLAN-001")["task_ids"])

    def test_cli_plan_create_supports_real_plan_id_and_legacy_task_id(self):
        real = self._run("plan", "create", "PLAN-001", "--goal-id", "GOAL-001", "--task", "TASK-001")
        self.assertEqual(real.returncode, 0, real.stderr)
        self.assertTrue((self.tmp / ".aiwf" / "artifacts" / "plans" / "PLAN-001.md").exists())

        legacy = self._run("plan", "create", "--task-id", "TASK-LEGACY")
        self.assertEqual(legacy.returncode, 0, legacy.stderr)
        self.assertTrue((self.tmp / ".aiwf" / "artifacts" / "plans" / "PLAN-TASK-LEGACY.md").exists())
        plans = json.loads((self.tmp / ".aiwf" / "state" / "plans.json").read_text())
        ids = {p["plan_id"] for p in plans["plans"]}
        self.assertIn("PLAN-001", ids)
        self.assertIn("PLAN-TASK-LEGACY", ids)

    def test_l2_explicit_missing_plan_id_blocks_activation(self):
        from aiwf_core.core.task_ledger import activate_task, upsert_task

        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["workflow_level"] = "L2_standard_team"
        state_path.write_text(json.dumps(state, indent=2) + "\n")
        upsert_task(str(self.tmp), "TASK-001", "Feature", status="ready", plan_id="PLAN-MISSING")

        result = activate_task(str(self.tmp), "TASK-001")

        self.assertFalse(result["activated"])
        self.assertTrue(any("missing plan registry entry" in b for b in result["blockers"]))

    def test_legacy_task_markdown_no_longer_allows_activation(self):
        from aiwf_core.core.task_ledger import activate_task, upsert_task

        self._seed_plan_markdown("TASK-001")
        upsert_task(str(self.tmp), "TASK-001", "Legacy only", status="ready")

        result = activate_task(str(self.tmp), "TASK-001")

        self.assertFalse(result["activated"])
        self.assertTrue(any("Legacy task-bound plan detected" in b for b in result["blockers"]))

    def test_task_close_reconciles_plan_progress(self):
        from aiwf_core.core.task_ledger import activate_task, close_task, upsert_task
        from aiwf_core.core.state.plan_ops import get_plan, upsert_plan

        upsert_plan(str(self.tmp), "PLAN-001", goal_id="GOAL-001", task_ids=["TASK-001", "TASK-002"], plan_kind="implementation", work_intent="feature", allowed_write=["src/"], purpose="Test task")
        self._seed_plan_markdown("PLAN-001")
        upsert_task(str(self.tmp), "TASK-001", "Feature A", status="ready", plan_id="PLAN-001", goal_id="GOAL-001")
        upsert_task(str(self.tmp), "TASK-002", "Feature B", status="ready", plan_id="PLAN-001", goal_id="GOAL-001")
        self.assertTrue(activate_task(str(self.tmp), "TASK-001")["activated"])
        self._mark_prepare_close_passed("TASK-001")

        result = close_task(str(self.tmp), "TASK-001")

        self.assertTrue(result["closed"], result["blockers"])
        self.assertTrue(result["plan_progress"]["reconciled"])
        self.assertEqual(result["plan_progress"]["remaining_task_ids"], ["TASK-002"])
        plan = get_plan(str(self.tmp), "PLAN-001")
        self.assertEqual(plan["closed_task_ids"], ["TASK-001"])
        self.assertEqual(plan["remaining_task_ids"], ["TASK-002"])
        self.assertEqual(plan["evidence_rollup"]["closed_count"], 1)
        self.assertEqual(plan["evidence_rollup"]["total_count"], 2)

    def test_plan_defaults_active_phase_to_implementation(self):
        from aiwf_core.core.state.plan_ops import get_plan, upsert_plan

        upsert_plan(str(self.tmp), "PLAN-001", goal_id="GOAL-001", plan_kind="implementation", work_intent="feature", allowed_write=["src/"], purpose="Test task")
        plan = get_plan(str(self.tmp), "PLAN-001")
        self.assertEqual(plan["active_phase"], "implementation")

    def test_plan_active_phase_is_settable(self):
        from aiwf_core.core.state.plan_ops import get_plan, upsert_plan

        upsert_plan(str(self.tmp), "PLAN-STRUCT", goal_id="GOAL-001",
                    plan_kind="structural", active_phase="framing")
        plan = get_plan(str(self.tmp), "PLAN-STRUCT")
        self.assertEqual(plan["plan_kind"], "structural")
        self.assertEqual(plan["active_phase"], "framing")

    def test_plan_rejects_invalid_active_phase(self):
        from aiwf_core.core.state.plan_ops import upsert_plan

        with self.assertRaises(ValueError):
            upsert_plan(str(self.tmp), "PLAN-BAD", goal_id="GOAL-001",
                        active_phase="garbage")

    # ── Stage 3.3: plan attaches to any Goal (CLI) ──────────────────

    def test_cli_plan_create_with_kind_structural(self):
        r = self._run("plan", "create", "PLAN-STRUCT", "--goal-id", "GOAL-001",
                       "--kind", "structural", "--title", "Structural Plan")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("structural", r.stdout)

    def test_cli_plan_create_default_kind_is_implementation(self):
        r = self._run("plan", "create", "PLAN-IMPL", "--goal-id", "GOAL-001")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("implementation", r.stdout)

    def test_cli_plan_create_with_target_goal(self):
        from aiwf_core.core.state.goal_tree_ops import init_root

        init_root(str(self.tmp), "GOAL-002", root_type="main", title="Second root")
        r = self._run("plan", "create", "PLAN-TG", "--goal-id", "GOAL-001",
                       "--target-goal", "GOAL-002", "--kind", "structural")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Target Goal: GOAL-002", r.stdout)

    def test_cli_plan_create_target_goal_defaults_to_goal_id(self):
        from aiwf_core.core.state.plan_ops import get_plan

        r = self._run("plan", "create", "PLAN-DEF", "--goal-id", "GOAL-001")
        self.assertEqual(r.returncode, 0, r.stderr)
        plan = get_plan(str(self.tmp), "PLAN-DEF")
        self.assertEqual(plan["target_goal_id"], "GOAL-001")

    def test_cli_plan_create_rejects_invalid_kind(self):
        r = self._run("plan", "create", "PLAN-BAD", "--goal-id", "GOAL-001",
                       "--kind", "garbage")
        self.assertNotEqual(r.returncode, 0)

    def test_structural_plan_allows_zero_tasks(self):
        from aiwf_core.core.state.plan_ops import get_plan, upsert_plan

        upsert_plan(str(self.tmp), "PLAN-STRUCT", goal_id="GOAL-001",
                    plan_kind="structural", task_ids=[])
        plan = get_plan(str(self.tmp), "PLAN-STRUCT")
        self.assertEqual(plan["plan_kind"], "structural")
        self.assertEqual(plan.get("task_ids", []), [])

    # ── Stage 3.9: plan CLI active_phase, interfaces, constraints, child_goal_policy ──

    def test_cli_plan_create_with_active_phase(self):
        r = self._run("plan", "create", "PLAN-FRAMING", "--goal-id", "GOAL-001",
                       "--kind", "structural", "--active-phase", "framing")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("framing", r.stdout)

    def test_cli_plan_create_with_interfaces_and_constraints(self):
        r = self._run("plan", "create", "PLAN-BOUND", "--goal-id", "GOAL-001",
                       "--interface", "goals.json is recursive Goal registry",
                       "--interface", "plans.json is machine plan authority",
                       "--constraint", "Goal Tree must not affect activation")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("goals.json is recursive Goal registry", r.stdout)
        self.assertIn("plans.json is machine plan authority", r.stdout)
        self.assertIn("Goal Tree must not affect activation", r.stdout)

    def test_cli_plan_create_with_child_goal_policy(self):
        r = self._run("plan", "create", "PLAN-POLICY", "--goal-id", "GOAL-001",
                       "--child-goal-policy", "allow_decomposition")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("allow_decomposition", r.stdout)

    def test_plan_artifact_contains_target_goal_and_phase(self):
        """Stage 3.9: .aiwf/artifacts/plans/PLAN-ID.md must write Target Goal, Plan Kind, Active Phase."""
        from pathlib import Path

        r = self._run("plan", "create", "PLAN-ARTIFACT",
                       "--goal-id", "GOAL-001",
                       "--target-goal", "GOAL-001",
                       "--kind", "structural",
                       "--active-phase", "framing",
                       "--interface", "test interface",
                       "--constraint", "test constraint",
                       "--child-goal-policy", "no_child_goals")
        self.assertEqual(r.returncode, 0, r.stderr)

        md_path = Path(self.tmp) / ".aiwf" / "artifacts" / "plans" / "PLAN-ARTIFACT.md"
        self.assertTrue(md_path.exists(), f"Plan artifact not found at {md_path}")
        content = md_path.read_text(encoding="utf-8")
        self.assertIn("Target Goal: GOAL-001", content)
        self.assertIn("Plan Kind: structural", content)
        self.assertIn("Active Phase: framing", content)
        self.assertIn("Interfaces: test interface", content)
        self.assertIn("Constraints: test constraint", content)
        self.assertIn("Child Goal Policy: no_child_goals", content)

    # ── Stage 3.9: target_goal_id validation ──

    def test_plan_rejects_target_goal_not_in_registry(self):
        """When goals.json has entries, target_goal_id must reference a real goal."""
        from aiwf_core.core.state.goal_tree_ops import init_root
        from aiwf_core.core.state.plan_ops import upsert_plan

        init_root(str(self.tmp), "GOAL-001", root_type="main")
        with self.assertRaises(ValueError):
            upsert_plan(str(self.tmp), "PLAN-BAD", goal_id="GOAL-001",
                        target_goal_id="GOAL-NONEXISTENT")

    def test_plan_target_goal_allows_goal_001_bootstrap_id(self):
        """GOAL-001 is the bootstrap root id."""
        from aiwf_core.core.state.goal_tree_ops import init_root
        from aiwf_core.core.state.plan_ops import get_plan, upsert_plan

        init_root(str(self.tmp), "GOAL-001", root_type="main")
        upsert_plan(str(self.tmp), "PLAN-OK", goal_id="GOAL-001",
                    target_goal_id="GOAL-001")
        plan = get_plan(str(self.tmp), "PLAN-OK")
        self.assertEqual(plan["target_goal_id"], "GOAL-001")

    def test_cli_plan_create_rejects_invalid_target_goal(self):
        """CLI should fail when target-goal doesn't exist in goals.json."""
        from aiwf_core.core.state.goal_tree_ops import init_root

        init_root(str(self.tmp), "GOAL-001", root_type="main")
        r = self._run("plan", "create", "PLAN-BAD",
                       "--goal-id", "GOAL-001",
                       "--target-goal", "GOAL-FAKE")
        self.assertNotEqual(r.returncode, 0)

    # ── Stage 3.9: archived is a valid goal status ──

    def test_archived_is_valid_goal_status(self):
        from aiwf_core.core.state_schema import VALID_GOAL_STATUSES

        self.assertIn("archived", VALID_GOAL_STATUSES)

    def test_prune_writes_archived_status(self):
        from aiwf_core.core.state.goal_tree_ops import get_goal, init_root, prune_branch

        init_root(str(self.tmp), "TMP-001", root_type="temporary")
        prune_branch(str(self.tmp), "TMP-001", reason="Cleanup")
        g = get_goal(str(self.tmp), "TMP-001")
        self.assertEqual(g["status"], "archived")


if __name__ == "__main__":
    unittest.main()
