"""Configurable write-policy contracts."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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

    def _remove_active_task(self):
        tasks_path = self.tmp / ".aiwf/state/tasks.json"
        tasks = json.loads(tasks_path.read_text())
        for task in tasks.get("tasks", []):
            task["status"] = "ready"
            task.pop("phase", None)
        tasks_path.write_text(json.dumps(tasks))
        state_path = self.tmp / ".aiwf/state/state.json"
        state = json.loads(state_path.read_text())
        state["active_task_id"] = ""
        state["phase"] = "planning"
        state_path.write_text(json.dumps(state))

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
        record_path = self.tmp / ".aiwf/records/tasks/TASK-001.json"
        record_path.parent.mkdir(parents=True, exist_ok=True)
        record_path.write_text(json.dumps({
            "task_id": "TASK-001",
            "implementation": {"task_id": "TASK-001", "implementation_ref": "abc"},
            "testing": {"task_id": "TASK-001", "status": "missing"},
            "review": {"task_id": "TASK-001", "result": "unknown"},
            "fix_loop": {"status": "none"},
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

    def test_human_can_temporarily_allow_main_session_project_writes(self):
        from aiwf_core.hooks.common.scope_checker import check_file_write
        from aiwf_core.core.temporary_access import enable_temporary_ai_writes

        self._remove_active_task()
        denied = check_file_write(self._event("src/main.py"))
        self.assertFalse(denied.allowed)

        enable_temporary_ai_writes(self.tmp)
        allowed = check_file_write(self._event("src/main.py"))
        delegated = check_file_write(self._event("src/main.py", "general-purpose"))
        executor = check_file_write(self._event("src/main.py", "aiwf-executor"))
        read_only = check_file_write(self._event("src/main.py", "aiwf-critic"))
        marker = check_file_write(self._event(
            ".aiwf/runtime/internal/temporary-ai-writes.json"
        ))
        truth = check_file_write(self._event(".aiwf/state/state.json"))

        self.assertTrue(allowed.allowed, allowed.reason)
        self.assertTrue(delegated.allowed, delegated.reason)
        self.assertTrue(executor.allowed, executor.reason)
        self.assertIn("human enabled", allowed.reason)
        self.assertFalse(read_only.allowed)
        self.assertFalse(marker.allowed)
        self.assertIn("human", marker.reason)
        self.assertFalse(truth.allowed)

    def test_shell_project_writes_use_the_same_temporary_permission(self):
        from aiwf_core.core.event_model import NormalizedEvent
        from aiwf_core.core.temporary_access import enable_temporary_ai_writes
        from aiwf_core.hooks.common.scope_checker import check_bash

        self._remove_active_task()
        event = NormalizedEvent(
            cwd=str(self.tmp),
            tool_input={"command": "mv old.txt new.txt"},
            agent_type="main",
        )
        denied = check_bash(event)
        self.assertFalse(denied["allowed"])
        self.assertIn("active Task", denied["reason"])

        git_mv = NormalizedEvent(
            cwd=str(self.tmp),
            tool_input={"command": "git mv old.txt new.txt"},
            agent_type="main",
        )
        self.assertFalse(check_bash(git_mv)["allowed"])

        enable_temporary_ai_writes(self.tmp)
        self.assertTrue(check_bash(event)["allowed"])
        self.assertTrue(check_bash(git_mv)["allowed"])
        delegated = NormalizedEvent(
            cwd=str(self.tmp),
            tool_input={"command": "mv old.txt new.txt"},
            agent_type="general-purpose",
        )
        executor = NormalizedEvent(
            cwd=str(self.tmp),
            tool_input={"command": "mv old.txt new.txt"},
            agent_type="aiwf-executor",
        )
        self.assertTrue(check_bash(delegated)["allowed"])
        self.assertTrue(check_bash(executor)["allowed"])
        marker = NormalizedEvent(
            cwd=str(self.tmp),
            tool_input={"command": "rm .aiwf/runtime/internal/temporary-ai-writes.json"},
            agent_type="main",
        )
        self.assertFalse(check_bash(marker)["allowed"])

    def test_only_planner_can_write_governance_documents(self):
        from aiwf_core.core.event_model import NormalizedEvent
        from aiwf_core.hooks.common.scope_checker import check_bash, check_file_write

        self._remove_active_task()
        direct = check_file_write(self._event(
            ".aiwf/tasks/TASK-999.md", "general-purpose",
        ))
        shell = check_bash(NormalizedEvent(
            cwd=str(self.tmp),
            tool_input={"command": "printf draft > .aiwf/tasks/TASK-999.md"},
            agent_type="general-purpose",
        ))

        self.assertFalse(direct.allowed)
        self.assertIn("owned by Planner", direct.reason)
        self.assertFalse(shell["allowed"])
        self.assertIn("owned by Planner", shell["reason"])

    def test_tui_reads_memory_and_shows_temporary_write_state(self):
        from aiwf_core.aiwf_ui import _build_status_bar, load_all
        from aiwf_core.core.temporary_access import enable_temporary_ai_writes
        from aiwf_core.tui_actions import memory_paths

        self._remove_active_task()
        enable_temporary_ai_writes(self.tmp)
        paths = [path.name for path in memory_paths(self.tmp)]
        data = load_all(self.tmp)

        self.assertIn("MEMORY.md", paths)
        self.assertIn("project-facts.md", paths)
        self.assertTrue(data["temporary_ai_writes"])
        self.assertIn("临时AI写入=开", _build_status_bar(data))

        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT)
        status = subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", "status", "--prompt"],
            cwd=self.tmp,
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertTrue(status.stdout.startswith("Do now: complete the user's current small"))
        self.assertIn("Do not create a Task", status.stdout)

    def test_tui_git_graph_delegates_to_tig(self):
        from aiwf_core.tui_actions import open_git_graph

        with patch("aiwf_core.tui_actions.shutil.which", return_value="/usr/local/bin/tig"), patch(
            "aiwf_core.tui_actions._run_external",
            return_value=SimpleNamespace(returncode=0),
        ) as run:
            self.assertEqual(open_git_graph(self.tmp, "summary"), "")
        run.assert_called_once_with(
            [
                "/usr/local/bin/tig",
                "--branches",
                "--remotes",
                "--simplify-by-decoration",
            ],
            self.tmp,
        )

        with patch("aiwf_core.tui_actions.shutil.which", return_value="/usr/local/bin/tig"), patch(
            "aiwf_core.tui_actions._run_external",
            return_value=SimpleNamespace(returncode=0),
        ) as run:
            self.assertEqual(open_git_graph(self.tmp, "detailed"), "")
        run.assert_called_once_with(
            ["/usr/local/bin/tig", "--branches", "--remotes"], self.tmp,
        )

    def test_tui_wraps_cjk_text_without_dropping_characters(self):
        from aiwf_core.tui_actions import _display_width, wrap_display_lines

        source = "详细：显示 branch 中的全部正常 commits"
        wrapped = wrap_display_lines([source], 12)

        self.assertEqual("".join(wrapped), source)
        self.assertGreater(len(wrapped), 1)
        self.assertTrue(all(_display_width(line) <= 12 for line in wrapped))

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
        tasks_path = self.tmp / ".aiwf/state/tasks.json"
        tasks = json.loads(tasks_path.read_text())
        tasks["tasks"][0]["status"] = "ready"
        tasks["tasks"][0].pop("phase", None)
        tasks["tasks"][0].pop("worktree_path", None)
        tasks_path.write_text(json.dumps(tasks))
        state_path = self.tmp / ".aiwf/state/state.json"
        state = json.loads(state_path.read_text())
        state.pop("active_task_id", None)
        state.pop("phase", None)
        state_path.write_text(json.dumps(state))

        result = sync_index(str(self.tmp))
        self.assertEqual(result["errors"], [])
        tasks = json.loads((self.tmp / ".aiwf/state/tasks.json").read_text())
        self.assertEqual(tasks["tasks"][0]["requirements"]["tester_write"], ["tests/**"])

    def test_sync_does_not_register_an_incomplete_task_document(self):
        from aiwf_core.core.index_ops import sync_index

        draft = self.tmp / ".aiwf/tasks/TASK-DRAFT.md"
        draft.write_text(
            "---\n"
            "id: TASK-DRAFT\n"
            "type: task\n"
            "title: Incomplete draft\n"
            "contract_status: ready\n"
            "goal_id: ''\n"
            "plan_id: PLAN-001\n"
            "---\n",
            encoding="utf-8",
        )

        result = sync_index(str(self.tmp))
        tasks = json.loads((self.tmp / ".aiwf/state/tasks.json").read_text())

        self.assertTrue(any("goal_id is empty" in item for item in result["errors"]))
        self.assertNotIn("TASK-DRAFT", {task.get("id") for task in tasks["tasks"]})

    def test_sync_rebuilds_complete_plan_task_rollup(self):
        from aiwf_core.core.index_ops import sync_index

        self._remove_active_task()
        task_doc = self.tmp / ".aiwf/tasks/TASK-001.md"
        task_doc.write_text(
            "---\n"
            "id: TASK-001\n"
            "type: task\n"
            "title: Completed task\n"
            "contract_status: closed\n"
            "goal_id: GOAL-001\n"
            "plan_id: PLAN-001\n"
            "executor_required: false\n"
            "tester_required: false\n"
            "reviewer_required: false\n"
            "rollback_required: false\n"
            "tester_write: []\n"
            "dependencies: []\n"
            "---\n",
            encoding="utf-8",
        )
        plans_path = self.tmp / ".aiwf/state/plans.json"
        plans_path.write_text(json.dumps({
            "plans": [{
                "id": "PLAN-001",
                "goal_id": "GOAL-001",
                "status": "open",
                "task_ids": ["TASK-001"],
                "task_status": {"TASK-001": "ready"},
                "closed_task_ids": [],
                "remaining_task_ids": ["TASK-001"],
                "task_rollup": {
                    "summary": "0/1 tasks closed under this plan.",
                    "closed_count": 0,
                    "total_count": 1,
                    "remaining_task_ids": ["TASK-001"],
                },
            }],
        }))

        sync_index(str(self.tmp))
        plan = json.loads(plans_path.read_text())["plans"][0]

        self.assertEqual(plan["task_status"], {"TASK-001": "closed"})
        self.assertEqual(plan["closed_task_ids"], ["TASK-001"])
        self.assertEqual(plan["remaining_task_ids"], [])
        self.assertEqual(plan["task_rollup"]["remaining_task_ids"], [])

if __name__ == "__main__":
    unittest.main()
