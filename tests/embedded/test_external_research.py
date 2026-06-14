"""External research bridge: low-trust inputs require Planner promotion."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 15


class TestExternalResearch(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="awresearch_"))
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                           capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)

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
        upsert_plan(str(self.tmp), plan_id, goal_id="GOAL-001", task_ids=[task_id],
                    plan_kind="implementation", work_intent="feature",
                    allowed_write=["src/"], purpose="Test task")
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

    def test_record_and_promote_research_without_mutating_goal(self):
        goal_path = self.tmp / ".aiwf" / "state" / "goal.json"
        before_goal = json.loads(goal_path.read_text())

        out = self._run_ok(
            "research", "record",
            "--source", "x",
            "--query", "dynamic workflows",
            "--claim", "Use topology only when uncertainty requires it",
            "--link", "https://example.com/thread",
            "--confidence", "low",
        ).stdout
        research_id = out.split("External research recorded: ")[1].splitlines()[0].strip()
        store = json.loads((self.tmp / ".aiwf" / "artifacts" / "research" / "external.json").read_text())
        self.assertEqual(store["records"][0]["status"], "raw")
        self.assertEqual(store["records"][0]["confidence"], "low")

        self._run_ok("research", "promote", research_id, "--decision", "Adopt only as advisory topology routing")
        store = json.loads((self.tmp / ".aiwf" / "artifacts" / "research" / "external.json").read_text())
        self.assertEqual(store["records"][0]["status"], "promoted")
        self.assertIn("Adopt only", store["records"][0]["used_for_decision"])
        self.assertEqual(before_goal, json.loads(goal_path.read_text()))

    def test_process_guidance_mentions_required_external_research(self):
        from aiwf_core.core.process_contract import planner_process_guidance

        self._run_ok(
            "state", "set-workflow-mode",
            "--request-mode", "research",
            "--workflow-pattern", "research_first",
            "--external-research-required",
        )
        guidance = planner_process_guidance(str(self.tmp))

        self.assertTrue(guidance["external_research_required"])
        self.assertTrue(any("External research is marked required" in c for c in guidance["conditional"]))

    def test_recovery_guidance_requires_research_promotion_or_user_skip(self):
        from aiwf_core.core.process_contract import planner_process_guidance

        self._run_ok(
            "state", "set-workflow-mode",
            "--request-mode", "execution",
            "--workflow-pattern", "research_first",
            "--external-research-required",
        )

        recovery = planner_process_guidance(str(self.tmp))["recovery"]

        self.assertEqual(recovery["state"], "blocked")
        self.assertEqual(recovery["category"], "user_decision")
        self.assertEqual(recovery["primary"], "resolve external research requirement")
        self.assertTrue(recovery["user_decision_required"])
        self.assertTrue(any("research skip" in item for item in recovery["legal_options"]))
        self.assertTrue(any("start implementation" in item for item in recovery["forbidden"]))

    def test_required_external_research_blocks_execution_activation_until_promoted(self):
        from aiwf_core.core.task_ledger import activate_task, upsert_task

        (self.tmp / ".aiwf" / "artifacts" / "reports" / "当前状态.md").unlink(missing_ok=True)
        self._run_ok(
            "state", "set-workflow-mode",
            "--request-mode", "execution",
            "--workflow-pattern", "research_first",
            "--external-research-required",
        )
        upsert_task(str(self.tmp), "TASK-001", "Needs research", status="ready")
        self._seed_plan("TASK-001")

        blocked = activate_task(str(self.tmp), "TASK-001")
        self.assertFalse(blocked["activated"])
        self.assertTrue(any("external_research_required=true" in b for b in blocked["blockers"]))

        out = self._run_ok(
            "research", "record",
            "--source", "web",
            "--query", "library current behavior",
            "--claim", "Current API changed recently",
        ).stdout
        research_id = out.split("External research recorded: ")[1].splitlines()[0].strip()
        self._run_ok("research", "promote", research_id, "--decision", "Use current API behavior in execution contract")

        allowed = activate_task(str(self.tmp), "TASK-001")
        self.assertTrue(allowed["activated"], allowed["blockers"])

    def test_required_external_research_allows_explicit_skip(self):
        from aiwf_core.core.task_ledger import activate_task, upsert_task

        (self.tmp / ".aiwf" / "artifacts" / "reports" / "当前状态.md").unlink(missing_ok=True)
        self._run_ok(
            "state", "set-workflow-mode",
            "--request-mode", "execution",
            "--workflow-pattern", "linear",
            "--external-research-required",
        )
        upsert_task(str(self.tmp), "TASK-001", "Skip research", status="ready")
        self._seed_plan("TASK-001")
        self.assertFalse(activate_task(str(self.tmp), "TASK-001")["activated"])

        self._run_ok("research", "skip", "--reason", "User supplied authoritative local source; external search would add no signal")
        allowed = activate_task(str(self.tmp), "TASK-001")
        self.assertTrue(allowed["activated"], allowed["blockers"])


if __name__ == "__main__":
    unittest.main()
