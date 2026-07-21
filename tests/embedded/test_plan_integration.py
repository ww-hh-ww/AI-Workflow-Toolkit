import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


class TestPlanIntegration(unittest.TestCase):
    def setUp(self):
        self.control = Path(tempfile.mkdtemp(prefix="aiwf_plan_integration_"))
        self.worktree = self.control.parent / f"{self.control.name}_plan"
        subprocess.run(["git", "init", "-b", "main"], cwd=self.control, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.control, check=True)
        subprocess.run(["git", "config", "user.name", "AIWF Test"], cwd=self.control, check=True)
        (self.control / "app.txt").write_text("base\n", encoding="utf-8")
        subprocess.run(["git", "add", "app.txt"], cwd=self.control, check=True)
        subprocess.run(["git", "commit", "-m", "base"], cwd=self.control, check=True, capture_output=True)
        subprocess.run(
            ["git", "worktree", "add", "-b", "aiwf/plan-001", str(self.worktree), "main"],
            cwd=self.control, check=True, capture_output=True,
        )
        (self.worktree / "feature.txt").write_text("feature\n", encoding="utf-8")
        subprocess.run(["git", "add", "feature.txt"], cwd=self.worktree, check=True)
        subprocess.run(["git", "commit", "-m", "TASK-001: feature"], cwd=self.worktree,
                       check=True, capture_output=True)
        self.plan_head = self._git(self.worktree, "rev-parse", "HEAD")

        state = self.control / ".aiwf/state"
        state.mkdir(parents=True)
        (state / "plans.json").write_text(json.dumps({
            "schema_version": 1,
            "plans": [{
                "id": "PLAN-001",
                "plan_id": "PLAN-001",
                "title": "Feature plan",
                "status": "open",
                "dependencies": [],
                "task_ids": ["TASK-001"],
                "task_status": {"TASK-001": "closed"},
                "git_worktree_path": str(self.worktree),
                "git_branch": "aiwf/plan-001",
                "git_base_branch": "main",
                "git_base_ref": self._git(self.control, "rev-parse", "main"),
                "git_head_ref": self.plan_head,
            }],
        }, indent=2) + "\n", encoding="utf-8")

    def tearDown(self):
        subprocess.run(["git", "worktree", "remove", "--force", str(self.worktree)],
                       cwd=self.control, capture_output=True)
        shutil.rmtree(self.worktree, ignore_errors=True)
        shutil.rmtree(self.control, ignore_errors=True)

    @staticmethod
    def _git(cwd: Path, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=cwd, check=True,
                              capture_output=True, text=True).stdout.strip()

    def test_prepare_prove_merge_and_close_uses_exact_candidate(self):
        from aiwf_core.core.git_snapshots import ref_tree
        from aiwf_core.core.git_workflow import plan_close_blockers, plan_integration_state
        from aiwf_core.core.plan_integration import finish_plan_integration, prepare_plan_integration
        from aiwf_core.core.state.plan_ops import load_plans

        (self.control / "base.txt").write_text("new base\n", encoding="utf-8")
        subprocess.run(["git", "add", "base.txt"], cwd=self.control, check=True)
        subprocess.run(["git", "commit", "-m", "advance main"], cwd=self.control,
                       check=True, capture_output=True)

        prepared = prepare_plan_integration(str(self.control), "PLAN-001")
        self.assertTrue(prepared["prepared"])
        self.assertNotEqual(prepared["candidate_ref"], self.plan_head)
        plan = load_plans(str(self.control))["plans"][0]
        self.assertEqual(plan_integration_state(str(self.control), plan), "integration_ready")

        result = finish_plan_integration(
            str(self.control), "PLAN-001", status="passed",
            commands=["test -f feature.txt"],
            verification_results=[{
                "command": "test -f feature.txt", "expected": "exit 0",
                "observed": "exit 0", "matched": True,
            }],
            summary="feature and current base work together",
        )
        self.assertTrue(result["merged"])
        plan = load_plans(str(self.control))["plans"][0]
        merge_commit = plan["integration"]["merge_commit"]
        self.assertEqual(self._git(self.control, "rev-parse", "HEAD"), merge_commit)
        self.assertEqual(ref_tree(str(self.control), merge_commit),
                         plan["integration"]["candidate_tree"])
        self.assertEqual(plan_integration_state(str(self.control), plan), "merged_pending_close")
        self.assertEqual(plan_close_blockers(str(self.control), plan), [])

    def test_base_change_invalidates_prepared_candidate(self):
        from aiwf_core.core.git_workflow import plan_integration_state
        from aiwf_core.core.plan_integration import finish_plan_integration, prepare_plan_integration
        from aiwf_core.core.state.plan_ops import load_plans

        prepare_plan_integration(str(self.control), "PLAN-001")
        (self.control / "later.txt").write_text("later\n", encoding="utf-8")
        subprocess.run(["git", "add", "later.txt"], cwd=self.control, check=True)
        subprocess.run(["git", "commit", "-m", "move base"], cwd=self.control,
                       check=True, capture_output=True)
        plan = load_plans(str(self.control))["plans"][0]
        self.assertEqual(plan_integration_state(str(self.control), plan), "base_changed")
        with self.assertRaisesRegex(ValueError, "base branch changed"):
            finish_plan_integration(
                str(self.control), "PLAN-001", status="passed",
                commands=["true"],
                verification_results=[{
                    "command": "true", "expected": "exit 0", "observed": "exit 0",
                    "matched": True,
                }],
                summary="stale proof",
            )

    def test_already_merged_plan_can_adopt_and_verify_current_base(self):
        from aiwf_core.core.git_workflow import plan_integration_state
        from aiwf_core.core.plan_integration import finish_plan_integration, prepare_plan_integration
        from aiwf_core.core.state.plan_ops import load_plans

        subprocess.run(
            ["git", "merge", "--no-ff", "aiwf/plan-001", "-m", "manual merge"],
            cwd=self.control, check=True, capture_output=True,
        )
        merged_head = self._git(self.control, "rev-parse", "HEAD")
        plan = load_plans(str(self.control))["plans"][0]
        self.assertEqual(plan_integration_state(str(self.control), plan), "merged_unverified")

        prepared = prepare_plan_integration(str(self.control), "PLAN-001")
        self.assertTrue(prepared["already_merged"])
        self.assertEqual(prepared["candidate_ref"], merged_head)
        self.assertEqual(Path(prepared["candidate_worktree"]).resolve(), self.control.resolve())
        plan = load_plans(str(self.control))["plans"][0]
        self.assertEqual(plan_integration_state(str(self.control), plan), "integration_ready")

        result = finish_plan_integration(
            str(self.control), "PLAN-001", status="passed",
            commands=["test -f feature.txt"],
            verification_results=[{
                "command": "test -f feature.txt", "expected": "exit 0",
                "observed": "exit 0", "matched": True,
            }],
            summary="adopted merged result verified",
        )
        self.assertEqual(result["integration"]["merge_commit"], merged_head)
        plan = load_plans(str(self.control))["plans"][0]
        self.assertEqual(plan_integration_state(str(self.control), plan), "merged_pending_close")

    def test_conflict_preflight_does_not_dirty_either_worktree(self):
        from aiwf_core.core.plan_integration import prepare_plan_integration
        from aiwf_core.core.state.plan_ops import load_plans, save_plans
        from aiwf_core.core.task_ledger import activate_task, load_ledger, upsert_task

        # Replace the feature commit with an overlapping change and update the governed head.
        (self.worktree / "app.txt").write_text("plan\n", encoding="utf-8")
        subprocess.run(["git", "add", "app.txt"], cwd=self.worktree, check=True)
        subprocess.run(["git", "commit", "-m", "TASK-002: overlap"], cwd=self.worktree,
                       check=True, capture_output=True)
        data = load_plans(str(self.control))
        data["plans"][0]["git_head_ref"] = self._git(self.worktree, "rev-parse", "HEAD")
        data["plans"][0]["task_status"]["TASK-002"] = "closed"
        save_plans(str(self.control), data)
        (self.control / "app.txt").write_text("main\n", encoding="utf-8")
        subprocess.run(["git", "add", "app.txt"], cwd=self.control, check=True)
        subprocess.run(["git", "commit", "-m", "main overlap"], cwd=self.control,
                       check=True, capture_output=True)

        base_before = self._git(self.control, "rev-parse", "HEAD")
        plan_before = self._git(self.worktree, "rev-parse", "HEAD")
        result = prepare_plan_integration(str(self.control), "PLAN-001")
        self.assertTrue(result["conflict"])
        self.assertEqual(self._git(self.control, "rev-parse", "HEAD"), base_before)
        self.assertEqual(self._git(self.worktree, "rev-parse", "HEAD"), plan_before)
        self.assertEqual(subprocess.run(
            ["git", "rev-parse", "-q", "--verify", "MERGE_HEAD"], cwd=self.control,
            capture_output=True,
        ).returncode, 1)
        self.assertEqual(subprocess.run(
            ["git", "rev-parse", "-q", "--verify", "MERGE_HEAD"], cwd=self.worktree,
            capture_output=True,
        ).returncode, 1)
        plan = load_plans(str(self.control))["plans"][0]
        self.assertEqual(plan["integration"]["status"], "conflict")

        upsert_task(
            str(self.control), "TASK-INTEGRATE", status="ready",
            plan_id="PLAN-001", kind="integration",
        )
        plan = load_plans(str(self.control))["plans"][0]
        self.assertEqual(plan["integration"]["status"], "conflict")
        activated = activate_task(str(self.control), "TASK-INTEGRATE")
        self.assertTrue(activated["activated"], activated["blockers"])
        task = next(
            item for item in load_ledger(str(self.control))["tasks"]
            if item["id"] == "TASK-INTEGRATE"
        )
        self.assertEqual(task["integration_base_ref"], result["base_ref"])
        self.assertEqual(task["integration_plan_ref"], result["plan_ref"])

    def test_integration_task_close_creates_the_reviewed_merge_commit(self):
        from aiwf_core.core.plan_integration import prepare_plan_integration
        from aiwf_core.core.state.context_ops import record_implementation
        from aiwf_core.core.state.plan_ops import load_plans, save_plans
        from aiwf_core.core.state.review_ops import record_review
        from aiwf_core.core.state.testing_ops import record_testing
        from aiwf_core.core.task_ledger import close_task

        (self.worktree / "app.txt").write_text("plan\n", encoding="utf-8")
        subprocess.run(["git", "add", "app.txt"], cwd=self.worktree, check=True)
        subprocess.run(["git", "commit", "-m", "TASK-002: overlap"], cwd=self.worktree,
                       check=True, capture_output=True)
        plan_ref = self._git(self.worktree, "rev-parse", "HEAD")
        data = load_plans(str(self.control))
        data["plans"][0]["git_head_ref"] = plan_ref
        data["plans"][0]["task_status"]["TASK-002"] = "closed"
        save_plans(str(self.control), data)
        (self.control / "app.txt").write_text("main\n", encoding="utf-8")
        subprocess.run(["git", "add", "app.txt"], cwd=self.control, check=True)
        subprocess.run(["git", "commit", "-m", "main overlap"], cwd=self.control,
                       check=True, capture_output=True)
        conflict = prepare_plan_integration(str(self.control), "PLAN-001")
        base_ref = conflict["base_ref"]

        tasks_path = self.control / ".aiwf/state/tasks.json"
        tasks_path.write_text(json.dumps({
            "schema_version": 1,
            "tasks": [{
                "id": "TASK-INTEGRATE",
                "title": "Resolve Plan integration",
                "status": "active",
                "phase": "implementing",
                "kind": "integration",
                "plan_id": "PLAN-001",
                "worktree_path": str(self.worktree),
                "git_branch": "aiwf/plan-001",
                "git_origin_ref": plan_ref,
                "integration_plan_ref": plan_ref,
                "integration_base_ref": base_ref,
                "requirements": {
                    "executor_required": True,
                    "tester_required": True,
                    "reviewer_required": True,
                },
            }],
        }, indent=2) + "\n", encoding="utf-8")
        data = load_plans(str(self.control))
        data["plans"][0]["task_ids"].append("TASK-INTEGRATE")
        data["plans"][0]["task_status"]["TASK-INTEGRATE"] = "active"
        save_plans(str(self.control), data)

        merge = subprocess.run(["git", "merge", "--no-commit", base_ref], cwd=self.worktree,
                               capture_output=True, text=True)
        self.assertNotEqual(merge.returncode, 0)
        (self.worktree / "app.txt").write_text("main + plan\n", encoding="utf-8")
        implementation = record_implementation(
            str(self.worktree), "resolved both behaviors", command="cat app.txt",
            task_id="TASK-INTEGRATE",
        )
        testing = record_testing(
            str(self.worktree), status="passed", commands=["grep -q 'main + plan' app.txt"],
            coverage_summary="combined behavior present",
            verification_results=[{
                "command": "grep -q 'main + plan' app.txt", "expected": "exit 0",
                "observed": "exit 0", "matched": True,
            }], task_id="TASK-INTEGRATE",
        )
        review = record_review(
            str(self.worktree), result="accepted", closure_allowed=True,
            summary="reviewed combined behavior", task_id="TASK-INTEGRATE",
        )
        self.assertEqual(review["reviewed_ref"], testing["tested_ref"])
        self.assertNotEqual(implementation["implementation_ref"], plan_ref)

        result = close_task(str(self.worktree), "TASK-INTEGRATE")
        self.assertTrue(result["closed"], result["blockers"])
        commit = result["task"]["closure"]["git_commit"]
        parents = self._git(self.worktree, "show", "-s", "--format=%P", commit).split()
        self.assertEqual(parents, [plan_ref, base_ref])
        self.assertEqual((self.worktree / "app.txt").read_text(), "main + plan\n")
        plan = load_plans(str(self.control))["plans"][0]
        self.assertEqual(plan["git_head_ref"], commit)
        self.assertNotIn("integration", plan)


if __name__ == "__main__":
    unittest.main()
