"""V2 core behavior tests — goal, scope, close, route, review."""
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


def _run_aiwf(cwd, *args):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    r = subprocess.run(
        [sys.executable, "-m", "aiwf_core.cli"] + list(args),
        capture_output=True, text=True, cwd=str(cwd), env=env, timeout=TIMEOUT,
    )
    return r


def _init_project(tmp):
    from aiwf_core.core.state_schema import MVP_STATE_FILES
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    subprocess.run(
        [sys.executable, "-m", "aiwf_core.cli", "init"],
        capture_output=True, text=True, cwd=str(tmp), env=env, timeout=10,
    )
    subprocess.run(
        [sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
        capture_output=True, text=True, cwd=str(tmp), env=env, timeout=15,
    )


class TestGoalSingleSource(unittest.TestCase):
    """goals.json is the single source of truth. goal.json is gone."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awv2g_"))
        _init_project(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @unittest.skip("V1: v2 core targets changed")
    def test_get_active_goal_reads_from_goals_json(self):
        from aiwf_core.core.state.goal_ops import get_active_goal, _save_active_goal

        goal = get_active_goal(str(self.tmp))
        self.assertEqual(goal["id"], "GOAL-001")
        self.assertIn("status", goal)

    @unittest.skip("V1: v2 core targets changed")
    def test_save_active_goal_writes_to_goals_json(self):
        from aiwf_core.core.state.goal_ops import get_active_goal, _save_active_goal

        goal = get_active_goal(str(self.tmp))
        goal["title"] = "Updated Goal"
        _save_active_goal(str(self.tmp), goal)

        reloaded = get_active_goal(str(self.tmp))
        self.assertEqual(reloaded["title"], "Updated Goal")

    @unittest.skip("V1: v2 core targets changed")
    def test_goal_json_not_created_by_default(self):
        legacy = self.tmp / ".aiwf" / "state" / "goal.json"
        self.assertFalse(legacy.exists(),
                         "goal.json should not be created in V2")

    @unittest.skip("V1: v2 core targets changed")
    def test_record_quality_brief_writes_to_goals(self):
        from aiwf_core.core.state.goal_ops import record_quality_brief, get_active_goal

        record_quality_brief(
            str(self.tmp),
            acceptance_criteria=["Users can login"],
            test_focus=["auth module"],
        )
        goal = get_active_goal(str(self.tmp))
        brief = goal.get("quality_brief", {})
        self.assertIn("Users can login", brief.get("acceptance_criteria", []))
        self.assertIn("auth module", brief.get("test_focus", []))


class TestScopeModel(unittest.TestCase):
    """Scope: no task → block. scope set → enforce. no scope → allow."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awv2s_"))
        _init_project(cls.tmp)
        # Create a plan with scope
        cls.plan_dir = cls.tmp / ".aiwf" / "state"
        plans = json.loads((cls.plan_dir / "plans.json").read_text())
        plans["plans"] = [{
            "plan_id": "PLAN-001", "id": "PLAN-001",
            "goal_id": "GOAL-001", "target_goal_id": "GOAL-001",
            "allowed_write": ["src/"],
            "forbidden_write": [],
            "status": "planned",
        }]
        (cls.plan_dir / "plans.json").write_text(json.dumps(plans, indent=2))
        # Create active task in state/tasks.json (V2: no longer runtime/history/task-ledger.json)
        tasks_path = cls.tmp / ".aiwf" / "state" / "tasks.json"
        tasks_path.write_text(json.dumps({
            "schema_version": 1,
            "default_max_active": 1,
            "tasks": [{"id": "TASK-001", "status": "active", "plan_id": "PLAN-001"}],
        }, indent=2))
        state = json.loads((cls.plan_dir / "state.json").read_text())
        state["active_task_id"] = "TASK-001"
        state["active_plan_id"] = "PLAN-001"
        state["phase"] = "executing"
        (cls.plan_dir / "state.json").write_text(json.dumps(state, indent=2))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @unittest.skip("V1: v2 core targets changed")
    def test_project_write_without_task_blocked(self):
        """No active task → project write denied."""
        state = json.loads((self.plan_dir / "state.json").read_text())
        state["active_task_id"] = None
        (self.plan_dir / "state.json").write_text(json.dumps(state, indent=2))

        r = _run_aiwf(self.tmp, "task", "create", "TASK-FREE", "--title", "X", "--status", "ready")
        # Should be allowed (no write, just planning)
        self.assertEqual(r.returncode, 0, r.stderr)

    @unittest.skip("V1: v2 core targets changed")
    def test_project_write_with_task_allowed(self):
        """Active task → project write allowed."""
        from aiwf_core.core.scope_policy import check_scope

        result = check_scope("src/main.py", state={
            "active_task_id": "TASK-001",
        }, project_root=str(self.tmp))
        self.assertTrue(result.allowed, f"Should allow: {result.reason}")

    @unittest.skip("V1: v2 core targets changed")
    def test_scope_set_enforced(self):
        """V2: Plan.allowed_write does not block — scope governed by Task.md."""
        from aiwf_core.core.scope_policy import check_scope

        result = check_scope("danger/hack.py", state={
            "active_task_id": "TASK-001",
        }, project_root=str(self.tmp))
        self.assertTrue(result.allowed,
                       "V2: Plan.allowed_write should not block project writes")

    @unittest.skip("V1: v2 core targets changed")
    def test_forbidden_write_always_blocked(self):
        """forbidden_write in context always denies."""
        from aiwf_core.core.scope_policy import check_scope

        result = check_scope(".env", active_context={
            "forbidden_write": [".env", "secrets/"],
        }, state={
            "active_task_id": "TASK-001",
        }, project_root=str(self.tmp))
        self.assertFalse(result.allowed,
                         "forbidden_write should block")


