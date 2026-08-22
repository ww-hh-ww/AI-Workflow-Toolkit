"""Contracts for the native Codex adapter."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _run(command, cwd, *, input_text="", env_update=None):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    env.update(env_update or {})
    return subprocess.run(
        command,
        cwd=str(cwd),
        env=env,
        input=input_text,
        capture_output=True,
        text=True,
        timeout=30,
    )


class TestCodexInstall(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="aiwf_codex_"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def install(self):
        result = _run(
            [sys.executable, "-m", "aiwf_core.cli", "install", "codex", "--force"],
            self.root,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def configure_active_task(self):
        worktree = self.root / ".codex/worktrees/plan-a"
        worktree.mkdir(parents=True)
        task_doc = self.root / ".aiwf/tasks/TASK-A.md"
        task_doc.parent.mkdir(parents=True, exist_ok=True)
        task_doc.write_text("# TASK-A\n", encoding="utf-8")
        tasks = {
            "tasks": [{
                "id": "TASK-A",
                "status": "active",
                "phase": "implementing",
                "plan_id": "PLAN-A",
                "doc_path": ".aiwf/tasks/TASK-A.md",
                "worktree_path": str(worktree),
                "requirements": {
                    "executor_required": True,
                    "tester_required": True,
                    "reviewer_required": True,
                },
            }],
        }
        (self.root / ".aiwf/state/tasks.json").write_text(
            json.dumps(tasks), encoding="utf-8",
        )
        return worktree

    def test_installs_native_codex_skills_agents_and_hooks(self):
        result = self.install()

        self.assertIn("Start Codex: codex", result.stdout)
        self.assertIn("$aiwf-planner", result.stdout)
        self.assertTrue((self.root / "AGENTS.md").exists())
        self.assertTrue((self.root / ".agents/skills/aiwf-planner/SKILL.md").exists())
        tester = (self.root / ".codex/agents/aiwf-tester.toml").read_text(encoding="utf-8")
        self.assertIn('name = "aiwf-tester"', tester)
        self.assertIn("developer_instructions = '''", tester)
        self.assertIn("Build a failure model", tester)
        self.assertIn("independent probes", tester)
        reviewer = (self.root / ".codex/agents/aiwf-reviewer.toml").read_text(
            encoding="utf-8"
        )
        self.assertIn('sandbox_mode = "workspace-write"', reviewer)
        self.assertIn("Independently judge whether", reviewer)
        self.assertIn("implement, test as the Tester", reviewer)
        self.assertNotIn("Claude Code", tester)
        critic_skill = (
            self.root / ".agents/skills/aiwf-critic/SKILL.md"
        ).read_text(encoding="utf-8")
        lifecycle = (
            self.root / ".agents/skills/aiwf-planner/references/lifecycle.md"
        ).read_text(encoding="utf-8")
        self.assertNotIn("Agent({", critic_skill)
        self.assertIn("Dispatch the `aiwf-critic` custom agent", critic_skill)
        self.assertNotIn("## SendMessage", lifecycle)
        self.assertIn("## Resume an existing agent", lifecycle)
        hooks = json.loads((self.root / ".codex/hooks.json").read_text(encoding="utf-8"))
        for event in (
            "UserPromptSubmit", "PreToolUse", "PostToolUse",
            "SubagentStart", "SubagentStop", "Stop",
        ):
            self.assertTrue(hooks["hooks"][event])
        encoded = json.dumps(hooks)
        self.assertIn("apply_patch|Edit|Write", encoded)
        self.assertIn("aiwf_codex_hook.py", encoded)
        self.assertFalse((self.root / ".claude/settings.json").exists())

        command = hooks["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
        hook_result = subprocess.run(
            command,
            cwd=str(self.root),
            env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT)},
            input=json.dumps({
                "hook_event_name": "UserPromptSubmit",
                "session_id": "codex-parent",
                "cwd": str(self.root),
            }),
            capture_output=True,
            text=True,
            timeout=30,
            shell=True,
        )
        self.assertEqual(hook_result.returncode, 0, hook_result.stderr)
        self.assertIn("aiwf status --prompt", hook_result.stdout)

    def test_reinstall_preserves_unrelated_codex_hooks(self):
        hooks_path = self.root / ".codex/hooks.json"
        hooks_path.parent.mkdir(parents=True)
        hooks_path.write_text(json.dumps({
            "project_doc_fallback_filenames": ["TEAM.md"],
            "hooks": {
                "PreToolUse": [{
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": "user-check"}],
                }],
            },
        }), encoding="utf-8")

        self.install()
        hooks = json.loads(hooks_path.read_text(encoding="utf-8"))
        self.assertEqual(hooks["project_doc_fallback_filenames"], ["TEAM.md"])
        self.assertIn("user-check", json.dumps(hooks["hooks"]["PreToolUse"]))

    def test_codex_agent_dispatch_uses_custom_role_without_skill_log(self):
        self.install()
        worktree = self.configure_active_task()
        launcher = self.root / "scripts/aiwf_codex_hook.py"
        pretool = {
            "hook_event_name": "PreToolUse",
            "session_id": "parent-1",
            "cwd": str(self.root),
            "tool_name": "Agent",
            "tool_input": {
                "agent_type": "aiwf-executor",
                "message": "Implement TASK-A",
            },
        }
        result = _run(
            [sys.executable, str(launcher), "aiwf_agent_gate.py"],
            self.root,
            input_text=json.dumps(pretool),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        response = json.loads(result.stdout)
        updated = response["hookSpecificOutput"]["updatedInput"]
        self.assertEqual(updated["agent_type"], "aiwf-executor")
        self.assertIn("Task: TASK-A", updated["message"])
        self.assertIn(str(worktree), updated["message"])

        started = {
            "hook_event_name": "SubagentStart",
            "session_id": "parent-1",
            "cwd": str(self.root),
            "agent_id": "child-1",
            "agent_type": "aiwf-executor",
        }
        result = _run(
            [sys.executable, str(launcher), "aiwf_agent_log.py"],
            self.root,
            input_text=json.dumps(started),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Task TASK-A", context)
        self.assertIn("aiwf task proof TASK-A", context)

        posttool = {
            **pretool,
            "hook_event_name": "PostToolUse",
            "tool_response": {"agent_id": "child-1"},
        }
        result = _run(
            [sys.executable, str(launcher), "aiwf_agent_log.py"],
            self.root,
            input_text=json.dumps(posttool),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        dispatch = (
            self.root / ".aiwf/runtime/internal/agent-dispatch.jsonl"
        ).read_text(encoding="utf-8")
        self.assertIn('"agent_id": "child-1"', dispatch)
        from aiwf_core.commands.state_commands import _require_role_dispatch

        self.assertEqual(
            _require_role_dispatch(self.root, "executor", "TASK-A"),
            "TASK-A",
        )

    def test_codex_agent_return_without_subagent_start_releases_dispatch(self):
        self.install()
        self.configure_active_task()
        launcher = self.root / "scripts/aiwf_codex_hook.py"
        event = {
            "hook_event_name": "PreToolUse",
            "session_id": "parent-failed",
            "cwd": str(self.root),
            "tool_name": "Agent",
            "tool_input": {
                "agent_type": "aiwf-executor",
                "message": "Implement TASK-A",
            },
        }
        result = _run(
            [sys.executable, str(launcher), "aiwf_agent_gate.py"],
            self.root,
            input_text=json.dumps(event),
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        result = _run(
            [sys.executable, str(launcher), "aiwf_agent_log.py"],
            self.root,
            input_text=json.dumps({
                **event,
                "hook_event_name": "PostToolUse",
                "tool_response": {"error": "agent did not start"},
            }),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("slot was released", context)
        dispatch = (
            self.root / ".aiwf/runtime/internal/agent-dispatch.jsonl"
        ).read_text(encoding="utf-8")
        self.assertIn(
            '"completion_source": "spawn_return_without_subagent_start"',
            dispatch,
        )
        self.assertIn('"status": "cancelled"', dispatch)

    def test_status_and_doctor_recognize_codex_install(self):
        self.install()
        status = _run(
            [sys.executable, "-m", "aiwf_core.cli", "status", "--prompt"],
            self.root,
        )
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertNotIn("No embedded AIWF installation found", status.stdout)
        self.assertIn("Required skills: $aiwf-planner", status.stdout)
        self.assertNotIn("Required skills: /aiwf-planner", status.stdout)
        doctor = _run(
            [sys.executable, "-m", "aiwf_core.cli", "doctor", "--host", "codex"],
            self.root,
        )
        self.assertEqual(doctor.returncode, 0, doctor.stderr)
        self.assertIn("AIWF Doctor - Codex", doctor.stdout)

    def test_native_codex_session_wins_when_adapters_coexist(self):
        self.install()
        plugin = self.root / "scripts/aiwf_opencode_plugin.js"
        plugin.write_text("// user also installed OpenCode\n", encoding="utf-8")

        status = _run(
            [sys.executable, "-m", "aiwf_core.cli", "status", "--prompt"],
            self.root,
            env_update={"CODEX_SESSION_ID": "codex-session"},
        )
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("Required skills: $aiwf-planner", status.stdout)


if __name__ == "__main__":
    unittest.main()
