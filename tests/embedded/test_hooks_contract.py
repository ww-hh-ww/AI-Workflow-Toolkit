"""Focused hooks contract — direct script invocation with official Claude JSON."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 10


def _run_script(script_path, stdin_json, cwd):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    return subprocess.run([sys.executable, str(script_path)], input=stdin_json,
                          capture_output=True, text=True,
                          cwd=str(cwd), env=env, timeout=TIMEOUT)


def _run_script_without_pythonpath(script_path, stdin_json, cwd):
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    return subprocess.run([sys.executable, str(script_path)], input=stdin_json,
                          capture_output=True, text=True,
                          cwd=str(cwd), env=env, timeout=TIMEOUT)


class TestHooks(unittest.TestCase):
    """Hook scripts respond correctly to official Claude JSON input."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awhk_"))
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        subprocess.run([sys.executable, "-m", "aiwf_core.cli",
                        "install", "claude", "--force"],
                       capture_output=True, text=True,
                       cwd=str(cls.tmp), env=env, timeout=20)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        # Reset state files between tests
        from aiwf_core.core.state_schema import MVP_STATE_FILES
        for fn, dfn in MVP_STATE_FILES.items():
            p = self.tmp / ".aiwf" / fn
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(dfn(), indent=2) + "\n")
        status_fp = self.tmp / ".aiwf" / "runtime" / "internal" / "status-hook-last.json"
        status_fp.unlink(missing_ok=True)
        (self.tmp / ".aiwf/runtime/internal/temporary-ai-writes.json").unlink(missing_ok=True)
        records_dir = self.tmp / ".aiwf/records/tasks"
        shutil.rmtree(records_dir, ignore_errors=True)
        records_dir.mkdir(parents=True, exist_ok=True)
        for name in ("agent-dispatch.jsonl", "skill-loads.jsonl"):
            (self.tmp / ".aiwf/runtime/internal" / name).unlink(missing_ok=True)

    def _scope(self, tool, file_path, allowed_write=None, forbidden_write=None, agent_type="",
               task_requirements=None):
        if allowed_write is not None:
            s = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
            s["active_context_id"] = "CTX-001"
            s["active_task_id"] = "TASK-001"
            (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(s, indent=2))
            # allowed_write lives on the Plan now — create one
            (self.tmp / ".aiwf" / "state" / "plans.json").write_text(json.dumps({
                "plans": [{"plan_id": "PLAN-001", "allowed_write": allowed_write,
                           "goal_id": "GOAL-001", "target_goal_id": "GOAL-001"}]}, indent=2))
            task_entry = {"id": "TASK-001", "status": "active", "plan_id": "PLAN-001"}
            if task_requirements:
                task_entry["requirements"] = task_requirements
                task_md = self.tmp / ".aiwf" / "tasks" / "TASK-001.md"
                task_md.parent.mkdir(parents=True, exist_ok=True)
                task_md.write_text(
                    "---\n"
                    "id: TASK-001\n"
                    "type: task\n"
                    f"executor_required: {str(bool(task_requirements.get('executor_required'))).lower()}\n"
                    f"tester_required: {str(bool(task_requirements.get('tester_required'))).lower()}\n"
                    f"reviewer_required: {str(bool(task_requirements.get('reviewer_required'))).lower()}\n"
                    + (
                        "tester_write:\n"
                        + "".join(f"  - {p}\n" for p in task_requirements.get("tester_write", []))
                        if task_requirements.get("tester_write") else ""
                    )
                    +
                    "---\n\n"
                    "# TASK-001\n",
                    encoding="utf-8",
                )
            (self.tmp / ".aiwf" / "state" / "tasks.json").write_text(json.dumps(
                {"tasks": [task_entry]}, indent=2))
        inp = json.dumps({"session_id": "t", "cwd": str(self.tmp),
                          "tool_name": tool, "tool_input": {"file_path": file_path},
                          "agent_type": agent_type})
        return _run_script(self.tmp / "scripts" / "aiwf_scope_check.py", inp, self.tmp)

    def _bash(self, cmd, agent_type=""):
        inp = json.dumps({"session_id": "t", "tool_name": "Bash",
                         "tool_input": {"command": cmd},
                         "agent_type": agent_type})
        return _run_script(self.tmp / "scripts" / "aiwf_bash_guard.py", inp, self.tmp)

    def _status(self, cwd=None):
        inp = json.dumps({"session_id": "t", "cwd": str(cwd or self.tmp),
                         "hook_event_name": "UserPromptSubmit"})
        return _run_script(self.tmp / "scripts" / "aiwf_status.py", inp, self.tmp)

    def _stop(self):
        inp = json.dumps({"session_id": "t", "cwd": str(self.tmp),
                         "hook_event_name": "Stop"})
        return _run_script(self.tmp / "scripts" / "aiwf_review_gate.py", inp, self.tmp)

    def _subagent_stop(self, agent_type, message):
        inp = json.dumps({
            "session_id": "t",
            "cwd": str(self.tmp),
            "hook_event_name": "SubagentStop",
            "agent_type": agent_type,
            "last_assistant_message": message,
        })
        return _run_script(self.tmp / "scripts" / "aiwf_agent_log.py", inp, self.tmp)

    def _agent_result(self, agent_type, message, prompt=""):
        inp = json.dumps({
            "session_id": "t",
            "cwd": str(self.tmp),
            "hook_event_name": "PostToolUse",
            "tool_name": "Agent",
            "tool_input": {"subagent_type": agent_type, "prompt": prompt},
            "tool_response": {"content": message},
        })
        return _run_script(self.tmp / "scripts" / "aiwf_agent_log.py", inp, self.tmp)

    def _write_state(self, name, data):
        path = self.tmp / ".aiwf" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n")

    def _set_active_task(self, phase="implementing", record=None):
        self._write_state("state/tasks.json", {"tasks": [{
            "id": "TASK-001",
            "status": "active",
            "phase": phase,
            "worktree_path": str(self.tmp),
            "requirements": {
                "executor_required": True,
                "tester_required": True,
                "reviewer_required": True,
            },
        }]})
        self._write_task_record(record or {
            "task_id": "TASK-001",
            "implementation": {"task_id": "TASK-001"},
            "testing": {"task_id": "TASK-001", "status": "missing"},
            "review": {"task_id": "TASK-001", "result": "unknown"},
            "fix_loop": {"status": "none"},
        })

    def _write_task_record(self, record):
        record.setdefault("schema_version", 1)
        record.setdefault("task_id", "TASK-001")
        self._write_state("records/tasks/TASK-001.json", record)

    def _task_record(self):
        return json.loads(
            (self.tmp / ".aiwf/records/tasks/TASK-001.json").read_text()
        )

    # ── UserPromptSubmit ──

    def test_status_returns_additional_context(self):
        r = self._status()
        out = json.loads(r.stdout.strip())
        self.assertIn("additionalContext", out["hookSpecificOutput"])
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("[AIWF]", ctx)
        self.assertIn("Plan Before Work", ctx)
        self.assertIn("aiwf status --prompt", ctx)
        self.assertLess(len(ctx), 1000)

    def test_status_hook_is_silent_when_fingerprint_does_not_change(self):
        first = self._status()
        self.assertNotEqual(first.stdout.strip(), "")

        second = self._status()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(second.stdout.strip(), "")

    def test_status_prompt_acknowledges_state_for_the_next_user_prompt(self):
        self.assertNotEqual(self._status().stdout.strip(), "")
        self._set_active_task("testing", {
            "task_id": "TASK-001",
            "implementation": {"task_id": "TASK-001", "implementation_ref": "abc"},
            "testing": {"task_id": "TASK-001", "status": "missing"},
            "review": {"task_id": "TASK-001", "result": "unknown"},
            "fix_loop": {"status": "none"},
        })
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        status = subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", "status", "--prompt"],
            cwd=self.tmp, env=env, capture_output=True, text=True, timeout=TIMEOUT,
        )

        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("Do now:", status.stdout)
        self.assertEqual(self._status().stdout.strip(), "")

    def test_status_hook_announces_temporary_ai_writes_once(self):
        from aiwf_core.core.temporary_access import enable_temporary_ai_writes

        enable_temporary_ai_writes(self.tmp)
        first = self._status()
        context = json.loads(first.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Human enabled temporary AI project writes", context)
        self.assertIn("do not create a Task", context)
        self.assertEqual(self._status().stdout.strip(), "")

    def test_status_hook_reports_close_task_stage(self):
        self._set_active_task("implementing")
        self.assertNotEqual(self._status().stdout.strip(), "")

        self._set_active_task("closing", {
            "task_id": "TASK-001",
            "implementation": {"task_id": "TASK-001", "implementation_ref": "abc"},
            "testing": {"task_id": "TASK-001", "status": "passed", "commands": ["pytest"]},
            "review": {
                "task_id": "TASK-001", "result": "accepted", "closure_allowed": True,
            },
            "fix_loop": {"status": "none"},
        })

        task_doc = self.tmp / ".aiwf" / "tasks" / "TASK-001.md"
        task_doc.parent.mkdir(parents=True, exist_ok=True)
        task_doc.write_text("---\nid: TASK-001\n---\n\n# TASK-001\n", encoding="utf-8")

        r = self._status()
        out = json.loads(r.stdout.strip())
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("TASK-001 changed state", ctx)
        self.assertIn("aiwf status --prompt", ctx)

    def test_status_hook_names_a_suspended_task(self):
        self._set_active_task("suspended", {
            "task_id": "TASK-001",
            "implementation": {"task_id": "TASK-001", "implementation_ref": "abc"},
            "testing": {"task_id": "TASK-001", "status": "failed"},
            "review": {"task_id": "TASK-001", "result": "unknown"},
            "fix_loop": {"status": "open", "route": "executor"},
        })
        tasks = json.loads((self.tmp / ".aiwf/state/tasks.json").read_text())
        tasks["tasks"][0]["status"] = "suspended"
        tasks["tasks"][0]["phase"] = "suspended"
        self._write_state("state/tasks.json", tasks)

        result = self._status()

        context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("TASK-001 is suspended", context)
        self.assertIn("aiwf status --prompt", context)

    def test_status_hook_names_the_parallel_task_that_changed(self):
        other = self.tmp / "plan-b"
        self._write_state("state/tasks.json", {"tasks": [
            {
                "id": "TASK-A1", "status": "active", "phase": "implementing",
                "worktree_path": str(self.tmp),
            },
            {
                "id": "TASK-B1", "status": "active", "phase": "implementing",
                "worktree_path": str(other),
            },
        ]})
        for task_id in ("TASK-A1", "TASK-B1"):
            self._write_state(f"records/tasks/{task_id}.json", {
                "task_id": task_id,
                "implementation": {"task_id": task_id},
                "testing": {"task_id": task_id, "status": "missing"},
                "review": {"task_id": task_id, "result": "unknown"},
                "fix_loop": {"status": "none"},
            })
        self.assertNotEqual(self._status(cwd=self.tmp).stdout.strip(), "")

        record_b = json.loads(
            (self.tmp / ".aiwf/records/tasks/TASK-B1.json").read_text()
        )
        record_b["testing"]["status"] = "passed"
        self._write_state("records/tasks/TASK-B1.json", record_b)

        result = self._status(cwd=self.tmp)
        context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("TASK-B1 changed state", context)
        self.assertNotIn("TASK-A1 changed state", context)

    def test_closed_plan_document_is_read_only_for_ai_tools(self):
        self._write_state("state/plans.json", {
            "plans": [{"plan_id": "PLAN-HISTORY", "status": "closed"}],
        })

        result = self._scope("Edit", ".aiwf/plans/PLAN-HISTORY.md")
        output = json.loads(result.stdout.strip())

        self.assertEqual(
            output.get("hookSpecificOutput", {}).get("permissionDecision"), "deny"
        )
        self.assertIn("records completed work", output["hookSpecificOutput"]["permissionDecisionReason"])

    def test_closed_plan_document_is_read_only_for_bash_writes(self):
        self._write_state("state/plans.json", {
            "plans": [{"plan_id": "PLAN-HISTORY", "status": "closed"}],
        })

        result = self._bash("echo changed >> .aiwf/plans/PLAN-HISTORY.md")
        output = json.loads(result.stdout.strip())

        hook_output = output.get("hookSpecificOutput", {})
        self.assertEqual(hook_output.get("permissionDecision"), "deny")
        self.assertIn("records completed work", hook_output["permissionDecisionReason"])

    def test_executor_return_opens_planner_fix_loop_and_status_routes_planner(self):
        self._set_active_task("implementing")

        result = self._subagent_stop(
            "aiwf-executor",
            "RETURN_TO_PLANNER: representative inputs disprove the chosen mechanism\n\nVerified in src/main.rs.",
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        fix_loop = self._task_record()["fix_loop"]
        self.assertEqual(fix_loop["status"], "open")
        self.assertEqual(fix_loop["route"], "planner")
        self.assertEqual(fix_loop["source"], "executor")
        self.assertIn("disprove the chosen mechanism", fix_loop["reason"])

        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        status = subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", "status", "--prompt"],
            capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT,
        )
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("Required skills: /aiwf-planner", status.stdout)
        self.assertIn("Planner decision", status.stdout)

    def test_normal_agent_report_does_not_open_fix_loop(self):
        self._set_active_task("implementing")
        result = self._subagent_stop("aiwf-executor", "Implemented and verified the task.")
        self.assertEqual(result.returncode, 0, result.stderr)
        fix_loop = self._task_record()["fix_loop"]
        self.assertNotEqual(fix_loop.get("status"), "open")

    def test_claude_agent_posttooluse_is_not_treated_as_completion(self):
        self._set_active_task("implementing")

        for role in ("aiwf-executor", "aiwf-tester", "aiwf-reviewer"):
            with self.subTest(role=role):
                result = self._agent_result(role, "Agent launched in the background.")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse(result.stdout.strip())

    def test_parallel_agent_launches_do_not_emit_false_return_messages(self):
        self._set_active_task("implementing")
        tasks_path = self.tmp / ".aiwf/state/tasks.json"
        state = json.loads(tasks_path.read_text())
        other = self.tmp / "plan-b"
        state["tasks"].append({
            "id": "TASK-B1", "status": "active", "phase": "testing",
            "worktree_path": str(other), "requirements": {},
        })
        tasks_path.write_text(json.dumps(state, indent=2) + "\n")
        self._write_state("records/tasks/TASK-B1.json", {
            "task_id": "TASK-B1",
            "implementation": {"task_id": "TASK-B1", "implementation_ref": "abc"},
            "testing": {"task_id": "TASK-B1", "status": "passed"},
            "review": {"task_id": "TASK-B1", "result": "unknown"},
            "fix_loop": {"status": "none"},
        })

        result = self._agent_result(
            "aiwf-tester",
            "Testing completed.",
            prompt=f"Test TASK-B1 in assigned worktree {other}.",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(result.stdout.strip())

    def test_subagent_stop_routes_external_finding(self):
        self._set_active_task("reviewing")
        result = self._subagent_stop(
            "aiwf-tester",
            "EXTERNAL_FINDING: service mode does not start the real pipeline",
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        fix_loop = self._task_record()["fix_loop"]
        self.assertEqual(fix_loop["route"], "planner")
        self.assertEqual(fix_loop["source"], "tester")
        self.assertIn("service mode", fix_loop["reason"])

    def test_reviewer_posttooluse_does_not_duplicate_native_return(self):
        self._set_active_task("closing")

        result = self._agent_result(
            "aiwf-reviewer",
            "REVIEW_REPORT\nAccepted after checking the final tested snapshot.",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(result.stdout.strip())

    # ── Stop ──

    def test_fresh_install_ordinary_stop_allows(self):
        r = self._stop()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn('"decision": "block"', r.stdout)
        self.assertEqual(r.stdout.strip(), "")

    def test_open_fix_loop_outside_closing_does_not_block_stop(self):
        self._set_active_task("testing", {
            "task_id": "TASK-001",
            "implementation": {"task_id": "TASK-001", "implementation_ref": "abc"},
            "testing": {"task_id": "TASK-001", "status": "failed"},
            "review": {"task_id": "TASK-001", "result": "unknown"},
            "fix_loop": {"status": "open", "route": "executor"},
        })

        result = self._stop()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "")

    def test_reviewed_active_task_cannot_stop_before_task_close(self):
        self._set_active_task("closing", {
            "task_id": "TASK-001",
            "implementation": {"task_id": "TASK-001", "implementation_ref": "abc"},
            "testing": {
                "task_id": "TASK-001", "status": "passed", "commands": ["pytest"],
                "tested_ref": "def",
            },
            "review": {
                "task_id": "TASK-001", "result": "accepted", "closure_allowed": True,
                "blockers": [], "reviewed_ref": "def",
            },
            "fix_loop": {"status": "none"},
        })

        result = self._stop()

        self.assertIn('"decision": "block"', result.stdout)
        self.assertIn("run aiwf status --prompt", result.stdout)

    def test_l1_plus_planner_main_project_write_is_blocked_before_implementation(self):
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["phase"] = "executing"
        state["active_context_id"] = "CTX-001"
        state["active_task_id"] = "TASK-001"
        self._write_state("state/state.json", state)
        self._write_state("state/plans.json", {
            "plans": [{"plan_id": "PLAN-001", "allowed_write": ["src/"],
                       "goal_id": "GOAL-001", "target_goal_id": "GOAL-001"}],
        })
        self._write_state("state/tasks.json", {
            "tasks": [{"id": "TASK-001", "status": "active", "plan_id": "PLAN-001",
                       "requirements": {"executor_required": True}}],
        })

        r = self._scope("Write", "src/lib.rs", allowed_write=["src/"],
                        task_requirements={"executor_required": True})
        out = json.loads(r.stdout.strip())

        self.assertEqual(out.get("hookSpecificOutput", {}).get("permissionDecision"), "deny")
        self.assertIn("executor", out["hookSpecificOutput"]["permissionDecisionReason"].lower())

    def test_l1_plus_planner_main_project_write_is_blocked_mid_task_testing(self):
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["phase"] = "testing"
        self._write_state("state/state.json", state)

        r = self._scope("Write", "src/lib.rs", allowed_write=["src/"],
                        task_requirements={"executor_required": True})
        out = json.loads(r.stdout.strip())

        self.assertEqual(out.get("hookSpecificOutput", {}).get("permissionDecision"), "deny")
        reason = out["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("executor", reason.lower())

    def test_l1_plus_executor_subagent_project_write_is_allowed(self):
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["phase"] = "executing"
        state["active_context_id"] = "CTX-001"
        state["active_task_id"] = "TASK-001"
        self._write_state("state/state.json", state)
        self._write_state("state/plans.json", {
            "plans": [{"plan_id": "PLAN-001", "allowed_write": ["src/"],
                       "goal_id": "GOAL-001", "target_goal_id": "GOAL-001"}],
        })
        self._write_state("state/tasks.json", {
            "tasks": [{"id": "TASK-001", "status": "active", "plan_id": "PLAN-001",
                       "requirements": {"executor_required": True}}],
        })

        r = self._scope("Write", "src/lib.rs", allowed_write=["src/"],
                        task_requirements={"executor_required": True},
                        agent_type="aiwf-executor")

        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")

    def test_tester_can_write_test_asset_when_executor_required(self):
        r = self._scope(
            "Write",
            "tests/task-002-validation.spec.js",
            allowed_write=["src/", "tests/"],
            task_requirements={
                "executor_required": True,
                "tester_required": True,
                "reviewer_required": True,
            },
            agent_type="aiwf-tester",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")

    def test_tester_cannot_write_implementation_when_executor_required(self):
        r = self._scope(
            "Write",
            "src/lib.rs",
            allowed_write=["src/", "tests/"],
            task_requirements={
                "executor_required": True,
                "tester_required": True,
                "reviewer_required": True,
            },
            agent_type="aiwf-tester",
        )
        out = json.loads(r.stdout.strip())
        self.assertEqual(out.get("hookSpecificOutput", {}).get("permissionDecision"), "deny")
        self.assertIn("test/verification assets", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_tester_write_frontmatter_allows_distributed_test_asset(self):
        r = self._scope(
            "Write",
            "crates/agent/src/behavior_validation.rs",
            allowed_write=["crates/"],
            task_requirements={
                "executor_required": True,
                "tester_required": True,
                "reviewer_required": True,
                "tester_write": ["crates/*/src/*_validation.rs"],
            },
            agent_type="aiwf-tester",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")

    def test_tester_write_frontmatter_blocks_unlisted_test_asset(self):
        r = self._scope(
            "Write",
            "tests/unlisted.spec.js",
            allowed_write=["tests/"],
            task_requirements={
                "executor_required": True,
                "tester_required": True,
                "reviewer_required": True,
                "tester_write": ["crates/*/src/*_validation.rs"],
            },
            agent_type="aiwf-tester",
        )
        out = json.loads(r.stdout.strip())
        self.assertEqual(out.get("hookSpecificOutput", {}).get("permissionDecision"), "deny")
        self.assertIn("test/verification assets", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_reviewer_project_write_is_not_controlled_by_write_policy(self):
        r = self._scope(
            "Write",
            "tests/review-fix.spec.js",
            allowed_write=["tests/"],
            task_requirements={
                "executor_required": False,
                "tester_required": True,
                "reviewer_required": True,
            },
            agent_type="aiwf-reviewer",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")

    def test_l1_plus_fix_loop_project_repair_requires_first_executor_evidence(self):
        self._write_task_record({
            "task_id": "TASK-001",
            "implementation": {"task_id": "TASK-001"},
            "testing": {"task_id": "TASK-001", "status": "missing"},
            "review": {"task_id": "TASK-001", "result": "unknown"},
            "fix_loop": {
                "status": "open",
                "route": "executor",
                "required_fixes": ["src/lib.rs"],
                "required_verification": ["cargo test"],
            },
        })

        r = self._scope("Write", "src/lib.rs", allowed_write=["src/"],
                        task_requirements={"executor_required": True})
        out = json.loads(r.stdout.strip())

        self.assertEqual(out.get("hookSpecificOutput", {}).get("permissionDecision"), "deny")
        self.assertIn("first implementation", out["hookSpecificOutput"]["permissionDecisionReason"])

        allowed = self._scope("Write", "src/lib.rs", allowed_write=["src/"],
                             task_requirements={"executor_required": True},
                             agent_type="aiwf-executor")
        self.assertEqual(allowed.returncode, 0, allowed.stderr)
        self.assertEqual(allowed.stdout.strip(), "")

    def test_planner_can_inline_repair_after_executor_evidence_exists(self):
        self._write_task_record({
            "task_id": "TASK-001",
            "implementation": {"task_id": "TASK-001", "implementation_ref": "abc"},
            "testing": {"task_id": "TASK-001", "status": "missing"},
            "review": {"task_id": "TASK-001", "result": "unknown"},
            "fix_loop": {
                "status": "open", "route": "planner", "required_fixes": ["src/lib.rs"],
            },
        })
        r = self._scope("Write", "src/lib.rs", allowed_write=["src/"],
                        task_requirements={"executor_required": True})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")

    def test_planner_project_write_allowed_after_task_executor_evidence_exists(self):
        self._write_task_record({
            "task_id": "TASK-001",
            "implementation": {"task_id": "TASK-001", "implementation_ref": "abc"},
            "testing": {"task_id": "TASK-001", "status": "missing"},
            "review": {"task_id": "TASK-001", "result": "unknown"},
            "fix_loop": {"status": "none"},
        })
        r = self._scope("Write", "src/followup.rs", allowed_write=["src/"],
                        task_requirements={"executor_required": True})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")

    def test_active_task_contract_conflict_routes_to_human_interrupt(self):
        result = self._scope(
            "Edit",
            ".aiwf/tasks/TASK-001.md",
            allowed_write=["src/"],
            task_requirements={"executor_required": True},
            agent_type="planner-main",
        )

        output = json.loads(result.stdout)
        reason = output["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("aiwf task interrupt", reason)
        self.assertIn("revise and sync the contract", reason)
        self.assertIn("Do not leave the choice to Executor", reason)

    def test_reviewing_stage_without_active_close_allows_stop(self):
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["phase"] = "reviewing"
        self._write_state("state/state.json", state)
        self._write_state("records/evidence.jsonl", {"records": []})
        self._write_state("records/testing.jsonl", {"status": "missing"})
        self._write_state("records/review.jsonl", {
            "result": "unknown",
            "closure_allowed": False,
            "cleanup_status": "unknown",
        })

        r = self._stop()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn('"decision": "block"', r.stdout)
        self.assertEqual(r.stdout.strip(), "")

    def test_status_with_execution_plan_without_task_is_healthy(self):
        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["request_mode"] = "execution"
        state["active_plan_id"] = "TASK-PLAN"
        state["active_task_id"] = None
        state_path.write_text(json.dumps(state, indent=2))

        r = self._status()
        ctx = json.loads(r.stdout.strip())["hookSpecificOutput"]["additionalContext"]

        # UserPromptSubmit is only a short lifecycle nudge. Detailed health
        # and routing live in `aiwf status --prompt`.
        self.assertIn("Plan Before Work", ctx)
        self.assertIn("aiwf status --prompt", ctx)

    def test_l2_review_json_must_use_cli(self):
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["active_task_id"] = "TASK-001"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(state, indent=2))
        r = self._scope("Write", ".aiwf/records/review.json")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("aiwf CLI", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_generated_hooks_run_without_pythonpath(self):
        inp = json.dumps({"session_id": "t", "cwd": str(self.tmp),
                          "tool_name": "Write",
                          "tool_input": {"file_path": ".aiwf/state/state.json"}})
        r = _run_script_without_pythonpath(
            self.tmp / "scripts" / "aiwf_scope_check.py", inp, self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("ModuleNotFoundError", r.stderr)

    # ── Scope check ──

    def test_write_outside_scope_denied(self):
        r = self._scope("Write", "danger/x.py", allowed_write=["src/"], agent_type="aiwf-executor")
        # V2: scope check no longer blocks on Plan.allowed_write;
        # project write with active task is allowed regardless of allowed_write directory.
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")

    def test_write_inside_scope_allowed(self):
        r = self._scope("Write", "src/main.py", allowed_write=["src/"], agent_type="aiwf-executor")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")

    def test_forbidden_write_always_denied(self):
        r = self._scope(
            "Write", ".env", allowed_write=["src/"], forbidden_write=[".env"],
            task_requirements={"executor_required": False},
        )
        # V2: pre-tool scope check no longer blocks on forbidden_write;
        # forbidden_write check moved to post-tool check_and_record_scope_violations.
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")

    def test_no_scope_denies_project_writes_without_active_task(self):
        r = self._scope("Write", "anywhere.py")
        self.assertEqual(r.returncode, 0)
        out = json.loads(r.stdout.strip())
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_temporary_write_permission_reaches_delegated_agents(self):
        from aiwf_core.core.temporary_access import enable_temporary_ai_writes

        enable_temporary_ai_writes(self.tmp)
        for role in ("general-purpose", "aiwf-executor"):
            with self.subTest(role=role):
                result = self._scope("Write", "lesson.html", agent_type=role)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), "")

        denied = self._scope(
            "Write", ".aiwf/tasks/TASK-999.md", agent_type="general-purpose",
        )
        output = json.loads(denied.stdout.strip())
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn(
            "owned by Planner",
            output["hookSpecificOutput"]["permissionDecisionReason"],
        )

    def test_ai_cannot_edit_human_command_policy(self):
        result = self._scope(
            "Write", ".aiwf/config/command-policy.json",
            agent_type="aiwf-executor",
        )
        output = json.loads(result.stdout.strip())
        reason = output["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("human-only commands", reason)

    def test_only_planner_may_edit_normal_aiwf_config(self):
        denied = self._scope(
            "Edit", ".aiwf/config/write-policy.json",
            agent_type="aiwf-tester",
        )
        output = json.loads(denied.stdout.strip())
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("owned by Planner", output["hookSpecificOutput"]["permissionDecisionReason"])

        allowed = self._scope(
            "Edit", ".aiwf/config/write-policy.json",
            agent_type="planner-main",
        )
        self.assertEqual(allowed.returncode, 0, allowed.stderr)
        self.assertEqual(allowed.stdout.strip(), "")

    def test_only_planner_may_edit_aiwf_memory(self):
        for role in ("aiwf-executor", "aiwf-tester", "aiwf-reviewer", "aiwf-architect"):
            with self.subTest(role=role):
                denied = self._scope(
                    "Edit", ".aiwf/memory/project-facts.md", agent_type=role,
                )
                output = json.loads(denied.stdout.strip())
                self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
                self.assertIn(
                    "owned by Planner",
                    output["hookSpecificOutput"]["permissionDecisionReason"],
                )

        allowed = self._scope(
            "Edit", ".aiwf/memory/project-facts.md", agent_type="planner-main",
        )
        self.assertEqual(allowed.returncode, 0, allowed.stderr)
        self.assertEqual(allowed.stdout.strip(), "")

    # ── Bash guard ──

    def test_rm_rf_blocked(self):
        self.assertIn("deny", self._bash("rm -rf /").stdout)

    def test_sudo_blocked(self):
        self.assertIn("deny", self._bash("sudo reboot").stdout)

    def test_git_reset_hard_blocked(self):
        self.assertIn("deny", self._bash("git reset --hard HEAD").stdout)

    def test_npm_test_allowed(self):
        r = self._bash("npm test")
        self.assertNotIn("deny", r.stdout)

    def test_pytest_allowed(self):
        r = self._bash("pytest -xvs tests/")
        self.assertNotIn("deny", r.stdout)

    def test_bash_write_to_state_json_blocked(self):
        r = self._bash("python3 -c \"open('.aiwf/state/state.json','w')\"")
        self.assertIn("deny", r.stdout)
        self.assertIn("mechanical truth", r.stdout)

    def test_git_commit_is_reserved_for_task_close_while_task_active(self):
        self._set_active_task("implementing")
        r = self._bash("git commit -m 'bypass review'")
        self.assertIn("deny", r.stdout)
        self.assertIn("aiwf task close", r.stdout)

    def test_ai_cannot_stage_files_while_task_active(self):
        self._set_active_task("implementing")
        for command in (
            "git add -A",
            "git add .aiwf/state/tasks.json",
            "cd src && git stage feature.py",
        ):
            with self.subTest(command=command):
                result = self._bash(command)
                self.assertIn("deny", result.stdout)
                self.assertIn("Do not stage files", result.stdout)

    def test_bash_write_to_fix_loop_blocked(self):
        r = self._bash("echo '{}' > .aiwf/state/fix-loop.json")
        self.assertIn("deny", r.stdout)
        self.assertIn("mechanical truth", r.stdout)

    def test_bash_read_of_state_json_also_blocked(self):
        # Reads are also blocked — use Read tool instead.
        r = self._bash("cat .aiwf/state/state.json")
        self.assertIn("deny", r.stdout)

    def test_git_can_stage_cli_generated_truth_without_an_active_task(self):
        for command in (
            "git add .aiwf/state/plans.json .aiwf/records/events.json",
            "cd '/tmp/project with spaces' && git add .aiwf/state/plans.json",
            "git diff -- .aiwf/state/plans.json",
        ):
            with self.subTest(command=command):
                result = self._bash(command)
                self.assertNotIn("deny", result.stdout)

        chained_write = self._bash(
            "git add .aiwf/state/plans.json && printf '{}' > .aiwf/state/plans.json"
        )
        self.assertIn("deny", chained_write.stdout)

    def test_bash_without_mechanical_truth_path_allowed(self):
        r = self._bash("python3 -c 'print(1+1)'")
        self.assertNotIn("deny", r.stdout)

    def test_project_shell_write_requires_task_or_human_temporary_permission(self):
        from aiwf_core.core.temporary_access import enable_temporary_ai_writes

        denied = self._bash("mv old.txt new.txt", agent_type="main")
        self.assertIn("deny", denied.stdout)
        self.assertIn("active Task", denied.stdout)

        enable_temporary_ai_writes(self.tmp)
        allowed = self._bash("mv old.txt new.txt", agent_type="main")
        self.assertNotIn("deny", allowed.stdout)

        self_enabled = self._bash(
            "rm .aiwf/runtime/internal/temporary-ai-writes.json",
            agent_type="main",
        )
        self.assertIn("deny", self_enabled.stdout)
        self.assertIn("human", self_enabled.stdout)

    def test_bash_modify_quality_review_blocked(self):
        r = self._bash("jq '.verdict=\"PASS\"' .aiwf/records/review.jsonl")
        self.assertIn("deny", r.stdout)

    def test_bash_cannot_rewrite_command_policy(self):
        result = self._bash("printf '{}' > .aiwf/config/command-policy.json")
        self.assertIn("deny", result.stdout)
        self.assertIn("human-only commands", result.stdout)

    def test_non_planner_bash_cannot_rewrite_aiwf_config(self):
        result = self._bash(
            "sed -i '' 's/true/false/' .aiwf/config/write-policy.json",
            agent_type="aiwf-tester",
        )
        self.assertIn("deny", result.stdout)
        self.assertIn("owned by Planner", result.stdout)

    def test_non_planner_bash_cannot_rewrite_aiwf_memory(self):
        denied = self._bash(
            "printf 'fact' >> .aiwf/memory/project-facts.md",
            agent_type="aiwf-executor",
        )
        self.assertIn("deny", denied.stdout)
        self.assertIn("owned by Planner", denied.stdout)

        allowed = self._bash(
            "printf 'fact' >> .aiwf/memory/project-facts.md",
            agent_type="planner-main",
        )
        self.assertNotIn("deny", allowed.stdout)

        read_only = self._bash(
            "cat .aiwf/memory/project-facts.md > /tmp/project-facts-copy.md",
            agent_type="aiwf-executor",
        )
        self.assertNotIn("deny", read_only.stdout)

    def test_human_only_commands_remain_blocked_if_policy_is_empty(self):
        path = self.tmp / ".aiwf/config/command-policy.json"
        original = path.read_text(encoding="utf-8")
        try:
            path.write_text('{"schema_version": 1, "deny": []}\n', encoding="utf-8")
            for command in (
                "aiwf task force-close",
                "aiwf task interrupt",
                "aiwf fixloop continue",
            ):
                result = self._bash(command)
                self.assertIn("deny", result.stdout)
                self.assertIn("Human action is required", result.stdout)
        finally:
            path.write_text(original, encoding="utf-8")

    def test_invalid_command_policy_fails_closed(self):
        path = self.tmp / ".aiwf/config/command-policy.json"
        original = path.read_text(encoding="utf-8")
        try:
            path.write_text("{invalid", encoding="utf-8")
            result = self._bash("pytest -q")
            self.assertIn("deny", result.stdout)
            self.assertIn("command-policy.json is invalid", result.stdout)
        finally:
            path.write_text(original, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
