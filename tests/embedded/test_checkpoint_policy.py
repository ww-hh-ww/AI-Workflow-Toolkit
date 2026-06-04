"""Checkpoint risk-trigger policy: L0/L1 no default, L2 risk-triggered, L3 must."""
import os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

class TestCheckpointPolicy(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awcp2_"))
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        subprocess.run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                       capture_output=True, text=True, cwd=str(cls.tmp), env=env, timeout=20)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _planner(self): return (self.tmp/".claude"/"skills"/"aiwf-planner"/"SKILL.md").read_text()
    def _reviewer(self): return (self.tmp/".claude"/"skills"/"aiwf-review"/"SKILL.md").read_text()
    def _close(self): return (self.tmp/".claude"/"skills"/"aiwf-close"/"SKILL.md").read_text()

    # ── L0/L1 no default ──
    def test_L0_no_checkpoint_by_default(self):
        self.assertIn("no checkpoint needed", self._planner().lower())

    def test_L1_no_checkpoint_by_default(self):
        c = self._planner()
        self.assertIn("L1", c)
        self.assertIn("no checkpoint needed", c.lower())

    # ── L2 risk-triggered ──
    def test_L2_is_risk_triggered_not_automatic(self):
        c = self._planner()
        self.assertIn("L2", c)
        self.assertIn("risk-triggered", c.lower())

    def test_L2_lists_risk_triggers(self):
        c = self._planner()
        triggers = ["multi-file", "shared", "API", "refactor", "external drift", "generated", "rollback"]
        found = sum(1 for t in triggers if t.lower() in c.lower())
        self.assertGreaterEqual(found, 4, f"Only {found}/7 risk triggers found")

    # ── L3 must, skip reason ──
    def test_L3_must_checkpoint_unless_skip(self):
        c = self._planner()
        self.assertIn("L3", c)
        self.assertIn("must create", c.lower())
        self.assertIn("skip", c.lower())

    def test_skip_reason_uses_goal_decide(self):
        c = self._planner()
        self.assertIn("goal decide", c.lower())

    # ── Modes ──
    def test_stash_mode_present(self):
        self.assertIn("--mode stash", self._planner())

    def test_patch_mode_present(self):
        self.assertIn("--mode patch", self._planner())

    def test_not_git_commit(self):
        self.assertIn("not a git commit", self._planner().lower())

    # ── Reviewer ──
    def test_reviewer_L2_only_with_triggers(self):
        c = self._reviewer()
        self.assertIn("L2", c)
        self.assertIn("risk trigger", c.lower())

    def test_reviewer_L3_requires_checkpoint_or_skip(self):
        c = self._reviewer()
        self.assertIn("L3", c)
        self.assertIn("skip", c.lower())

    def test_reviewer_blocks_risky_not_every_L2(self):
        c = self._reviewer()
        self.assertIn("not every l2", c.lower())

    # ── Close ──
    def test_close_distinguishes_checkpoint_vs_commit(self):
        c = self._close()
        self.assertIn("checkpoint", c.lower())
        self.assertIn("git commit", c.lower())
        self.assertIn("confirm", c.lower())


if __name__ == "__main__":
    unittest.main()
