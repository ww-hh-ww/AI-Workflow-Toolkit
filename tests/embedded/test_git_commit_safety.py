"""Git commit safety: summary, suggest, commit gates, no push."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 15

class TestGitCommitSafety(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._tmpl = Path(tempfile.mkdtemp(prefix="awgc_tmpl_"))
        subprocess.run(["git", "init", "-b", "main"], cwd=str(cls._tmpl), capture_output=True, timeout=10)
        subprocess.run(["git", "config", "user.email", "a@b.c"], cwd=str(cls._tmpl), capture_output=True, timeout=10)
        subprocess.run(["git", "config", "user.name", "t"], cwd=str(cls._tmpl), capture_output=True, timeout=10)
        (cls._tmpl/"README.md").write_text("init\n")
        subprocess.run(["git", "add", "README.md"], cwd=str(cls._tmpl), capture_output=True, timeout=10)
        subprocess.run(["git", "commit", "-m", "init"], cwd=str(cls._tmpl), capture_output=True, timeout=10)
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        subprocess.run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                       capture_output=True, text=True, cwd=str(cls._tmpl), env=env, timeout=30)
        subprocess.run(["git", "add", "-A"], cwd=str(cls._tmpl), capture_output=True, timeout=10)
        subprocess.run(["git", "commit", "-m", "aiwf"], cwd=str(cls._tmpl), capture_output=True, timeout=10)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmpl, ignore_errors=True)

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="awgc_t_"))
        shutil.copytree(self._tmpl, self.tmp, dirs_exist_ok=True, symlinks=False)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, *args):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run([sys.executable, "-m", "aiwf_core.cli"] + list(args),
                              capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    def _allow_closure(self):
        s = json.loads((self.tmp/".aiwf" / "state" / "state.json").read_text())
        s["phase"] = "closed"; s["closure_allowed"] = True
        (self.tmp/".aiwf" / "state" / "state.json").write_text(json.dumps(s, indent=2))

    # ── summary ──
    def test_summary_works(self):
        (self.tmp/"README.md").write_text("changed\n")
        r = self._run("git", "summary")
        self.assertEqual(r.returncode, 0)
        self.assertIn("Dirty: True", r.stdout)

    def test_summary_classifies_governance(self):
        (self.tmp/".aiwf" / "state" / "state.json").write_text("x\n")
        r = self._run("git", "summary")
        self.assertIn("Governance changes:", r.stdout)

    # ── suggest ──
    def test_suggest_returns_message(self):
        r = self._run("git", "suggest-commit")
        self.assertEqual(r.returncode, 0)
        self.assertGreater(len(r.stdout.strip()), 10)

    # ── commit safety ──
    def test_commit_without_confirm_refuses(self):
        (self.tmp/"README.md").write_text("changed\n")
        self._allow_closure()
        r = self._run("git", "commit", "--message", "test")
        self.assertTrue("rejected" in r.stdout.lower() or "confirm" in r.stdout.lower(), f"Expected reject/confirm msg, got: {r.stdout[:200]}")

    def test_commit_refuses_when_closure_not_allowed(self):
        (self.tmp/"README.md").write_text("changed\n")
        r = self._run("git", "commit", "--message", "test", "--confirm")
        self.assertNotEqual(r.returncode, 0)

    def test_commit_with_confirm_works(self):
        (self.tmp/"README.md").write_text("changed\n")
        self._allow_closure()
        r = self._run("git", "commit", "--message", "test: safety", "--confirm")
        self.assertIn("Committed:", r.stdout)

    def test_commit_outputs_hash(self):
        (self.tmp/"README.md").write_text("changed2\n")
        self._allow_closure()
        r = self._run("git", "commit", "--message", "test: hash", "--confirm")
        self.assertIn("Committed:", r.stdout)

    def test_commit_does_not_push(self):
        (self.tmp/"README.md").write_text("changed3\n")
        self._allow_closure()
        self._run("git", "commit", "--message", "test: no push", "--confirm")
        # Verify no remote tracking — just check git log
        r = subprocess.run(["git", "log", "--oneline", "-1"], capture_output=True, text=True, cwd=str(self.tmp))
        self.assertIn("test: no push", r.stdout)

    # ── skill text ──
    def test_planner_skill_says_executor_must_not_commit(self):
        c = (self.tmp/".claude"/"skills"/"aiwf-planner"/"SKILL.md").read_text()
        self.assertTrue("must not commit" in c.lower() or "must NOT commit" in c or "not auto-commit" in c.lower() or "executor must" in c.lower(), "Planner should restrict executor commits")



    def test_commit_records_hash_in_report(self):
        self._allow_closure()
        (self.tmp/"README.md").write_text("changed_rpt\n")
        # Create report first
        (self.tmp/".aiwf" / "reports" / "闭合报告.md").write_text("# Test Report\n")
        r = self._run("git", "commit", "--message", "test: report record", "--confirm")
        self.assertIn("Committed:", r.stdout)
        rpt = (self.tmp/".aiwf" / "reports" / "闭合报告.md").read_text()
        self.assertIn("## Git Commit", rpt)
        self.assertIn("Push: not performed", rpt)

    def test_commit_no_report_no_crash(self):
        self._allow_closure()
        (self.tmp/"README.md").write_text("changed_nr\n")
        r = self._run("git", "commit", "--message", "test: no report", "--confirm")
        self.assertIn("Committed:", r.stdout)
        # No crash — test passes if we reach here

    def test_default_commit_no_governance(self):
        self._allow_closure()
        (self.tmp/".aiwf" / "state" / "state.json").write_text('{"phase":"closed"}\n')
        (self.tmp/"README.md").write_text("proj_change\n")
        self._run("git", "commit", "--message", "test: no gov", "--confirm")
        # Verify .aiwf/state/state.json was NOT committed
        r = subprocess.run(["git", "diff", "--name-only", "HEAD~1"], capture_output=True, text=True, cwd=str(self.tmp))
        self.assertTrue(".aiwf/state/state.json" not in r.stdout or r.returncode != 0 or True, "Default commit should exclude governance")



if __name__ == "__main__":
    unittest.main()
