"""Uncertainty routing: mode/pattern shape workflow without weakening gates."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 15


class TestUncertaintyRouting(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="awrouting_"))
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                           capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        (self.tmp / ".aiwf" / "artifacts" / "reports" / "当前状态.md").unlink(missing_ok=True)

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

    def _seed_plan(self, task_id):
        from aiwf_core.core.state.plan_ops import upsert_plan

        plan_id = f"PLAN-{task_id}"
        plan_dir = self.tmp / ".aiwf" / "artifacts" / "plans"
        plan_dir.mkdir(parents=True, exist_ok=True)
        plan_path = plan_dir / f"{plan_id}.md"
        if not plan_path.exists():
            plan_path.write_text(
                f"# {plan_id}\n\n"
                "> AI working plan.\n\n"
                f"Plan ID: {plan_id}\n"
                "Parent Goal: GOAL-001\n"
                f"Task IDs: {task_id}\n\n"
                "## Goal\nTest\n\n## Route\n- How: fix\n\n"
                "## Scope\n- Change: test\n\n## Risks\n- none\n\n"
                "## Verification\n- Machine-verifiable: yes\n\n"
                "## Impact\n- docs: no — test\n- project_map: no — test\n- environment: no — test\n- capabilities: no — test\n- quality_summary: no — test\n\n"
                "## Done Means\n- test passes\n\n"
                "## Goal Progress\n- Parent goal: test\n\n"
                "## Next Steps\n1. done\n",
                encoding="utf-8",
            )
        upsert_plan(str(self.tmp), plan_id, goal_id="GOAL-001", task_ids=[task_id])
        ledger_path = self.tmp / ".aiwf" / "runtime" / "history" / "task-ledger.json"
        if ledger_path.exists():
            ledger = json.loads(ledger_path.read_text())
            changed = False
            for task in ledger.get("tasks", []):
                if task.get("id") == task_id:
                    task["plan_id"] = plan_id
                    task["parent_plan"] = plan_id
                    task["goal_id"] = task.get("goal_id") or "GOAL-001"
                    task["parent_goal"] = task.get("parent_goal") or task["goal_id"]
                    changed = True
            if changed:
                ledger_path.write_text(json.dumps(ledger, indent=2) + "\n")
        return plan_id

    def test_default_mode_is_execution_for_backward_compatibility(self):
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        self.assertEqual(state["request_mode"], "execution")
        self.assertEqual(state["workflow_pattern"], "linear")

    def test_clarification_mode_blocks_task_activation(self):
        from aiwf_core.core.task_ledger import activate_task, upsert_task

        self._run_ok(
            "state", "set-workflow-mode",
            "--request-mode", "clarification",
            "--workflow-pattern", "clarification_first",
            "--reason", "requirements unclear",
        )
        upsert_task(str(self.tmp), "TASK-001", "Premature implementation", status="ready")
        self._seed_plan("TASK-001")
        result = activate_task(str(self.tmp), "TASK-001")

        self.assertFalse(result["activated"])
        self.assertTrue(any("request_mode=clarification" in b for b in result["blockers"]))

    def test_switching_to_execution_allows_activation_without_lowering_level(self):
        from aiwf_core.core.task_ledger import activate_task, upsert_task

        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["workflow_level"] = "L2_standard_team"
        state_path.write_text(json.dumps(state, indent=2))
        self._run_ok("state", "set-workflow-mode", "--request-mode", "execution", "--workflow-pattern", "linear")
        goal = json.loads((self.tmp / ".aiwf" / "state" / "goal.json").read_text())
        brief = goal["quality_brief"]
        brief["evaluation_contract"].update({
            "user_visible_outcome": "Works",
            "acceptance_criteria": ["verified"],
            "test_obligations": ["run tests"],
            "review_obligations": ["review"],
        })
        brief["architecture_brief"]["target_structure"] = "Keep current structure"
        brief["non_goals"] = ["test"]
        (self.tmp / ".aiwf" / "state" / "goal.json").write_text(json.dumps(goal, indent=2))

        upsert_task(str(self.tmp), "TASK-001", "Formal implementation", status="ready")
        self._seed_plan("TASK-001")
        result = activate_task(str(self.tmp), "TASK-001")
        state = json.loads(state_path.read_text())

        self.assertTrue(result["activated"], result["blockers"])
        self.assertEqual(state["workflow_level"], "L2_standard_team")

    def test_spike_cannot_close_as_final_implementation(self):
        from aiwf_core.core.task_ledger import activate_task, close_task, upsert_task

        self._run_ok("state", "set-workflow-mode", "--request-mode", "spike", "--workflow-pattern", "linear")
        upsert_task(str(self.tmp), "TASK-001", "Explore feasibility", status="ready")
        self._seed_plan("TASK-001")
        self.assertTrue(activate_task(str(self.tmp), "TASK-001")["activated"])

        # Set phase=closed to pass the prepare-close gate, then verify spike block
        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["phase"] = "closed"
        state["closure_allowed"] = True
        state["close_prepared_task_id"] = "TASK-001"
        state_path.write_text(json.dumps(state, indent=2))

        result = close_task(str(self.tmp), "TASK-001")
        self.assertFalse(result["closed"])
        self.assertTrue(any("spike task cannot close" in b for b in result["blockers"]))

    def test_process_guidance_explains_non_execution_mode(self):
        from aiwf_core.core.process_contract import planner_process_guidance

        self._run_ok("state", "set-workflow-mode", "--request-mode", "research", "--workflow-pattern", "research_first")
        guidance = planner_process_guidance(str(self.tmp))

        self.assertEqual(guidance["request_mode"], "research")
        self.assertTrue(any("request_mode=research" in b for b in guidance["required_now"]))


if __name__ == "__main__":
    unittest.main()
