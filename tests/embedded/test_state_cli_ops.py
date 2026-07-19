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
        shutil.rmtree(self.tmp / ".aiwf/records/tasks", ignore_errors=True)
        (self.tmp / ".aiwf/records/tasks").mkdir(parents=True, exist_ok=True)
        (self.tmp / ".aiwf/runtime/internal/agent-dispatch.jsonl").unlink(
            missing_ok=True
        )

    def _run(self, *args):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT)
        return subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", *args],
            cwd=str(self.tmp), env=env, capture_output=True, text=True, timeout=15,
        )

    def _set_active_task(self, task_id="TASK-ACTIVE", phase="implementing", record=None):
        self._write_json("state/tasks.json", {"tasks": [{
            "id": task_id,
            "status": "active",
            "phase": phase,
            "worktree_path": str(self.tmp),
            "requirements": {
                "executor_required": True,
                "tester_required": True,
                "reviewer_required": True,
            },
        }]})
        value = record or {
            "task_id": task_id,
            "implementation": {"task_id": task_id},
            "testing": {"task_id": task_id, "status": "missing"},
            "review": {"task_id": task_id, "result": "unknown"},
            "fix_loop": {"status": "none"},
        }
        self._write_json(f"records/tasks/{task_id}.json", value)

    def _write_json(self, relative, value):
        path = self.tmp / ".aiwf" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    def test_fixloop_public_cli_opens_and_resolves(self):
        self._set_active_task()
        opened = self._run(
            "fixloop", "open", "--route", "planner",
            "--reason", "Executor found a contract conflict",
            "--required-fix", "Clarify the active contract", "--source", "executor",
        )
        self.assertEqual(opened.returncode, 0, opened.stderr)
        fix_path = self.tmp / ".aiwf/records/tasks/TASK-ACTIVE.json"
        current = json.loads(fix_path.read_text())
        self.assertEqual(current["fix_loop"]["route"], "planner")
        self.assertEqual(current["fix_loop"]["required_fixes"], ["Clarify the active contract"])

        resolved = self._run(
            "fixloop", "resolve", "--resolution", "Planner confirmed the contract",
            "--source", "planner",
        )
        self.assertEqual(resolved.returncode, 0, resolved.stderr)
        self.assertEqual(json.loads(fix_path.read_text())["fix_loop"]["status"], "resolved")

    def test_status_prompt_follows_fixloop_route(self):
        cases = {
            "planner": "/aiwf-planner",
            "executor": "/aiwf-implement",
            "tester": "/aiwf-test",
            "environment": "/aiwf-planner",
        }
        for route, skill in cases.items():
            self._set_active_task(record={
                "task_id": "TASK-ACTIVE",
                "implementation": {"task_id": "TASK-ACTIVE"},
                "testing": {"task_id": "TASK-ACTIVE", "status": "missing"},
                "review": {"task_id": "TASK-ACTIVE", "result": "unknown"},
                "fix_loop": {
                    "status": "open", "route": route, "reason": "route test",
                    "required_fixes": [], "required_verification": [],
                },
            })
            status = self._run("status", "--prompt")
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertIn(f"Required skills: {skill}", status.stdout)
            self.assertIn("fix-loop=open", status.stdout)
            if route == "planner":
                self.assertIn("aiwf fixloop status --task-id TASK-ACTIVE", status.stdout)

    def test_escalated_fixloop_routes_to_planner_and_user_decision(self):
        self._set_active_task(record={
            "task_id": "TASK-ACTIVE",
            "implementation": {"task_id": "TASK-ACTIVE", "implementation_ref": "abc"},
            "testing": {"task_id": "TASK-ACTIVE", "status": "failed"},
            "review": {"task_id": "TASK-ACTIVE", "result": "unknown"},
            "fix_loop": {
                "status": "open", "route": "executor", "reason": "repeated failure",
                "escalation_required": True, "required_fixes": [],
                "required_verification": [],
            },
        })

        status = self._run("status", "--prompt")

        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("Required skills: /aiwf-planner", status.stdout)
        self.assertIn("ask the user whether to retry", status.stdout)

    def test_status_prompt_names_task_and_supplies_agent_assignment(self):
        self._set_active_task()
        status = self._run("status", "--prompt")
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("give the Agent this Task ID", status.stdout)
        self.assertIn("AIWF supplies the current Task contract", status.stdout)

    def test_status_reports_running_agent_without_guessing_that_it_is_stuck(self):
        self._set_active_task()
        dispatch = self.tmp / ".aiwf/runtime/internal/agent-dispatch.jsonl"
        dispatch.parent.mkdir(parents=True, exist_ok=True)
        dispatch.write_text(json.dumps({
            "timestamp": "2026-07-19T10:00:00+00:00",
            "subagent_type": "aiwf-executor",
            "task_id": "TASK-ACTIVE",
            "session_id": "test",
            "status": "started",
        }) + "\n", encoding="utf-8")

        status = self._run("status", "--prompt")

        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("Required skills: none", status.stdout)
        self.assertIn("no return has been observed", status.stdout)
        self.assertIn("not proof that the Agent is stuck", status.stdout)
        self.assertIn("Do not stop, retry, or substitute", status.stdout)

    def test_planner_prompt_prints_control_root_memory_path(self):
        status = self._run("status", "--prompt")
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("Required skills: /aiwf-planner", status.stdout)
        self.assertIn(
            f"Planner memory root: {self.tmp.resolve() / '.aiwf' / 'memory'}",
            status.stdout,
        )

    def test_task_calibration_is_replaced_not_duplicated(self):
        created = self._run(
            "task", "create", "TASK-CAL", "--title", "Calibrate me",
            "--goal", "GOAL-001", "--plan", "PLAN-001",
        )
        self.assertEqual(created.returncode, 0, created.stderr)
        tasks = json.loads((self.tmp / ".aiwf/state/tasks.json").read_text())
        tasks["tasks"][0].update({
            "status": "active", "phase": "closing", "worktree_path": str(self.tmp),
        })
        self._write_json("state/tasks.json", tasks)
        for summary in ["First actual result.", "Final actual result."]:
            result = self._run("task", "calibrate", "TASK-CAL", "--summary", summary)
            self.assertEqual(result.returncode, 0, result.stderr)
        task_md = (self.tmp / ".aiwf/tasks/TASK-CAL.md").read_text()
        self.assertEqual(task_md.count("## Closure Calibration"), 1)
        self.assertIn("Final actual result.", task_md)
        self.assertNotIn("First actual result.", task_md)

    def test_status_routes_missing_calibration_before_close(self):
        self._set_active_task("TASK-CAL", "closing", {
            "task_id": "TASK-CAL",
            "implementation": {"task_id": "TASK-CAL", "implementation_ref": "abc"},
            "testing": {"task_id": "TASK-CAL", "status": "adequate", "tested_ref": "def"},
            "review": {
                "task_id": "TASK-CAL", "result": "accepted", "closure_allowed": True,
                "reviewed_ref": "def", "blockers": [],
            },
            "fix_loop": {"status": "none"},
        })
        task_doc = self.tmp / ".aiwf/tasks/TASK-CAL.md"
        task_doc.parent.mkdir(parents=True, exist_ok=True)
        task_doc.write_text("---\nid: TASK-CAL\n---\n\n# TASK-CAL\n")
        missing = self._run("status", "--prompt")
        self.assertIn("Required skills: /aiwf-planner", missing.stdout)
        self.assertIn("aiwf task calibrate TASK-CAL", missing.stdout)

        task_doc.write_text(
            "---\nid: TASK-CAL\n---\n\n# TASK-CAL\n\n"
            "## Closure Calibration\n\nActually done.\n"
        )
        ready = self._run("status", "--prompt")
        self.assertIn("Required skills: /aiwf-close", ready.stdout)
        self.assertIn("close TASK-CAL", ready.stdout)

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
        self.assertIn("Required skills: /aiwf-planner", result.stdout)
        self.assertIn("Before the next Task", result.stdout)
        self.assertIn("completed Task Calibration", result.stdout)

    def test_status_reports_missing_plan_git_history_when_tasks_are_done(self):
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
        self.assertIn("PLAN-CLOSE-OUT | Git history incomplete", result.stdout)
        self.assertIn("aiwf plan show PLAN-CLOSE-OUT", result.stdout)
        self.assertIn("Required skills: /aiwf-planner", result.stdout)

    def test_sync_clears_plan_hold_when_task_set_changes(self):
        self._write_json("state/plans.json", {
            "plans": [{
                "id": "PLAN-HELD",
                "plan_id": "PLAN-HELD",
                "status": "open",
                "task_ids": ["TASK-DONE"],
                "task_status": {"TASK-DONE": "closed"},
                "integration_hold_ref": "abc123",
            }],
        })
        self._write_json("state/tasks.json", {
            "tasks": [
                {"id": "TASK-DONE", "plan_id": "PLAN-HELD", "status": "closed"},
                {"id": "TASK-NEXT", "plan_id": "PLAN-HELD", "status": "ready"},
            ],
        })

        from aiwf_core.core.index_ops import _sync_plan_task_relations

        changes = []
        _sync_plan_task_relations(self.tmp, False, changes)

        self.assertTrue(changes)
        plan = json.loads(
            (self.tmp / ".aiwf/state/plans.json").read_text(encoding="utf-8")
        )["plans"][0]
        self.assertNotIn("integration_hold_ref", plan)
        self.assertEqual(plan["task_status"]["TASK-NEXT"], "ready")

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

    def test_corrupt_state_is_reported_and_not_replaced_with_defaults(self):
        tasks_path = self.tmp / ".aiwf/state/tasks.json"
        corrupt = '{"tasks": ['
        tasks_path.write_text(corrupt, encoding="utf-8")

        result = self._run("task", "list")

        self.assertEqual(result.returncode, 1)
        self.assertIn("AIWF state error", result.stderr)
        self.assertIn("tasks.json", result.stderr)
        self.assertEqual(tasks_path.read_text(encoding="utf-8"), corrupt)


if __name__ == "__main__":
    unittest.main()
