import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


class TestGitTaskRecords(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="aiwf_git_records_"))
        self._git("init", "-b", "main")
        self._git("config", "user.email", "test@example.com")
        self._git("config", "user.name", "AIWF Test")
        (self.root / "app.txt").write_text("old\n", encoding="utf-8")
        self._git("add", "app.txt")
        self._git("commit", "-m", "seed")
        self.origin = self._git("rev-parse", "HEAD")
        for rel in (
            ".aiwf/state", ".aiwf/tasks", ".aiwf/records/tasks",
            ".aiwf/records/experiments", ".aiwf/runtime/internal",
            ".aiwf/runtime/experiments",
        ):
            (self.root / rel).mkdir(parents=True, exist_ok=True)
        self.task = {
            "id": "TASK-001", "status": "active", "phase": "executing",
            "kind": "implementation", "doc_path": ".aiwf/tasks/TASK-001.md",
            "goal_id": "GOAL-001", "plan_id": "PLAN-001", "dependencies": [],
            "worktree_path": str(self.root), "git_origin_ref": self.origin,
            "requirements": {"executor_required": True, "reviewer_required": True},
        }
        self._write_json(".aiwf/state/state.json", {
            "schema_version": 1, "active_task_id": "TASK-001",
        })
        self._save_task()
        (self.root / ".aiwf/tasks/TASK-001.md").write_text(self._task_doc(), encoding="utf-8")

    def tearDown(self):
        subprocess.run(["git", "worktree", "prune"], cwd=self.root, capture_output=True)
        shutil.rmtree(self.root, ignore_errors=True)

    def _git(self, *args):
        result = subprocess.run(
            ["git", *args], cwd=self.root, capture_output=True, text=True, check=True,
        )
        return result.stdout.strip()

    def _write_json(self, relative, value):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    def _save_task(self):
        self._write_json(".aiwf/state/tasks.json", {
            "schema_version": 1, "tasks": [self.task],
        })

    @staticmethod
    def _task_doc(calibrated=False):
        calibration = "\n## Closure Calibration\n\nAccepted current candidate.\n" if calibrated else ""
        return """---
id: TASK-001
type: task
title: Stable task
contract_status: active
goal_id: GOAL-001
plan_id: PLAN-001
executor_required: true
reviewer_required: true
---

# TASK-001

## Fixed Contract

### Structural Home

Owned by the active Plan.

### Objective

Deliver the current candidate.

### Contract Responsibility

Own the behavior and proof.

### Proof Standard

Done When:

- [Running] The real entrypoint emits new.

Verification Commands:

| ID | Command | Expected Observable Output |
|----|---------|----------------------------|
| V-001 | python3 -c "print('new')" | stdout is exactly new |

### Dispatch Decisions

Independent Executor and Reviewer.
""" + calibration

    @staticmethod
    def _evidence(observed="new", matched=True):
        return [{
            "verification_id": "V-001",
            "command": "python3 -c \"print('new')\"",
            "expected": "stdout is exactly new",
            "observed": observed,
            "matched": matched,
            "verdict": "matched" if matched else "mismatched",
            "basis": "exact stdout" if matched else "wrong stdout",
        }]

    def _record_implementation(self, content="new\n"):
        from aiwf_core.core.state.context_ops import record_implementation

        (self.root / "app.txt").write_text(content, encoding="utf-8")
        return record_implementation(
            str(self.root), "candidate", self._evidence(), "TASK-001",
        )

    def _accept(self, observations=None):
        from aiwf_core.core.state.review_ops import record_review

        return record_review(
            str(self.root), "accepted", closure_allowed=True,
            cleanup_status="fresh", structure_status="sound",
            summary="accepted current candidate",
            adversarial_observations=observations or [], task_id="TASK-001",
        )

    def test_snapshot_and_review_bind_one_stable_ref(self):
        implementation = self._record_implementation()
        review = self._accept()
        self.assertEqual(review["reviewed_ref"], implementation["implementation_ref"])
        self.assertEqual(
            self._git("show", f"{implementation['implementation_ref']}:app.txt"), "new",
        )

    def test_mismatched_executor_evidence_cannot_create_candidate(self):
        from aiwf_core.core.state.context_ops import record_implementation

        (self.root / "app.txt").write_text("wrong\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "proof is incomplete"):
            record_implementation(
                str(self.root), "wrong", self._evidence("wrong", False), "TASK-001",
            )

    def test_new_implementation_invalidates_review_but_preserves_observations(self):
        from aiwf_core.core.state.context_ops import record_implementation
        from aiwf_core.core.task_records import load_task_record

        self._record_implementation()
        self._accept([{
            "severity": "warn", "kind": "edge", "message": "watch edge",
            "disposition": "pending",
        }])
        (self.root / "app.txt").write_text("newer\n", encoding="utf-8")
        record_implementation(str(self.root), "newer", self._evidence(), "TASK-001")
        review = load_task_record(self.root, "TASK-001")["review"]

        self.assertEqual(review["result"], "unknown")
        self.assertEqual(review["adversarial_observations"][0]["message"], "watch edge")

    def test_needs_change_routes_executor_then_reviewer_acceptance_resolves(self):
        from aiwf_core.core.state.context_ops import record_implementation
        from aiwf_core.core.state.review_ops import record_review
        from aiwf_core.core.task_records import load_task_record

        self._record_implementation()
        record_review(
            str(self.root), "needs_change", blockers=["old path remains"],
            summary="bypass defect", task_id="TASK-001",
        )
        self.assertEqual(
            load_task_record(self.root, "TASK-001")["fix_loop"]["route"], "executor",
        )

        (self.root / "app.txt").write_text("fixed\n", encoding="utf-8")
        record_implementation(str(self.root), "fixed bypass", self._evidence(), "TASK-001")
        self.assertEqual(
            load_task_record(self.root, "TASK-001")["fix_loop"]["route"], "reviewer",
        )
        self._accept()
        self.assertEqual(
            load_task_record(self.root, "TASK-001")["fix_loop"]["status"], "resolved",
        )

    def test_project_change_after_review_blocks_close(self):
        from aiwf_core.core.task_ledger import close_task

        self._record_implementation()
        self._accept()
        (self.root / ".aiwf/tasks/TASK-001.md").write_text(
            self._task_doc(calibrated=True), encoding="utf-8",
        )
        (self.root / "app.txt").write_text("changed after review\n", encoding="utf-8")
        result = close_task(str(self.root), "TASK-001")
        self.assertFalse(result["closed"])
        self.assertTrue(any("review" in item.lower() or "snapshot" in item.lower()
                            for item in result["blockers"]))

    def test_close_commits_exact_reviewed_tree(self):
        from aiwf_core.core.task_ledger import close_task

        implementation = self._record_implementation()
        self._accept()
        unicode_path = self.root / "结果 file.txt"
        unicode_path.write_text("kept\n", encoding="utf-8")
        # The new file appeared after evidence, so refresh the stable candidate and Review.
        from aiwf_core.core.state.context_ops import record_implementation
        record_implementation(str(self.root), "include unicode", self._evidence(), "TASK-001")
        review = self._accept()
        (self.root / ".aiwf/tasks/TASK-001.md").write_text(
            self._task_doc(calibrated=True), encoding="utf-8",
        )

        result = close_task(str(self.root), "TASK-001", note="done")
        self.assertTrue(result["closed"], result["blockers"])
        commit = result["task"]["closure"]["git_commit"]
        self.assertEqual(result["task"]["closure"]["reviewed_ref"], review["reviewed_ref"])
        self.assertEqual(self._git("show", f"{commit}:app.txt"), "new")
        self.assertEqual(self._git("show", f"{commit}:结果 file.txt"), "kept")
        self.assertNotEqual(commit, implementation["implementation_ref"])

    def test_closed_post_implementation_experiment_becomes_stale_after_repair(self):
        from aiwf_core.core.experiment_records import (
            finish_experiment, load_experiment, open_experiment,
            record_experiment, start_experiment,
        )
        from aiwf_core.core.state.context_ops import record_implementation

        implementation = self._record_implementation()
        open_experiment(
            str(self.root), "EXP-OLD", "Does this candidate preserve ordering?",
            task_id="TASK-001", subject_ref=implementation["implementation_ref"],
            timing="post_implementation",
        )
        running = start_experiment(str(self.root), "EXP-OLD")
        record_experiment(
            running["worktree_path"], "EXP-OLD", "supported", "ordering observed",
            commands=["observe ordering"], observations=["A preceded B"],
        )
        finish_experiment(str(self.root), "EXP-OLD")

        (self.root / "app.txt").write_text("repaired\n", encoding="utf-8")
        repaired = record_implementation(
            str(self.root), "repair", self._evidence(), "TASK-001",
        )
        stale = load_experiment(str(self.root), "EXP-OLD")
        self.assertEqual(stale["status"], "stale")
        self.assertIn("EXP-OLD", repaired["stale_experiment_ids"])


if __name__ == "__main__":
    unittest.main()
