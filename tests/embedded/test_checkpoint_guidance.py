"""Checkpoint mode guidance: skills reference stash/patch, commit safety, fallback."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 15

class TestCheckpointGuidance(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awcg_"))
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        subprocess.run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                       capture_output=True, text=True, cwd=str(cls.tmp), env=env, timeout=20)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _content(self, path):
        return (self.tmp/".claude"/path).read_text()

    # ── planner ──
    def test_planner_has_mode_stash(self):
        self.assertIn("--mode stash", self._content("skills/aiwf-planner-meta/SKILL.md"))

    def test_planner_has_mode_patch(self):
        self.assertIn("--mode patch", self._content("skills/aiwf-planner-meta/SKILL.md"))

    def test_planner_mentions_L2_L3_risky(self):
        c = self._content("skills/aiwf-planner-meta/SKILL.md")
        self.assertIn("L2", c)
        self.assertIn("L3", c)

    def test_planner_says_not_a_git_commit(self):
        self.assertIn("not a git commit", self._content("skills/aiwf-planner-meta/SKILL.md").lower())

    # ── reviewer ──
    def test_reviewer_has_stash_patch(self):
        c = self._content("agents/aiwf-reviewer.md")
        self.assertIn("stash checkpoint", c.lower())
        self.assertIn("checkpoint", c.lower())

    def test_reviewer_has_skip_reason(self):
        self.assertIn("skip reason", self._content("agents/aiwf-reviewer.md").lower())

    def test_reviewer_missing_checkpoint_blocker(self):
        self.assertIn("blocker", self._content("skills/aiwf-review/SKILL.md").lower())

    # ── close ──
    def test_create_default_is_patch(self):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        subprocess.run(["git", "init", "-b", "main"], cwd=str(self.tmp), capture_output=True, timeout=5)
        subprocess.run(["git", "config", "user.email", "a@b.c"], cwd=str(self.tmp), capture_output=True, timeout=5)
        subprocess.run(["git", "config", "user.name", "t"], cwd=str(self.tmp), capture_output=True, timeout=5)
        (self.tmp/"README.md").write_text("init\n")
        subprocess.run(["git", "add", "README.md"], cwd=str(self.tmp), capture_output=True, timeout=5)
        subprocess.run(["git", "commit", "-m", "init"], cwd=str(self.tmp), capture_output=True, timeout=5)
        (self.tmp/"README.md").write_text("changed\n")
        r = subprocess.run([sys.executable, "-m", "aiwf_core.cli", "checkpoint", "create", "--label", "default-test"],
                          capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        self.assertEqual(r.returncode, 0)
        for d in (self.tmp/".aiwf"/"checkpoints").iterdir():
            ck = json.loads((d/"CHECKPOINT.json").read_text())
            if ck.get("label") == "default-test":
                self.assertEqual(ck.get("provider", "patch"), "patch")
                break


if __name__ == "__main__":
    unittest.main()
