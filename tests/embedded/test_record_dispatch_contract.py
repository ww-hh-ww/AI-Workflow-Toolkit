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
        prompt="",
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
            "prompt": prompt or "TASK-001",
        }
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

    def _allowed_input(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        hook = output["hookSpecificOutput"]
        self.assertEqual(hook["permissionDecision"], "allow")
        return hook["updatedInput"]

    def _agent_return(self, subagent_type, message="TASK-001 completed."):
        payload = json.dumps({
            "hook_event_name": "PostToolUse",
            "tool_name": "Agent",
            "tool_input": {
                "subagent_type": subagent_type,
                "prompt": "TASK-001",
            },
            "tool_response": {"content": message},
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

    def _agent_failure(self, subagent_type, error="Agent initialization failed"):
        payload = json.dumps({
            "hook_event_name": "PostToolUseFailure",
            "tool_name": "Agent",
            "tool_input": {
                "subagent_type": subagent_type,
                "prompt": "TASK-001",
            },
            "error": error,
            "is_interrupt": False,
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

    def test_dispatch_from_control_session_uses_prompt_assignment(self):
        outside = self.tmp.parent
        allowed = self._dispatch(
            "aiwf-reviewer", "aiwf-review", event_cwd=outside,
        )
        updated = self._allowed_input(allowed)
        self.assertIn("Task: TASK-001", updated["prompt"])
        self.assertIn(
            f"Task contract: {self.tmp.resolve() / '.aiwf/tasks/TASK-001.md'}",
            updated["prompt"],
        )
        self.assertIn(f"Assigned worktree: {self.tmp}", updated["prompt"])

    def test_dispatch_does_not_require_an_unsupported_agent_cwd_field(self):
        result = self._dispatch(
            "aiwf-reviewer", "aiwf-review", event_cwd=self.tmp.parent,
        )
        updated = self._allowed_input(result)
        self.assertNotIn("cwd", updated)

    def test_dispatch_adds_assignment_without_deleting_planner_context(self):
        result = self._dispatch(
            "aiwf-reviewer",
            "aiwf-review",
            prompt=(
                "TASK-001\nFixed Contract: stale duplicated instructions\n"
                "Use a fallback that Task.md does not permit.\n"
                "USER_DELTA: The user explicitly requires a Windows smoke test."
            ),
        )

        prompt = self._allowed_input(result)["prompt"]
        self.assertIn("Task contract:", prompt)
        self.assertIn("Assigned worktree:", prompt)
        self.assertIn("Planner context:", prompt)
        self.assertIn("stale duplicated instructions", prompt)
        self.assertIn("Use a fallback", prompt)
        self.assertIn(
            "USER_DELTA: The user explicitly requires a Windows smoke test.",
            prompt,
        )

    def test_general_purpose_cannot_substitute_for_active_task_role(self):
        payload = json.dumps({
            "hook_event_name": "PreToolUse",
            "tool_name": "Agent",
            "tool_input": {
                "subagent_type": "general-purpose",
                "prompt": "Implement TASK-001",
            },
            "cwd": str(self.tmp),
            "session_id": "test",
        })
        result = subprocess.run(
            [sys.executable, str(self.tmp / "scripts" / "aiwf_agent_gate.py")],
            cwd=self.tmp,
            env=self.env,
            input=payload,
            capture_output=True,
            text=True,
        )

        output = json.loads(result.stdout)
        reason = output["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("Cannot use general-purpose as a substitute", reason)

    def _complete(
        self,
        subagent_type,
        message="TASK-001 completed.",
        agent_id="",
        transcript_path="",
    ):
        payload = json.dumps({
            "hook_event_name": "SubagentStop",
            "agent_type": subagent_type,
            "agent_id": agent_id,
            "transcript_path": transcript_path,
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

        self._allowed_input(result)

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

    def test_implementation_fix_loop_explains_inline_repair_before_tester(self):
        record = self._read_record()
        record["fix_loop"] = {"status": "open", "route": "executor"}
        self._write_record(record)

        result = self._dispatch("aiwf-tester", "aiwf-test")

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        reason = output["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("implementation repair", reason)
        self.assertIn("Repair inline", reason)
        self.assertIn("Record the repaired implementation", reason)

    def test_escalated_fix_loop_blocks_more_agents_for_user_decision(self):
        record = self._read_record()
        record["fix_loop"] = {
            "status": "open", "route": "executor", "escalation_required": True,
        }
        self._write_record(record)

        result = self._dispatch("aiwf-executor", "aiwf-implement")

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        reason = output["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("Planner and user decision", reason)
        self.assertIn("recorded failures", reason)

    def test_second_workflow_role_waits_for_subagent_stop(self):
        first = self._dispatch("aiwf-executor", "aiwf-implement")
        self._allowed_input(first)

        blocked = self._dispatch("aiwf-executor", "aiwf-implement")
        output = json.loads(blocked.stdout)
        reason = output["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("is still running", reason)

        completed = self._complete("aiwf-executor")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        allowed = self._dispatch("aiwf-executor", "aiwf-implement")
        self._allowed_input(allowed)

    def test_agent_tool_return_closes_dispatch_before_subagent_stop(self):
        first = self._dispatch("aiwf-executor", "aiwf-implement")
        self._allowed_input(first)

        returned = self._agent_return("aiwf-executor")
        self.assertEqual(returned.returncode, 0, returned.stderr)
        allowed = self._dispatch("aiwf-executor", "aiwf-implement")
        self._allowed_input(allowed)

        entries = [
            json.loads(line) for line in
            (self.tmp / ".aiwf/runtime/internal/agent-dispatch.jsonl")
            .read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(entries[-2]["status"], "completed")
        self.assertEqual(entries[-2]["completion_source"], "agent_return")

    def test_stopped_agent_return_cancels_dispatch(self):
        first = self._dispatch("aiwf-executor", "aiwf-implement")
        self._allowed_input(first)

        returned = self._agent_return(
            "aiwf-executor", "Agent was stopped before completion."
        )
        self.assertEqual(returned.returncode, 0, returned.stderr)
        entries = [
            json.loads(line) for line in
            (self.tmp / ".aiwf/runtime/internal/agent-dispatch.jsonl")
            .read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(entries[-1]["status"], "cancelled")
        self.assertEqual(entries[-1]["completion_source"], "agent_return")

        allowed = self._dispatch("aiwf-executor", "aiwf-implement")
        self._allowed_input(allowed)

    def test_failed_agent_tool_releases_dispatch_for_retry(self):
        first = self._dispatch("aiwf-executor", "aiwf-implement")
        self._allowed_input(first)

        failed = self._agent_failure("aiwf-executor")
        self.assertEqual(failed.returncode, 0, failed.stderr)
        output = json.loads(failed.stdout)
        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("running slot was released", context)
        entries = [
            json.loads(line) for line in
            (self.tmp / ".aiwf/runtime/internal/agent-dispatch.jsonl")
            .read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(entries[-1]["status"], "cancelled")
        self.assertEqual(entries[-1]["completion_source"], "agent_failure")

        allowed = self._dispatch("aiwf-executor", "aiwf-implement")
        self._allowed_input(allowed)

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
        self._allowed_input(first)
        completed = self._complete("aiwf-executor", "Implementation completed.")
        self.assertEqual(completed.returncode, 0, completed.stderr)

        entries = [
            json.loads(line) for line in
            (self.tmp / ".aiwf/runtime/internal/agent-dispatch.jsonl")
            .read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(entries[-1]["task_id"], "TASK-001")
        self.assertEqual(entries[-1]["status"], "completed")

    def test_parallel_subagent_stop_uses_its_transcript_assignment(self):
        tasks_path = self.tmp / ".aiwf" / "state" / "tasks.json"
        tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
        second_worktree = self.tmp / "another-worktree"
        tasks["tasks"].append({
            "id": "TASK-002",
            "status": "active",
            "phase": "implementing",
            "worktree_path": str(second_worktree),
            "requirements": {},
        })
        tasks_path.write_text(json.dumps(tasks, indent=2) + "\n", encoding="utf-8")
        dispatch_path = self.tmp / ".aiwf/runtime/internal/agent-dispatch.jsonl"
        dispatch_path.parent.mkdir(parents=True, exist_ok=True)
        dispatch_path.write_text("\n".join([
            json.dumps({
                "subagent_type": "aiwf-executor", "task_id": task_id,
                "session_id": "test", "status": "started",
            })
            for task_id in ("TASK-001", "TASK-002")
        ]) + "\n", encoding="utf-8")

        main = self.tmp / "session.jsonl"
        agent = main.with_suffix("") / "subagents" / "agent-b.jsonl"
        agent.parent.mkdir(parents=True)
        agent.write_text(json.dumps({
            "prompt": f"Work on TASK-002 in assigned worktree {second_worktree}",
        }) + "\n", encoding="utf-8")

        completed = self._complete(
            "aiwf-executor",
            "Implementation completed.",
            agent_id="b",
            transcript_path=str(main),
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        entries = [
            json.loads(line) for line in dispatch_path.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(entries[-1]["task_id"], "TASK-002")
        self.assertEqual(entries[-1]["status"], "completed")


if __name__ == "__main__":
    unittest.main()
