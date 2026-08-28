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
        instruction = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("## Codex Agent Dispatch", instruction)
        self.assertIn("only valid next role from Task state", instruction)
        self.assertIn("Never imitate a required", instruction)
        self.assertTrue((self.root / ".agents/skills/aiwf-planner/SKILL.md").exists())
        experimenter = (self.root / ".codex/agents/aiwf-experimenter.toml").read_text(encoding="utf-8")
        self.assertIn('name = "aiwf-experimenter"', experimenter)
        self.assertIn("developer_instructions = '''", experimenter)
        self.assertIn("disposable full-project worktree", experimenter)
        self.assertIn("concrete `--observation`", experimenter)
        reviewer = (self.root / ".codex/agents/aiwf-reviewer.toml").read_text(
            encoding="utf-8"
        )
        self.assertIn('sandbox_mode = "workspace-write"', reviewer)
        self.assertIn("You judge stable reality", reviewer)
        self.assertIn("needs_experiment", reviewer)
        self.assertNotIn("Claude Code", experimenter)
        self.assertFalse((self.root / ".codex/agents/aiwf-tester.toml").exists())
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
        self.assertEqual(hooks["hooks"]["SubagentStart"][-1]["matcher"], "*")
        self.assertEqual(hooks["hooks"]["SubagentStop"][-1]["matcher"], "*")
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

    def test_codex_posttool_does_not_race_subagent_start(self):
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
                "tool_response": {"status": "started", "agent_id": "child-pending"},
            }),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        dispatch = (
            self.root / ".aiwf/runtime/internal/agent-dispatch.jsonl"
        ).read_text(encoding="utf-8")
        self.assertNotIn("spawn_return_without_subagent_start", dispatch)
        self.assertNotIn('"status": "cancelled"', dispatch)
        self.assertIn('"status": "bound"', dispatch)
        self.assertIn('"agent_id": "child-pending"', dispatch)

    def test_codex_explicit_spawn_failure_releases_dispatch(self):
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
        dispatched = _run(
            [sys.executable, str(launcher), "aiwf_agent_gate.py"],
            self.root,
            input_text=json.dumps(event),
        )
        self.assertEqual(dispatched.returncode, 0, dispatched.stderr)

        failed = _run(
            [sys.executable, str(launcher), "aiwf_agent_log.py"],
            self.root,
            input_text=json.dumps({
                **event,
                "hook_event_name": "PostToolUse",
                "tool_response": {"error": "custom agent could not start"},
            }),
        )
        self.assertEqual(failed.returncode, 0, failed.stderr)
        note = json.loads(failed.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("dispatch failed", note)
        dispatch = (
            self.root / ".aiwf/runtime/internal/agent-dispatch.jsonl"
        ).read_text(encoding="utf-8")
        self.assertIn('"status": "cancelled"', dispatch)
        self.assertIn('"completion_source": "agent_failure"', dispatch)

    def test_codex_binds_generic_spawn_to_the_unique_task_role(self):
        self.install()
        self.configure_active_task()
        launcher = self.root / "scripts/aiwf_codex_hook.py"
        result = _run(
            [sys.executable, str(launcher), "aiwf_agent_gate.py"],
            self.root,
            input_text=json.dumps({
                "hook_event_name": "PreToolUse",
                "session_id": "parent-generic",
                "cwd": str(self.root),
                "tool_name": "spawn_agent",
                "tool_input": {
                    "message": "Implement TASK-A",
                },
            }),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        updated = json.loads(result.stdout)["hookSpecificOutput"]["updatedInput"]
        self.assertNotIn("agent_type", updated)
        self.assertIn("bound this independent child as aiwf-executor", updated["message"])
        self.assertIn("# AIWF Executor", updated["message"])
        dispatch_path = self.root / ".aiwf/runtime/internal/agent-dispatch.jsonl"
        before_start = dispatch_path.read_text(encoding="utf-8")
        self.assertIn('"status": "started"', before_start)
        self.assertIn('"session_id": "parent-generic"', before_start)

        started = _run(
            [sys.executable, str(launcher), "aiwf_agent_log.py"],
            self.root,
            input_text=json.dumps({
                "hook_event_name": "SubagentStart",
                "session_id": "parent-generic",
                "cwd": str(self.root),
                "agent_id": "child-generic",
                "agent_type": "default",
            }),
        )
        self.assertEqual(started.returncode, 0, started.stderr)
        self.assertTrue(started.stdout, before_start)
        context = json.loads(started.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Task TASK-A", context)
        dispatch = dispatch_path.read_text(encoding="utf-8")
        self.assertIn('"subagent_type": "aiwf-executor"', dispatch)
        self.assertIn('"agent_id": "child-generic"', dispatch)

        stopped = _run(
            [sys.executable, str(launcher), "aiwf_agent_log.py"],
            self.root,
            input_text=json.dumps({
                "hook_event_name": "SubagentStop",
                "session_id": "parent-generic",
                "cwd": str(self.root),
                "agent_id": "child-generic",
                "agent_type": "default",
                "last_assistant_message": "TASK-A implementation is complete",
            }),
        )
        self.assertEqual(stopped.returncode, 0, stopped.stderr)
        blocker = json.loads(stopped.stdout)
        self.assertEqual(blocker["decision"], "block")
        self.assertIn("no fresh implementation record", blocker["reason"])

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
