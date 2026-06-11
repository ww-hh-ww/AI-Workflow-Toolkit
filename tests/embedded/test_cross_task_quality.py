"""Cross-task quality digest and tester/reviewer responsibility contract."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 15


class TestCrossTaskQuality(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awctq_"))
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        subprocess.run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                       capture_output=True, text=True, cwd=str(cls.tmp), env=env, timeout=20)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        from aiwf_core.core.state_schema import MVP_STATE_FILES
        for fn, dfn in MVP_STATE_FILES.items():
            p = self.tmp / ".aiwf" / fn; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(dfn(), indent=2) + "\n")
        for optional in ["task-history.json", "quality-digest.md", "current-state.md", "reports/质量摘要.md"]:
            path = self.tmp / ".aiwf" / optional
            if path.exists():
                path.unlink()

    def _run(self, *args):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run([sys.executable, "-m", "aiwf_core.cli", *args],
                              capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    def _seed_closed_state(self):
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state.update({"phase": "closed", "closure_allowed": True})
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(state, indent=2))
        (self.tmp / ".aiwf" / "state" / "goal.json").write_text(json.dumps({"active_goal": "finish task"}, indent=2))
        (self.tmp / ".aiwf" / "evidence" / "records.json").write_text(json.dumps({
            "records": [{"id": "EV-001", "status": "accepted", "changed_files": ["src/shared.py"]}]
        }, indent=2))
        (self.tmp / ".aiwf" / "quality" / "testing.json").write_text(json.dumps({
            "status": "adequate",
            "commands": ["pytest"],
            "untested_risks": ["manual integration"],
            "cross_task_risks": ["Repeated shared module changes need integration watch"],
        }, indent=2))
        (self.tmp / ".aiwf" / "quality" / "review.json").write_text(json.dumps({
            "result": "accepted",
            "closure_allowed": True,
            "architecture_drift": ["shared.py changed in consecutive tasks"],
            "testing_debt": ["integration coverage remains thin"],
        }, indent=2))

    def _seed_plan_impact(self, quality_summary="no"):
        plan_dir = self.tmp / ".aiwf" / "plans"
        plan_dir.mkdir(parents=True, exist_ok=True)
        (plan_dir / "TASK-QD.md").write_text(
            "# TASK-QD\n\n"
            "## Impact\n"
            "- docs: no — test\n"
            "- project_map: no — test\n"
            "- environment: no — test\n"
            "- capabilities: no — test\n"
            f"- quality_summary: {quality_summary} — test\n",
            encoding="utf-8",
        )
        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["active_plan_id"] = "TASK-QD"
        state_path.write_text(json.dumps(state, indent=2))

    def test_cross_task_quality_evaluates_history_and_observations(self):
        from aiwf_core.core.cross_task_quality import evaluate_cross_task_quality

        (self.tmp / ".aiwf" / "history" / "task-history.json").write_text(json.dumps({
            "tasks": [
                {"id": "t1", "changed_files": ["src/shared.py"], "fix_loop_attempt_count": 1, "untested_risk_count": 1},
                {"id": "t2", "changed_files": ["src/shared.py"], "fix_loop_attempt_count": 2, "untested_risk_count": 1},
            ]
        }, indent=2))
        testing = json.loads((self.tmp / ".aiwf" / "quality" / "testing.json").read_text())
        testing["cross_task_risks"] = ["risk"]
        (self.tmp / ".aiwf" / "quality" / "testing.json").write_text(json.dumps(testing, indent=2))
        review = json.loads((self.tmp / ".aiwf" / "quality" / "review.json").read_text())
        review["architecture_drift"] = ["drift"]
        (self.tmp / ".aiwf" / "quality" / "review.json").write_text(json.dumps(review, indent=2))

        result = evaluate_cross_task_quality(str(self.tmp))

        self.assertEqual(result["fix_loop_attempts"], 3)
        self.assertEqual(result["risk_task_count"], 2)
        self.assertEqual(result["repeated_change_hotspots"][0]["path"], "src/shared.py")
        self.assertTrue(any(s["kind"] == "fix_loop_trend" for s in result["signals"]))

    def test_rebase_writes_quality_digest_and_current_state_reference(self):
        self._seed_closed_state()
        self._seed_plan_impact("yes")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, str(self.tmp / "scripts" / "aiwf_rebase_state.py")],
                           capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)

        self.assertEqual(r.returncode, 0, r.stderr)
        digest = (self.tmp / ".aiwf" / "reports" / "质量摘要.md").read_text()
        current = (self.tmp / ".aiwf" / "reports" / "当前状态.md").read_text()
        self.assertIn("Tester / Reviewer Observations", digest)
        self.assertIn("Repeated shared module changes", digest)
        self.assertIn(".aiwf/reports/质量摘要.md", current)

    def test_rebase_does_not_write_quality_digest_when_impact_says_no(self):
        self._seed_closed_state()
        self._seed_plan_impact("no")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, str(self.tmp / "scripts" / "aiwf_rebase_state.py")],
                           capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)

        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse((self.tmp / ".aiwf" / "reports" / "质量摘要.md").exists())
        current = (self.tmp / ".aiwf" / "reports" / "当前状态.md").read_text()
        self.assertIn("not generated (Impact.quality_summary is not yes)", current)

    def test_record_testing_accepts_cross_task_fields(self):
        r = self._run("state", "record-testing", "--status", "adequate",
                      "--cross-task-risk", "repeated parser churn",
                      "--testing-debt", "manual path deferred",
                      "--repeated-change-hotspot", "src/parser.py")
        self.assertEqual(r.returncode, 0)
        testing = json.loads((self.tmp / ".aiwf" / "quality" / "testing.json").read_text())
        self.assertIn("repeated parser churn", testing["cross_task_risks"])
        self.assertIn("manual path deferred", testing["testing_debt"])
        self.assertIn("src/parser.py", testing["repeated_change_hotspots"])

    def test_quality_digest_cli_writes_digest(self):
        self._seed_plan_impact("yes")
        (self.tmp / ".aiwf" / "history" / "task-history.json").write_text(json.dumps({
            "tasks": [
                {"id": "t1", "changed_files": ["src/shared.py"], "fix_loop_attempt_count": 1, "untested_risk_count": 0},
                {"id": "t2", "changed_files": ["src/shared.py"], "fix_loop_attempt_count": 2, "untested_risk_count": 1},
            ]
        }, indent=2))
        r = self._run("quality", "digest")

        self.assertEqual(r.returncode, 0)
        self.assertIn("Quality digest written", r.stdout)
        self.assertTrue((self.tmp / ".aiwf" / "reports" / "质量摘要.md").exists())

    def test_quality_digest_blocked_when_impact_quality_summary_no(self):
        self._seed_plan_impact("no")
        r = self._run("quality", "digest")

        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Impact.quality_summary is not 'yes'", r.stderr)

    def test_quality_digest_allowed_with_force_when_impact_says_no(self):
        self._seed_plan_impact("no")
        (self.tmp / ".aiwf" / "history" / "task-history.json").write_text(json.dumps({
            "tasks": [
                {"id": "t1", "changed_files": ["src/shared.py"], "fix_loop_attempt_count": 1, "untested_risk_count": 0},
            ]
        }, indent=2))
        r = self._run("quality", "digest", "--force")

        self.assertEqual(r.returncode, 0)
        self.assertIn("Quality digest written", r.stdout)
        self.assertTrue((self.tmp / ".aiwf" / "reports" / "质量摘要.md").exists())

    def test_user_prompt_submit_keeps_short_context_process_focused(self):
        (self.tmp / ".aiwf" / "history" / "task-history.json").write_text(json.dumps({
            "tasks": [
                {"id": "t1", "changed_files": ["src/shared.py"], "fix_loop_attempt_count": 1, "untested_risk_count": 0},
                {"id": "t2", "changed_files": ["src/shared.py"], "fix_loop_attempt_count": 1, "untested_risk_count": 0},
                {"id": "t3", "changed_files": ["src/shared.py"], "fix_loop_attempt_count": 1, "untested_risk_count": 0},
            ]
        }, indent=2))
        inp = json.dumps({"session_id": "t", "cwd": str(self.tmp), "hook_event_name": "UserPromptSubmit"})
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, str(self.tmp / "scripts" / "aiwf_status.py")],
                           input=inp, capture_output=True, text=True,
                           cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        out = json.loads(r.stdout.strip())
        ctx = out["hookSpecificOutput"]["additionalContext"]

        self.assertIn("Process: level=L1_review_light mode=execution route=linear", ctx)
        self.assertIn("PRIMARY: activate task", ctx)
        self.assertNotIn("QUALITY ESCALATION:", ctx)

    def test_tester_and_reviewer_skills_own_cross_task_quality(self):
        test_skill = (self.tmp / ".claude" / "skills" / "aiwf-test" / "SKILL.md").read_text().lower()
        review_skill = (self.tmp / ".claude" / "skills" / "aiwf-review" / "SKILL.md").read_text().lower()
        self.assertIn("cross-task quality observation is part of tester responsibility", test_skill)
        self.assertIn("cross-task quality observation is part of reviewer responsibility", review_skill)


if __name__ == "__main__":
    unittest.main()
