import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class TestRecordDispatchContract(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aiwf_dispatch_"))
        self.env = os.environ.copy()
        self.env["PYTHONPATH"] = str(PROJECT_ROOT)
        subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
            cwd=self.tmp,
            env=self.env,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(["git", "init", "-b", "main"], cwd=self.tmp, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.tmp, check=True)
        subprocess.run(["git", "config", "user.name", "AIWF Test"], cwd=self.tmp, check=True)
        (self.tmp / "project.txt").write_text("base\n", encoding="utf-8")
        # A Task starts from a clean repository. AIWF installation files are
        # part of that baseline unless the project explicitly gitignores them.
        subprocess.run(["git", "add", "-A"], cwd=self.tmp, check=True)
        subprocess.run(["git", "commit", "-m", "base"], cwd=self.tmp, check=True, capture_output=True)
        subprocess.run(["git", "switch", "-c", "feature/test"], cwd=self.tmp, check=True, capture_output=True)
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=self.tmp, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        tasks_path = self.tmp / ".aiwf" / "state" / "tasks.json"
        tasks_path.write_text(json.dumps({
            "tasks": [{
                "id": "TASK-001",
                "status": "active",
                "phase": "reviewing",
                "worktree_path": str(self.tmp),
                "git_origin_ref": head,
                "git_branch": "feature/test",
                "requirements": {
                    "executor_required": True,
                    "tester_required": True,
                    "reviewer_required": True,
                },
            }],
        }, indent=2) + "\n", encoding="utf-8")
        self.record_path = self.tmp / ".aiwf/records/tasks/TASK-001.json"
        self.record_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_record({
            "schema_version": 1,
            "task_id": "TASK-001",
            "implementation": {
                "task_id": "TASK-001", "implementation_ref": head, "summary": "ready",
            },
            "testing": {
                "task_id": "TASK-001", "status": "passed", "based_on_ref": head,
                "tested_ref": head, "commands": ["pytest -q"], "summary": "passed",
            },
            "review": {"task_id": "TASK-001", "result": "unknown"},
            "fix_loop": {"status": "none"},
        })

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", *args],
            cwd=self.tmp,
            env=self.env,
            capture_output=True,
            text=True,
        )

    def _read_record(self):
        return json.loads(self.record_path.read_text(encoding="utf-8"))

    def _write_record(self, record):
        self.record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    def _dispatch(
        self,
        subagent_type,
        skill,
        session_id="test",
        skill_session_id="",
        event_cwd="",
        agent_cwd="",
        include_agent_cwd=True,
    ):
        log = self.tmp / ".aiwf" / "runtime" / "internal" / "skill-loads.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(json.dumps({
            "skill": skill,
            "task_id": "TASK-001",
            "session_id": skill_session_id or session_id,
        }) + "\n")
        tool_input = {
            "subagent_type": subagent_type,
            "prompt": f"Work on TASK-001 in assigned worktree {self.tmp}. Verify cwd first.",
        }
        if include_agent_cwd:
            tool_input["cwd"] = str(agent_cwd or self.tmp)
        payload = json.dumps({
            "hook_event_name": "PreToolUse",
            "tool_name": "Agent",
            "tool_input": tool_input,
            "cwd": str(event_cwd or self.tmp),
            "session_id": session_id,
        })
        return subprocess.run(
            [sys.executable, str(self.tmp / "scripts" / "aiwf_agent_gate.py")],
            cwd=self.tmp,
            env=self.env,
            input=payload,
            capture_output=True,
            text=True,
        )

    def test_dispatch_uses_assigned_worktree_as_agent_cwd(self):
        outside = self.tmp.parent
        allowed = self._dispatch(
            "aiwf-reviewer", "aiwf-review", event_cwd=outside,
        )
        self.assertEqual(allowed.returncode, 0, allowed.stderr)
        self.assertEqual(allowed.stdout.strip(), "")

    def test_dispatch_rejects_wrong_effective_agent_cwd(self):
        result = self._dispatch(
            "aiwf-reviewer", "aiwf-review", event_cwd=self.tmp.parent,
            include_agent_cwd=False,
        )
        output = json.loads(result.stdout)
        reason = output["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("Agent cwd must be the assigned worktree", reason)
        self.assertIn("do not call EnterWorktree", reason)

    def _complete(self, subagent_type, message="TASK-001 completed."):
        payload = json.dumps({
            "hook_event_name": "SubagentStop",
            "agent_type": subagent_type,
            "last_assistant_message": message,
            "cwd": str(self.tmp),
            "session_id": "test",
        })
        return subprocess.run(
            [sys.executable, str(self.tmp / "scripts" / "aiwf_agent_log.py")],
            cwd=self.tmp,
            env=self.env,
            input=payload,
            capture_output=True,
            text=True,
        )

    def test_review_record_is_blocked_before_required_reviewer_dispatch(self):
        blocked = self._cli(
            "record", "review", "--result", "needs_fix",
            "--summary", "main path bypass", "--blocker", "wire consumer",
        )
        self.assertEqual(blocked.returncode, 1)
        self.assertIn("requires a task-scoped aiwf-reviewer dispatch", blocked.stderr)

        dispatched = self._dispatch("aiwf-reviewer", "aiwf-review")
        self.assertEqual(dispatched.returncode, 0, dispatched.stderr)
        entry = json.loads(
            (self.tmp / ".aiwf" / "runtime" / "internal" / "agent-dispatch.jsonl")
            .read_text(encoding="utf-8").splitlines()[-1]
        )
        self.assertEqual(entry["status"], "started")

        recorded = self._cli(
            "record", "review", "--result", "needs_fix",
            "--summary", "main path bypass", "--blocker", "wire consumer",
        )
        self.assertEqual(recorded.returncode, 0, recorded.stderr)

    def test_inline_record_is_allowed_when_role_is_not_required(self):
        tasks_path = self.tmp / ".aiwf" / "state" / "tasks.json"
        tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
        tasks["tasks"][0]["requirements"]["tester_required"] = False
        tasks_path.write_text(json.dumps(tasks, indent=2) + "\n", encoding="utf-8")

        result = self._cli(
            "record", "testing", "--status", "passed",
            "--command", "pytest -q",
            "--verification-result", "pytest -q:::all pass:::all pass:::matched",
            "--summary", "inline validation passed",
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_tester_dispatch_is_blocked_before_executor_record(self):
        record = self._read_record()
        record["implementation"] = {"task_id": "TASK-001"}
        self._write_record(record)

        result = self._dispatch("aiwf-tester", "aiwf-test")

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        reason = output["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("Finish Executor first", reason)

    def test_executor_optional_task_can_dispatch_tester_from_origin(self):
        tasks_path = self.tmp / ".aiwf" / "state" / "tasks.json"
        tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
        tasks["tasks"][0]["requirements"]["executor_required"] = False
        tasks_path.write_text(json.dumps(tasks, indent=2) + "\n", encoding="utf-8")
        record = self._read_record()
        record["implementation"] = {"task_id": "TASK-001"}
        self._write_record(record)

        result = self._dispatch("aiwf-tester", "aiwf-test")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "")

    def test_reviewer_dispatch_is_blocked_before_tested_snapshot(self):
        record = self._read_record()
        record["testing"] = {"task_id": "TASK-001", "status": "missing"}
        self._write_record(record)

        result = self._dispatch("aiwf-reviewer", "aiwf-review")

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        reason = output["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("Finish Tester first", reason)

    def test_open_planner_fix_loop_blocks_workflow_role_dispatch(self):
        record = self._read_record()
        record["fix_loop"] = {"status": "open", "route": "planner"}
        self._write_record(record)

        result = self._dispatch("aiwf-executor", "aiwf-implement")

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        reason = output["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("fix-loop routes to planner", reason)

    def test_second_workflow_role_waits_for_subagent_stop(self):
        first = self._dispatch("aiwf-executor", "aiwf-implement")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout.strip(), "")

        blocked = self._dispatch("aiwf-executor", "aiwf-implement")
        output = json.loads(blocked.stdout)
        reason = output["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("is still running", reason)

        completed = self._complete("aiwf-executor")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        allowed = self._dispatch("aiwf-executor", "aiwf-implement")
        self.assertEqual(allowed.returncode, 0, allowed.stderr)
        self.assertEqual(allowed.stdout.strip(), "")

    def test_agent_requires_skill_loaded_in_the_current_session(self):
        result = self._dispatch(
            "aiwf-executor", "aiwf-implement",
            session_id="new-session", skill_session_id="old-session",
        )

        output = json.loads(result.stdout)
        reason = output["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("skill not loaded", reason)

    def test_subagent_stop_can_resolve_task_from_worktree(self):
        tasks_path = self.tmp / ".aiwf" / "state" / "tasks.json"
        tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
        tasks["tasks"].append({
            "id": "TASK-002",
            "status": "active",
            "phase": "implementing",
            "worktree_path": str(self.tmp / "another-worktree"),
            "requirements": {},
        })
        tasks_path.write_text(json.dumps(tasks, indent=2) + "\n", encoding="utf-8")

        first = self._dispatch("aiwf-executor", "aiwf-implement")
        self.assertEqual(first.stdout.strip(), "")
        completed = self._complete("aiwf-executor", "Implementation completed.")
        self.assertEqual(completed.returncode, 0, completed.stderr)

        entries = [
            json.loads(line) for line in
            (self.tmp / ".aiwf/runtime/internal/agent-dispatch.jsonl")
            .read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(entries[-1]["task_id"], "TASK-001")
        self.assertEqual(entries[-1]["status"], "completed")


if __name__ == "__main__":
    unittest.main()
