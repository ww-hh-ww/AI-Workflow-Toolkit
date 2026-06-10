"""Context dispatch operational: CLI, state help, status presence, prompt cache."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 15

class TestContextDispatchOperational(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awcdo_"))
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        subprocess.run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                       capture_output=True, text=True, cwd=str(cls.tmp), env=env, timeout=20)

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
                              capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    def _status(self):
        inp = json.dumps({"session_id":"t","cwd":str(self.tmp),"hook_event_name":"UserPromptSubmit"})
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, str(self.tmp/"scripts"/"aiwf_status.py")],
                          input=inp, capture_output=True, text=True,
                          cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        out = json.loads(r.stdout.strip())
        return out["hookSpecificOutput"]["additionalContext"]

    # ── CLI ──
    def test_start_context_cli_writes_all_fields(self):
        r = self._run("state", "start-context", "--context-id", "CTX-001",
                      "--label", "subtract", "--allowed-write", "src/calc.js",
                      "--purpose", "implement subtract", "--test-focus", "normal subtraction",
                      "--review-focus", "no unrelated change", "--non-goal", "no redesign")
        self.assertEqual(r.returncode, 0)
        ctxs = json.loads((self.tmp/".aiwf" / "state" / "contexts.json").read_text())
        ctx = [c for c in ctxs["contexts"] if c["id"]=="CTX-001"][0]
        self.assertEqual(ctx["purpose"], "implement subtract")
        self.assertEqual(ctx["test_focus"], ["normal subtraction"])
        self.assertEqual(ctx["review_focus"], ["no unrelated change"])
        self.assertEqual(ctx["non_goals"], ["no redesign"])
        self.assertEqual(ctx["allowed_write"], ["src/calc.js"])

    def test_start_context_sets_active_context(self):
        self._run("state", "start-context", "--context-id", "CTX-002",
                  "--label", "test", "--purpose", "test")
        s = json.loads((self.tmp/".aiwf" / "state" / "state.json").read_text())
        self.assertEqual(s["active_context_id"], "CTX-002")

    def test_start_context_output_is_short(self):
        r = self._run("state", "start-context", "--context-id", "CTX-003",
                      "--purpose", "test", "--test-focus", "a")
        self.assertLess(len(r.stdout), 800)
        self.assertNotIn("{", r.stdout)

    def test_start_context_no_touch_claude_md(self):
        before = (self.tmp/"CLAUDE.md").read_text()
        self._run("state", "start-context", "--context-id", "CTX-004", "--purpose", "x")
        after = (self.tmp/"CLAUDE.md").read_text()
        self.assertEqual(before, after)

    def test_state_help_lists_all_subcommands(self):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, "-m", "aiwf_core.cli", "state"],
                          capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        self.assertIn("record-quality-policy", r.stdout)
        self.assertIn("record-quality-brief", r.stdout)
        self.assertIn("start-context", r.stdout)

    # ── Planner skill ──
    def test_planner_skill_has_start_context_cli(self):
        c = (self.tmp/".claude"/"skills"/"aiwf-planner-contracts"/"SKILL.md").read_text()
        self.assertIn("aiwf state start-context", c)
        self.assertIn("--purpose", c)
        self.assertIn("--test-focus", c)

    # ── Status ──
    def test_status_shows_context_dispatch_present(self):
        self._run("state", "start-context", "--context-id", "CTX-001",
                  "--purpose", "test", "--test-focus", "subtract")
        ctx = self._status()
        self.assertIn("Context dispatch: present", ctx)

    def test_status_shows_context_dispatch_missing(self):
        self._run("state", "start-context", "--context-id", "CTX-002")
        s = json.loads((self.tmp/".aiwf" / "state" / "state.json").read_text())
        s["phase"] = "implementing"
        (self.tmp/".aiwf" / "state" / "state.json").write_text(json.dumps(s, indent=2))
        ctx = self._status()
        self.assertIn("Context dispatch: missing", ctx)

    def test_status_no_dump_context_dispatch(self):
        self._run("state", "start-context", "--context-id", "CTX-003",
                  "--purpose", "secret-purpose-xyz", "--read-hint", "secret-hint-abc")
        ctx = self._status()
        self.assertNotIn("secret-purpose-xyz", ctx)
        self.assertNotIn("secret-hint-abc", ctx)


if __name__ == "__main__":
    unittest.main()
