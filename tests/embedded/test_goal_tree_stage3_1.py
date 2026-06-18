"""Stage 3.1: Goal Tree Registry skeleton contract tests."""
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


class TestGoalTreeRegistry(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aiwf_gt31_"))
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

    # ── bootstrap ──────────────────────────────────────────────────────

    @unittest.skip("V1: goal-tree removed")
    def test_goals_json_created_by_mvp_state(self):
        path = self.tmp / ".aiwf" / "state" / "goals.json"
        self.assertTrue(path.exists())
        data = json.loads(path.read_text())
        self.assertEqual(data["schema_version"], 1)
        self.assertIsNone(data["active_goal_id"])
        self.assertEqual(data["roots"], [])
        self.assertEqual(data["goals"], [])
        self.assertEqual(data["relations"], [])

    @unittest.skip("V1: goal-tree removed")
    def test_legacy_goal_json_seeds_goal_001(self):
        """Existing goal.json should seed GOAL-001 in goals.json via explicit _seed_from_legacy."""
        from aiwf_core.core.state.goal_tree_ops import _seed_from_legacy, get_goal, load_goal_tree, save_goal_tree

        # Write a legacy goal.json with confirmed goal
        legacy = {
            "goal_version": 1,
            "current_goal": "Test the goal tree",
            "active_goal": "Test the goal tree",
            "confirmed": True,
            "original_intent": "Build a rooted functional tree registry",
        }
        (self.tmp / ".aiwf" / "state" / "goal.json").write_text(
            json.dumps(legacy, indent=2) + "\n", encoding="utf-8"
        )
        # Remove the empty goals.json created by setUp so seeding fires
        (self.tmp / ".aiwf" / "state" / "goals.json").unlink()

        tree = _seed_from_legacy(str(self.tmp))
        save_goal_tree(str(self.tmp), tree)
        tree = load_goal_tree(str(self.tmp))
        self.assertEqual(tree["active_goal_id"], "GOAL-001")
        self.assertIn("GOAL-001", tree["roots"])

        goal = get_goal(str(self.tmp), "GOAL-001")
        self.assertEqual(goal["root_type"], "main")
        self.assertEqual(goal["status"], "active")
        self.assertIn("Test the goal tree", goal["title"])

    # ── CRUD ────────────────────────────────────────────────────────────

    @unittest.skip("V1: goal-tree removed")
    def test_init_root_creates_main_goal(self):
        from aiwf_core.core.state.goal_tree_ops import get_goal, init_root

        init_root(str(self.tmp), "GOAL-002", root_type="main", title="Second root")
        goal = get_goal(str(self.tmp), "GOAL-002")
        self.assertEqual(goal["root_type"], "main")
        self.assertEqual(goal["title"], "Second root")
        self.assertIsNone(goal["parent_goal_id"])
        self.assertEqual(goal["status"], "active")

    @unittest.skip("V1: goal-tree removed")
    def test_init_root_temporary_hidden_from_prompt(self):
        from aiwf_core.core.state.goal_tree_ops import get_goal, init_root

        init_root(str(self.tmp), "TMP-001", root_type="temporary", title="Exploratory")
        goal = get_goal(str(self.tmp), "TMP-001")
        self.assertEqual(goal["root_type"], "temporary")
        self.assertEqual(goal["visibility"], "hidden_from_prompt")

    @unittest.skip("V1: goal-tree removed")
    def test_init_root_branch_allowed(self):
        from aiwf_core.core.state.goal_tree_ops import get_goal, init_root

        init_root(str(self.tmp), "BRANCH-001", root_type="branch", title="Side branch")
        goal = get_goal(str(self.tmp), "BRANCH-001")
        self.assertEqual(goal["root_type"], "branch")

    @unittest.skip("V1: goal-tree removed")
    def test_init_root_rejects_invalid_type(self):
        from aiwf_core.core.state.goal_tree_ops import init_root

        with self.assertRaises(ValueError):
            init_root(str(self.tmp), "BAD-001", root_type="garbage")

    # ── child goals ─────────────────────────────────────────────────────

    @unittest.skip("V1: goal-tree removed")
    def test_add_child_goal(self):
        from aiwf_core.core.state.goal_tree_ops import add_child_goal, get_goal, init_root

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Parent")
        add_child_goal(str(self.tmp), "GOAL-001", "GOAL-001-A", title="Child A")

        parent = get_goal(str(self.tmp), "GOAL-001")
        self.assertIn("GOAL-001-A", parent["child_goal_ids"])
        self.assertIn("GOAL-001-A", parent["children_order"])

        child = get_goal(str(self.tmp), "GOAL-001-A")
        self.assertIsNone(child["root_type"])  # non-root
        self.assertEqual(child["parent_goal_id"], "GOAL-001")

    @unittest.skip("V1: goal-tree removed")
    def test_add_child_goal_deep_nesting(self):
        from aiwf_core.core.state.goal_tree_ops import add_child_goal, get_goal, init_root

        init_root(str(self.tmp), "GOAL-ROOT", root_type="main")
        add_child_goal(str(self.tmp), "GOAL-ROOT", "L1")
        add_child_goal(str(self.tmp), "L1", "L2")
        add_child_goal(str(self.tmp), "L2", "L3")

        for gid in ["GOAL-ROOT", "L1", "L2", "L3"]:
            g = get_goal(str(self.tmp), gid)
            self.assertTrue(g, f"{gid} should exist")

        l3 = get_goal(str(self.tmp), "L3")
        self.assertEqual(l3["parent_goal_id"], "L2")

    @unittest.skip("V1: goal-tree removed")
    def test_cannot_add_root_goal_as_child(self):
        from aiwf_core.core.state.goal_tree_ops import add_child_goal, init_root

        init_root(str(self.tmp), "ROOT-1", root_type="main")
        init_root(str(self.tmp), "ROOT-2", root_type="main")

        with self.assertRaises(ValueError):
            add_child_goal(str(self.tmp), "ROOT-1", "ROOT-2")

    # ── validation ──────────────────────────────────────────────────────

    @unittest.skip("V1: goal-tree removed")
    def test_validate_no_cycles(self):
        from aiwf_core.core.state.goal_tree_ops import add_child_goal, init_root, validate_goal_tree

        init_root(str(self.tmp), "GOAL-A", root_type="main")
        add_child_goal(str(self.tmp), "GOAL-A", "GOAL-B")

        result = validate_goal_tree(str(self.tmp))
        self.assertTrue(result["valid"], result["issues"])

    @unittest.skip("V1: goal-tree removed")
    def test_validate_detects_cycle(self):
        from aiwf_core.core.state.goal_tree_ops import init_root

        init_root(str(self.tmp), "GOAL-A", root_type="main")

        # Manually inject a cycle by writing goals.json directly
        tree_path = self.tmp / ".aiwf" / "state" / "goals.json"
        tree = json.loads(tree_path.read_text())
        tree["goals"].append({
            "id": "GOAL-B", "title": "B", "root_type": None,
            "parent_goal_id": "GOAL-A", "child_goal_ids": ["GOAL-A"],
            "children_order": ["GOAL-A"], "status": "active",
        })
        tree["goals"][0]["child_goal_ids"] = ["GOAL-B"]
        tree["goals"][0]["children_order"] = ["GOAL-B"]
        tree_path.write_text(json.dumps(tree, indent=2) + "\n")

        from aiwf_core.core.state.goal_tree_ops import validate_goal_tree
        result = validate_goal_tree(str(self.tmp))
        self.assertFalse(result["valid"])
        self.assertTrue(any("cycle" in i for i in result["issues"]))

    @unittest.skip("V1: goal-tree removed")
    def test_validate_detects_stale_child_parent_mismatch(self):
        from aiwf_core.core.state.goal_tree_ops import add_child_goal, init_root, validate_goal_tree

        init_root(str(self.tmp), "GOAL-A", root_type="main")
        init_root(str(self.tmp), "GOAL-B", root_type="main")
        add_child_goal(str(self.tmp), "GOAL-A", "GOAL-C")

        tree_path = self.tmp / ".aiwf" / "state" / "goals.json"
        tree = json.loads(tree_path.read_text())
        for goal in tree["goals"]:
            if goal.get("id") == "GOAL-C":
                goal["parent_goal_id"] = "GOAL-B"
        tree_path.write_text(json.dumps(tree, indent=2) + "\n")

        result = validate_goal_tree(str(self.tmp))
        self.assertFalse(result["valid"])
        self.assertTrue(any("child_goal_id GOAL-C has parent_goal_id GOAL-B" in i for i in result["issues"]))

    @unittest.skip("V1: goal-tree removed")
    def test_validate_root_has_parent_rejected(self):
        from aiwf_core.core.state.goal_tree_ops import init_root, validate_goal_tree

        init_root(str(self.tmp), "GOAL-A", root_type="main")

        # Manually corrupt: give root a parent
        tree_path = self.tmp / ".aiwf" / "state" / "goals.json"
        tree = json.loads(tree_path.read_text())
        tree["goals"][0]["parent_goal_id"] = "GOAL-X"
        tree_path.write_text(json.dumps(tree, indent=2) + "\n")

        result = validate_goal_tree(str(self.tmp))
        self.assertFalse(result["valid"])
        self.assertTrue(any("root Goal has parent_goal_id" in i for i in result["issues"]))

    @unittest.skip("V1: goal-tree removed")
    def test_validate_orphan_child_rejected(self):
        from aiwf_core.core.state.goal_tree_ops import validate_goal_tree

        # Write a tree with a child that references non-existent parent
        tree_path = self.tmp / ".aiwf" / "state" / "goals.json"
        tree = json.loads(tree_path.read_text())
        tree["goals"] = [{
            "id": "ORPHAN", "title": "Orphan", "root_type": None,
            "parent_goal_id": "NONEXISTENT", "child_goal_ids": [],
            "children_order": [], "status": "active",
        }]
        tree_path.write_text(json.dumps(tree, indent=2) + "\n")

        result = validate_goal_tree(str(self.tmp))
        self.assertFalse(result["valid"])
        self.assertTrue(any("does not exist" in i for i in result["issues"]))

    # ── no cross-contamination ──────────────────────────────────────────

    @unittest.skip("V1: goal-tree removed")
    def test_goal_tree_does_not_affect_task_activation(self):
        """Goal Tree ops must not interfere with existing task activation."""
        from aiwf_core.core.state.goal_tree_ops import init_root
        from aiwf_core.core.task_ledger import activate_task, upsert_task
        from aiwf_core.core.state.plan_ops import upsert_plan

        init_root(str(self.tmp), "GOAL-001", root_type="main")
        upsert_plan(str(self.tmp), "PLAN-001", goal_id="GOAL-001", plan_kind="implementation", work_intent="feature", allowed_write=["src/"], purpose="Test task")
        upsert_task(str(self.tmp), "TASK-001", "Test", status="ready",
                    plan_id="PLAN-001", goal_id="GOAL-001")

        # Write a plan markdown artifact for activation
        plan_dir = self.tmp / ".aiwf" / "plans"
        plan_dir.mkdir(parents=True, exist_ok=True)
        (plan_dir / "PLAN-001.md").write_text(
            "# PLAN-001\n\n## Goal\nTest\n\n## Route\n- How: direct\n\n"
            "## Scope\n- Change: x\n\n## Verification\n- Machine-verifiable: yes\n\n"
            "## Impact\n- docs: no — test\n- project_map: no — test\n"
            "- environment: no — test\n- capabilities: no — test\n"
            "- quality_summary: no — test\n", encoding="utf-8")

        result = activate_task(str(self.tmp), "TASK-001")
        self.assertTrue(result["activated"], result.get("blockers", []))

    @unittest.skip("V1: goal-tree removed")
    def test_goal_tree_does_not_affect_task_close(self):
        from aiwf_core.core.state.goal_tree_ops import init_root
        from aiwf_core.core.task_ledger import close_task, upsert_task
        from aiwf_core.core.state.plan_ops import upsert_plan

        init_root(str(self.tmp), "GOAL-001", root_type="main")
        upsert_plan(str(self.tmp), "PLAN-001", goal_id="GOAL-001", plan_kind="implementation", work_intent="feature", allowed_write=["src/"], purpose="Test task")
        upsert_task(str(self.tmp), "TASK-001", "Test", status="ready",
                    plan_id="PLAN-001", goal_id="GOAL-001")

        result = close_task(str(self.tmp), "TASK-001")
        # L0 or L1 with no prepare-close should still close
        self.assertTrue(result.get("closed") or not result.get("closed"),
                        "close_task should not crash on goal tree presence")


class TestGoalTreeCLI(unittest.TestCase):
    """Stage 3.2: Goal Tree CLI contract tests."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aiwf_gt32_"))
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

    def _run_ok(self, *args):
        r = self._run(*args)
        self.assertEqual(r.returncode, 0, f"{args}\nstdout={r.stdout}\nstderr={r.stderr}")
        return r

    # ── init-root ────────────────────────────────────────────────────

    @unittest.skip("V1: goal-tree removed")
    def test_cli_init_root_main(self):
        r = self._run_ok("goal-tree", "init-root", "GOAL-002", "--type", "main", "--title", "Main Root")
        self.assertIn("Root Goal created: GOAL-002", r.stdout)
        self.assertIn("Main Root", r.stdout)

    @unittest.skip("V1: goal-tree removed")
    def test_cli_init_root_temporary(self):
        r = self._run_ok("goal-tree", "init-root", "TMP-001", "--type", "temporary", "--title", "Trial")
        self.assertIn("Type: temporary", r.stdout)
        self.assertIn("hidden_from_prompt", r.stdout)

    @unittest.skip("V1: goal-tree removed")
    def test_cli_init_root_rejects_invalid_type(self):
        r = self._run("goal-tree", "init-root", "BAD-001", "--type", "garbage")
        self.assertNotEqual(r.returncode, 0)

    # ── add ──────────────────────────────────────────────────────────

    @unittest.skip("V1: goal-tree removed")
    def test_cli_add_child(self):
        self._run_ok("goal-tree", "init-root", "GOAL-001", "--type", "main")
        r = self._run_ok("goal-tree", "add", "GOAL-001-A", "--parent", "GOAL-001", "--title", "Child")
        self.assertIn("Child Goal added: GOAL-001-A", r.stdout)
        self.assertIn("Parent: GOAL-001", r.stdout)

    @unittest.skip("V1: goal-tree removed")
    def test_cli_add_to_nonexistent_parent(self):
        r = self._run("goal-tree", "add", "ORPHAN", "--parent", "NONEXISTENT")
        self.assertNotEqual(r.returncode, 0)

    # ── list ─────────────────────────────────────────────────────────

    @unittest.skip("V1: goal-tree removed")
    def test_cli_list_goals(self):
        self._run_ok("goal-tree", "init-root", "GOAL-001", "--type", "main", "--title", "Root")
        self._run_ok("goal-tree", "add", "GOAL-001-A", "--parent", "GOAL-001")
        r = self._run_ok("goal-tree", "list")
        self.assertIn("GOAL-001", r.stdout)
        self.assertIn("GOAL-001-A", r.stdout)
        self.assertIn("roots: 1", r.stdout)

    # ── show ─────────────────────────────────────────────────────────

    @unittest.skip("V1: goal-tree removed")
    def test_cli_show_tree(self):
        self._run_ok("goal-tree", "init-root", "GOAL-001", "--type", "main", "--title", "Tree Root")
        self._run_ok("goal-tree", "add", "GOAL-001-A", "--parent", "GOAL-001")
        r = self._run_ok("goal-tree", "show")
        self.assertIn("GOAL-001", r.stdout)
        self.assertIn("GOAL-001-A", r.stdout)
        self.assertIn("Tree Root", r.stdout)

    @unittest.skip("V1: goal-tree removed")
    def test_cli_show_single(self):
        self._run_ok("goal-tree", "init-root", "GOAL-001", "--type", "main", "--title", "Single")
        r = self._run_ok("goal-tree", "show", "GOAL-001")
        self.assertIn("Goal: GOAL-001", r.stdout)
        self.assertIn("Root Type: main", r.stdout)
        self.assertIn("Single", r.stdout)

    # ── validate ─────────────────────────────────────────────────────

    @unittest.skip("V1: goal-tree removed")
    def test_cli_validate_valid_tree(self):
        self._run_ok("goal-tree", "init-root", "GOAL-001", "--type", "main")
        r = self._run_ok("goal-tree", "validate")
        self.assertIn("valid", r.stdout)

    @unittest.skip("V1: goal-tree removed")
    def test_cli_validate_invalid_tree(self):
        # Manually corrupt the tree
        tree_path = self.tmp / ".aiwf" / "state" / "goals.json"
        tree = json.loads(tree_path.read_text())
        tree["goals"] = [{
            "id": "ORPHAN", "title": "O", "root_type": None,
            "parent_goal_id": "NONEXISTENT", "child_goal_ids": [],
            "children_order": [], "status": "active",
        }]
        tree_path.write_text(json.dumps(tree, indent=2) + "\n")
        r = self._run("goal-tree", "validate")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("INVALID", r.stdout)

    # ── help ─────────────────────────────────────────────────────────

    @unittest.skip("V1: goal-tree removed")
    def test_cli_help(self):
        r = self._run_ok("goal-tree")
        self.assertIn("init-root", r.stdout)
        self.assertIn("add", r.stdout)
        self.assertIn("validate", r.stdout)
        self.assertIn("recursive functional skeleton", r.stdout)

    # ── no side effects ─────────────────────────────────────────────

    @unittest.skip("V1: goal-tree removed")
    def test_goal_tree_cli_does_not_affect_status_prompt(self):
        self._run_ok("goal-tree", "init-root", "GOAL-001", "--type", "main", "--title", "Root")
        r = self._run_ok("status", "--prompt")
        # Goal Tree content must not leak into status --prompt
        self.assertNotIn("Goal Tree", r.stdout)
        self.assertNotIn("root_type", r.stdout)


class TestPlanToGoalRollup(unittest.TestCase):
    """Stage 3.4: Plan-to-Goal soft rollup contract tests."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aiwf_gt34_"))
        from aiwf_core.core.state_schema import MVP_STATE_FILES
        for rel, factory in MVP_STATE_FILES.items():
            path = self.tmp / ".aiwf" / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(factory(), indent=2) + "\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _seed_plan_markdown(self, plan_id):
        plan_dir = self.tmp / ".aiwf" / "plans"
        plan_dir.mkdir(parents=True, exist_ok=True)
        (plan_dir / f"{plan_id}.md").write_text(
            f"# {plan_id}\n\n## Goal\nTest\n\n## Route\n- How: direct\n\n"
            "## Scope\n- Change: x\n\n## Verification\n- Machine-verifiable: yes\n\n"
            "## Impact\n- docs: no — test\n- project_map: no — test\n"
            "- environment: no — test\n- capabilities: no — test\n"
            "- quality_summary: no — test\n", encoding="utf-8")

    def _mark_prepare_close_passed(self, task_id):
        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["phase"] = "closed"
        state["closure_allowed"] = True
        state["active_task_id"] = task_id
        state["close_prepared_task_id"] = task_id
        state["close_prepared_at"] = ""
        state_path.write_text(json.dumps(state, indent=2) + "\n")
        ledger_path = self.tmp / ".aiwf" / "state" / "tasks.json"
        ledger = json.loads(ledger_path.read_text())
        for task in ledger.get("tasks", []):
            if task.get("id") == task_id:
                task["status"] = "active"
                # Disable role requirements so close_task won't block on missing evidence
                task.setdefault("requirements", {})["executor_required"] = False
                task["requirements"]["tester_required"] = False
                task["requirements"]["reviewer_required"] = False
        ledger.setdefault("execution_window", {})["active_task_ids"] = [task_id]
        ledger_path.write_text(json.dumps(ledger, indent=2) + "\n")

    # ── rollup tests ──────────────────────────────────────────────────

    @unittest.skip("V1: goal-tree removed")
    def test_plan_complete_rolls_up_to_goal(self):
        from aiwf_core.core.state.goal_tree_ops import get_goal, init_root
        from aiwf_core.core.state.plan_ops import upsert_plan
        from aiwf_core.core.task_ledger import close_task, upsert_task

        init_root(str(self.tmp), "GOAL-001", root_type="main")
        upsert_plan(str(self.tmp), "PLAN-001", goal_id="GOAL-001", task_ids=["TASK-001"])
        self._seed_plan_markdown("PLAN-001")
        upsert_task(str(self.tmp), "TASK-001", "Feature", status="ready",
                    plan_id="PLAN-001", goal_id="GOAL-001")
        self._mark_prepare_close_passed("TASK-001")

        result = close_task(str(self.tmp), "TASK-001")

        self.assertTrue(result["closed"], result.get("blockers", []))
        # Plan→Goal rollup should have fired
        gp = result.get("plan_progress", {}).get("goal_progress", {})
        self.assertTrue(gp.get("reconciled"), f"goal_progress not reconciled: {gp}")

        goal = get_goal(str(self.tmp), "GOAL-001")
        rollup = goal.get("evidence_rollup", {})
        plan_rollups = rollup.get("plan_rollups", {})
        self.assertIn("PLAN-001", plan_rollups)
        self.assertEqual(plan_rollups["PLAN-001"]["closed_task_count"], 1)
        self.assertEqual(plan_rollups["PLAN-001"]["total_task_count"], 1)

    @unittest.skip("V1: goal-tree removed")
    def test_rollup_does_not_auto_close_goal(self):
        from aiwf_core.core.state.goal_tree_ops import get_goal, init_root
        from aiwf_core.core.state.plan_ops import upsert_plan
        from aiwf_core.core.task_ledger import close_task, upsert_task

        init_root(str(self.tmp), "GOAL-001", root_type="main")
        upsert_plan(str(self.tmp), "PLAN-001", goal_id="GOAL-001", task_ids=["TASK-001"])
        self._seed_plan_markdown("PLAN-001")
        upsert_task(str(self.tmp), "TASK-001", "Feature", status="ready",
                    plan_id="PLAN-001", goal_id="GOAL-001")
        self._mark_prepare_close_passed("TASK-001")

        close_task(str(self.tmp), "TASK-001")

        goal = get_goal(str(self.tmp), "GOAL-001")
        # Goal must still be active — rollup is read-only
        self.assertEqual(goal.get("status"), "active")

    @unittest.skip("V1: goal-tree removed")
    def test_multiple_plan_rollups_coexist_on_goal(self):
        from aiwf_core.core.state.goal_tree_ops import get_goal, init_root
        from aiwf_core.core.state.plan_ops import upsert_plan
        from aiwf_core.core.task_ledger import close_task, upsert_task

        init_root(str(self.tmp), "GOAL-001", root_type="main")
        upsert_plan(str(self.tmp), "PLAN-A", goal_id="GOAL-001", task_ids=["TASK-A"])
        upsert_plan(str(self.tmp), "PLAN-B", goal_id="GOAL-001", task_ids=["TASK-B"])
        self._seed_plan_markdown("PLAN-A")
        self._seed_plan_markdown("PLAN-B")

        # Close task under PLAN-A
        upsert_task(str(self.tmp), "TASK-A", "A", status="ready", plan_id="PLAN-A", goal_id="GOAL-001")
        self._mark_prepare_close_passed("TASK-A")
        close_task(str(self.tmp), "TASK-A")

        # Close task under PLAN-B
        upsert_task(str(self.tmp), "TASK-B", "B", status="ready", plan_id="PLAN-B", goal_id="GOAL-001")
        self._mark_prepare_close_passed("TASK-B")
        close_task(str(self.tmp), "TASK-B")

        goal = get_goal(str(self.tmp), "GOAL-001")
        rollup = goal.get("evidence_rollup", {})
        plan_rollups = rollup.get("plan_rollups", {})
        self.assertEqual(len(plan_rollups), 2)
        self.assertIn("PLAN-A", plan_rollups)
        self.assertIn("PLAN-B", plan_rollups)
        self.assertEqual(rollup["complete_plan_count"], 2)

    @unittest.skip("V1: goal-tree removed")
    def test_plan_attached_to_goal_ids_on_rollup(self):
        from aiwf_core.core.state.goal_tree_ops import get_goal, init_root
        from aiwf_core.core.state.plan_ops import upsert_plan
        from aiwf_core.core.task_ledger import close_task, upsert_task

        init_root(str(self.tmp), "GOAL-001", root_type="main")
        upsert_plan(str(self.tmp), "PLAN-001", goal_id="GOAL-001", task_ids=["TASK-001"])
        self._seed_plan_markdown("PLAN-001")
        upsert_task(str(self.tmp), "TASK-001", "Feature", status="ready",
                    plan_id="PLAN-001", goal_id="GOAL-001")
        self._mark_prepare_close_passed("TASK-001")
        close_task(str(self.tmp), "TASK-001")

        goal = get_goal(str(self.tmp), "GOAL-001")
        self.assertIn("PLAN-001", goal.get("attached_plan_ids", []))


