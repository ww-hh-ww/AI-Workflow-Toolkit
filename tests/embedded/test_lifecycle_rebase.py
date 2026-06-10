"""Lifecycle rebase: current-state.md generation, skill wiring, prompt cache."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 15

class TestLifecycleRebase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awlr_"))
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        subprocess.run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                       capture_output=True, text=True, cwd=str(cls.tmp), env=env, timeout=20)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        from aiwf_core.core.state_schema import MVP_STATE_FILES
        (self.tmp/".aiwf").mkdir(parents=True, exist_ok=True)
        for fn, dfn in MVP_STATE_FILES.items():
            p = self.tmp / ".aiwf" / fn; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(dfn(), indent=2)+"\n")
        cs = self.tmp / ".aiwf" / "reports" / "当前状态.md"
        if cs.exists(): cs.unlink()
        hist = self.tmp / ".aiwf" / "history" / "task-history.json"
        if hist.exists(): hist.unlink()

    def _rebase(self):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run([sys.executable, str(self.tmp/"scripts"/"aiwf_rebase_state.py")],
                              capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    def _seed_closed_state(self):
        s = json.loads((self.tmp/".aiwf" / "state" / "state.json").read_text())
        s.update({"phase":"closed","close_attempt":False,"closure_allowed":True,
                  "workflow_level":"L1_review_light","task_type":"small_function"})
        (self.tmp/".aiwf" / "state" / "state.json").write_text(json.dumps(s,indent=2))
        (self.tmp/".aiwf" / "state" / "goal.json").write_text(json.dumps(
            {"active_goal":"add subtract","confirmed":True},indent=2))
        (self.tmp/".aiwf" / "evidence" / "records.json").write_text(json.dumps(
            {"records":[{"id":"EV-001","status":"accepted","changed_files":["src/calc.js","test/calc.test.js"]}]},indent=2))
        (self.tmp/".aiwf" / "quality" / "testing.json").write_text(json.dumps(
            {"status":"adequate","commands":["pytest"],"untested_risks":["overflow"]},indent=2))
        (self.tmp/".aiwf" / "quality" / "review.json").write_text(json.dumps({
            "result":"accepted","lessons":["Path normalization needed","Promote evidence before gate"],
            "negative_patterns":["Do not use Bash to write JSON state"],
            "followups":["Consider helper for input validation"]
        },indent=2))

    # ── rebase script ──
    def test_rebase_script_exists_and_compiles(self):
        self.assertTrue((self.tmp/"scripts"/"aiwf_rebase_state.py").exists())
        import py_compile
        py_compile.compile(str(self.tmp/"scripts"/"aiwf_rebase_state.py"), doraise=True)

    def test_rebase_generates_current_state_md(self):
        self._seed_closed_state()
        r = self._rebase()
        self.assertEqual(r.returncode, 0)
        cs = (self.tmp/".aiwf"/"reports"/"当前状态.md")
        self.assertTrue(cs.exists())

    def test_current_state_has_last_closed_task(self):
        self._seed_closed_state()
        self._rebase()
        content = (self.tmp/".aiwf"/"reports"/"当前状态.md").read_text()
        self.assertIn("add subtract", content)
        self.assertIn("L1_review_light", content)
        self.assertIn("small_function", content)

    def test_current_state_starts_with_executive_summary(self):
        self._seed_closed_state()
        self._rebase()
        content = (self.tmp/".aiwf"/"reports"/"当前状态.md").read_text()
        self.assertIn("## Executive Summary", content)
        self.assertIn("Now: phase=closed", content)
        self.assertIn("Quality: testing=adequate", content)
        self.assertIn("Blockers: none", content)

    def test_current_state_has_changed_files_not_raw_json(self):
        self._seed_closed_state()
        self._rebase()
        content = (self.tmp/".aiwf"/"reports"/"当前状态.md").read_text()
        self.assertIn("src/calc.js", content)
        self.assertNotIn('"records"', content)
        self.assertNotIn('"state"', content)

    def test_current_state_has_lessons_max_5(self):
        self._seed_closed_state()
        self._rebase()
        content = (self.tmp/".aiwf"/"reports"/"当前状态.md").read_text()
        self.assertIn("Path normalization", content)
        self.assertIn("Carry-forward lessons", content)

    def test_current_state_has_raw_audit_refs(self):
        self._seed_closed_state()
        self._rebase()
        content = (self.tmp/".aiwf"/"reports"/"当前状态.md").read_text()
        self.assertIn("Raw audit references", content)
        self.assertIn(".aiwf/evidence/records.json", content)
        self.assertIn(".aiwf/quality/review.json", content)


    # ── safety guards ──

    def test_rebase_refuses_when_phase_not_closed(self):
        """Rebase must NOT generate current-state when phase is not closed."""
        s = json.loads((self.tmp/".aiwf" / "state" / "state.json").read_text())
        s["phase"] = "implementing"
        s["closure_allowed"] = False
        (self.tmp/".aiwf" / "state" / "state.json").write_text(json.dumps(s, indent=2))
        r = self._rebase()
        self.assertNotEqual(r.returncode, 0)  # skipped
        self.assertFalse((self.tmp/".aiwf"/"reports"/"当前状态.md").exists(),
                        "Should NOT create current-state when not closed")

    def test_rebase_preserves_existing_current_state_when_not_closed(self):
        """Existing current-state.md must NOT be overwritten when phase is not closed."""
        (self.tmp/".aiwf"/"reports"/"当前状态.md").write_text("# previous clean summary\n")
        s = json.loads((self.tmp/".aiwf" / "state" / "state.json").read_text())
        s["phase"] = "reviewing"; s["closure_allowed"] = False
        (self.tmp/".aiwf" / "state" / "state.json").write_text(json.dumps(s, indent=2))
        self._rebase()
        content = (self.tmp/".aiwf"/"reports"/"当前状态.md").read_text()
        self.assertIn("previous clean summary", content)

    def test_rebase_succeeds_when_closed_and_allowed(self):
        self._seed_closed_state()
        r = self._rebase()
        self.assertEqual(r.returncode, 0)

    def test_current_state_has_contexts_involved_not_superseded(self):
        self._seed_closed_state()
        self._rebase()
        content = (self.tmp/".aiwf"/"reports"/"当前状态.md").read_text()
        self.assertNotIn("Superseded / closed contexts", content)
        self.assertIn("Contexts involved", content)

    def test_rebase_records_task_history(self):
        self._seed_closed_state()
        self._rebase()
        history = json.loads((self.tmp/".aiwf" / "history" / "task-history.json").read_text())
        self.assertEqual(len(history["tasks"]), 1)
        task = history["tasks"][0]
        self.assertEqual(task["testing_status"], "adequate")
        self.assertIn("src/calc.js", task["changed_files"])
        self.assertEqual(task["untested_risk_count"], 1)

    def test_current_state_has_task_history_trend(self):
        self._seed_closed_state()
        self._rebase()
        content = (self.tmp/".aiwf"/"reports"/"当前状态.md").read_text()
        self.assertIn("Task history trend", content)
        self.assertIn("Recent closed tasks: 1", content)


        # ── skill text ──
    def test_planner_skill_mentions_current_state(self):
        c = (self.tmp/".claude"/"skills"/"aiwf-planner-execute"/"SKILL.md").read_text()
        self.assertIn("current-state.md", c)

    # ── status ──
    def test_status_shows_current_state_available(self):
        self._seed_closed_state()
        self._rebase()
        inp = json.dumps({"session_id":"t","cwd":str(self.tmp),"hook_event_name":"UserPromptSubmit"})
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, str(self.tmp/"scripts"/"aiwf_status.py")],
                          input=inp, capture_output=True, text=True,
                          cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        out = json.loads(r.stdout.strip())
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Current state: available", ctx)

    # ── no side effects ──
    def test_rebase_no_modify_claude_md(self):
        self._seed_closed_state()
        before = (self.tmp/"CLAUDE.md").read_text()
        self._rebase()
        after = (self.tmp/"CLAUDE.md").read_text()
        self.assertEqual(before, after)

    def test_rebase_no_modify_settings_json(self):
        self._seed_closed_state()
        before = (self.tmp/".claude"/"settings.json").read_text()
        self._rebase()
        after = (self.tmp/".claude"/"settings.json").read_text()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
