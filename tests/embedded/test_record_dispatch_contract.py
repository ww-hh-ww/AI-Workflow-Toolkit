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
        subprocess.run(["git", "add", "project.txt"], cwd=self.tmp, check=True)
        subprocess.run(["git", "commit", "-m", "base"], cwd=self.tmp, check=True, capture_output=True)
        subprocess.run(["git", "switch", "-c", "feature/test"], cwd=self.tmp, check=True, capture_output=True)
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=self.tmp, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state.update({
            "active_task_id": "TASK-001",
            "phase": "reviewing",
            "git_origin_ref": head,
        })
        state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        tasks_path = self.tmp / ".aiwf" / "state" / "tasks.json"
        tasks_path.write_text(json.dumps({
            "tasks": [{
                "id": "TASK-001",
                "status": "active",
                "git_origin_ref": head,
                "requirements": {
                    "executor_required": True,
                    "tester_required": True,
                    "reviewer_required": True,
                },
            }],
            "execution_window": {"active_task_ids": ["TASK-001"]},
        }, indent=2) + "\n", encoding="utf-8")
        (self.tmp / ".aiwf/records/implementation.json").write_text(json.dumps({
            "task_id": "TASK-001", "implementation_ref": head, "summary": "ready",
        }, indent=2) + "\n")
        (self.tmp / ".aiwf/records/testing.json").write_text(json.dumps({
            "task_id": "TASK-001", "status": "passed", "based_on_ref": head,
            "tested_ref": head, "commands": ["pytest -q"], "summary": "passed",
        }, indent=2) + "\n")

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

    def _dispatch(self, subagent_type, skill):
        log = self.tmp / ".aiwf" / "runtime" / "internal" / "skill-loads.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(json.dumps({"skill": skill, "task_id": "TASK-001"}) + "\n")
        payload = json.dumps({
            "hook_event_name": "PreToolUse",
            "tool_name": "Agent",
            "tool_input": {"subagent_type": subagent_type},
            "cwd": str(self.tmp),
            "session_id": "test",
        })
        return subprocess.run(
            [sys.executable, str(self.tmp / "scripts" / "aiwf_agent_gate.py")],
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


if __name__ == "__main__":
    unittest.main()
