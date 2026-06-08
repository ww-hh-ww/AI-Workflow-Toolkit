"""Task plan artifact: human continuity without becoming mechanical truth."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 15


class TestTaskPlanArtifact(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="awplan_"))
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                           capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        (self.tmp / ".aiwf" / "reports" / "当前状态.md").unlink(missing_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, *args):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run([sys.executable, "-m", "aiwf_core.cli", *args],
                              capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    def _run_ok(self, *args):
        r = self._run(*args)
        self.assertEqual(r.returncode, 0, f"{args}\nstdout={r.stdout}\nstderr={r.stderr}")
        return r

    def test_plan_create_writes_human_artifact_and_active_plan_id(self):
        self._run_ok("plan", "create", "--task-id", "TASK-001", "--context-id", "CTX-001", "--title", "Build route")

        plan = self.tmp / ".aiwf" / "plans" / "TASK-001.md"
        self.assertTrue(plan.exists())
        text = plan.read_text()
        self.assertIn("not AIWF mechanical truth", text)
        self.assertIn("TASK-001", text)
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        self.assertEqual(state["active_plan_id"], "TASK-001")

    def test_execution_plan_without_active_task_routes_to_plan_only_drift(self):
        from aiwf_core.core.process_contract import planner_process_guidance

        self._run_ok("plan", "create", "--task-id", "TASK-001", "--context-id", "CTX-001", "--title", "Build route")

        guidance = planner_process_guidance(str(self.tmp))

        self.assertEqual(guidance["recovery"]["state"], "blocked")
        self.assertEqual(guidance["recovery"]["category"], "plan_only_drift")
        self.assertEqual(guidance["recovery"]["owner"], "planner")
        self.assertIn("TASK-001", guidance["recovery"]["primary"])
        self.assertTrue(any("Plan-only drift" in item for item in guidance["required_now"]))
        self.assertTrue(any("rewriting the plan" in item for item in guidance["recovery"]["forbidden"]))

    def test_non_execution_plan_remains_open_discussion_not_plan_only_drift(self):
        from aiwf_core.core.process_contract import planner_process_guidance

        self._run_ok("plan", "create", "--task-id", "TASK-001", "--context-id", "CTX-001", "--title", "Build route")
        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["request_mode"] = "discussion"
        state_path.write_text(json.dumps(state, indent=2) + "\n")

        guidance = planner_process_guidance(str(self.tmp))

        self.assertEqual(guidance["recovery"]["state"], "open")
        self.assertEqual(guidance["recovery"]["category"], "discussion")
        self.assertFalse(any("Plan-only drift" in item for item in guidance["required_now"]))

    def test_plan_update_treats_backslash_content_as_literal_text(self):
        self._run_ok("plan", "create", "--task-id", "TASK-001", "--context-id", "CTX-001", "--title", "Build route")
        content = r"Preserve regex capture text: \1 and \g<name> are literal notes."

        self._run_ok("plan", "update", "--task-id", "TASK-001", "--section", "scope", "--content", content)

        plan = (self.tmp / ".aiwf" / "plans" / "TASK-001.md").read_text()
        self.assertIn(content, plan)

    def test_plan_checklist_cannot_replace_mechanical_close_gates(self):
        from aiwf_core.core.task_ledger import activate_task, active_task_completion_blockers, upsert_task
        from aiwf_core.core.task_plan import create_task_plan, update_task_plan_section

        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["workflow_level"] = "L2_standard_team"
        state_path.write_text(json.dumps(state, indent=2))
        goal = json.loads((self.tmp / ".aiwf" / "state" / "goal.json").read_text())
        brief = goal["quality_brief"]
        brief["evaluation_contract"].update({
            "user_visible_outcome": "Feature works",
            "acceptance_criteria": ["checked in plan"],
            "test_obligations": ["run tests"],
            "review_obligations": ["review contract"],
        })
        brief["architecture_brief"]["target_structure"] = "Preserve public CLI shape"
        (self.tmp / ".aiwf" / "state" / "goal.json").write_text(json.dumps(goal, indent=2))

        create_task_plan(str(self.tmp), "TASK-001", context_id="CTX-001", title="Plan says done")
        update_task_plan_section(str(self.tmp), "TASK-001", "testing", "- [x] All tests passed\n- [x] Reviewed\n")
        upsert_task(str(self.tmp), "TASK-001", "L2 work", status="ready", allowed_write=["src/a.py"])
        self.assertTrue(activate_task(str(self.tmp), "TASK-001")["activated"])

        blockers = active_task_completion_blockers(str(self.tmp))
        self.assertTrue(any("independent testing" in b for b in blockers))
        self.assertTrue(any("independent review" in b for b in blockers))


if __name__ == "__main__":
    unittest.main()
