import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


class TestGitTaskRecords(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aiwf_git_records_"))
        from aiwf_core.core.state_schema import MVP_STATE_FILES

        for rel, default_fn in MVP_STATE_FILES.items():
            path = self.tmp / ".aiwf" / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(default_fn(), indent=2) + "\n", encoding="utf-8")
        subprocess.run(["git", "init", "-b", "main"], cwd=self.tmp, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.tmp, check=True)
        subprocess.run(["git", "config", "user.name", "AIWF Test"], cwd=self.tmp, check=True)
        (self.tmp / "README.md").write_text("base\n", encoding="utf-8")
        (self.tmp / "CLAUDE.md").write_text("base project rules\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md", "CLAUDE.md"], cwd=self.tmp, check=True)
        subprocess.run(["git", "commit", "-m", "base"], cwd=self.tmp, check=True, capture_output=True)
        subprocess.run(["git", "switch", "-c", "feature/test"], cwd=self.tmp, check=True, capture_output=True)
        self.origin = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=self.tmp, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        task = {
            "id": "TASK-001", "title": "ship feature", "status": "active",
            "git_origin_ref": self.origin,
            "requirements": {
                "executor_required": True,
                "tester_required": True,
                "reviewer_required": True,
            },
        }
        (self.tmp / ".aiwf/state/tasks.json").write_text(
            json.dumps({"schema_version": 1, "default_max_active": 1, "tasks": [task]}, indent=2) + "\n",
            encoding="utf-8",
        )
        state = json.loads((self.tmp / ".aiwf/state/state.json").read_text())
        state.update({"active_task_id": "TASK-001", "phase": "executing", "git_origin_ref": self.origin})
        (self.tmp / ".aiwf/state/state.json").write_text(json.dumps(state, indent=2) + "\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _record_full_chain(self):
        from aiwf_core.core.state.context_ops import record_implementation
        from aiwf_core.core.state.review_ops import record_review
        from aiwf_core.core.state.testing_ops import record_testing

        (self.tmp / "src").mkdir(exist_ok=True)
        (self.tmp / "src/feature.py").write_text("VALUE = 1\n", encoding="utf-8")
        implementation = record_implementation(
            str(self.tmp), "implemented and wired feature", command="python -m compileall src",
        )
        (self.tmp / "tests").mkdir(exist_ok=True)
        (self.tmp / "tests/test_feature.py").write_text("def test_value(): assert 1 == 1\n", encoding="utf-8")
        testing = record_testing(
            str(self.tmp), status="passed", commands=["pytest -q"],
            coverage_summary="tests passed",
            verification_results=[{
                "command": "pytest -q", "expected": "pass", "observed": "1 passed", "matched": True,
            }],
        )
        review = record_review(
            str(self.tmp), result="accepted", closure_allowed=True,
            summary="implementation and tests form one sound change",
        )
        return implementation, testing, review

    def test_tester_snapshot_extends_implementation_and_review_matches_it(self):
        implementation, testing, review = self._record_full_chain()
        self.assertEqual(testing["based_on_ref"], implementation["implementation_ref"])
        self.assertNotEqual(testing["tested_ref"], implementation["implementation_ref"])
        self.assertEqual(review["reviewed_ref"], testing["tested_ref"])
        self.assertEqual(testing["test_changed_files"], ["tests/test_feature.py"])
        self.assertNotIn("evidence_id", testing)
        self.assertNotIn("accepted_evidence_ids", review)

    def test_write_after_review_invalidates_close(self):
        from aiwf_core.core.task_ledger import close_task

        self._record_full_chain()
        (self.tmp / "src/feature.py").write_text("VALUE = 2\n", encoding="utf-8")
        result = close_task(str(self.tmp))
        self.assertFalse(result["closed"])
        self.assertIn("changed after review", " ".join(result["blockers"]))

    def test_close_commits_the_reviewed_implementation_and_tests(self):
        from aiwf_core.core.task_ledger import close_task

        _, testing, _ = self._record_full_chain()
        result = close_task(str(self.tmp), note="feature and tests completed")
        self.assertTrue(result["closed"], result["blockers"])
        commit = result["task"]["closure"]["git_commit"]
        committed = subprocess.run(
            ["git", "show", "--format=", "--name-only", commit], cwd=self.tmp,
            check=True, capture_output=True, text=True,
        ).stdout.splitlines()
        self.assertIn("src/feature.py", committed)
        self.assertIn("tests/test_feature.py", committed)
        self.assertEqual(result["task"]["closure"]["reviewed_ref"], testing["tested_ref"])

    def test_activation_rejects_protected_branch_and_dirty_start(self):
        from aiwf_core.core.git_workflow import task_activation_git_blockers

        self.assertEqual(task_activation_git_blockers(str(self.tmp)), [])
        (self.tmp / "unrelated.txt").write_text("dirty\n", encoding="utf-8")
        self.assertIn("clean project worktree", " ".join(task_activation_git_blockers(str(self.tmp))))
        (self.tmp / "unrelated.txt").unlink()
        subprocess.run(["git", "switch", "main"], cwd=self.tmp, check=True, capture_output=True)
        self.assertIn("protected branch", " ".join(task_activation_git_blockers(str(self.tmp))))

    def test_plan_closes_only_after_feature_branch_is_merged(self):
        from aiwf_core.core.git_workflow import bind_plan_branch, plan_close_blockers

        plan = {"task_status": {"TASK-001": "closed"}}
        bind_plan_branch(str(self.tmp), plan)
        (self.tmp / "merged.txt").write_text("done\n", encoding="utf-8")
        subprocess.run(["git", "add", "merged.txt"], cwd=self.tmp, check=True)
        subprocess.run(["git", "commit", "-m", "task"], cwd=self.tmp, check=True, capture_output=True)
        plan["git_head_ref"] = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=self.tmp, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        self.assertIn("switch to 'main'", " ".join(plan_close_blockers(str(self.tmp), plan)))
        subprocess.run(["git", "switch", "main"], cwd=self.tmp, check=True, capture_output=True)
        subprocess.run(
            ["git", "merge", "--no-ff", "feature/test", "-m", "merge plan"],
            cwd=self.tmp, check=True, capture_output=True,
        )
        self.assertEqual(plan_close_blockers(str(self.tmp), plan), [])

    def test_reviewed_rename_is_committed_as_the_exact_snapshot(self):
        from aiwf_core.core.state.context_ops import record_implementation
        from aiwf_core.core.state.review_ops import record_review
        from aiwf_core.core.state.testing_ops import record_testing
        from aiwf_core.core.task_ledger import close_task

        (self.tmp / "README.md").rename(self.tmp / "PROJECT.md")
        record_implementation(str(self.tmp), "renamed the project document")
        record_testing(str(self.tmp), status="passed", commands=["test -f PROJECT.md"],
                       coverage_summary="renamed file exists")
        record_review(str(self.tmp), result="accepted", closure_allowed=True,
                      summary="rename is complete and no old path remains")
        result = close_task(str(self.tmp))
        self.assertTrue(result["closed"], result["blockers"])
        self.assertTrue((self.tmp / "PROJECT.md").exists())
        self.assertFalse((self.tmp / "README.md").exists())

    def test_project_instruction_changes_are_in_the_reviewed_snapshot(self):
        from aiwf_core.core.git_workflow import changed_project_files
        from aiwf_core.core.task_ledger import close_task

        (self.tmp / "CLAUDE.md").write_text("updated project rules\n", encoding="utf-8")
        self.assertIn("CLAUDE.md", changed_project_files(str(self.tmp)))

        implementation, _, _ = self._record_full_chain()
        self.assertIn("CLAUDE.md", implementation["changed_files"])
        result = close_task(str(self.tmp))
        self.assertTrue(result["closed"], result["blockers"])
        committed = subprocess.run(
            ["git", "show", "--format=", "--name-only", result["task"]["closure"]["git_commit"]],
            cwd=self.tmp, check=True, capture_output=True, text=True,
        ).stdout.splitlines()
        self.assertIn("CLAUDE.md", committed)


if __name__ == "__main__":
    unittest.main()
