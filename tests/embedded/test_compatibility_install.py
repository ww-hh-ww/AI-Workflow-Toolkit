"""Contracts for the additive Windows and OpenCode compatibility layers."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _run(command, cwd):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    return subprocess.run(
        command, cwd=str(cwd), env=env, capture_output=True, text=True, timeout=20,
    )


class TestOpenCodeInstall(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="aiwf_opencode_"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def install(self):
        result = _run(
            [sys.executable, "-m", "aiwf_core.cli", "install", "opencode", "--force"],
            self.root,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_installs_native_assets_without_claude_settings(self):
        result = _run(
            [sys.executable, "-m", "aiwf_core.cli", "install", "opencode", "--force"],
            self.root,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("initialize Git and create the initial commit", result.stdout)
        self.assertTrue((self.root / "AGENTS.md").exists())
        self.assertTrue((self.root / "opencode.json").exists())
        self.assertTrue((self.root / ".opencode/plugins/aiwf.js").exists())
        self.assertTrue((self.root / ".opencode/agents/aiwf-planner.md").exists())
        self.assertTrue((self.root / ".opencode/agents/aiwf-executor.md").exists())
        self.assertTrue((self.root / ".opencode/skills/aiwf-planner/SKILL.md").exists())
        self.assertTrue((self.root / ".opencode/commands/aiwf-planner.md").exists())
        self.assertFalse((self.root / ".claude/settings.json").exists())

    def test_status_recognizes_opencode_only_install(self):
        self.install()
        result = _run(
            [sys.executable, "-m", "aiwf_core.cli", "status", "--prompt"],
            self.root,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("No embedded AIWF installation found", result.stdout)

    def test_open_code_prompts_use_open_code_capabilities(self):
        self.install()
        all_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (self.root / ".opencode").rglob("*.md")
        )
        self.assertNotIn("Claude Code", all_text)
        self.assertNotIn("SendMessage", all_text)
        self.assertNotIn("Agent({subagent_type", all_text)
        planner = (self.root / ".opencode/agents/aiwf-planner.md").read_text(encoding="utf-8")
        executor = (self.root / ".opencode/agents/aiwf-executor.md").read_text(encoding="utf-8")
        reviewer = (self.root / ".opencode/agents/aiwf-reviewer.md").read_text(encoding="utf-8")
        architect = (self.root / ".opencode/agents/aiwf-architect.md").read_text(encoding="utf-8")
        self.assertIn("mode: primary", planner)
        self.assertIn("mode: subagent", executor)
        self.assertIn("  edit: allow", executor)
        self.assertIn("  edit: allow", architect)
        self.assertIn("  edit: deny", reviewer)

    def test_plugin_covers_native_tool_and_compaction_events(self):
        self.install()
        plugin = (self.root / ".opencode/plugins/aiwf.js").read_text(encoding="utf-8")
        self.assertNotIn(str(self.root), plugin)
        self.assertTrue((self.root / ".aiwf/runtime/internal/python-command.json").exists())
        self.assertIn('"chat.message"', plugin)
        self.assertIn('"shell.env"', plugin)
        self.assertIn('output.env.AIWF_HOST = "opencode"', plugin)
        self.assertIn('"tool.execute.before"', plugin)
        self.assertIn('"tool.execute.after"', plugin)
        self.assertIn('"experimental.session.compacting"', plugin)
        self.assertIn("prepareTaskRole", plugin)
        self.assertIn("sessionAssignments", plugin)
        self.assertNotIn("must run from its Plan worktree", plugin)
        self.assertIn("must run in the foreground", plugin)
        self.assertIn("sessionAgents", plugin)
        self.assertIn("client.session.messages", plugin)
        self.assertIn("const cwd = directory || worktree", plugin)
        self.assertIn("OpenCode child task_id", plugin)
        self.assertIn("Move to", plugin)
        self.assertIn("aiwf_status.py", plugin)
        self.assertIn('result.skill = result.name', plugin)
        lifecycle = (
            self.root / ".opencode/skills/aiwf-planner/references/lifecycle.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Keep planning decisions in the control-root Planner session", lifecycle)
        self.assertIn("Dispatch the named\nOpenCode subagent there", lifecycle)
        self.assertIn("routes its project tools to the assigned Plan worktree", lifecycle)
        self.assertNotIn("start or attach an OpenCode session", lifecycle)
        self.assertIn("`task_id` set to its Task session ID", lifecycle)
        self.assertNotIn("Planner does not switch worktrees", lifecycle)
        node = shutil.which("node")
        if node:
            checked = _run([node, "--check", str(self.root / ".opencode/plugins/aiwf.js")], self.root)
            self.assertEqual(checked.returncode, 0, checked.stderr)

    def test_open_code_events_keep_host_identity(self):
        from aiwf_core.adapters.claude.normalize_event import normalize

        with patch.dict(os.environ, {"AIWF_HOOK_ENGINE": "opencode"}):
            event = normalize({
                "hook_event_name": "PreToolUse",
                "session_id": "session-1",
                "cwd": str(self.root),
                "tool_name": "Write",
                "tool_input": {"file_path": "src/example.py"},
                "agent_type": "aiwf-executor",
            })
        self.assertEqual(event.engine, "opencode")
        self.assertEqual(event.agent_type, "aiwf-executor")

    def test_reinstall_preserves_user_config(self):
        (self.root / "opencode.json").write_text(
            json.dumps({"default_agent": "build", "share": "disabled"}), encoding="utf-8",
        )
        self.install()
        config = json.loads((self.root / "opencode.json").read_text(encoding="utf-8"))
        self.assertEqual(config["default_agent"], "build")
        self.assertEqual(config["share"], "disabled")

    def test_claude_and_open_code_adapters_can_coexist(self):
        self.install()
        result = _run(
            [sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
            self.root,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / ".opencode/plugins/aiwf.js").exists())
        self.assertTrue((self.root / ".claude/settings.json").exists())
        self.assertTrue((self.root / "AGENTS.md").exists())
        self.assertTrue((self.root / "CLAUDE.md").exists())
        doctor = _run(
            [sys.executable, "-m", "aiwf_core.cli", "doctor", "--host", "opencode"],
            self.root,
        )
        self.assertEqual(doctor.returncode, 0, doctor.stderr)
        self.assertIn("AIWF Doctor - OpenCode - healthy", doctor.stdout)

    def test_doctor_recognizes_open_code_install(self):
        self.install()
        result = _run([sys.executable, "-m", "aiwf_core.cli", "doctor"], self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("OpenCode", result.stdout)
        self.assertIn("tool.execute.before", result.stdout)

    def test_open_code_task_return_reports_a_missing_role_record(self):
        self.install()
        tasks = self.root / ".aiwf/state/tasks.json"
        tasks.write_text(json.dumps({"tasks": [{
            "id": "TASK-001",
            "status": "active",
            "phase": "implementing",
            "worktree_path": str(self.root),
            "requirements": {
                "executor_required": True,
                "tester_required": True,
                "reviewer_required": True,
            },
        }]}), encoding="utf-8")
        runtime = self.root / ".aiwf/runtime/internal"
        runtime.mkdir(parents=True, exist_ok=True)
        (runtime / "agent-dispatch.jsonl").write_text(json.dumps({
            "timestamp": "2026-07-21T00:00:00+00:00",
            "subagent_type": "aiwf-executor",
            "task_id": "TASK-001",
            "session_id": "parent-session",
            "worktree_path": str(self.root),
            "status": "started",
        }) + "\n", encoding="utf-8")
        event = json.dumps({
            "hook_event_name": "PostToolUse",
            "session_id": "parent-session",
            "cwd": str(self.root),
            "tool_name": "Task",
            "tool_input": {
                "subagent_type": "aiwf-executor",
                "prompt": "Implement TASK-001",
            },
            "tool_response": {
                "metadata": {"sessionId": "child-session"},
                "output": "TASK-001 implementation complete",
            },
        })
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        env["AIWF_HOOK_ENGINE"] = "opencode"
        result = subprocess.run(
            [sys.executable, str(self.root / "scripts/aiwf_agent_log.py")],
            cwd=self.root,
            env=env,
            input=event,
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        note = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("no fresh implementation record", note)
        self.assertIn("same OpenCode child", note)
        dispatches = [
            json.loads(line)
            for line in (runtime / "agent-dispatch.jsonl").read_text(
                encoding="utf-8"
            ).splitlines()
        ]
        self.assertTrue(any(
            item.get("status") == "bound"
            and item.get("agent_id") == "child-session"
            for item in dispatches
        ))
        self.assertTrue(any(
            item.get("status") == "completed"
            and item.get("agent_id") == "child-session"
            and item.get("completion_source") == "agent_return"
            for item in dispatches
        ))

    def test_status_prompt_uses_opencode_child_continuation(self):
        self.install()
        runtime = self.root / ".aiwf/runtime/internal"
        runtime.mkdir(parents=True, exist_ok=True)
        entries = [
            {
                "timestamp": "2026-07-21T00:00:00+00:00",
                "subagent_type": "aiwf-executor",
                "task_id": "TASK-001",
                "session_id": "parent-session",
                "worktree_path": str(self.root),
                "status": "started",
            },
            {
                "timestamp": "2026-07-21T00:01:00+00:00",
                "subagent_type": "aiwf-executor",
                "task_id": "TASK-001",
                "session_id": "parent-session",
                "worktree_path": str(self.root),
                "agent_id": "child-session",
                "status": "bound",
            },
            {
                "timestamp": "2026-07-21T00:02:00+00:00",
                "subagent_type": "aiwf-executor",
                "task_id": "TASK-001",
                "session_id": "parent-session",
                "worktree_path": str(self.root),
                "agent_id": "child-session",
                "status": "completed",
            },
        ]
        (runtime / "agent-dispatch.jsonl").write_text(
            "\n".join(json.dumps(item) for item in entries) + "\n",
            encoding="utf-8",
        )
        from aiwf_core.commands.flow import _task_next

        task = {
            "id": "TASK-001",
            "requirements": {"executor_required": True},
        }
        role, action = _task_next(task, {}, self.root, host="opencode")
        self.assertEqual(role, "Executor")
        self.assertIn("task_id child-session", action)
        self.assertNotIn("SendMessage", action)
        self.assertNotIn("Claude session", action)


class TestWindowsCompatibility(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "native Windows contract")
    def test_native_windows_claude_install_uses_exec_hooks(self):
        root = Path(tempfile.mkdtemp(prefix="aiwf_windows_native_"))
        try:
            result = _run(
                [sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                root,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            settings = json.loads((root / ".claude/settings.json").read_text(encoding="utf-8"))
            handlers = [
                handler
                for groups in settings["hooks"].values()
                for group in groups
                for handler in group.get("hooks", [])
            ]
            self.assertTrue(all(handler.get("args") for handler in handlers))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_windows_hook_pass_uses_shell_free_python_exec(self):
        from aiwf_core.install_claude import _build_settings_json
        from aiwf_core.platform.windows_install import apply_windows_claude_compat

        root = Path(tempfile.mkdtemp(prefix="aiwf_windows_"))
        try:
            settings = root / ".claude/settings.json"
            settings.parent.mkdir(parents=True)
            settings.write_text(json.dumps(_build_settings_json()), encoding="utf-8")
            apply_windows_claude_compat(root)
            data = json.loads(settings.read_text(encoding="utf-8"))
            handlers = [
                handler
                for groups in data["hooks"].values()
                for group in groups
                for handler in group.get("hooks", [])
            ]
            self.assertTrue(handlers)
            self.assertTrue(all(item["command"] == sys.executable for item in handlers))
            self.assertTrue(all(item.get("args", [""])[0].startswith("${CLAUDE_PROJECT_DIR}/scripts/aiwf_") for item in handlers))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_windows_reinstall_does_not_duplicate_managed_hooks(self):
        from aiwf_core.install_claude import _build_settings_json, _merge_hooks
        from aiwf_core.platform.windows_install import apply_windows_claude_compat

        root = Path(tempfile.mkdtemp(prefix="aiwf_windows_reinstall_"))
        try:
            settings = root / ".claude/settings.json"
            settings.parent.mkdir(parents=True)
            settings.write_text(json.dumps(_build_settings_json()), encoding="utf-8")
            apply_windows_claude_compat(root)
            data = json.loads(settings.read_text(encoding="utf-8"))
            data["hooks"] = _merge_hooks(data["hooks"], _build_settings_json()["hooks"])
            settings.write_text(json.dumps(data), encoding="utf-8")
            apply_windows_claude_compat(root)
            data = json.loads(settings.read_text(encoding="utf-8"))
            managed = [
                handler
                for groups in data.get("hooks", {}).values()
                for group in groups
                for handler in group.get("hooks", [])
                if any("/scripts/aiwf_" in str(arg).replace("\\", "/") for arg in handler.get("args", []))
            ]
            expected = sum(
                len(group.get("hooks", []))
                for groups in _build_settings_json()["hooks"].values()
                for group in groups
            )
            self.assertEqual(len(managed), expected)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_windows_lock_adapter_uses_msvcrt(self):
        import aiwf_core.platform.file_lock as file_lock

        calls = []

        class FakeMsvcrt:
            LK_LOCK = 1
            LK_UNLCK = 2

            @staticmethod
            def locking(fd, mode, count):
                calls.append((fd, mode, count))

        with tempfile.TemporaryFile("w+b") as handle:
            with patch.object(file_lock.os, "name", "nt"), patch.dict(sys.modules, {"msvcrt": FakeMsvcrt}):
                file_lock._lock(handle)
                file_lock._unlock(handle)
        self.assertEqual([item[1] for item in calls], [FakeMsvcrt.LK_LOCK, FakeMsvcrt.LK_UNLCK])


if __name__ == "__main__":
    unittest.main()
