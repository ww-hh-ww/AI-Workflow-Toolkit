"""Quality brief operational: CLI, status presence, heavy-testing cleanup."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 15

def _install(cwd):
    env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
    subprocess.run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                   capture_output=True, text=True, cwd=str(cwd), env=env, timeout=20)

def _rj(path): return json.loads(path.read_text())

class TestQualityBriefOperational(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awqbo_"))
        _install(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        from aiwf_core.core.state_schema import MVP_STATE_FILES
        for fn, dfn in MVP_STATE_FILES.items():
            p = self.tmp / ".aiwf" / fn; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(dfn(), indent=2) + "\n")

    def _run(self, *args):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run([sys.executable, "-m", "aiwf_core.cli"] + list(args),
                              capture_output=True, text=True,
                              cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    # ── CLI ──
    def test_cli_writes_quality_brief(self):
        r = self._run("state", "record-quality-brief",
                      "--acceptance", "subtract returns a-b",
                      "--test-focus", "normal subtraction",
                      "--review-focus", "no unrelated change",
                      "--non-goal", "do not redesign",
                      "--escalation-trigger", "validator change needs L2")
        self.assertEqual(r.returncode, 0)
        g = _rj(self.tmp / ".aiwf" / "state" / "goal.json")
        brief = g["quality_brief"]
        self.assertEqual(brief["acceptance_criteria"], ["subtract returns a-b"])
        self.assertEqual(len(brief["test_focus"]), 1)
        self.assertEqual(brief["non_goals"][0], "do not redesign")

    def test_cli_preserves_active_goal(self):
        g = _rj(self.tmp / ".aiwf" / "state" / "goal.json")
        g["active_goal"] = "add subtract"; g["confirmed"] = True
        (self.tmp / ".aiwf" / "state" / "goal.json").write_text(json.dumps(g, indent=2))
        self._run("state", "record-quality-brief", "--test-focus", "subtract")
        g2 = _rj(self.tmp / ".aiwf" / "state" / "goal.json")
        self.assertEqual(g2["active_goal"], "add subtract")
        self.assertTrue(g2["confirmed"])

    def test_cli_output_is_short_no_json_dump(self):
        r = self._run("state", "record-quality-brief",
                      "--test-focus", "a", "--review-focus", "b")
        self.assertLess(len(r.stdout), 600)
        self.assertNotIn("{", r.stdout)

    def test_cli_no_touch_claude_md(self):
        before = (self.tmp / "CLAUDE.md").read_text()
        self._run("state", "record-quality-brief", "--test-focus", "x")
        after = (self.tmp / "CLAUDE.md").read_text()
        self.assertEqual(before, after)

    # ── status ──
    def test_status_shows_brief_present(self):
        self._run("state", "record-quality-brief", "--acceptance", "must work")
        r = self._run("status")
        self.assertIn("Quality brief: present", r.stdout)

    def test_status_shows_brief_missing_when_confirmed(self):
        g = _rj(self.tmp / ".aiwf" / "state" / "goal.json")
        g["confirmed"] = True
        (self.tmp / ".aiwf" / "state" / "goal.json").write_text(json.dumps(g, indent=2))
        r = self._run("status")
        self.assertIn("Quality brief: missing", r.stdout)

    # ── heavy-testing cleanup ──
    def test_claude_md_no_deep_testing_tester(self):
        c = (self.tmp / "CLAUDE.md").read_text()
        self.assertNotIn("deep testing", c.lower())
        self.assertNotIn("happy/edge/adverse/regression", c.lower())

    def test_agent_tester_no_old_rule(self):
        c = (self.tmp / ".claude" / "agents" / "aiwf-tester.md").read_text()
        self.assertNotIn("Test at least one adverse/edge/regression case", c)
        self.assertIn("test_template", c.lower())

    def test_planner_skill_has_cli_for_brief(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-planner" / "SKILL.md").read_text()
        self.assertIn("record-quality-brief", c)

    # ── prompt cache ──
    def test_status_does_not_dump_brief_content(self):
        self._run("state", "record-quality-brief",
                  "--acceptance", "secret-criteria-xyz",
                  "--test-focus", "secret-focus-abc")
        inp = json.dumps({"session_id":"t","cwd":str(self.tmp),"hook_event_name":"UserPromptSubmit"})
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, str(self.tmp/"scripts"/"aiwf_status.py")],
                          input=inp, capture_output=True, text=True,
                          cwd=str(self.tmp), env=env, timeout=10)
        out = json.loads(r.stdout.strip())
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertNotIn("secret-criteria-xyz", ctx)
        self.assertNotIn("secret-focus-abc", ctx)
        self.assertIn("Quality brief: present", ctx)



    # ── standalone status hook ──

    def test_status_script_no_aiwf_core_imports(self):
        script = (self.tmp / "scripts" / "aiwf_status.py").read_text()
        self.assertNotIn("from aiwf_core", script)
        self.assertNotIn("import aiwf_core", script)

    def test_status_script_runs_without_pythonpath(self):
        """Status script must run without PYTHONPATH set."""
        script = str(self.tmp / "scripts" / "aiwf_status.py")
        inp = json.dumps({"session_id": "t", "cwd": str(self.tmp),
                         "hook_event_name": "UserPromptSubmit"})
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)  # Remove PYTHONPATH
        r = subprocess.run([sys.executable, script],
                          input=inp, capture_output=True, text=True,
                          cwd=str(self.tmp), env=env, timeout=10)
        self.assertEqual(r.returncode, 0)
        out = json.loads(r.stdout.strip())
        self.assertIn("additionalContext", out["hookSpecificOutput"])
        self.assertIn("[AIWF]", out["hookSpecificOutput"]["additionalContext"])

    def test_status_output_is_valid_claude_json(self):
        script = str(self.tmp / "scripts" / "aiwf_status.py")
        inp = json.dumps({"session_id": "t", "cwd": str(self.tmp),
                         "hook_event_name": "UserPromptSubmit"})
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, script],
                          input=inp, capture_output=True, text=True,
                          cwd=str(self.tmp), env=env, timeout=10)
        out = json.loads(r.stdout.strip())
        self.assertIn("hookSpecificOutput", out)
        self.assertIn("additionalContext", out["hookSpecificOutput"])
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertLess(len(ctx), 800)  # Still short

    def test_cli_facade_no_deep_testing(self):
        """CLI embedded facade must not say deep testing for tester."""
        r = self._run("install", "claude", "--force")
        # Check the default facade output text — not the install output
        # The facade is triggered by running aiwf with no args
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r2 = subprocess.run([sys.executable, "-m", "aiwf_core.cli"],
                           capture_output=True, text=True,
                           cwd=str(self.tmp), env=env, timeout=10)
        # "deep testing" should not appear as tester description
        if "deep testing" in r2.stdout.lower():
            # Check if it refers to tester
            idx = r2.stdout.lower().find("deep testing")
            context = r2.stdout[idx-30:idx+50]
            if "tester" in context.lower() or "test" in context.lower():
                self.fail(f"CLI facade has 'deep testing' near tester: {context}")



if __name__ == "__main__":
    unittest.main()
