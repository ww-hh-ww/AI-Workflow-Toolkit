from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


class GovernanceGitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aiwf_governance_git_"))
        subprocess.run(["git", "init", "-b", "main"], cwd=self.tmp, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "AIWF Test"], cwd=self.tmp, check=True)
        subprocess.run(["git", "config", "user.email", "aiwf@example.test"], cwd=self.tmp, check=True)
        (self.tmp / ".aiwf/config").mkdir(parents=True)
        (self.tmp / ".aiwf/state").mkdir(parents=True)
        (self.tmp / ".aiwf/runtime/internal").mkdir(parents=True)
        (self.tmp / ".aiwf/config/write-policy.json").write_text(json.dumps({
            "schema_version": 1,
            "governance_git_tracking": "tracked",
        }, indent=2) + "\n", encoding="utf-8")
        (self.tmp / ".aiwf/state/tasks.json").write_text(
            '{"schema_version": 1, "tasks": []}\n', encoding="utf-8",
        )
        (self.tmp / ".aiwf/runtime/internal/session.log").write_text(
            "local\n", encoding="utf-8",
        )
        (self.tmp / "app.txt").write_text("base\n", encoding="utf-8")
        from aiwf_core.core.governance_git import ensure_governance_gitignore

        ensure_governance_gitignore(self.tmp)
        subprocess.run(["git", "add", "-A"], cwd=self.tmp, check=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=self.tmp, check=True, capture_output=True,
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _git(self, *args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=self.tmp, check=True,
            capture_output=True, text=True,
        ).stdout.strip()

    def test_checkpoint_commits_only_stable_governance(self):
        from aiwf_core.core.governance_git import checkpoint_governance

        (self.tmp / ".aiwf/state/tasks.json").write_text(
            '{"schema_version": 1, "tasks": [{"id": "TASK-001"}]}\n',
            encoding="utf-8",
        )
        (self.tmp / ".aiwf/runtime/internal/session.log").write_text(
            "changed locally\n", encoding="utf-8",
        )
        (self.tmp / "app.txt").write_text("uncommitted project work\n", encoding="utf-8")

        result = checkpoint_governance(self.tmp, reason="before activation")

        self.assertTrue(result["committed"])
        self.assertEqual(
            self._git("show", "--pretty=format:", "--name-only", "HEAD").strip(),
            ".aiwf/state/tasks.json",
        )
        status = self._git("status", "--short")
        self.assertIn("app.txt", status)
        self.assertEqual(self._git("diff", "--cached", "--name-only"), "")
        self.assertNotIn(".aiwf/state/tasks.json", status)
        self.assertNotIn(".aiwf/runtime", status)

    def test_local_mode_untracks_governance_but_keeps_config(self):
        from aiwf_core.core.governance_git import set_governance_tracking

        result = set_governance_tracking(self.tmp, "local")

        self.assertTrue(result["committed"])
        tracked = self._git("ls-files", ".aiwf").splitlines()
        self.assertIn(".aiwf/config/write-policy.json", tracked)
        self.assertNotIn(".aiwf/state/tasks.json", tracked)
        policy = json.loads(
            (self.tmp / ".aiwf/config/write-policy.json").read_text(encoding="utf-8")
        )
        self.assertEqual(policy["governance_git_tracking"], "local")

        (self.tmp / ".aiwf/state/tasks.json").write_text(
            '{"schema_version": 1, "tasks": [{"id": "LOCAL"}]}\n',
            encoding="utf-8",
        )
        self.assertNotIn(".aiwf/state/tasks.json", self._git("status", "--short"))

    def test_checkpoint_accepts_an_existing_governance_only_index(self):
        from aiwf_core.core.governance_git import checkpoint_governance

        (self.tmp / ".aiwf/state/tasks.json").write_text(
            '{"schema_version": 1, "tasks": [{"id": "STAGED"}]}\n',
            encoding="utf-8",
        )
        subprocess.run(
            ["git", "add", ".aiwf/state/tasks.json"], cwd=self.tmp, check=True,
        )

        result = checkpoint_governance(self.tmp)

        self.assertTrue(result["committed"])
        self.assertEqual(self._git("diff", "--cached", "--name-only"), "")
        self.assertEqual(
            self._git("show", "--pretty=format:", "--name-only", "HEAD").strip(),
            ".aiwf/state/tasks.json",
        )

    def test_checkpoint_rejects_an_index_with_project_files(self):
        from aiwf_core.core.governance_git import checkpoint_governance

        (self.tmp / ".aiwf/state/tasks.json").write_text(
            '{"schema_version": 1, "tasks": [{"id": "PENDING"}]}\n',
            encoding="utf-8",
        )
        (self.tmp / "app.txt").write_text("staged project work\n", encoding="utf-8")
        subprocess.run(["git", "add", "app.txt"], cwd=self.tmp, check=True)

        with self.assertRaisesRegex(ValueError, "will not disturb an existing Git index"):
            checkpoint_governance(self.tmp)

    def test_tracked_mode_restores_governance_after_local_mode(self):
        from aiwf_core.core.governance_git import set_governance_tracking

        set_governance_tracking(self.tmp, "local")
        result = set_governance_tracking(self.tmp, "tracked")

        self.assertTrue(result["committed"])
        tracked = self._git("ls-files", ".aiwf").splitlines()
        self.assertIn(".aiwf/config/write-policy.json", tracked)
        self.assertIn(".aiwf/state/tasks.json", tracked)
        self.assertNotIn(".aiwf/runtime/internal/session.log", tracked)


if __name__ == "__main__":
    unittest.main()
