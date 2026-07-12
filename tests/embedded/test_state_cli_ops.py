"""Current public CLI routing and calibration contracts."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


class TestStateCliOps(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="aiwf_cli_"))
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT)
        result = subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
            cwd=str(cls.tmp), env=env, capture_output=True, text=True, timeout=20,
        )
        if result.returncode:
            raise AssertionError(result.stderr)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        from aiwf_core.core.state_schema import MVP_STATE_FILES
        for name, factory in MVP_STATE_FILES.items():
            path = self.tmp / ".aiwf" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(factory(), indent=2) + "\n")

    def _run(self, *args):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT)
        return subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", *args],
            cwd=str(self.tmp), env=env, capture_output=True, text=True, timeout=15,
        )

    def test_fixloop_public_cli_opens_and_resolves(self):
        opened = self._run(
            "fixloop", "open", "--route", "planner",
            "--reason", "Executor found a contract conflict",
            "--required-fix", "Clarify the active contract", "--source", "executor",
        )
        self.assertEqual(opened.returncode, 0, opened.stderr)
        fix_path = self.tmp / ".aiwf" / "state" / "fix-loop.json"
        current = json.loads(fix_path.read_text())
        self.assertEqual(current["route"], "planner")
        self.assertEqual(current["required_fixes"], ["Clarify the active contract"])

        resolved = self._run(
            "fixloop", "resolve", "--resolution", "Planner confirmed the contract",
            "--source", "planner",
        )
        self.assertEqual(resolved.returncode, 0, resolved.stderr)
        self.assertEqual(json.loads(fix_path.read_text())["status"], "resolved")

    def test_status_prompt_follows_fixloop_route(self):
        cases = {
            "planner": "/aiwf-planner",
            "executor": "/aiwf-implement",
            "tester": "/aiwf-test",
            "environment": "/aiwf-planner",
        }
        path = self.tmp / ".aiwf" / "state" / "fix-loop.json"
        for route, skill in cases.items():
            path.write_text(json.dumps({
                "status": "open", "route": route, "reason": "route test",
                "required_fixes": [], "required_verification": [],
            }))
            status = self._run("status", "--prompt")
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertIn(f"[ATTN] {skill}", status.stdout)
            self.assertIn(".aiwf/state/fix-loop.json", status.stdout)

    def test_task_calibration_is_replaced_not_duplicated(self):
        created = self._run(
            "task", "create", "TASK-CAL", "--title", "Calibrate me",
            "--goal", "GOAL-001", "--plan", "PLAN-001",
        )
        self.assertEqual(created.returncode, 0, created.stderr)
        for summary in ["First actual result.", "Final actual result."]:
            result = self._run("task", "calibrate", "TASK-CAL", "--summary", summary)
            self.assertEqual(result.returncode, 0, result.stderr)
        task_md = (self.tmp / ".aiwf/tasks/TASK-CAL.md").read_text()
        self.assertEqual(task_md.count("## Closure Calibration"), 1)
        self.assertIn("Final actual result.", task_md)
        self.assertNotIn("First actual result.", task_md)

    def test_status_routes_missing_calibration_before_close(self):
        state_path = self.tmp / ".aiwf/state/state.json"
        state = json.loads(state_path.read_text())
        state.update({"phase": "reviewing", "active_task_id": "TASK-CAL"})
        state_path.write_text(json.dumps(state))
        task_doc = self.tmp / ".aiwf/tasks/TASK-CAL.md"
        task_doc.parent.mkdir(parents=True, exist_ok=True)
        task_doc.write_text("---\nid: TASK-CAL\n---\n\n# TASK-CAL\n")
        (self.tmp / ".aiwf/records/testing.json").write_text(json.dumps({
            "status": "adequate", "commands": [],
        }))
        (self.tmp / ".aiwf/records/review.json").write_text(json.dumps({
            "result": "accepted", "closure_allowed": True, "blockers": [],
        }))

        missing = self._run("status", "--prompt")
        self.assertIn("[ATTN] /aiwf-planner", missing.stdout)
        self.assertIn("Next: calibrate before close", missing.stdout)

        task_doc.write_text(
            "---\nid: TASK-CAL\n---\n\n# TASK-CAL\n\n"
            "## Closure Calibration\n\nActually done.\n"
        )
        ready = self._run("status", "--prompt")
        self.assertIn("[ATTN] /aiwf-close", ready.stdout)
        self.assertIn("Next: close task", ready.stdout)

    def test_status_routes_after_a_completed_plan_task(self):
        state_path = self.tmp / ".aiwf/state/state.json"
        state = json.loads(state_path.read_text())
        state.update({
            "phase": "planning", "active_task_id": None,
            "active_plan_id": "PLAN-AFTER-TASK",
        })
        state_path.write_text(json.dumps(state))
        (self.tmp / ".aiwf/state/plans.json").write_text(json.dumps({
            "active_plan_id": "PLAN-AFTER-TASK",
            "plans": [{
                "plan_id": "PLAN-AFTER-TASK", "status": "open",
                "task_ids": ["TASK-DONE", "TASK-NEXT"],
                "task_status": {"TASK-DONE": "closed", "TASK-NEXT": "ready"},
            }],
        }))
        (self.tmp / ".aiwf/state/tasks.json").write_text(json.dumps({
            "tasks": [
                {"id": "TASK-DONE", "status": "closed"},
                {"id": "TASK-NEXT", "status": "ready"},
            ],
        }))
        plan_doc = self.tmp / ".aiwf/plans/PLAN-AFTER-TASK.md"
        plan_doc.parent.mkdir(parents=True, exist_ok=True)
        plan_doc.write_text("---\nid: PLAN-AFTER-TASK\n---\n\n# Plan\n")

        result = self._run("status", "--prompt")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[ATTN] /aiwf-planner", result.stdout)
        self.assertIn("Focus: After a Task", result.stdout)
        self.assertIn("compare the actual result with the Plan", result.stdout)
        self.assertIn(".aiwf/plans/PLAN-AFTER-TASK.md", result.stdout)

    def test_status_routes_plan_close_out_when_no_tasks_remain(self):
        state_path = self.tmp / ".aiwf/state/state.json"
        state = json.loads(state_path.read_text())
        state.update({
            "phase": "planning", "active_task_id": None,
            "active_plan_id": "PLAN-CLOSE-OUT",
        })
        state_path.write_text(json.dumps(state))
        (self.tmp / ".aiwf/state/plans.json").write_text(json.dumps({
            "active_plan_id": "PLAN-CLOSE-OUT",
            "plans": [{
                "plan_id": "PLAN-CLOSE-OUT", "status": "open",
                "task_ids": ["TASK-DONE"],
                "task_status": {"TASK-DONE": "closed"},
            }],
        }))
        (self.tmp / ".aiwf/state/tasks.json").write_text(json.dumps({
            "tasks": [{"id": "TASK-DONE", "status": "closed"}],
        }))

        result = self._run("status", "--prompt")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Focus: Close Out a Plan", result.stdout)
        self.assertIn("confirm the delivered parts work together", result.stdout)

    def test_closed_plan_rejects_new_task_links(self):
        plans_path = self.tmp / ".aiwf/state/plans.json"
        plans_path.write_text(json.dumps({
            "active_plan_id": None,
            "plans": [{
                "plan_id": "PLAN-HISTORY", "id": "PLAN-HISTORY",
                "status": "closed", "task_ids": [], "task_status": {},
            }],
        }))

        linked = self._run("plan", "link-task", "PLAN-HISTORY", "TASK-LATE")
        self.assertNotEqual(linked.returncode, 0)
        self.assertIn("is closed", linked.stderr)

        created = self._run(
            "task", "create", "TASK-LATE", "--title", "Late work",
            "--plan", "PLAN-HISTORY",
        )
        self.assertNotEqual(created.returncode, 0)
        self.assertIn("is closed", created.stderr)
        tasks = json.loads((self.tmp / ".aiwf/state/tasks.json").read_text())
        self.assertNotIn("TASK-LATE", [item.get("id") for item in tasks.get("tasks", [])])

    def test_closed_plan_rejects_structural_mutation(self):
        (self.tmp / ".aiwf/state/plans.json").write_text(json.dumps({
            "active_plan_id": None,
            "plans": [
                {
                    "plan_id": "PLAN-HISTORY", "id": "PLAN-HISTORY",
                    "status": "closed", "task_ids": ["TASK-OLD"],
                    "task_status": {"TASK-OLD": "closed"},
                    "dependencies": ["PLAN-DEP"],
                },
                {"plan_id": "PLAN-DEP", "id": "PLAN-DEP", "status": "closed"},
                {"plan_id": "PLAN-NEW-DEP", "id": "PLAN-NEW-DEP", "status": "open"},
            ],
        }))

        commands = [
            ("plan", "unlink-task", "PLAN-HISTORY", "TASK-OLD"),
            ("plan", "dep", "add", "PLAN-HISTORY", "PLAN-NEW-DEP"),
            (
                "plan", "dep", "remove", "PLAN-HISTORY", "PLAN-DEP",
                "--reason", "change history",
            ),
            ("plan", "create", "PLAN-HISTORY", "--title", "rewrite history"),
        ]
        for command in commands:
            result = self._run(*command)
            self.assertNotEqual(result.returncode, 0, command)
            self.assertIn("closed", result.stderr.lower(), command)


if __name__ == "__main__":
    unittest.main()