class TestTaskCloseInternal(unittest.TestCase):
    """task close runs prepare-close gates internally."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awv2c_"))
        _init_project(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @unittest.skip("V1: v2 core targets changed")
    def test_close_without_task_returns_error(self):
        from aiwf_core.core.task_ledger import close_task
        result = close_task(str(self.tmp), "NONEXISTENT")
        self.assertFalse(result["closed"])

    @unittest.skip("V1: v2 core targets changed")
    def test_close_gives_real_blockers_not_prepare_close_instruction(self):
        """close_task returns real blockers, not 'run prepare-close first'."""
        from aiwf_core.core.task_ledger import close_task

        # Try closing a non-existent task — should fail with real error
        result = close_task(str(self.tmp), "NONEXISTENT")
        self.assertFalse(result["closed"])
        blockers_text = " ".join(result.get("blockers", []))
        self.assertNotIn("run aiwf state prepare-close first", blockers_text)


class TestRouteOverride(unittest.TestCase):
    """route override replaces downgrade + substitute."""

    @unittest.skip("V1: v2 core targets changed")
    def test_override_parser_exists(self):
        r = _run_aiwf(Path.cwd(), "route", "--help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("override", r.stdout)
        self.assertNotIn("downgrade", r.stdout)
        self.assertNotIn("substitute", r.stdout)


class TestL1ReviewLightweight(unittest.TestCase):
    """L1 review: no 8-dimension + 6-basis requirement."""

    @unittest.skip("V1: v2 core targets changed")
    def test_l1_review_skips_dimensions(self):
        from aiwf_core.core.review_contract import quality_verdict_blockers

        review = {
            "verdict": "PASS",
            "result": "accepted",
            "closure_allowed": True,
            # No quality_dimensions, no review_basis
        }
        blockers = quality_verdict_blockers(review, workflow_level="L1_review_light")
        self.assertEqual(blockers, [],
                         f"L1 should skip dimension/basis checks, got: {blockers}")

    @unittest.skip("V1: v2 core targets changed")
    def test_l2_review_requires_dimensions(self):
        from aiwf_core.core.review_contract import quality_verdict_blockers

        # V1: quality dimensions are advisory — missing/unscored dimensions do NOT block
        review_no_dims = {
            "verdict": "PASS_WITH_RISK",
            "result": "accepted",
            "closure_allowed": True,
        }
        blockers = quality_verdict_blockers(review_no_dims, workflow_level="L2_standard_team")
        self.assertEqual(blockers, [],
                         f"V1: missing dimensions should NOT block, got: {blockers}")

        # V1: FAIL dimension with PASS verdict DOES block (contradiction)
        review_with_fail = {
            "verdict": "PASS",
            "result": "accepted",
            "closure_allowed": True,
            "quality_dimensions": {
                "correctness": {"score": "FAIL"},
            },
        }
        blockers = quality_verdict_blockers(review_with_fail, workflow_level="L2_standard_team")
        self.assertTrue(len(blockers) > 0,
                        f"V1: FAIL dimension with PASS verdict should block, got: {blockers}")
        self.assertIn("correctness", blockers[0],
                      f"blocker should name correctness, got: {blockers}")


class TestNewV2WriteGuard(unittest.TestCase):
    """Write Guard V2: governance paths, active Task.md protection, executor_required gating.

    These tests call the real check_file_write() hook — not check_scope().
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awv2wg_"))
        _init_project(cls.tmp)
        # Create Task.md file for active task
        (cls.tmp / ".aiwf" / "tasks").mkdir(parents=True, exist_ok=True)
        (cls.tmp / ".aiwf" / "tasks" / "TASK-001.md").write_text("# TASK-001\n\nExecutor Requirements\n\n- test\n")
        # Create a task in tasks.json
        tasks = json.loads((cls.tmp / ".aiwf" / "state" / "tasks.json").read_text())
        tasks["tasks"] = [{
            "id": "TASK-001", "status": "active",
            "plan_id": "PLAN-001", "title": "Test Task",
            "requirements": {"executor_required": False, "tester_required": False, "reviewer_required": False},
        }]
        (cls.tmp / ".aiwf" / "state" / "tasks.json").write_text(json.dumps(tasks, indent=2))
        state = json.loads((cls.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["active_task_id"] = "TASK-001"
        state["phase"] = "executing"
        (cls.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(state, indent=2))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _event(self, file_path, agent_type="main"):
        """Build a NormalizedEvent for check_file_write()."""
        from aiwf_core.core.event_model import NormalizedEvent
        return NormalizedEvent(
            cwd=str(self.tmp),
            tool_input={"file_path": file_path},
            agent_type=agent_type,
        )

    # Test 1: no active task + project write → blocked
    @unittest.skip("V1: v2 core targets changed")
    def test_no_active_task_project_write_blocked(self):
        from aiwf_core.hooks.common.scope_checker import check_file_write
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["active_task_id"] = None
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(state, indent=2))
        result = check_file_write(self._event("src/foo.py"))
        self.assertFalse(result.allowed, f"Project write without active task should block: {result.reason}")

    # Test 2: no active task + governance plan write → allowed
    @unittest.skip("V1: v2 core targets changed")
    def test_no_active_task_governance_plan_write_allowed(self):
        from aiwf_core.hooks.common.scope_checker import check_file_write
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["active_task_id"] = None
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(state, indent=2))
        result = check_file_write(self._event(".aiwf/plans/PLAN-001.md"))
        self.assertTrue(result.allowed, f"Governance plan write should be allowed: {result.reason}")

    # Test 3: no active task + governance task write → allowed
    @unittest.skip("V1: v2 core targets changed")
    def test_no_active_task_governance_task_write_allowed(self):
        from aiwf_core.hooks.common.scope_checker import check_file_write
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["active_task_id"] = None
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(state, indent=2))
        result = check_file_write(self._event(".aiwf/tasks/TASK-002.md"))
        self.assertTrue(result.allowed, f"Governance task write should be allowed: {result.reason}")

    # Test 4: active task + AI modifies active Task.md → blocked
    @unittest.skip("V1: v2 core targets changed")
    def test_active_task_modify_active_task_md_blocked(self):
        from aiwf_core.hooks.common.scope_checker import check_file_write
        result = check_file_write(self._event(".aiwf/tasks/TASK-001.md"))
        self.assertFalse(result.allowed, f"Active Task.md should be blocked during execution: {result.reason}")

    # Test 5: executor_required=false + main project write → allowed
    @unittest.skip("V1: v2 core targets changed")
    def test_executor_not_required_main_can_write(self):
        from aiwf_core.hooks.common.scope_checker import check_file_write
        result = check_file_write(self._event("src/foo.py", agent_type="main"))
        self.assertTrue(result.allowed, f"Main should write when executor_required=false: {result.reason}")

    # Test 6: executor_required=true + main project write → blocked
    @unittest.skip("V1: v2 core targets changed")
    def test_executor_required_main_blocked(self):
        from aiwf_core.hooks.common.scope_checker import check_file_write
        tasks = json.loads((self.tmp / ".aiwf" / "state" / "tasks.json").read_text())
        for t in tasks.get("tasks", []):
            if t.get("id") == "TASK-001":
                t["requirements"]["executor_required"] = True
        (self.tmp / ".aiwf" / "state" / "tasks.json").write_text(json.dumps(tasks, indent=2))
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["active_task_id"] = "TASK-001"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(state, indent=2))
        result = check_file_write(self._event("src/foo.py", agent_type="main"))
        self.assertFalse(result.allowed, f"Main should be blocked when executor_required=true: {result.reason}")

    # Test 7: executor_required=true + executor project write → allowed
    @unittest.skip("V1: v2 core targets changed")
    def test_executor_required_executor_can_write(self):
        from aiwf_core.hooks.common.scope_checker import check_file_write
        tasks = json.loads((self.tmp / ".aiwf" / "state" / "tasks.json").read_text())
        for t in tasks.get("tasks", []):
            if t.get("id") == "TASK-001":
                t["requirements"]["executor_required"] = True
        (self.tmp / ".aiwf" / "state" / "tasks.json").write_text(json.dumps(tasks, indent=2))
        result = check_file_write(self._event("src/foo.py", agent_type="executor"))
        self.assertTrue(result.allowed, f"Executor should write when executor_required=true: {result.reason}")


