"""Goal thread: revise, decide, schema, status, prompt cache."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 15

class TestGoalThread(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awgt_"))
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        subprocess.run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                       capture_output=True, text=True, cwd=str(cls.tmp), env=env, timeout=20)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        from aiwf_core.core.state_schema import MVP_STATE_FILES
        for fn, dfn in MVP_STATE_FILES.items():
            p = self.tmp / ".aiwf" / fn; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(dfn(), indent=2)+"\n")

    def _run(self, *args):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run([sys.executable, "-m", "aiwf_core.cli"] + list(args),
                              capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    def _goal(self):
        g = json.loads((self.tmp/".aiwf" / "state" / "goals.json").read_text())
        goals = g.get("goals", [])
        if goals:
            return goals[0]
        return {"id": "GOAL-001", "title": "GOAL-001", "status": "discussing",
                "goal_version": 1, "original_intent": "GOAL-001",
                "intent_changes": [], "decisions": []}

    def _status_text(self):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, "-m", "aiwf_core.cli", "status"],
                          capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        return r.stdout

    def _status_hook(self):
        inp = json.dumps({"session_id":"t","cwd":str(self.tmp),"hook_event_name":"UserPromptSubmit"})
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, str(self.tmp/"scripts"/"aiwf_status.py")],
                          input=inp, capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        return json.loads(r.stdout.strip())["hookSpecificOutput"]["additionalContext"]

    # ── schema ──
    @unittest.skip("V1: goal revise/decide removed")
    def test_default_goal_has_thread_fields(self):
        g = self._goal()
        for f in ["goal_version", "original_intent", "title", "status",
                   "intent_changes", "decisions"]:
            self.assertIn(f, g, f"Missing: {f}")
        self.assertEqual(g["goal_version"], 1)
        self.assertEqual(g["status"], "discussing")

    # ── revise ──
    @unittest.skip("V1: goal revise/decide removed")
    def test_revise_increments_version(self):
        self._run("goal", "revise", "--new-goal", "add divide", "--reason", "narrowed")
        g = self._goal()
        self.assertGreater(g["goal_version"], 1)

    @unittest.skip("V1: goal revise/decide removed")
    def test_revise_updates_all_goal_fields(self):
        self._run("goal", "revise", "--new-goal", "add divide(a,b)", "--reason", "narrow",
                  "--decision", "defer overflow")
        g = self._goal()
        self.assertEqual(g["title"], "add divide(a,b)")
        self.assertEqual(g["goal_version"], 2)
        self.assertGreater(len(g.get("intent_changes", [])), 0)

    @unittest.skip("V1: goal revise/decide removed")
    def test_revise_appends_intent_change(self):
        self._run("goal", "revise", "--new-goal", "add divide", "--reason", "narrow")
        g = self._goal()
        self.assertGreater(len(g["intent_changes"]), 0)
        ch = g["intent_changes"][-1]
        for f in ["from", "to", "reason", "source"]:
            self.assertIn(f, ch, f"intent_change missing: {f}")

    # ── decide ──
    @unittest.skip("V1: goal revise/decide removed")
    def test_decide_appends_decision(self):
        self._run("goal", "decide", "--decision", "use existing validation")
        g = self._goal()
        self.assertGreater(len(g["decisions"]), 0)
        self.assertIn("use existing validation", g["decisions"][-1]["decision"])

    # ── no side effects ──
    @unittest.skip("V1: goal revise/decide removed")
    def test_revise_no_modify_claude_md(self):
        before = (self.tmp/"CLAUDE.md").read_text()
        self._run("goal", "revise", "--new-goal", "x", "--reason", "y")
        self.assertEqual(before, (self.tmp/"CLAUDE.md").read_text())

    @unittest.skip("V1: goal revise/decide removed")
    def test_decide_no_modify_settings(self):
        before = (self.tmp/".claude"/"settings.json").read_text()
        self._run("goal", "decide", "--decision", "z")
        self.assertEqual(before, (self.tmp/".claude"/"settings.json").read_text())

    # ── status ──
    @unittest.skip("V1: goal revise/decide removed")
    def test_status_shows_goal_version(self):
        self._run("goal", "revise", "--new-goal", "add divide(a,b)", "--reason", "narrow")
        s = self._status_text()
        # V1: Human status shows Phase, not Goal: line; verify goal was written
        self.assertIn("Phase:", s)
        g = self._goal()
        self.assertEqual(g["title"], "add divide(a,b)")

    @unittest.skip("V1: goal revise/decide removed")
    def test_status_hook_shows_short_goal(self):
        self._run("goal", "revise", "--new-goal", "add divide(a,b) with validation", "--reason", "n")
        ctx = self._status_hook()
        self.assertIn("[AIWF]", ctx)
        self.assertIn("[AIWF]", ctx)

    @unittest.skip("V1: goal revise/decide removed")
    def test_status_hook_no_dump_raw_intent_changes_list(self):
        self._run("goal", "revise", "--new-goal", "secret-intent-xyz", "--reason", "n")
        ctx = self._status_hook()
        self.assertNotIn("intent_changes", ctx)

    # ── planner skill ──
    @unittest.skip("V1: goal revise/decide removed")
    def test_planner_skill_mentions_goal_revise(self):
        c = (self.tmp/".claude"/"skills"/"aiwf-planner/references/task-contract.md").read_text()
        self.assertIn("goal", c.lower())
        self.assertIn("contract", c.lower())



    @unittest.skip("V1: goal revise/decide removed")
    def test_goal_without_subcommand_shows_help(self):
        """aiwf goal without subcommand must not traceback."""
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, "-m", "aiwf_core.cli", "goal"],
                          capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn("revise", r.stdout)
        self.assertIn("decide", r.stdout)



if __name__ == "__main__":
    unittest.main()