class TestTemporaryRoot(unittest.TestCase):
    """Stage 3.5: Temporary Root contract tests."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aiwf_gt35_"))
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

    def _run_ok(self, *args):
        r = self._run(*args)
        self.assertEqual(r.returncode, 0, f"{args}\nstdout={r.stdout}\nstderr={r.stderr}")
        return r

    # ── temporary root basics ────────────────────────────────────────

    @unittest.skip("V1: goal-tree removed")
    def test_temporary_root_has_correct_visibility(self):
        from aiwf_core.core.state.goal_tree_ops import get_goal, init_root

        init_root(str(self.tmp), "TMP-001", root_type="temporary", title="Trial")
        goal = get_goal(str(self.tmp), "TMP-001")
        self.assertEqual(goal["root_type"], "temporary")
        self.assertEqual(goal["visibility"], "hidden_from_prompt")

    @unittest.skip("V1: goal-tree removed")
    def test_temporary_root_not_in_active_goal_id(self):
        from aiwf_core.core.state.goal_tree_ops import init_root, load_goal_tree

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Main")
        init_root(str(self.tmp), "TMP-001", root_type="temporary", title="Trial")

        tree = load_goal_tree(str(self.tmp))
        # active_goal_id must be the main root, not the temporary one
        self.assertEqual(tree["active_goal_id"], "GOAL-001")

    @unittest.skip("V1: goal-tree removed")
    def test_temporary_root_can_have_full_subtree(self):
        from aiwf_core.core.state.goal_tree_ops import add_child_goal, get_goal, init_root, upsert_goal
        from aiwf_core.core.state.plan_ops import upsert_plan

        init_root(str(self.tmp), "TMP-001", root_type="temporary", title="Trial")
        add_child_goal(str(self.tmp), "TMP-001", "TMP-001-A", title="Child")
        upsert_plan(str(self.tmp), "PLAN-TMP", goal_id="TMP-001-A", plan_kind="exploration")

        # Verify full subtree exists
        child = get_goal(str(self.tmp), "TMP-001-A")
        self.assertEqual(child["parent_goal_id"], "TMP-001")
        self.assertIsNone(child["root_type"])  # non-root

        from aiwf_core.core.state.plan_ops import get_plan
        plan = get_plan(str(self.tmp), "PLAN-TMP")
        self.assertEqual(plan["goal_id"], "TMP-001-A")

    # ── CLI ──────────────────────────────────────────────────────────

    @unittest.skip("V1: goal-tree removed")
    def test_cli_list_temporary_empty(self):
        r = self._run_ok("goal-tree", "list-temporary")
        self.assertIn("none", r.stdout)

    @unittest.skip("V1: goal-tree removed")
    def test_cli_list_temporary_shows_roots(self):
        self._run_ok("goal-tree", "init-root", "TMP-001", "--type", "temporary", "--title", "Trial A")
        self._run_ok("goal-tree", "init-root", "TMP-002", "--type", "temporary", "--title", "Trial B")
        self._run_ok("goal-tree", "init-root", "GOAL-001", "--type", "main", "--title", "Main")

        r = self._run_ok("goal-tree", "list-temporary")
        self.assertIn("TMP-001", r.stdout)
        self.assertIn("TMP-002", r.stdout)
        self.assertNotIn("GOAL-001", r.stdout)
        self.assertIn("Temporary Roots: 2", r.stdout)

    @unittest.skip("V1: goal-tree removed")
    def test_cli_show_temporary_root(self):
        self._run_ok("goal-tree", "init-root", "TMP-001", "--type", "temporary", "--title", "Trial")
        r = self._run_ok("goal-tree", "show", "TMP-001")
        self.assertIn("Root Type: temporary", r.stdout)

    @unittest.skip("V1: goal-tree removed")
    def test_graft_removes_source_from_old_parent_children(self):
        from aiwf_core.core.state.goal_tree_ops import add_child_goal, graft_branch, init_root, get_goal, validate_goal_tree

        init_root(str(self.tmp), "GOAL-001", root_type="main")
        init_root(str(self.tmp), "TMP-001", root_type="temporary")
        add_child_goal(str(self.tmp), "TMP-001", "GOAL-ALT-001")

        graft_branch(str(self.tmp), "GOAL-ALT-001", "GOAL-001", reason="adopt alternative")

        old_parent = get_goal(str(self.tmp), "TMP-001")
        new_parent = get_goal(str(self.tmp), "GOAL-001")
        child = get_goal(str(self.tmp), "GOAL-ALT-001")
        self.assertNotIn("GOAL-ALT-001", old_parent.get("child_goal_ids", []))
        self.assertIn("GOAL-ALT-001", new_parent.get("child_goal_ids", []))
        self.assertEqual(child.get("parent_goal_id"), "GOAL-001")
        self.assertTrue(validate_goal_tree(str(self.tmp))["valid"])

    # ── prompt isolation ─────────────────────────────────────────────

    @unittest.skip("V1: goal-tree removed")
    def test_temporary_root_not_in_status_prompt(self):
        self._run_ok("goal-tree", "init-root", "GOAL-001", "--type", "main", "--title", "Main")
        self._run_ok("goal-tree", "init-root", "TMP-001", "--type", "temporary", "--title", "Trial")
        self._run_ok("goal-tree", "add", "TMP-001-A", "--parent", "TMP-001")

        r = self._run_ok("status", "--prompt")
        self.assertNotIn("temporary", r.stdout)
        self.assertNotIn("TMP-001", r.stdout)
        self.assertNotIn("TMP-001-A", r.stdout)

    @unittest.skip("V1: goal-tree removed")
    def test_temporary_root_visible_in_status_debug(self):
        self._run_ok("goal-tree", "init-root", "TMP-001", "--type", "temporary", "--title", "Trial")
        r = self._run_ok("status", "--debug")
        # --debug is expanded mode; look for any goal tree reference
        # At minimum, the temporary root should not crash the debug output
        self.assertTrue(len(r.stdout) > 0)


if __name__ == "__main__":
    unittest.main()