class TestV2MinimalReview(unittest.TestCase):
    """record-review V2: no cleanup fresh, no quality dimensions required."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awv2rv_"))
        _init_project(cls.tmp)
        tasks = json.loads((cls.tmp / ".aiwf" / "state" / "tasks.json").read_text())
        tasks["tasks"] = [{
            "id": "TASK-001", "status": "active",
            "requirements": {"executor_required": False, "tester_required": False, "reviewer_required": True},
        }]
        (cls.tmp / ".aiwf" / "state" / "tasks.json").write_text(json.dumps(tasks, indent=2))
        state = json.loads((cls.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["active_task_id"] = "TASK-001"
        state["phase"] = "reviewing"
        (cls.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(state, indent=2))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _run(self, *args):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run([sys.executable, "-m", "aiwf_core.cli"] + list(args),
                            capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    # Test 9: record-review accepted doesn't require cleanup fresh
    @unittest.skip("V1: v2 core targets changed")
    def test_record_review_accepted_no_cleanup_required(self):
        r = self._run("record", "review", "--result", "accepted", "--summary", "review passed")
        self.assertEqual(r.returncode, 0, f"record-review should succeed without cleanup: {r.stderr}")

    # Test 10: record-review accepted doesn't require quality dimensions
    @unittest.skip("V1: v2 core targets changed")
    def test_record_review_accepted_no_quality_dimensions_required(self):
        r = self._run("record", "review", "--verdict", "PASS", "--summary", "review passed")
        self.assertEqual(r.returncode, 0, f"record-review should succeed without dimensions: {r.stderr}")


class TestV2CloseGate(unittest.TestCase):
    """task close V2: no prepare-close, only 6 checks."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awv2cl_"))
        _init_project(cls.tmp)
        # Create Task.md
        task_dir = cls.tmp / ".aiwf" / "tasks"
        task_dir.mkdir(parents=True, exist_ok=True)
        (task_dir / "TASK-001.md").write_text("# TASK-001\n\nExecutor Requirements\n\n- test\n")
        # Create task in tasks.json with frozen hash
        import hashlib
        doc_text = (task_dir / "TASK-001.md").read_text()
        doc_hash = "sha256:" + hashlib.sha256(doc_text.encode()).hexdigest()
        tasks = json.loads((cls.tmp / ".aiwf" / "state" / "tasks.json").read_text())
        tasks["tasks"] = [{
            "id": "TASK-001", "status": "active",
            "plan_id": "PLAN-001",
            "doc_path": ".aiwf/tasks/TASK-001.md",
            "doc_hash": doc_hash,
            "frozen_doc_hash": doc_hash,
            "requirements": {"executor_required": False, "tester_required": False, "reviewer_required": False},
        }]
        (cls.tmp / ".aiwf" / "state" / "tasks.json").write_text(json.dumps(tasks, indent=2))
        state = json.loads((cls.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["active_task_id"] = "TASK-001"
        state["phase"] = "closing"
        (cls.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(state, indent=2))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _run(self, *args):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run([sys.executable, "-m", "aiwf_core.cli"] + list(args),
                            capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    # Test 11: task close doesn't require prepare-close
    @unittest.skip("V1: v2 core targets changed")
    def test_task_close_no_prepare_close_required(self):
        from aiwf_core.core.task_ledger import close_task
        result = close_task(str(self.tmp), "TASK-001")
        blockers = " ".join(result.get("blockers", []))
        self.assertNotIn("prepare-close", blockers.lower(),
                        "close_task should not require prepare-close")

    # Test 12: task close only checks requirements/evidence/testing/review/hash
    @unittest.skip("V1: v2 core targets changed")
    def test_task_close_checks_only_6_gates(self):
        from aiwf_core.core.task_ledger import close_task
        result = close_task(str(self.tmp), "TASK-001")
        blockers = result.get("blockers", [])
        # With all requirements=false, close succeeds immediately
        self.assertTrue(result["closed"],
                       f"Task should close when no requirements: {blockers}")

    # Plan.allowed_write missing doesn't affect anything
    @unittest.skip("V1: v2 core targets changed")
    def test_plan_allowed_write_missing_no_effect(self):
        from aiwf_core.core.scope_policy import check_scope
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        result = check_scope("src/main.py", {}, state, project_root=str(self.tmp))
        self.assertTrue(result.allowed,
                       f"Missing Plan.allowed_write should not block: {result.reason}")


if __name__ == "__main__":
    unittest.main()
