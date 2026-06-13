"""Stage 2: optional Milestone node contract tests."""
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


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


class TestMilestoneStage2(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aiwf_ms2_"))
        from aiwf_core.core.state_schema import MVP_STATE_FILES
        for rel, factory in MVP_STATE_FILES.items():
            _write(self.tmp / ".aiwf" / rel, factory())

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

    def _valid_plan(self, plan_id="PLAN-001", task_id="TASK-001", milestone_id=""):
        from aiwf_core.core.task_plan import create_task_plan, update_task_plan_section

        create_task_plan(
            str(self.tmp),
            plan_id=plan_id,
            goal_id="GOAL-001",
            task_ids=[task_id],
            title="Test plan",
            milestone_id=milestone_id,
            work_intent="feature",
        )
        update_task_plan_section(str(self.tmp), plan_id, "impact",
            "- docs: no — test\n"
            "- project_map: no — test\n"
            "- environment: no — test\n"
            "- capabilities: no — test\n"
            "- quality_summary: no — test\n")

    def test_default_milestones_file_is_created_by_schema(self):
        path = self.tmp / ".aiwf" / "state" / "milestones.json"
        self.assertTrue(path.exists())
        data = json.loads(path.read_text())
        self.assertEqual(data["schema_version"], 1)
        self.assertIsNone(data["active_milestone_id"])
        self.assertEqual(data["milestones"], [])

    def test_milestone_ops_crud(self):
        from aiwf_core.core.state.milestone_ops import get_milestone, list_milestones, upsert_milestone

        upsert_milestone(str(self.tmp), "MS-001", goal_id="GOAL-001", title="Release package hygiene")

        self.assertEqual(len(list_milestones(str(self.tmp))), 1)
        milestone = get_milestone(str(self.tmp), "MS-001")
        self.assertEqual(milestone["title"], "Release package hygiene")
        self.assertEqual(milestone["status"], "pending")

    def test_milestone_cli_create_list_show_update(self):
        self._run_ok("milestone", "create", "MS-001", "--goal-id", "GOAL-001", "--title", "Release hygiene")
        listed = self._run_ok("milestone", "list").stdout
        self.assertIn("MS-001", listed)
        shown = self._run_ok("milestone", "show", "MS-001").stdout
        self.assertIn("Release hygiene", shown)
        self._run_ok("milestone", "update", "MS-001", "--status", "active")
        data = json.loads((self.tmp / ".aiwf" / "state" / "milestones.json").read_text())
        self.assertEqual(data["active_milestone_id"], "MS-001")

    def test_ordinary_task_without_milestone_can_activate(self):
        from aiwf_core.core.task_ledger import activate_task, upsert_task

        self._valid_plan()
        upsert_task(str(self.tmp), "TASK-001", "No milestone task", status="ready",
                    plan_id="PLAN-001", goal_id="GOAL-001")

        result = activate_task(str(self.tmp), "TASK-001")

        self.assertTrue(result["activated"], result["blockers"])

    def test_plan_milestone_id_must_exist(self):
        r = self._run("plan", "create", "PLAN-001", "--goal-id", "GOAL-001",
                      "--milestone-id", "MS-MISSING")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("milestone not found", r.stderr)

    def test_task_inherits_plan_milestone_on_activation(self):
        from aiwf_core.core.state.milestone_ops import upsert_milestone
        from aiwf_core.core.task_ledger import activate_task, load_ledger, upsert_task

        upsert_milestone(str(self.tmp), "MS-001", goal_id="GOAL-001", status="active")
        self._valid_plan(milestone_id="MS-001")
        upsert_task(str(self.tmp), "TASK-001", "Milestone task", status="ready",
                    plan_id="PLAN-001", goal_id="GOAL-001")

        result = activate_task(str(self.tmp), "TASK-001")

        self.assertTrue(result["activated"], result["blockers"])
        task = next(t for t in load_ledger(str(self.tmp))["tasks"] if t["id"] == "TASK-001")
        self.assertEqual(task["milestone_id"], "MS-001")

    def test_task_plan_milestone_conflict_blocks_activation(self):
        from aiwf_core.core.state.milestone_ops import upsert_milestone
        from aiwf_core.core.task_ledger import activate_task, upsert_task

        upsert_milestone(str(self.tmp), "MS-001", goal_id="GOAL-001", status="active")
        upsert_milestone(str(self.tmp), "MS-002", goal_id="GOAL-001", status="pending")
        self._valid_plan(milestone_id="MS-001")
        upsert_task(str(self.tmp), "TASK-001", "Conflict", status="ready",
                    plan_id="PLAN-001", goal_id="GOAL-001", milestone_id="MS-002")

        result = activate_task(str(self.tmp), "TASK-001")

        self.assertFalse(result["activated"])
        self.assertTrue(any("does not match plan.milestone_id" in b for b in result["blockers"]))

    def test_plan_reconcile_rolls_up_to_milestone_without_auto_close(self):
        from aiwf_core.core.state.milestone_ops import get_milestone, upsert_milestone
        from aiwf_core.core.task_ledger import activate_task, close_task, upsert_task

        upsert_milestone(str(self.tmp), "MS-001", goal_id="GOAL-001", status="active")
        self._valid_plan(milestone_id="MS-001")
        upsert_task(str(self.tmp), "TASK-001", "Close under milestone", status="ready",
                    plan_id="PLAN-001", goal_id="GOAL-001", milestone_id="MS-001")
        self.assertTrue(activate_task(str(self.tmp), "TASK-001")["activated"])
        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["phase"] = "closed"
        state["closure_allowed"] = True
        state["active_task_id"] = "TASK-001"
        state["close_prepared_task_id"] = "TASK-001"
        state["close_prepared_at"] = ""
        state_path.write_text(json.dumps(state, indent=2) + "\n")

        result = close_task(str(self.tmp), "TASK-001")

        self.assertTrue(result["closed"], result["blockers"])
        milestone_progress = result["plan_progress"]["milestone_progress"]
        self.assertTrue(milestone_progress["reconciled"])
        milestone = get_milestone(str(self.tmp), "MS-001")
        self.assertEqual(milestone["evidence_rollup"]["closed_plan_count"], 1)
        self.assertEqual(milestone["evidence_rollup"]["total_plan_count"], 1)
        self.assertEqual(milestone["status"], "active")

    def test_milestone_close_requires_assessment_then_allows_pass(self):
        from aiwf_core.core.state.milestone_ops import close_milestone, record_milestone_assessment, upsert_milestone

        upsert_milestone(str(self.tmp), "MS-001", goal_id="GOAL-001", status="active")
        blocked = close_milestone(str(self.tmp), "MS-001")
        self.assertFalse(blocked["closed"])
        self.assertTrue(any("stage synthesis required" in b for b in blocked["blockers"]))

        record_milestone_assessment(
            str(self.tmp),
            "MS-001",
            verdict="PASS_WITH_RISK",
            summary="Stage outcome is coherent; residual risk documented.",
            residual_risks=["follow-up validation remains"],
            next_recommendation="Proceed to next plan",
        )
        from aiwf_core.core.state.milestone_ops import (
            record_milestone_integration,
            record_milestone_arch_review,
        )
        record_milestone_integration(
            str(self.tmp), "MS-001", status="passed",
            summary="Integration tests passed",
        )
        record_milestone_arch_review(
            str(self.tmp), "MS-001", status="intact",
            notes="Cross-goal interfaces are intact",
        )
        closed = close_milestone(str(self.tmp), "MS-001")

        self.assertTrue(closed["closed"], closed["blockers"])

    def test_milestone_close_cli_returns_nonzero_when_blocked(self):
        self._run_ok("milestone", "create", "MS-001", "--goal-id", "GOAL-001", "--status", "active")

        blocked = self._run("milestone", "close", "MS-001")

        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("closed=False", blocked.stdout)

    def test_milestone_close_blocks_incomplete_attached_plan(self):
        from aiwf_core.core.state.milestone_ops import (
            close_milestone,
            record_milestone_assessment,
            upsert_milestone,
        )

        upsert_milestone(
            str(self.tmp),
            "MS-001",
            goal_id="GOAL-001",
            status="active",
            plan_ids=["PLAN-001"],
            task_ids=["TASK-001"],
        )
        self._valid_plan(milestone_id="MS-001")
        record_milestone_assessment(
            str(self.tmp),
            "MS-001",
            verdict="PASS",
            summary="Synthesis written too early.",
        )

        blocked = close_milestone(str(self.tmp), "MS-001")

        self.assertFalse(blocked["closed"])
        self.assertTrue(any("plan not complete" in b for b in blocked["blockers"]))


class TestMilestoneStatusDisplay(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aiwf_ms2_status_"))
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
            cwd=str(self.tmp),
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        (self.tmp / ".aiwf" / "artifacts" / "reports" / "当前状态.md").unlink(missing_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run_ok(self, *args):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", *args],
            cwd=str(self.tmp),
            env=env,
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )
        self.assertEqual(r.returncode, 0, f"{args}\nstdout={r.stdout}\nstderr={r.stderr}")
        return r

    def test_status_prompt_keeps_milestone_short_and_debug_expands(self):
        self._run_ok("milestone", "create", "MS-001", "--goal-id", "GOAL-001",
                     "--title", "Release package hygiene", "--status", "active")
        self._run_ok("plan", "create", "PLAN-001", "--goal-id", "GOAL-001",
                     "--milestone-id", "MS-001", "--task", "TASK-001")

        prompt = self._run_ok("status", "--prompt").stdout
        debug = self._run_ok("status", "--debug").stdout

        self.assertIn("milestone=MS-001", prompt)
        self.assertNotIn("Release package hygiene", prompt)
        self.assertIn("Milestone:", debug)
        self.assertIn("MS-001", debug)


class TestMissionIntegration(unittest.TestCase):
    """Mission — project-level semantic container above the Goal Tree."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aiwf_mission_"))
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
            cwd=str(self.tmp), env=env, timeout=30,
        )
        self.assertEqual(r.returncode, 0, r.stderr)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, *args):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", *args],
            capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT,
        )

    def _run_ok(self, *args):
        r = self._run(*args)
        self.assertEqual(r.returncode, 0, f"{args}\nstdout={r.stdout}\nstderr={r.stderr}")
        return r

    def test_mission_show_default(self):
        r = self._run_ok("mission", "show")
        self.assertIn("MISSION-001", r.stdout)
        self.assertIn("draft", r.stdout)

    def test_mission_update_statement(self):
        self._run_ok("mission", "update", "--statement", "Build the best solver")
        r = self._run_ok("mission", "show")
        self.assertIn("Build the best solver", r.stdout)

    def test_mission_update_boundaries(self):
        self._run_ok("mission", "update", "--boundary", "No GUI", "--boundary", "No cloud")
        r = self._run_ok("mission", "show")
        self.assertIn("No GUI", r.stdout)
        self.assertIn("No cloud", r.stdout)

    def test_mission_update_status(self):
        self._run_ok("mission", "update", "--status", "active")
        r = self._run_ok("mission", "show")
        self.assertIn("active", r.stdout)

    def test_milestone_create_with_mission_id(self):
        self._run_ok("milestone", "create", "MS-001", "--mission-id", "MISSION-001",
                     "--title", "Core engine checkpoint")
        from aiwf_core.core.state.milestone_ops import get_milestone
        ms = get_milestone(str(self.tmp), "MS-001")
        self.assertEqual(ms.get("mission_id"), "MISSION-001")

    def test_milestone_close_checks_covered_goals(self):
        from aiwf_core.core.state.milestone_ops import (
            close_milestone, upsert_milestone, record_milestone_assessment,
        )

        # GOAL-001 is not in the Goal Tree unless explicitly registered.
        # close_milestone should block when a covered_goal is missing.
        upsert_milestone(
            str(self.tmp), "MS-001",
            goal_id="GOAL-001", status="active",
            covered_goal_ids=["GOAL-001"],
        )
        record_milestone_assessment(
            str(self.tmp), "MS-001",
            verdict="PASS", summary="Ready",
        )

        blocked = close_milestone(str(self.tmp), "MS-001")
        self.assertFalse(blocked["closed"])
        self.assertTrue(any("not registered" in b for b in blocked["blockers"]))

    def test_milestone_close_succeeds_when_no_covered_goals(self):
        from aiwf_core.core.state.milestone_ops import (
            close_milestone, upsert_milestone, record_milestone_assessment,
        )

        upsert_milestone(
            str(self.tmp), "MS-001",
            goal_id="GOAL-001", status="active",
        )
        record_milestone_assessment(
            str(self.tmp), "MS-001",
            verdict="PASS", summary="Ready",
        )
        from aiwf_core.core.state.milestone_ops import (
            record_milestone_integration,
            record_milestone_arch_review,
        )
        record_milestone_integration(
            str(self.tmp), "MS-001", status="passed",
            summary="Integration tests passed",
        )
        record_milestone_arch_review(
            str(self.tmp), "MS-001", status="intact",
            notes="Cross-goal interfaces are intact",
        )

        result = close_milestone(str(self.tmp), "MS-001")
        self.assertTrue(result["closed"], result.get("blockers", []))

    def test_mission_attach_milestone(self):
        self._run_ok("mission", "update", "--statement", "Test mission")
        self._run_ok("milestone", "create", "MS-001", "--mission-id", "MISSION-001")
        self._run_ok("mission", "update", "--add-milestone", "MS-001")
        r = self._run_ok("mission", "show")
        self.assertIn("MS-001", r.stdout)

    def test_mission_attach_goal_root(self):
        self._run_ok("mission", "update", "--add-goal-root", "GOAL-001")
        r = self._run_ok("mission", "show")
        self.assertIn("GOAL-001", r.stdout)
