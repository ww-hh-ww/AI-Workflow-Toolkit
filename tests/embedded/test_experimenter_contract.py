import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


class TestExperimenterContract(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="aiwf_experiment_"))
        self._git("init", "-b", "main")
        self._git("config", "user.email", "test@example.com")
        self._git("config", "user.name", "AIWF Test")
        (self.root / "app.txt").write_text("stable\n", encoding="utf-8")
        self._git("add", "app.txt")
        self._git("commit", "-m", "seed")
        self.origin = self._git("rev-parse", "HEAD")

        for rel in (
            ".aiwf/state",
            ".aiwf/tasks",
            ".aiwf/records/tasks",
            ".aiwf/records/experiments",
            ".aiwf/runtime/internal",
            ".aiwf/runtime/experiments",
        ):
            (self.root / rel).mkdir(parents=True, exist_ok=True)
        self._write_json(
            ".aiwf/state/state.json",
            {"schema_version": 1, "active_task_id": "TASK-001"},
        )
        self.task = {
            "id": "TASK-001",
            "status": "active",
            "phase": "executing",
            "kind": "implementation",
            "doc_path": ".aiwf/tasks/TASK-001.md",
            "goal_id": "GOAL-001",
            "plan_id": "PLAN-001",
            "worktree_path": str(self.root),
            "git_origin_ref": self.origin,
            "requirements": {
                "executor_required": False,
                "reviewer_required": False,
            },
        }
        self._write_json(
            ".aiwf/state/tasks.json",
            {"schema_version": 1, "tasks": [self.task]},
        )
        (self.root / ".aiwf/tasks/TASK-001.md").write_text(
            """---
id: TASK-001
type: task
title: Experiment contract
contract_status: active
goal_id: GOAL-001
plan_id: PLAN-001
executor_required: false
reviewer_required: false
---

# TASK-001

## Fixed Contract

### Structural Home

This belongs to the active Plan.

### Objective

Change stable behavior.

### Contract Responsibility

Own the stable result and its evidence.

### Proof Standard

Done When:

- [Running] The stable entrypoint reports the new result.

Verification Commands:

| ID | Command | Expected Observable Output |
|----|---------|----------------------------|
| V-001 | python3 -c "print('new')" | stdout is exactly new |

### Dispatch Decisions

Executor and Reviewer are inline in this fixture.
""",
            encoding="utf-8",
        )

    def tearDown(self):
        subprocess.run(
            ["git", "worktree", "prune"], cwd=self.root,
            capture_output=True, text=True,
        )
        shutil.rmtree(self.root, ignore_errors=True)

    def _git(self, *args):
        result = subprocess.run(
            ["git", *args], cwd=self.root, capture_output=True, text=True,
            check=True,
        )
        return result.stdout.strip()

    def _write_json(self, relative, value):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def _v_result():
        return [{
            "verification_id": "V-001",
            "command": "python3 -c \"print('new')\"",
            "expected": "stdout is exactly new",
            "observed": "new",
            "matched": True,
            "verdict": "matched",
            "basis": "observed exact stdout",
        }]

    def _implementation(self, text="candidate\n"):
        from aiwf_core.core.state.context_ops import record_implementation

        (self.root / "app.txt").write_text(text, encoding="utf-8")
        return record_implementation(
            str(self.root), "stable candidate", self._v_result(), "TASK-001",
        )

    def test_executor_v_evidence_is_the_review_subject(self):
        from aiwf_core.core.state.review_ops import record_review

        implementation = self._implementation()
        review = record_review(
            str(self.root), "accepted", closure_allowed=True,
            cleanup_status="fresh", structure_status="sound",
            summary="whole story holds", task_id="TASK-001",
        )

        self.assertEqual(review["reviewed_ref"], implementation["implementation_ref"])
        self.assertNotIn("tested_ref", review)

    def test_experiment_snapshots_disposable_project_and_retains_facts(self):
        from aiwf_core.core.experiment_records import (
            finish_experiment,
            open_experiment,
            record_experiment,
            start_experiment,
        )
        from aiwf_core.core.task_proof import build_task_proof

        opened = open_experiment(
            str(self.root), "EXP-001", "Does a prototype expose the real limit?",
            hypothesis="the prototype fails at the boundary", task_id="TASK-001",
        )
        self.assertEqual(opened["subject_ref"], self.origin)
        running = start_experiment(str(self.root), "EXP-001")
        worktree = Path(running["worktree_path"])
        (worktree / "prototype.txt").write_text("boundary failed\n", encoding="utf-8")
        recorded = record_experiment(
            str(worktree), "EXP-001", "supported", "boundary fails in prototype",
            commands=["run prototype"], observations=["exit=23 at boundary"],
            promotion_candidates=["prototype.txt"],
        )

        self.assertTrue(recorded["experiment_ref"])
        self.assertFalse((self.root / "prototype.txt").exists())
        self.assertEqual(
            self._git("show", f"{recorded['experiment_ref']}:prototype.txt"),
            "boundary failed",
        )
        proof = build_task_proof(str(self.root), self.task)
        self.assertEqual(proof["experiments"][0]["conclusion"], "supported")

        closed = finish_experiment(str(self.root), "EXP-001")
        self.assertEqual(closed["status"], "closed")
        self.assertFalse(worktree.exists())
        self.assertEqual(closed["experiment_ref"], recorded["experiment_ref"])

    def test_reviewer_waits_until_current_experiment_is_disposed(self):
        from aiwf_core.core.experiment_records import (
            finish_experiment,
            open_experiment,
            record_experiment,
            start_experiment,
        )
        from aiwf_core.core.state.review_ops import record_review

        implementation = self._implementation()
        open_experiment(
            str(self.root), "EXP-POST", "Does the current candidate bypass the entrypoint?",
            task_id="TASK-001", subject_ref=implementation["implementation_ref"],
            timing="post_implementation",
        )
        running = start_experiment(str(self.root), "EXP-POST")
        with self.assertRaisesRegex(ValueError, "empirical work"):
            record_review(str(self.root), "accepted", task_id="TASK-001")

        worktree = Path(running["worktree_path"])
        record_experiment(
            str(worktree), "EXP-POST", "falsified", "no bypass observed",
            commands=["trace entrypoint"], observations=["all calls reached new path"],
        )
        with self.assertRaisesRegex(ValueError, "disposed"):
            record_review(str(self.root), "accepted", task_id="TASK-001")
        finish_experiment(str(self.root), "EXP-POST")

        review = record_review(
            str(self.root), "accepted", closure_allowed=True,
            summary="candidate and empirical evidence hold", task_id="TASK-001",
        )
        self.assertEqual(review["reviewed_ref"], implementation["implementation_ref"])

    def test_review_needs_experiment_opens_question_without_executor_fixloop(self):
        from aiwf_core.core.experiment_records import load_experiment
        from aiwf_core.core.state.review_ops import record_review
        from aiwf_core.core.task_records import load_task_record

        implementation = self._implementation()
        review = record_review(
            str(self.root), "needs_experiment", summary="runtime fact is unknown",
            experiment_request={
                "experiment_id": "EXP-REVIEW",
                "question": "Does the real runtime preserve ordering?",
                "hypothesis": "ordering is preserved",
            },
            task_id="TASK-001",
        )
        experiment = load_experiment(str(self.root), "EXP-REVIEW")

        self.assertEqual(review["result"], "needs_experiment")
        self.assertEqual(experiment["subject_ref"], implementation["implementation_ref"])
        self.assertEqual(experiment["status"], "open")
        self.assertNotEqual(
            load_task_record(self.root, "TASK-001")["fix_loop"]["status"], "open",
        )

    def test_invalid_experiment_request_does_not_partially_replace_review(self):
        from aiwf_core.core.experiment_records import (
            finish_experiment,
            open_experiment,
            record_experiment,
            start_experiment,
        )
        from aiwf_core.core.state.review_ops import record_review
        from aiwf_core.core.task_records import load_task_record

        implementation = self._implementation()
        accepted = record_review(
            str(self.root), "accepted", closure_allowed=True,
            summary="accepted baseline", task_id="TASK-001",
        )
        open_experiment(
            str(self.root), "EXP-DUP", "existing empirical question",
            task_id="TASK-001", subject_ref=implementation["implementation_ref"],
            timing="post_implementation",
        )
        running = start_experiment(str(self.root), "EXP-DUP")
        record_experiment(
            running["worktree_path"], "EXP-DUP", "supported",
            "existing experiment completed", observations=["observed existing fact"],
        )
        finish_experiment(str(self.root), "EXP-DUP")

        with self.assertRaisesRegex(ValueError, "experiment already exists"):
            record_review(
                str(self.root), "needs_experiment", summary="need another fact",
                experiment_request={
                    "experiment_id": "EXP-DUP",
                    "question": "new empirical question",
                },
                task_id="TASK-001",
            )

        current = load_task_record(self.root, "TASK-001")["review"]
        self.assertEqual(current["result"], accepted["result"])
        self.assertEqual(current["reviewed_ref"], accepted["reviewed_ref"])

    def test_experimenter_can_write_only_inside_running_disposable_worktree(self):
        from aiwf_core.core.event_model import NormalizedEvent
        from aiwf_core.core.experiment_records import open_experiment, start_experiment
        from aiwf_core.hooks.common.scope_checker import check_file_write

        open_experiment(
            str(self.root), "EXP-SCOPE", "Can instrumentation expose the path?",
            task_id="TASK-001",
        )
        running = start_experiment(str(self.root), "EXP-SCOPE")
        worktree = Path(running["worktree_path"])

        def event(path):
            return NormalizedEvent(
                engine="claude", event_type="pre_tool_use", tool_name="Write",
                tool_input={"file_path": str(path)}, cwd=str(worktree),
                agent_type="aiwf-experimenter",
            )

        self.assertTrue(check_file_write(event(worktree / "probe.py")).allowed)
        denied = check_file_write(event(self.root / "stable.py"))
        self.assertFalse(denied.allowed)
        self.assertIn("stable project reality", denied.reason)


if __name__ == "__main__":
    unittest.main()
