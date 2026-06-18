"""Uncertainty routing: mode/pattern shape workflow without weakening gates (V2)."""
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
        (self.tmp / ".aiwf" / "records" / "当前状态.md").unlink(missing_ok=True)

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
        """V2: create a Plan.md in aiwf/plans/ and register in plans.json + attach task."""
        from aiwf_core.core.state.plan_ops import upsert_plan, attach_task_to_plan

        plan_id = f"PLAN-{task_id}"
        plan_dir = self.tmp / ".aiwf" / "plans"
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
        attach_task_to_plan(str(self.tmp), plan_id, task_id)
        return plan_id

    @unittest.skip("V1: routing hidden")
    def test_default_mode_is_execution_for_backward_compatibility(self):
        """V2: request_mode/workflow_pattern default to execution/linear when absent."""
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        self.assertEqual(state.get("request_mode", "execution"), "execution")
        self.assertEqual(state.get("workflow_pattern", "linear"), "linear")

    @unittest.skip("V1: routing hidden")
    def test_clarification_mode_blocks_implementation(self):
        """V2: clarification mode is enforced via process guidance (advisory gate)."""
        from aiwf_core.core.process_contract import planner_process_guidance

        self._run_ok(
            "state", "set-workflow-mode",
            "--request-mode", "clarification",
            "--workflow-pattern", "clarification_first",
            "--reason", "requirements unclear",
        )
        guidance = planner_process_guidance(str(self.tmp))

        self.assertEqual(guidance["recovery"]["category"], "clarification")
        self.assertIn("do not activate implementation while request_mode is non-execution",
                      guidance["recovery"]["forbidden"])

    @unittest.skip("V1: routing hidden")
    def test_switching_to_execution_allows_activation_without_lowering_level(self):
        from aiwf_core.core.task_ledger import activate_task, upsert_task
        from aiwf_core.core.state.goal_ops import record_quality_brief

        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["workflow_level"] = "L2_standard_team"
        state_path.write_text(json.dumps(state, indent=2))
        self._run_ok("state", "set-workflow-mode", "--request-mode", "execution", "--workflow-pattern", "linear")

        # V2: quality_brief lives in goals.json, use the API not raw file writes
        record_quality_brief(
            str(self.tmp),
            user_visible_outcome="Works",
            evaluation_acceptance_criteria=["verified"],
            test_obligations=["run tests"],
            review_obligations=["review"],
            target_structure="Keep current structure",
            non_goals=["test"],
        )

        upsert_task(str(self.tmp), "TASK-001", "Formal implementation", status="ready")
        self._seed_plan("TASK-001")
        result = activate_task(str(self.tmp), "TASK-001")
        state = json.loads(state_path.read_text())

        self.assertTrue(result["activated"], result["blockers"])
        self.assertEqual(state["workflow_level"], "L2_standard_team")

    @unittest.skip("V1: routing hidden")
    def test_spike_mode_reported_in_process_guidance(self):
        """V2: spike restrictions are enforced via process guidance, not close_task."""
        from aiwf_core.core.process_contract import planner_process_guidance

        self._run_ok("state", "set-workflow-mode", "--request-mode", "spike", "--workflow-pattern", "linear")
        guidance = planner_process_guidance(str(self.tmp))

        self.assertEqual(guidance["recovery"]["category"], "spike")
        self.assertIn("do not treat spike output as final implementation closure",
                      guidance["recovery"]["forbidden"])

    @unittest.skip("V1: routing hidden")
    def test_process_guidance_explains_non_execution_mode(self):
        from aiwf_core.core.process_contract import planner_process_guidance

        self._run_ok("state", "set-workflow-mode", "--request-mode", "research", "--workflow-pattern", "research_first")
        guidance = planner_process_guidance(str(self.tmp))

        self.assertEqual(guidance["recovery"]["category"], "research")
        self.assertIn("do not activate implementation while request_mode is non-execution",
                      guidance["recovery"]["forbidden"])


if __name__ == "__main__":
    unittest.main()
