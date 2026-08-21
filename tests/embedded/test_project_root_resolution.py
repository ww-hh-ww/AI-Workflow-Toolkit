"""AIWF commands and hooks stay anchored to the installed project root."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 20


class TestProjectRootResolution(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aiwf_root_resolution_"))
        self.child = self.tmp / "app" / "Sources"
        self.child.mkdir(parents=True)
        result = self._run(self.tmp, "install", "claude", "--force")
        self.assertEqual(result.returncode, 0, result.stderr)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, cwd, *args):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", *args],
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )

    def test_nested_cli_command_uses_installed_ancestor(self):
        result = self._run(self.child, "plan", "create", "PLAN-NESTED")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(
            (self.tmp / ".aiwf" / "plans" / "PLAN-NESTED.md").exists()
        )
        self.assertFalse((self.tmp / "app" / ".aiwf").exists())
        self.assertFalse((self.child / ".aiwf").exists())

    def test_partial_nested_aiwf_does_not_shadow_installed_ancestor(self):
        partial = self.tmp / "app" / ".aiwf" / "state"
        partial.mkdir(parents=True)
        (partial / "state.json").write_text(
            json.dumps({"scope_violation": True}) + "\n", encoding="utf-8"
        )

        result = self._run(self.child, "plan", "create", "PLAN-RECOVERED")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(
            (self.tmp / ".aiwf" / "plans" / "PLAN-RECOVERED.md").exists()
        )
        self.assertFalse(
            (self.tmp / "app" / ".aiwf" / "plans" / "PLAN-RECOVERED.md").exists()
        )

    def test_event_normalizer_uses_installed_ancestor(self):
        from aiwf_core.adapters.claude.normalize_event import normalize

        event = normalize({
            "hook_event_name": "PreToolUse",
            "cwd": str(self.child),
            "tool_name": "Write",
            "tool_input": {"file_path": str(self.tmp / "app" / "Sources" / "File.swift")},
        })

        self.assertEqual(Path(event.cwd), self.tmp.resolve())

    def test_explicit_nested_install_creates_independent_root(self):
        nested_root = self.tmp / "independent"
        nested_root.mkdir()

        result = self._run(nested_root, "install", "claude", "--force")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((nested_root / ".aiwf" / "state" / "state.json").exists())
        self.assertTrue((nested_root / ".claude" / "settings.json").exists())

    def test_install_without_git_on_path_still_creates_a_project(self):
        root = self.tmp / "no-git"
        root.mkdir()
        env = os.environ.copy()
        env["PATH"] = ""
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        result = subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
            cwd=str(root), env=env, capture_output=True, text=True, timeout=TIMEOUT,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((root / ".aiwf" / "state" / "state.json").exists())
        self.assertFalse((root / ".git").exists())
        self.assertIn(
            "/.aiwf/runtime/",
            (root / ".gitignore").read_text(encoding="utf-8"),
        )
        self.assertIn("not a Git repository", result.stdout)

    def test_record_commands_keep_nested_plan_worktree_context(self):
        from aiwf_core.core.plan_worktrees import _hide_worktree_governance

        subprocess.run(["git", "init", "-b", "main"], cwd=self.tmp, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=self.tmp, check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "AIWF Test"],
            cwd=self.tmp, check=True,
        )
        (self.tmp / "seed.txt").write_text("seed\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.tmp, check=True)
        subprocess.run(
            ["git", "commit", "-m", "seed"],
            cwd=self.tmp, check=True, capture_output=True,
        )
        origin = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=self.tmp, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        worktree = self.tmp / ".claude" / "worktrees" / "plan-005"
        subprocess.run(
            ["git", "worktree", "add", "-b", "plan-005", str(worktree)],
            cwd=self.tmp, check=True, capture_output=True,
        )
        _hide_worktree_governance(worktree)

        task_doc = self.tmp / ".aiwf" / "tasks" / "TASK-004.md"
        task_doc.write_text(
            """# TASK-004

## Fixed Contract

### Structural Home

GOAL-001 / PLAN-005.

### Objective

Record work from the Plan worktree.

### Contract Responsibility

Keep role records bound to the assigned worktree.

### Proof Standard

- [Running] The assigned worktree records the result.

Verification Commands:

| ID | Command | Expected |
| --- | --- | --- |
| V-001 | test -f src/feature.txt | feature file exists |
""",
            encoding="utf-8",
        )
        tasks = json.loads((self.tmp / ".aiwf" / "state" / "tasks.json").read_text())
        tasks["tasks"] = [{
            "id": "TASK-004",
            "status": "active",
            "phase": "implementing",
            "doc_path": ".aiwf/tasks/TASK-004.md",
            "worktree_path": str(worktree.resolve()),
            "git_origin_ref": origin,
            "git_branch": "plan-005",
            "requirements": {
                "executor_required": False,
                "tester_required": False,
                "reviewer_required": False,
            },
        }]
        (self.tmp / ".aiwf" / "state" / "tasks.json").write_text(
            json.dumps(tasks, indent=2) + "\n", encoding="utf-8",
        )
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["active_task_id"] = "TASK-004"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(
            json.dumps(state, indent=2) + "\n", encoding="utf-8",
        )
        (worktree / "src").mkdir()
        (worktree / "src" / "feature.txt").write_text("ready\n", encoding="utf-8")

        def run_record(*args):
            return subprocess.run(
                [sys.executable, "-m", "aiwf_core.cli", *args],
                cwd=worktree,
                env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT)},
                capture_output=True,
                text=True,
                timeout=TIMEOUT,
            )

        implementation = run_record(
            "record", "implementation", "--task-id", "TASK-004",
            "--summary", "created the feature file",
        )
        self.assertEqual(implementation.returncode, 0, implementation.stderr)
        testing = run_record(
            "record", "testing", "--task-id", "TASK-004", "--status", "passed",
            "--check", "V-001", "--observed", "feature exists",
            "--verdict", "matched", "--basis", "the assigned worktree contains the file",
        )
        self.assertEqual(testing.returncode, 0, testing.stderr)
        review = run_record(
            "record", "review", "--task-id", "TASK-004", "--result", "accepted",
            "--summary", "records and evidence use the assigned worktree",
        )
        self.assertEqual(review.returncode, 0, review.stderr)


if __name__ == "__main__":
    unittest.main()
