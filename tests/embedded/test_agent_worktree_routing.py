"""Task-role Agents are mechanically routed to their Plan worktrees."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from aiwf_core.core.agent_worktree import AgentWorktreeError, route_agent_tool
from aiwf_core.core.event_model import NormalizedEvent


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class TestAgentWorktreeRouting(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aiwf-route-")
        self.root = Path(self.temp.name)
        subprocess.run(
            ["git", "init", "-q"], cwd=self.root, check=True,
            capture_output=True, text=True,
        )
        self.worktree_a = self.root / "worktrees" / "plan-a"
        self.worktree_b = self.root / "worktrees" / "plan-b"
        self.worktree_a.mkdir(parents=True)
        self.worktree_b.mkdir(parents=True)
        state = self.root / ".aiwf/state"
        state.mkdir(parents=True)
        (state / "state.json").write_text("{}\n", encoding="utf-8")
        (state / "tasks.json").write_text(json.dumps({"tasks": [
            {
                "id": "TASK-A", "status": "active", "phase": "implementing",
                "worktree_path": str(self.worktree_a),
            },
            {
                "id": "TASK-B", "status": "active", "phase": "implementing",
                "worktree_path": str(self.worktree_b),
            },
        ]}), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def _event(self, tool_name, tool_input, *, agent_id="a", transcript_path=""):
        return NormalizedEvent(
            engine="claude",
            event_type="pre_tool_use",
            session_id="session-1",
            cwd=str(self.root),
            tool_name=tool_name,
            tool_input=tool_input,
            agent_id=agent_id,
            agent_type="aiwf-executor",
            transcript_path=str(transcript_path),
        )

    def _agent_transcript(self, agent_id, first_task, later_task=""):
        main = self.root / "session.jsonl"
        transcript = main.with_suffix("") / "subagents" / f"agent-{agent_id}.jsonl"
        transcript.parent.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps({
            "message": (
                f"Implement {first_task} in assigned worktree "
                f"{self.worktree_a if first_task == 'TASK-A' else self.worktree_b}"
            )
        })]
        if later_task:
            lines.append(json.dumps({
                "tool_output": (
                    f"Other active task {later_task} uses "
                    f"{self.worktree_b if later_task == 'TASK-B' else self.worktree_a}"
                )
            }))
        transcript.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return main

    def test_parallel_same_role_agents_use_their_own_transcripts(self):
        main = self._agent_transcript("a", "TASK-A", later_task="TASK-B")
        self._agent_transcript("b", "TASK-B", later_task="TASK-A")

        routed_a = route_agent_tool(
            self._event("Read", {"file_path": "src/value.py"}, transcript_path=main),
            self.root,
        )
        routed_b = route_agent_tool(
            self._event(
                "Read", {"file_path": "src/value.py"},
                agent_id="b", transcript_path=main,
            ),
            self.root,
        )

        self.assertEqual(
            routed_a.tool_input["file_path"],
            str((self.worktree_a / "src/value.py").resolve()),
        )
        self.assertEqual(
            routed_b.tool_input["file_path"],
            str((self.worktree_b / "src/value.py").resolve()),
        )

    def test_bash_is_rooted_on_every_call(self):
        main = self._agent_transcript("a", "TASK-A")
        routed = route_agent_tool(
            self._event("Bash", {"command": "pwd && pytest -q"}, transcript_path=main),
            self.root,
        )
        self.assertTrue(
            routed.tool_input["command"].startswith(
                f"cd {self.worktree_a.resolve()} && "
            )
        )
        self.assertIn("pwd && pytest -q", routed.tool_input["command"])

    def test_relative_governance_read_uses_control_root(self):
        main = self._agent_transcript("a", "TASK-A")
        routed = route_agent_tool(
            self._event(
                "Read", {"file_path": ".aiwf/tasks/TASK-A.md"},
                transcript_path=main,
            ),
            self.root,
        )
        self.assertEqual(
            routed.tool_input["file_path"],
            str((self.root / ".aiwf/tasks/TASK-A.md").resolve()),
        )

    def test_one_unfinished_dispatch_is_a_safe_fallback(self):
        runtime = self.root / ".aiwf/runtime/internal"
        runtime.mkdir(parents=True)
        (runtime / "agent-dispatch.jsonl").write_text(json.dumps({
            "subagent_type": "aiwf-executor",
            "task_id": "TASK-B",
            "session_id": "session-1",
            "status": "started",
        }) + "\n", encoding="utf-8")

        routed = route_agent_tool(
            self._event("Glob", {"pattern": "**/*.py"}), self.root,
        )
        self.assertEqual(routed.assignment.task_id, "TASK-B")
        self.assertEqual(routed.tool_input["path"], str(self.worktree_b.resolve()))

    def test_ambiguous_parallel_agent_is_blocked(self):
        runtime = self.root / ".aiwf/runtime/internal"
        runtime.mkdir(parents=True)
        (runtime / "agent-dispatch.jsonl").write_text("\n".join([
            json.dumps({
                "subagent_type": "aiwf-executor", "task_id": task_id,
                "session_id": "session-1", "status": "started",
            })
            for task_id in ("TASK-A", "TASK-B")
        ]) + "\n", encoding="utf-8")

        with self.assertRaises(AgentWorktreeError):
            route_agent_tool(self._event("Read", {"file_path": "README.md"}), self.root)


class TestAgentWorktreeHookIntegration(unittest.TestCase):
    def test_write_and_bash_hooks_route_into_a_real_git_worktree(self):
        with tempfile.TemporaryDirectory(prefix="aiwf-route-hook-") as temp:
            top = Path(temp).resolve()
            control = top / "control"
            worktree = top / "plan-a"
            control.mkdir()
            env = os.environ.copy()
            env["PYTHONPATH"] = str(PROJECT_ROOT)

            def run(command, cwd=control, **kwargs):
                return subprocess.run(
                    command, cwd=cwd, env=env, capture_output=True, text=True,
                    check=True, **kwargs,
                )

            run(["git", "init", "-q"])
            run(["git", "config", "user.name", "AIWF Test"])
            run(["git", "config", "user.email", "aiwf@example.invalid"])
            (control / "README.md").write_text("base\n", encoding="utf-8")
            run(["git", "add", "README.md"])
            run(["git", "commit", "-qm", "base"])
            run([
                sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force",
            ])
            run(["git", "worktree", "add", "-q", "-b", "plan-a", str(worktree)])

            tasks_path = control / ".aiwf/state/tasks.json"
            tasks_path.write_text(json.dumps({"tasks": [{
                "id": "TASK-A",
                "status": "active",
                "phase": "implementing",
                "plan_id": "PLAN-A",
                "worktree_path": str(worktree),
                "requirements": {
                    "executor_required": True,
                    "tester_required": False,
                    "reviewer_required": False,
                },
            }]}), encoding="utf-8")
            (control / ".aiwf/state/plans.json").write_text(json.dumps({
                "plans": [{"plan_id": "PLAN-A", "status": "active"}],
            }), encoding="utf-8")
            task_doc = control / ".aiwf/tasks/TASK-A.md"
            task_doc.parent.mkdir(parents=True, exist_ok=True)
            task_doc.write_text(
                "---\nid: TASK-A\ntype: task\nexecutor_required: true\n"
                "tester_required: false\nreviewer_required: false\n---\n\n# TASK-A\n",
                encoding="utf-8",
            )

            main_transcript = control / "session.jsonl"
            agent_transcript = (
                main_transcript.with_suffix("") / "subagents" / "agent-a.jsonl"
            )
            agent_transcript.parent.mkdir(parents=True)
            agent_transcript.write_text(json.dumps({
                "message": f"Implement TASK-A in assigned worktree {worktree}",
            }) + "\n", encoding="utf-8")

            common = {
                "hook_event_name": "PreToolUse",
                "session_id": "session-1",
                "cwd": str(control),
                "agent_id": "a",
                "agent_type": "aiwf-executor",
                "transcript_path": str(main_transcript),
            }
            write_event = dict(common, tool_name="Write", tool_input={
                "file_path": "src/generated.txt", "content": "ok\n",
            })
            write_hook = run(
                [sys.executable, str(control / "scripts/aiwf_scope_check.py")],
                input=json.dumps(write_event),
            )
            write_output = json.loads(write_hook.stdout)["hookSpecificOutput"]
            self.assertEqual(write_output["permissionDecision"], "allow")
            self.assertEqual(
                write_output["updatedInput"]["file_path"],
                str(worktree / "src/generated.txt"),
            )

            bash_event = dict(common, tool_name="Bash", tool_input={
                "command": "touch routed-marker.txt",
            })
            bash_hook = run(
                [sys.executable, str(control / "scripts/aiwf_bash_guard.py")],
                input=json.dumps(bash_event),
            )
            bash_output = json.loads(bash_hook.stdout)["hookSpecificOutput"]
            self.assertEqual(bash_output["permissionDecision"], "allow")
            routed_command = bash_output["updatedInput"]["command"]
            run(["/bin/sh", "-c", routed_command])
            self.assertTrue((worktree / "routed-marker.txt").exists())
            self.assertFalse((control / "routed-marker.txt").exists())


if __name__ == "__main__":
    unittest.main()
