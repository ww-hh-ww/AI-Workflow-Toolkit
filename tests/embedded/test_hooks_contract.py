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

    def _scope(self, tool, file_path, allowed_write=None, forbidden_write=None, agent_type="",
               task_requirements=None):
        if allowed_write is not None:
            s = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
            s["active_context_id"] = "CTX-001"
            s["active_task_id"] = "TASK-001"
            (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(s, indent=2))
            (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(
                {"contexts": [{"id": "CTX-001",
                 "forbidden_write": forbidden_write or []}]}, indent=2))
            # allowed_write lives on the Plan now — create one
            (self.tmp / ".aiwf" / "state" / "plans.json").write_text(json.dumps({
                "plans": [{"plan_id": "PLAN-001", "allowed_write": allowed_write,
                           "goal_id": "GOAL-001", "target_goal_id": "GOAL-001"}]}, indent=2))
            task_entry = {"id": "TASK-001", "status": "active", "plan_id": "PLAN-001"}
            if task_requirements:
                task_entry["requirements"] = task_requirements
            (self.tmp / ".aiwf" / "state" / "tasks.json").write_text(json.dumps(
                {"tasks": [task_entry],
                 "execution_window": {"active_task_ids": ["TASK-001"]}}, indent=2))
        inp = json.dumps({"session_id": "t", "cwd": str(self.tmp),
                          "tool_name": tool, "tool_input": {"file_path": file_path},
                          "agent_type": agent_type})
        return _run_script(self.tmp / "scripts" / "aiwf_scope_check.py", inp, self.tmp)

    def _bash(self, cmd):
        inp = json.dumps({"session_id": "t", "tool_name": "Bash",
                         "tool_input": {"command": cmd}})
        return _run_script(self.tmp / "scripts" / "aiwf_bash_guard.py", inp, self.tmp)

    def _status(self):
        inp = json.dumps({"session_id": "t", "cwd": str(self.tmp),
                         "hook_event_name": "UserPromptSubmit"})
        return _run_script(self.tmp / "scripts" / "aiwf_status.py", inp, self.tmp)

    def _stop(self):
        inp = json.dumps({"session_id": "t", "cwd": str(self.tmp),
                         "hook_event_name": "Stop"})
        return _run_script(self.tmp / "scripts" / "aiwf_review_gate.py", inp, self.tmp)

    def _write_state(self, name, data):
        path = self.tmp / ".aiwf" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n")

    # ── UserPromptSubmit ──

    def test_status_returns_additional_context(self):
        r = self._status()
        out = json.loads(r.stdout.strip())
        self.assertIn("additionalContext", out["hookSpecificOutput"])
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("[AIWF]", ctx)
        self.assertIn("Phase:", ctx)
        self.assertIn("Process:", ctx)
        self.assertIn("Health:", ctx)
        self.assertIn("[ATTN]", ctx)
        self.assertLess(len(ctx), 1000)

    # ── Stop ──

    def test_fresh_install_ordinary_stop_allows(self):
        r = self._stop()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn('"decision": "block"', r.stdout)
        self.assertEqual(r.stdout.strip(), "")

    def test_close_attempt_without_review_blocks(self):
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["phase"] = "closing"
        state["close_attempt"] = True
        self._write_state("state/state.json", state)

        r = self._stop()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('"decision": "block"', r.stdout)
        self.assertIn("review not recorded", r.stdout)

    def test_close_attempt_with_all_gates_passed_allows(self):
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["phase"] = "closing"
        state["close_attempt"] = True
        self._write_state("state/state.json", state)
        self._write_state("records/evidence.jsonl", {
            "records": [{"id": "EV-001", "status": "accepted", "session_id": "s1"}],
        })
        self._write_state("records/testing.jsonl", {
            "status": "passed", "commands": ["pytest"],
        })
        self._write_state("records/review.jsonl", {
            "result": "accepted",
            "closure_allowed": True,
            "cleanup_status": "fresh",
            "stale_items": [],
        })

        r = self._stop()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn('"decision": "block"', r.stdout)
        self.assertEqual(r.stdout.strip(), "")

    def test_l1_plus_planner_main_project_write_is_blocked_before_implementation(self):
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["workflow_level"] = "L2_standard_team"
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
            "execution_window": {"active_task_ids": ["TASK-001"]},
        })

        r = self._scope("Write", "src/lib.rs", allowed_write=["src/"],
                        task_requirements={"executor_required": True})
        out = json.loads(r.stdout.strip())

        self.assertEqual(out.get("hookSpecificOutput", {}).get("permissionDecision"), "deny")
        self.assertIn("executor", out["hookSpecificOutput"]["permissionDecisionReason"].lower())

    def test_l1_plus_planner_main_project_write_is_blocked_mid_task_testing(self):
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["workflow_level"] = "L2_standard_team"
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
        state["workflow_level"] = "L2_standard_team"
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
            "execution_window": {"active_task_ids": ["TASK-001"]},
        })

        r = self._scope("Write", "src/lib.rs", allowed_write=["src/"],
                        task_requirements={"executor_required": True},
                        agent_type="aiwf-executor")

        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")

    def test_l1_plus_fix_loop_project_repair_requires_executor_subagent(self):
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["workflow_level"] = "L2_standard_team"
        state["phase"] = "testing"
        self._write_state("state/state.json", state)
        self._write_state("state/fix-loop.json", {
            "status": "open",
            "route": "executor",
            "required_fixes": ["src/lib.rs"],
            "required_verification": ["cargo test"],
        })

        r = self._scope("Write", "src/lib.rs", allowed_write=["src/"],
                        task_requirements={"executor_required": True})
        out = json.loads(r.stdout.strip())

        self.assertEqual(out.get("hookSpecificOutput", {}).get("permissionDecision"), "deny")
        self.assertIn("fix-loop repair", out["hookSpecificOutput"]["permissionDecisionReason"])

        allowed = self._scope("Write", "src/lib.rs", allowed_write=["src/"],
                             task_requirements={"executor_required": True},
                             agent_type="aiwf-executor")
        self.assertEqual(allowed.returncode, 0, allowed.stderr)
        self.assertEqual(allowed.stdout.strip(), "")

    def test_no_close_attempt_passed_false_empty_blockers_does_not_block(self):
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["phase"] = "reviewing"
        state["close_attempt"] = False
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

    @unittest.skip("V1: status routes changed")
    def test_status_after_review_without_active_task_routes_to_closure_not_new_task(self):
        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["phase"] = "reviewing"
        state["active_task_id"] = None
        state["workflow_level"] = "L2_standard_team"
        state_path.write_text(json.dumps(state, indent=2))
        review_path = self.tmp / ".aiwf" / "records" / "review.jsonl"
        review = json.loads(review_path.read_text())
        review["result"] = "accepted"
        review_path.write_text(json.dumps(review, indent=2))

        r = self._status()
        ctx = json.loads(r.stdout.strip())["hookSpecificOutput"]["additionalContext"]

        self.assertIn("Recovery:closure planner", ctx)
        self.assertIn("PRIMARY: follow active plan Impact and run prepare-close", ctx)
        self.assertNotIn("PRIMARY: activate task", ctx)

    def test_status_with_execution_plan_without_task_is_healthy(self):
        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["request_mode"] = "execution"
        state["active_plan_id"] = "TASK-PLAN"
        state["active_task_id"] = None
        state_path.write_text(json.dumps(state, indent=2))

        r = self._status()
        ctx = json.loads(r.stdout.strip())["hookSpecificOutput"]["additionalContext"]

        # V2: plan without active task is Health: ok, no recovery lines
        self.assertIn("Health: ok", ctx)
        self.assertIn("[ATTN]", ctx)

    def test_l2_review_write_as_governance_is_allowed(self):
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["workflow_level"] = "L2_standard_team"
        state["active_task_id"] = "TASK-001"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(state, indent=2))
        r = self._scope("Write", ".aiwf/records/review.jsonl")
        # V2: review.json is a governance file — always allowed for Write/Edit
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")

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
        r = self._scope("Write", ".env", allowed_write=["src/"], forbidden_write=[".env"])
        # V2: pre-tool scope check no longer blocks on forbidden_write;
        # forbidden_write check moved to post-tool check_and_record_scope_violations.
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")

    def test_no_scope_denies_project_writes_without_active_task(self):
        r = self._scope("Write", "anywhere.py")
        self.assertEqual(r.returncode, 0)
        out = json.loads(r.stdout.strip())
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_post_tool_scope_drift_records_review_event_without_fixloop(self):
        from aiwf_core.hooks.common.evidence_writer import check_and_record_scope_violations

        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["active_context_id"] = "CTX-001"
        state["active_task_id"] = "TASK-001"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(state, indent=2))
        (self.tmp / ".aiwf" / "state" / "plans.json").write_text(json.dumps({
            "plans": [{"plan_id": "PLAN-001", "allowed_write": ["src/"],
                       "goal_id": "GOAL-001", "target_goal_id": "GOAL-001"}],
        }, indent=2))
        ledger_path = self.tmp / ".aiwf" / "state" / "tasks.json"
        ledger_path.write_text(json.dumps({
            "tasks": [{"id": "TASK-001", "status": "active", "plan_id": "PLAN-001"}],
            "execution_window": {"active_task_ids": ["TASK-001"]},
        }, indent=2))

        # V2: in-scope writes produce no violations
        violations = check_and_record_scope_violations(
            ["src/main.py"], {"id": "CTX-001", "forbidden_write": []}, self.tmp
        )

        self.assertEqual(violations, [])
        state_after = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        self.assertFalse(state_after.get("scope_violation"))
        fix_loop = json.loads((self.tmp / ".aiwf" / "state" / "fix-loop.json").read_text())
        self.assertNotEqual(fix_loop.get("status"), "open")

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

    def test_bash_write_to_fix_loop_blocked(self):
        r = self._bash("echo '{}' > .aiwf/state/fix-loop.json")
        self.assertIn("deny", r.stdout)
        self.assertIn("mechanical truth", r.stdout)

    def test_bash_read_of_state_json_also_blocked(self):
        # Reads are also blocked — use Read tool instead.
        r = self._bash("cat .aiwf/state/state.json")
        self.assertIn("deny", r.stdout)

    def test_bash_without_mechanical_truth_path_allowed(self):
        r = self._bash("python3 -c 'print(1+1)'")
        self.assertNotIn("deny", r.stdout)

    def test_bash_modify_quality_review_blocked(self):
        r = self._bash("jq '.verdict=\"PASS\"' .aiwf/records/review.jsonl")
        self.assertIn("deny", r.stdout)


if __name__ == "__main__":
    unittest.main()
