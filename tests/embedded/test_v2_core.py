"""Configurable write-policy contracts."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


class TestConfigurableWritePolicy(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aiwf_policy_"))
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT)
        result = subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
            cwd=str(self.tmp), env=env, capture_output=True, text=True, timeout=20,
        )
        if result.returncode:
            raise AssertionError(result.stderr)
        (self.tmp / ".aiwf/tasks/TASK-001.md").write_text(
            "---\nid: TASK-001\nexecutor_required: true\n"
            "tester_required: true\nreviewer_required: true\n---\n"
        )
        tasks_path = self.tmp / ".aiwf/state/tasks.json"
        tasks = json.loads(tasks_path.read_text())
        tasks["tasks"] = [{
            "id": "TASK-001", "status": "active",
            "requirements": {
                "executor_required": True,
                "tester_required": True,
                "reviewer_required": True,
            },
        }]
        tasks_path.write_text(json.dumps(tasks))
        state_path = self.tmp / ".aiwf/state/state.json"
        state = json.loads(state_path.read_text())
        state.update({"active_task_id": "TASK-001", "phase": "executing"})
        state_path.write_text(json.dumps(state))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _event(self, path, role="main"):
        from aiwf_core.core.event_model import NormalizedEvent
        return NormalizedEvent(cwd=str(self.tmp), tool_input={"file_path": path}, agent_type=role)

    def _policy(self, **updates):
        path = self.tmp / ".aiwf/config/write-policy.json"
        policy = json.loads(path.read_text())
        policy.update(updates)
        path.write_text(json.dumps(policy))

    def test_first_implementation_requires_executor_by_default(self):
        from aiwf_core.hooks.common.scope_checker import check_file_write
        result = check_file_write(self._event("src/main.py"))
        self.assertFalse(result.allowed)
        self.assertIn("first implementation write", result.reason)

    def test_policy_can_allow_inline_first_implementation(self):
        from aiwf_core.hooks.common.scope_checker import check_file_write
        self._policy(first_implementation_requires_executor=False)
        self.assertTrue(check_file_write(self._event("src/main.py")).allowed)

    def test_tester_write_mode_is_configurable_and_reviewer_has_no_separate_policy(self):
        from aiwf_core.hooks.common.scope_checker import check_file_write
        self._policy(tester_project_writes="allow_all")
        self.assertTrue(check_file_write(self._event("src/test.py", "aiwf-tester")).allowed)
        reviewer = check_file_write(self._event("src/main.py", "aiwf-reviewer"))
        self.assertFalse(reviewer.allowed)
        self.assertIn("first implementation", reviewer.reason)
        (self.tmp / ".aiwf/records/implementation.json").write_text(json.dumps({
            "task_id": "TASK-001", "implementation_ref": "abc",
        }))
        self.assertTrue(check_file_write(self._event("src/main.py", "aiwf-reviewer")).allowed)

    def test_read_only_roles_are_blocked_by_default(self):
        from aiwf_core.hooks.common.scope_checker import check_file_write
        for role in ("aiwf-architect", "aiwf-explorer", "aiwf-critic"):
            self.assertFalse(check_file_write(self._event("src/main.py", role)).allowed)

    def test_architect_can_write_only_assigned_markdown_report(self):
        from aiwf_core.hooks.common.scope_checker import check_file_write
        state_path = self.tmp / ".aiwf/state/state.json"
        state = json.loads(state_path.read_text())
        state["active_task_id"] = ""
        state_path.write_text(json.dumps(state))
        allowed = check_file_write(self._event(
            "docs/architect/ARCH-20260711/code-reality.md", "aiwf-architect"
        ))
        denied = check_file_write(self._event(
            "docs/architect/ARCH-20260711/code-reality.json", "aiwf-architect"
        ))
        self.assertTrue(allowed.allowed, allowed.reason)
        self.assertFalse(denied.allowed)

    def test_machine_truth_stays_protected_under_permissive_policy(self):
        from aiwf_core.hooks.common.scope_checker import check_file_write
        self._policy(
            project_writes_require_active_task=False,
            first_implementation_requires_executor=False,
            tester_project_writes="allow_all",
        )
        result = check_file_write(self._event(".aiwf/state/state.json"))
        self.assertFalse(result.allowed)
        self.assertIn("mechanical truth", result.reason)

    def test_sync_preserves_tester_write_as_a_list(self):
        from aiwf_core.core.index_ops import sync_index

        task_doc = self.tmp / ".aiwf/tasks/TASK-001.md"
        task_doc.write_text(
            "---\n"
            "id: TASK-001\n"
            "type: task\n"
            "title: Test write policy\n"
            "contract_status: ready\n"
            "goal_id: GOAL-001\n"
            "plan_id: PLAN-001\n"
            "executor_required: true\n"
            "tester_required: true\n"
            "reviewer_required: true\n"
            "rollback_required: false\n"
            "tester_write:\n"
            "  - tests/**\n"
            "---\n",
            encoding="utf-8",
        )
        state_path = self.tmp / ".aiwf/state/state.json"
        state = json.loads(state_path.read_text())
        state["active_task_id"] = None
        state_path.write_text(json.dumps(state))

        result = sync_index(str(self.tmp))
        self.assertEqual(result["errors"], [])
        tasks = json.loads((self.tmp / ".aiwf/state/tasks.json").read_text())
        self.assertEqual(tasks["tasks"][0]["requirements"]["tester_write"], ["tests/**"])


if __name__ == "__main__":
    unittest.main()
