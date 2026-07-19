import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


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
            json.dumps({"schema_version": 1, "tasks": [task]}, indent=2) + "\n",
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

    def test_recorded_repair_routes_to_tester_and_verified_fix_loop_resolves(self):
        from aiwf_core.commands.flow import _task_next
        from aiwf_core.core.state.context_ops import record_implementation
        from aiwf_core.core.state.testing_ops import record_testing
        from aiwf_core.core.task_records import load_task_record

        (self.tmp / "src").mkdir(exist_ok=True)
        feature = self.tmp / "src/feature.py"
        feature.write_text("VALUE = 1\n", encoding="utf-8")
        record_implementation(str(self.tmp), "initial implementation")
        record_testing(
            str(self.tmp), status="failed", commands=["pytest -q"],
            failure_summary="feature still fails",
        )
        failed_record = load_task_record(self.tmp, "TASK-001")
        self.assertEqual(failed_record["fix_loop"]["route"], "executor")

        feature.write_text("VALUE = 2\n", encoding="utf-8")
        record_implementation(str(self.tmp), "small repair recorded inline")
        repaired_record = load_task_record(self.tmp, "TASK-001")
        self.assertEqual(repaired_record["fix_loop"]["status"], "open")
        self.assertEqual(repaired_record["fix_loop"]["route"], "tester")
        task = json.loads((self.tmp / ".aiwf/state/tasks.json").read_text())["tasks"][0]
        next_role, next_action = _task_next(task, repaired_record)
        self.assertEqual(next_role, "Verification follow-up")
        self.assertIn("retest inline", next_action)
        self.assertIn("dispatch aiwf-tester", next_action)

        result = record_testing(
            str(self.tmp), status="passed", commands=["pytest -q"],
            coverage_summary="repair verified",
            verification_results=[{
                "command": "pytest -q", "expected": "pass",
                "observed": "1 passed", "matched": True,
            }],
        )
        self.assertTrue(result["fix_loop_resolved"])
        verified_record = load_task_record(self.tmp, "TASK-001")
        self.assertEqual(verified_record["fix_loop"]["status"], "resolved")
        self.assertEqual(_task_next(task, verified_record)[0], "Reviewer")

    def test_write_after_review_invalidates_close(self):
        from aiwf_core.core.task_ledger import close_task

        self._record_full_chain()
        (self.tmp / "src/feature.py").write_text("VALUE = 2\n", encoding="utf-8")
        result = close_task(str(self.tmp))
        self.assertFalse(result["closed"])
        blockers = " ".join(result["blockers"])
        self.assertIn("changed after review", blockers)
        self.assertIn("modified: src/feature.py", blockers)
        self.assertIn("intentionally outside the branch", blockers)

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

    def test_close_commits_unicode_and_space_in_filename(self):
        from aiwf_core.core.state.context_ops import record_implementation
        from aiwf_core.core.state.review_ops import record_review
        from aiwf_core.core.state.testing_ops import record_testing
        from aiwf_core.core.task_ledger import close_task

        relative = ".claude/skills/teach/lessons/0001-电路变量 与基本定律.html"
        lesson = self.tmp / relative
        lesson.parent.mkdir(parents=True, exist_ok=True)
        lesson.write_text("<h1>电路变量与基本定律</h1>\n", encoding="utf-8")

        implementation = record_implementation(str(self.tmp), "created the lesson")
        self.assertEqual(implementation["changed_files"], [relative])
        record_testing(
            str(self.tmp), status="passed", commands=[f"test -f '{relative}'"],
            coverage_summary="lesson exists",
        )
        record_review(
            str(self.tmp), result="accepted", closure_allowed=True,
            summary="the reviewed lesson path is exact",
        )
        before_close = subprocess.run(
            ["git", "cat-file", "-e", f"HEAD:{relative}"], cwd=self.tmp,
            capture_output=True, text=True,
        )
        self.assertNotEqual(before_close.returncode, 0)

        result = close_task(str(self.tmp))
        self.assertTrue(result["closed"], result["blockers"])
        commit = result["task"]["closure"]["git_commit"]
        tree = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", "-z", commit],
            cwd=self.tmp, check=True, capture_output=True, text=True,
        ).stdout.split("\0")
        self.assertIn(relative, tree)

    def test_new_review_removes_old_closure_calibration(self):
        task_doc = self.tmp / ".aiwf/tasks/TASK-001.md"
        task_doc.parent.mkdir(parents=True, exist_ok=True)
        task_doc.write_text(
            "---\nid: TASK-001\n---\n\n# TASK-001\n\n"
            "## Closure Calibration\n\nStale result from an earlier review.\n",
            encoding="utf-8",
        )

        self._record_full_chain()

        self.assertNotIn("## Closure Calibration", task_doc.read_text(encoding="utf-8"))

    def test_activation_rejects_protected_branch_and_dirty_start(self):
        from aiwf_core.core.git_workflow import task_activation_git_blockers

        self.assertEqual(task_activation_git_blockers(str(self.tmp)), [])
        (self.tmp / "unrelated.txt").write_text("dirty\n", encoding="utf-8")
        self.assertIn("clean project worktree", " ".join(task_activation_git_blockers(str(self.tmp))))
        (self.tmp / "unrelated.txt").unlink()
        subprocess.run(["git", "switch", "main"], cwd=self.tmp, check=True, capture_output=True)
        self.assertIn("protected branch", " ".join(task_activation_git_blockers(str(self.tmp))))

    def test_plan_closes_only_after_feature_branch_is_merged(self):
        from aiwf_core.core.git_workflow import (
            bind_plan_branch,
            plan_close_blockers,
            plan_integration_state,
            plan_merged_into_base,
        )
        from aiwf_core.core.state.plan_ops import load_plans, save_plans

        plan = {"task_status": {"TASK-001": "closed"}}
        bind_plan_branch(str(self.tmp), plan)
        (self.tmp / "merged.txt").write_text("done\n", encoding="utf-8")
        subprocess.run(["git", "add", "merged.txt"], cwd=self.tmp, check=True)
        subprocess.run(["git", "commit", "-m", "task"], cwd=self.tmp, check=True, capture_output=True)
        plan["git_head_ref"] = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=self.tmp, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        plan.update({"id": "PLAN-001", "plan_id": "PLAN-001", "status": "open"})
        self.assertFalse(plan_merged_into_base(str(self.tmp), plan))
        self.assertEqual(plan_integration_state(str(self.tmp), plan), "awaiting_decision")

        save_plans(str(self.tmp), {"schema_version": 1, "plans": [plan]})
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        held = subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", "plan", "hold", "PLAN-001"],
            cwd=self.tmp, env=env, capture_output=True, text=True,
        )
        self.assertEqual(held.returncode, 0, held.stderr)
        self.assertIn("Plan integration held", held.stdout)
        plan = load_plans(str(self.tmp))["plans"][0]
        self.assertEqual(plan["integration_hold_ref"], plan["git_head_ref"])
        self.assertEqual(plan_integration_state(str(self.tmp), plan), "held")

        from aiwf_core.aiwf_ui import _build_detail, _build_status_bar, load_all

        ui_data = load_all(self.tmp)
        detail = _build_detail(
            {"kind": "plan", "id": "PLAN-001", "title": "Plan 1"}, ui_data,
        )
        self.assertIn(" Next: Intentionally left open", detail)
        self.assertIn("保留Plan=1", _build_status_bar(ui_data))

        self.assertIn("switch to 'main'", " ".join(plan_close_blockers(str(self.tmp), plan)))
        subprocess.run(["git", "switch", "main"], cwd=self.tmp, check=True, capture_output=True)
        subprocess.run(
            ["git", "merge", "--no-ff", "feature/test", "-m", "merge plan"],
            cwd=self.tmp, check=True, capture_output=True,
        )
        self.assertTrue(plan_merged_into_base(str(self.tmp), plan))
        self.assertEqual(plan_integration_state(str(self.tmp), plan), "merged_pending_close")
        self.assertEqual(plan_close_blockers(str(self.tmp), plan), [])

    def test_new_task_clears_a_held_plan_decision(self):
        from aiwf_core.core.state.plan_ops import (
            attach_task_to_plan,
            load_plans,
            save_plans,
        )

        save_plans(str(self.tmp), {
            "schema_version": 1,
            "plans": [{
                "id": "PLAN-HELD",
                "plan_id": "PLAN-HELD",
                "status": "open",
                "task_ids": ["TASK-DONE"],
                "task_status": {"TASK-DONE": "closed"},
                "integration_hold_ref": "abc123",
            }],
        })

        result = attach_task_to_plan(str(self.tmp), "PLAN-HELD", "TASK-NEXT")

        self.assertTrue(result["attached"])
        plan = load_plans(str(self.tmp))["plans"][0]
        self.assertNotIn("integration_hold_ref", plan)
        self.assertEqual(plan["task_status"]["TASK-NEXT"], "unknown")

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
