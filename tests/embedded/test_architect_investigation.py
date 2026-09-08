import io
import json
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from tests.embedded import test_experimenter_contract as fixtures
from aiwf_core.core.experiment_records import (
    open_experiment, start_experiment, record_experiment, finish_experiment,
    experiment_role, load_experiment,
)
from aiwf_core.core.event_model import NormalizedEvent
from aiwf_core.hooks.common.scope_checker import check_file_write, check_bash


class TestArchitectInvestigation(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.TestExperimenterContract()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.root = self.fixture.root
        self.repo = Path(__file__).resolve().parents[2]

    def test_task_planning_has_no_git_binding_or_runtime_side_effect(self):
        task = {**self.fixture.task, "status": "ready", "git_origin_ref": ""}
        self.fixture._write_json(".aiwf/state/tasks.json", {"tasks": [task]})
        with patch("aiwf_core.core.experiment_records._git") as git:
            with self.assertRaisesRegex(ValueError, "plan the experiment in Task.md"):
                open_experiment(str(self.root), "EXP-PLAN", "A planned question", task_id="TASK-001")
            git.assert_not_called()
        self.assertEqual(load_experiment(self.root, "EXP-PLAN"), {})

    def test_task_pre_subject_stays_on_activation_baseline(self):
        (self.root / "later.txt").write_text("later commit")
        self.fixture._git("add", "later.txt")
        self.fixture._git("commit", "-m", "later")
        exp = open_experiment(str(self.root), "EXP-TASK", "Task question", task_id="TASK-001")
        self.assertEqual(exp["subject_ref"], self.fixture.origin)
        self.assertEqual(experiment_role(exp), "aiwf-experimenter")
        task = {**self.fixture.task, "git_origin_ref": self.fixture._git("rev-parse", "HEAD")}
        self.fixture._write_json(".aiwf/state/tasks.json", {"tasks": [task]})
        with self.assertRaisesRegex(ValueError, "stale"):
            start_experiment(str(self.root), "EXP-TASK")

    def test_plan_investigation_writes_only_disposable_project_and_keeps_assets(self):
        from aiwf_core.commands.flow import _print_plan_experiment_prompt
        from aiwf_core.core.experiment_assets import experiment_asset_bytes

        exp = open_experiment(str(self.root), "EXP-ARCH", "Which mechanism works?", plan_id="PLAN-001")
        self.assertEqual(experiment_role(exp), "aiwf-architect")
        output = io.StringIO()
        with redirect_stdout(output):
            _print_plan_experiment_prompt(exp)
        self.assertIn("aiwf-architect", output.getvalue())
        self.assertNotIn("aiwf-experimenter", output.getvalue())
        worktree = Path(start_experiment(str(self.root), "EXP-ARCH")["worktree_path"])
        def event(role, path, tool="Write"):
            value = {"file_path": str(path)} if tool == "Write" else {"command": f"touch {path}"}
            return NormalizedEvent(engine="claude", event_type="pre_tool_use", tool_name=tool,
                                   cwd=str(worktree), agent_type=role, tool_input=value)
        self.assertTrue(check_file_write(event("aiwf-architect", worktree / "prototype.py")).allowed)
        self.assertFalse(check_file_write(event("aiwf-experimenter", worktree / "prototype.py")).allowed)
        self.assertFalse(check_file_write(event("aiwf-architect", self.root / "app.txt")).allowed)
        self.assertFalse(check_file_write(event("aiwf-architect", self.root / ".aiwf/state/state.json")).allowed)
        self.assertEqual(check_bash(event("aiwf-architect", worktree / "probe.py", "Bash"))["decision"], "allow")
        self.assertEqual(check_bash(event("aiwf-architect", self.root / "app.txt", "Bash"))["decision"], "deny")
        (worktree / "prototype.py").write_text("print('observation')\n")
        record_experiment(str(worktree), "EXP-ARCH", "supported", "Mechanism observed",
                          observations=["real output"], promotion_candidates=["prototype.py"])
        finish_experiment(str(self.root), "EXP-ARCH")
        self.assertIn(b"observation", experiment_asset_bytes(self.root, "EXP-ARCH", "prototype.py"))
        self.assertFalse((self.root / "prototype.py").exists())

    def test_installed_dispatch_and_completion_require_architect_evidence(self):
        self._check_installed_dispatch("claude")

    def test_codex_generic_child_uses_plan_architect_dispatch(self):
        self._check_installed_dispatch("codex")

    def _check_installed_dispatch(self, engine):
        from aiwf_core.install_claude import _write_scripts
        from aiwf_core.core.agent_runtime import bind_dispatch_agent

        with patch("aiwf_core.install_claude._project_root", return_value=self.root):
            _write_scripts()
        open_experiment(str(self.root), "EXP-ARCH", "Which mechanism works?", plan_id="PLAN-001")
        log = self.root / ".aiwf/runtime/internal/skill-loads.jsonl"
        log.write_text(json.dumps({"skill": "aiwf-architect", "session_id": "parent"}) + "\n"
                       + json.dumps({"skill": "aiwf-experiment", "session_id": "parent"}) + "\n")
        def run(script, event):
            result = subprocess.run([sys.executable, str(self.root / "scripts" / script)],
                cwd=self.root, env={**os.environ, "PYTHONPATH": str(self.repo), "AIWF_HOOK_ENGINE": engine},
                input=json.dumps(event), text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout) if result.stdout.strip() else {}
        event = {"session_id": "parent", "cwd": str(self.root), "tool_name": "Agent",
                 "hook_event_name": "PreToolUse", "tool_input": {"subagent_type": "aiwf-experimenter", "prompt": "EXP-ARCH"}}
        event["tool_input"]["subagent_type"] = "aiwf-architect"
        self.assertEqual(run("aiwf_agent_gate.py", event)["hookSpecificOutput"]["permissionDecision"], "deny")
        worktree = Path(start_experiment(str(self.root), "EXP-ARCH")["worktree_path"])
        event["tool_input"]["subagent_type"] = "aiwf-experimenter"
        denied = run("aiwf_agent_gate.py", event)
        self.assertEqual(denied["hookSpecificOutput"]["permissionDecision"], "deny")
        event["tool_input"]["subagent_type"] = "aiwf-architect"
        if engine == "codex":
            event["tool_name"] = "spawn_agent"
            event["tool_input"].pop("subagent_type")
        allowed = run("aiwf_agent_gate.py", event)
        self.assertIn(str(worktree), allowed["hookSpecificOutput"]["updatedInput"]["prompt"])
        bind_dispatch_agent(self.root, "aiwf-architect", "child", task_id="PLAN-001", session_id="parent")
        stop = {"hook_event_name": "SubagentStop", "session_id": "parent", "cwd": str(worktree),
                "agent_type": "default" if engine == "codex" else "aiwf-architect",
                "agent_id": "child", "last_assistant_message": "Investigation done"}
        self.assertEqual(run("aiwf_agent_log.py", stop)["decision"], "block")
        recorded = subprocess.run(
            ["bash", str(self.repo / "bin/aiwf"), "experiment", "record", "EXP-ARCH",
             "--conclusion", "supported", "--summary", "Measured", "--observation", "real output"],
            cwd=worktree, env={**os.environ, "PYTHONPATH": str(self.repo)}, text=True, capture_output=True,
        )
        self.assertEqual(recorded.returncode, 0, recorded.stderr)
        self.assertNotEqual(run("aiwf_agent_log.py", stop).get("decision"), "block")
        self.assertFalse((self.root / ".aiwf/records/tasks/PLAN-001.json").exists())


if __name__ == "__main__":
    unittest.main()
