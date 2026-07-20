import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
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

    def _fresh_implementation_record(self):
        record = self._read_record()
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=self.tmp, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        record["implementation"].update({
            "task_id": "TASK-001",
            "implementation_ref": head,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        })
        self._write_record(record)

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

    def _agent_return(
        self,
        subagent_type,
        message="TASK-001 completed.",
        tool_response=None,
    ):
        payload = json.dumps({
            "hook_event_name": "PostToolUse",
            "tool_name": "Agent",
            "tool_input": {
                "subagent_type": subagent_type,
                "prompt": "TASK-001",
            },
            "tool_response": tool_response or {"content": message},
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

    def _task_stop(
        self,
        agent_id,
        *,
        task_type="local_agent",
        event_name="PostToolUse",
    ):
        payload = json.dumps({
            "hook_event_name": event_name,
            "tool_name": "TaskStop",
            "tool_input": {"task_id": agent_id},
            "tool_response": {
                "message": f"Successfully stopped task: {agent_id}",
                "task_id": agent_id,
                "task_type": task_type,
                "command": "TASK-001 executor",
            },
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

    def test_reviewer_waits_for_complete_strict_testing_proof(self):
        (self.tmp / ".aiwf/tasks/TASK-001.md").write_text(
            """# TASK-001

## Fixed Contract

### Structural Home
GOAL-001 / PLAN-001.

### Objective
Ship the entry point.

### Contract Responsibility
The public entry point works.

### Proof Standard
- **Running:** Both commands pass.

Verification Commands:

| Command | Expected |
|---|---|
| `pytest -q` | tests pass |
| `python3 app.py` | prints ready |
""",
            encoding="utf-8",
        )
        record = self._read_record()
        record["testing"].update({
            "commands": ["pytest -q"],
            "verification_results": [{
                "command": "pytest -q", "expected": "tests pass",
                "observed": "10 passed", "matched": True,
            }],
        })
        self._write_record(record)

        result = self._dispatch("aiwf-reviewer", "aiwf-review")

        reason = json.loads(result.stdout)["hookSpecificOutput"][
            "permissionDecisionReason"
        ]
        self.assertIn("Tester proof is incomplete", reason)
        self.assertIn("python3 app.py", reason)

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

    def _start(self, subagent_type, agent_id):
        payload = json.dumps({
            "hook_event_name": "SubagentStart",
            "agent_type": subagent_type,
            "agent_id": agent_id,
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

    def _complete_after_return_check(self, subagent_type, agent_id):
        checked = self._complete(subagent_type, agent_id=agent_id)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        output = json.loads(checked.stdout)
        self.assertEqual(output["decision"], "block")
        self.assertIn("final contract check", output["reason"])
        return self._complete(subagent_type, agent_id=agent_id)

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
        self.assertIn("human decision", reason)
        self.assertIn("aiwf fixloop continue --task-id TASK-001", reason)

    def test_escalated_fix_loop_blocks_tester_until_human_continues(self):
        from aiwf_core.core.state.fixloop_ops import continue_fix_loop

        record = self._read_record()
        record["implementation"] = {
            "task_id": "TASK-001",
            "implementation_ref": "fresh-ref",
        }
        record["testing"] = {
            "task_id": "TASK-001", "status": "missing", "tested_ref": "",
        }
        record["fix_loop"] = {
            "status": "open", "route": "tester", "escalation_required": True,
        }
        self._write_record(record)

        blocked_tester = self._dispatch("aiwf-tester", "aiwf-test")
        reason = json.loads(blocked_tester.stdout)["hookSpecificOutput"][
            "permissionDecisionReason"
        ]
        self.assertIn("human decision", reason)

        continue_fix_loop(str(self.tmp), task_id="TASK-001")
        tester = self._dispatch("aiwf-tester", "aiwf-test")
        self._allowed_input(tester)

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

    def test_same_task_role_lock_applies_across_sessions(self):
        first = self._dispatch(
            "aiwf-executor", "aiwf-implement", session_id="session-a",
        )
        self._allowed_input(first)

        blocked = self._dispatch(
            "aiwf-tester", "aiwf-test", session_id="session-b",
        )

        self.assertEqual(blocked.returncode, 0, blocked.stderr)
        output = json.loads(blocked.stdout)
        reason = output["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("aiwf-executor is still running", reason)

    def test_subagent_lifecycle_records_resumable_executor_id(self):
        first = self._dispatch("aiwf-executor", "aiwf-implement")
        self._allowed_input(first)
        started = self._start("aiwf-executor", "executor-123")
        self.assertEqual(started.returncode, 0, started.stderr)
        self._fresh_implementation_record()
        completed = self._complete_after_return_check(
            "aiwf-executor", "executor-123",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

        entries = [
            json.loads(line) for line in
            (self.tmp / ".aiwf/runtime/internal/agent-dispatch.jsonl")
            .read_text(encoding="utf-8").splitlines()
        ]
        self.assertIn("bound", [entry["status"] for entry in entries])
        self.assertIn("return_check", [entry["status"] for entry in entries])
        self.assertEqual(entries[-1]["status"], "completed")
        self.assertEqual(entries[-1]["agent_id"], "executor-123")

    def test_fix_loop_prompt_prefers_original_executor_and_has_fallback(self):
        first = self._dispatch("aiwf-executor", "aiwf-implement")
        self._allowed_input(first)
        self._start("aiwf-executor", "executor-123")
        self._fresh_implementation_record()
        self._complete_after_return_check("aiwf-executor", "executor-123")
        record = self._read_record()
        record["fix_loop"] = {"status": "open", "route": "executor"}
        self._write_record(record)

        status = self._cli("status", "--prompt")

        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("SendMessage", status.stdout)
        self.assertIn("executor-123", status.stdout)
        self.assertIn("aiwf task proof TASK-001", status.stdout)
        self.assertIn("dispatch a new aiwf-executor", status.stdout)

    def test_resumed_executor_reopens_the_dispatch_window(self):
        first = self._dispatch("aiwf-executor", "aiwf-implement")
        self._allowed_input(first)
        self._start("aiwf-executor", "executor-123")
        self._fresh_implementation_record()
        self._complete_after_return_check("aiwf-executor", "executor-123")

        resumed = self._start("aiwf-executor", "executor-123")

        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        entries = [
            json.loads(line) for line in
            (self.tmp / ".aiwf/runtime/internal/agent-dispatch.jsonl")
            .read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(entries[-1]["status"], "started")
        self.assertTrue(entries[-1]["resumed"])
        self.assertEqual(entries[-1]["agent_id"], "executor-123")

        from aiwf_core.core.agent_runtime import resumable_agent
        self.assertIsNone(resumable_agent(
            self.tmp,
            task_id="TASK-001",
            subagent_type="aiwf-executor",
        ))

        blocked = self._dispatch("aiwf-executor", "aiwf-implement")
        output = json.loads(blocked.stdout)
        self.assertIn(
            "is still running",
            output["hookSpecificOutput"]["permissionDecisionReason"],
        )

    def test_subagent_stop_checks_contract_then_keeps_agent_alive_until_recorded(self):
        first = self._dispatch("aiwf-executor", "aiwf-implement")
        self._allowed_input(first)
        self._start("aiwf-executor", "executor-123")

        blocked = self._complete(
            "aiwf-executor", agent_id="executor-123",
        )

        self.assertEqual(blocked.returncode, 0, blocked.stderr)
        output = json.loads(blocked.stdout)
        self.assertEqual(output["decision"], "block")
        self.assertIn("final contract check", output["reason"])
        self.assertIn("Reread the Task.md Fixed Contract", output["reason"])
        self.assertIn("do not rerun them", output["reason"])

        missing_record = self._complete(
            "aiwf-executor", agent_id="executor-123",
        )
        output = json.loads(missing_record.stdout)
        self.assertEqual(output["decision"], "block")
        self.assertIn("aiwf record implementation", output["reason"])
        self.assertIn("do not rerun successful checks", output["reason"])

        still_running = self._dispatch("aiwf-executor", "aiwf-implement")
        reason = json.loads(still_running.stdout)["hookSpecificOutput"][
            "permissionDecisionReason"
        ]
        self.assertIn("is still running", reason)

        self._fresh_implementation_record()
        completed = self._complete(
            "aiwf-executor", agent_id="executor-123",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertFalse(completed.stdout.strip())

    def test_tester_cannot_return_with_incomplete_chinese_proof_record(self):
        (self.tmp / ".aiwf/tasks/TASK-001.md").write_text(
            """# TASK-001

## 固定契约

### 结构归属

GOAL-001 / PLAN-001。

### 目标

交付可运行入口。

### 契约责任

入口必须通过公开边界运行。

### 证明标准

- **Running：** 入口输出 ready。

验证命令：

| 命令 | 预期可观察结果 |
|------|----------------|
| `pytest -q` | tests pass |
| `python3 app.py` | prints ready |
""",
            encoding="utf-8",
        )
        record = self._read_record()
        record["testing"] = {"task_id": "TASK-001", "status": "missing"}
        self._write_record(record)

        self._allowed_input(self._dispatch("aiwf-tester", "aiwf-test"))
        self.assertEqual(self._start("aiwf-tester", "tester-123").returncode, 0)
        first_stop = self._complete("aiwf-tester", agent_id="tester-123")
        self.assertEqual(json.loads(first_stop.stdout)["decision"], "block")

        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=self.tmp, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        record = self._read_record()
        record["testing"] = {
            "task_id": "TASK-001",
            "status": "passed",
            "tested_ref": head,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "commands": ["pytest -q"],
            "verification_results": [{
                "command": "pytest -q",
                "expected": "tests pass",
                "observed": "10 passed",
                "matched": True,
            }],
        }
        self._write_record(record)

        incomplete = self._complete("aiwf-tester", agent_id="tester-123")
        reason = json.loads(incomplete.stdout)["reason"]
        self.assertIn("complete Verification Commands contract", reason)
        self.assertIn("python3 app.py", reason)
        self.assertIn("Existing valid results are preserved", reason)

        record = self._read_record()
        record["testing"].update({
            "commands": ["pytest -q", "python3 app.py"],
            "verification_results": [
                {
                    "command": "pytest -q",
                    "expected": "tests pass",
                    "observed": "10 passed",
                    "matched": True,
                },
                {
                    "command": "python3 app.py",
                    "expected": "prints ready",
                    "observed": "ready",
                    "matched": True,
                },
            ],
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        })
        self._write_record(record)

        completed = self._complete("aiwf-tester", agent_id="tester-123")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertFalse(completed.stdout.strip())

    def test_cancelled_executor_is_not_offered_for_resume(self):
        first = self._dispatch("aiwf-executor", "aiwf-implement")
        self._allowed_input(first)
        self._start("aiwf-executor", "executor-123")
        self._complete(
            "aiwf-executor",
            message="Agent was stopped before completion.",
            agent_id="executor-123",
        )
        record = self._read_record()
        record["fix_loop"] = {"status": "open", "route": "executor"}
        self._write_record(record)

        status = self._cli("status", "--prompt")

        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertNotIn("SendMessage", status.stdout)
        self.assertIn("dispatch aiwf-executor", status.stdout)

    def test_task_stop_releases_only_the_bound_local_agent(self):
        self._allowed_input(self._dispatch("aiwf-executor", "aiwf-implement"))
        self.assertEqual(self._start("aiwf-executor", "executor-123").returncode, 0)

        stopped = self._task_stop("executor-123")

        self.assertEqual(stopped.returncode, 0, stopped.stderr)
        context = json.loads(stopped.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("was stopped for TASK-001", context)
        entries = [
            json.loads(line) for line in
            (self.tmp / ".aiwf/runtime/internal/agent-dispatch.jsonl")
            .read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(entries[-1]["status"], "cancelled")
        self.assertEqual(entries[-1]["completion_source"], "task_stop")
        self.assertEqual(entries[-1]["agent_id"], "executor-123")
        self._allowed_input(self._dispatch("aiwf-executor", "aiwf-implement"))

    def test_task_stop_does_not_release_background_bash_or_failed_stop(self):
        self._allowed_input(self._dispatch("aiwf-executor", "aiwf-implement"))
        self.assertEqual(self._start("aiwf-executor", "executor-123").returncode, 0)

        bash_stop = self._task_stop("executor-123", task_type="local_bash")
        failed_stop = self._task_stop(
            "executor-123", event_name="PostToolUseFailure",
        )

        self.assertEqual(bash_stop.returncode, 0, bash_stop.stderr)
        self.assertFalse(bash_stop.stdout.strip())
        self.assertEqual(failed_stop.returncode, 0, failed_stop.stderr)
        self.assertFalse(failed_stop.stdout.strip())
        blocked = self._dispatch("aiwf-tester", "aiwf-test")
        reason = json.loads(blocked.stdout)["hookSpecificOutput"][
            "permissionDecisionReason"
        ]
        self.assertIn("aiwf-executor is still running", reason)

    def test_role_record_does_not_end_the_agent_dispatch(self):
        first = self._dispatch("aiwf-executor", "aiwf-implement")
        self._allowed_input(first)
        self._start("aiwf-executor", "executor-123")
        recorded = self._cli(
            "record", "implementation",
            "--summary", "implementation complete",
            "--command", "pytest -q",
            "--exit-code", "0",
        )
        self.assertEqual(recorded.returncode, 0, recorded.stderr)

        still_running = self._dispatch("aiwf-executor", "aiwf-implement")
        output = json.loads(still_running.stdout)
        self.assertEqual(
            output["hookSpecificOutput"]["permissionDecision"], "deny"
        )

        stopped = self._complete(
            "aiwf-executor",
            message="Agent was stopped after recording.",
            agent_id="executor-123",
        )

        self.assertEqual(stopped.returncode, 0, stopped.stderr)
        entries = [
            json.loads(line) for line in
            (self.tmp / ".aiwf/runtime/internal/agent-dispatch.jsonl")
            .read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(entries[-1]["status"], "cancelled")
        record = self._read_record()
        record["fix_loop"] = {"status": "open", "route": "executor"}
        self._write_record(record)
        status = self._cli("status", "--prompt")
        self.assertNotIn("SendMessage", status.stdout)

    def test_missing_role_record_prefers_resuming_the_original_agent(self):
        from aiwf_core.commands.flow import _task_next
        from aiwf_core.core.agent_runtime import (
            bind_dispatch_agent,
            finish_dispatch,
            start_dispatch,
        )

        agents = {
            "aiwf-executor": "executor-123",
            "aiwf-tester": "tester-123",
            "aiwf-reviewer": "reviewer-123",
        }
        for role, agent_id in agents.items():
            session_id = f"session-{role}"
            self.assertFalse(start_dispatch(
                self.tmp, "TASK-001", role, session_id,
                "PLAN-001", str(self.tmp),
            ))
            self.assertTrue(bind_dispatch_agent(
                self.tmp, role, agent_id,
                task_id="TASK-001", session_id=session_id,
            ))
            self.assertTrue(finish_dispatch(
                self.tmp, role,
                task_id="TASK-001", session_id=session_id,
                source="subagent_stop", agent_id=agent_id,
            ))

        task = {
            "id": "TASK-001",
            "requirements": {
                "executor_required": True,
                "tester_required": True,
                "reviewer_required": True,
            },
        }
        cases = (
            (
                {"implementation": {}, "testing": {}, "review": {}},
                "Executor", "resume aiwf-executor executor-123",
            ),
            (
                {
                    "implementation": {"implementation_ref": "abc"},
                    "testing": {}, "review": {},
                },
                "Tester", "resume aiwf-tester tester-123",
            ),
            (
                {
                    "implementation": {"implementation_ref": "abc"},
                    "testing": {"status": "passed", "tested_ref": "def"},
                    "review": {},
                },
                "Reviewer", "resume aiwf-reviewer reviewer-123",
            ),
        )
        for record, expected_role, expected_action in cases:
            with self.subTest(role=expected_role):
                role, action = _task_next(task, record, self.tmp)
                self.assertEqual(role, expected_role)
                self.assertIn(expected_action, action)
                self.assertIn("resumed original Claude session", action)
                self.assertIn("try once", action)
                self.assertIn("if unavailable or resume fails, dispatch a new", action)

    def test_agent_tool_result_keeps_dispatch_open_until_subagent_stop(self):
        first = self._dispatch("aiwf-executor", "aiwf-implement")
        self._allowed_input(first)

        returned = self._agent_return(
            "aiwf-executor",
            tool_response={
                "status": "async_launched",
                "isAsync": True,
                "content": "The agent is working in the background.",
            },
        )
        self.assertEqual(returned.returncode, 0, returned.stderr)
        context = json.loads(returned.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("running in the background for TASK-001", context)
        self.assertIn("do not wait for the other parallel Plans", context)
        blocked = self._dispatch("aiwf-executor", "aiwf-implement")
        output = json.loads(blocked.stdout)
        self.assertEqual(
            output["hookSpecificOutput"]["permissionDecision"], "deny"
        )

        completed = self._complete("aiwf-executor")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        allowed = self._dispatch("aiwf-executor", "aiwf-implement")
        self._allowed_input(allowed)

        entries = [
            json.loads(line) for line in
            (self.tmp / ".aiwf/runtime/internal/agent-dispatch.jsonl")
            .read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(entries[-2]["status"], "completed")
        self.assertEqual(entries[-2]["completion_source"], "subagent_stop")

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
        self.assertEqual(entries[-1]["completion_source"], "agent_cancelled")

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
