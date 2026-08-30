import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


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
        from aiwf_core.core.task_proof import build_task_proof

        implementation = self._record_implementation()
        proof = build_task_proof(str(self.root), self.task)
        binding = proof["snapshot_binding"]
        self.assertEqual(binding["snapshot_kind"], "aiwf_hidden_commit")
        self.assertEqual(binding["branch_head_ref"], self.origin)
        self.assertNotEqual(binding["branch_head_ref"], implementation["implementation_ref"])
        self.assertFalse(binding["head_equals_implementation"])
        self.assertEqual(binding["candidate_tree_status"], "matched")
        self.assertFalse(binding["branch_update_required"])
        self.assertEqual(binding["candidate_tree"], binding["implementation_tree"])
        self.assertTrue(self._git("status", "--porcelain"))
        review = self._accept()
        self.assertEqual(review["reviewed_ref"], implementation["implementation_ref"])
        self.assertEqual(
            self._git("show", f"{implementation['implementation_ref']}:app.txt"), "new",
        )

    def test_task_proof_reports_actual_tree_drift_without_requiring_head_alignment(self):
        from aiwf_core.core.task_proof import build_task_proof

        self._record_implementation()
        (self.root / "app.txt").write_text("changed after snapshot\n", encoding="utf-8")
        binding = build_task_proof(str(self.root), self.task)["snapshot_binding"]
        self.assertEqual(binding["candidate_tree_status"], "changed")
        self.assertIsNone(binding["branch_update_required"])
        self.assertTrue(binding["tree_changes"])

    def test_snapshot_binding_exposes_git_failure_behind_unavailable(self):
        from aiwf_core.core.git_snapshots import snapshot_binding

        implementation = self._record_implementation()
        with patch(
            "aiwf_core.core.git_snapshots._worktree_tree",
            side_effect=PermissionError("sandbox denied temporary Git index"),
        ):
            binding = snapshot_binding(
                str(self.root), implementation["implementation_ref"],
            )

        self.assertEqual(binding["candidate_tree_status"], "unavailable")
        self.assertIn("sandbox denied temporary Git index", binding["candidate_tree_error"])

    def test_review_freshness_unavailable_is_codex_only_advisory(self):
        from aiwf_core.core.state.review_ops import record_review

        implementation = self._record_implementation()
        unavailable = {
            "implementation_ref": implementation["implementation_ref"],
            "implementation_tree": "tree-current",
            "candidate_tree": "",
            "candidate_tree_status": "unavailable",
            "candidate_tree_error": "sandbox denied temporary Git index",
        }
        with patch(
            "aiwf_core.core.git_snapshots.snapshot_binding",
            return_value=unavailable,
        ):
            with self.assertRaisesRegex(ValueError, "freshness is unavailable"):
                record_review(
                    str(self.root), "accepted", closure_allowed=True,
                    summary="non-Codex cannot adopt a main-session packet",
                    task_id="TASK-001",
                )

        (self.root / ".codex").mkdir()
        (self.root / ".codex/hooks.json").write_text("{}\n", encoding="utf-8")
        planner_skill = self.root / ".agents/skills/aiwf-planner/SKILL.md"
        planner_skill.parent.mkdir(parents=True)
        planner_skill.write_text("---\nname: aiwf-planner\n---\n", encoding="utf-8")
        changed = dict(unavailable, candidate_tree_status="changed")
        with patch.dict(os.environ, {"AIWF_HOST": "codex"}, clear=False):
            with patch(
                "aiwf_core.core.git_snapshots.snapshot_binding",
                return_value=changed,
            ):
                with self.assertRaisesRegex(ValueError, "differs from implementation_ref"):
                    record_review(
                        str(self.root), "accepted", closure_allowed=True,
                        summary="changed must remain blocked", task_id="TASK-001",
                    )
            with patch(
                "aiwf_core.core.git_snapshots.snapshot_binding",
                return_value=unavailable,
            ):
                review = record_review(
                    str(self.root), "accepted", closure_allowed=True,
                    summary="main Codex task supplied the exact matched binding",
                    task_id="TASK-001",
                )

        self.assertEqual(review["result"], "accepted")
        self.assertEqual(review["reviewed_ref"], implementation["implementation_ref"])

    def test_codex_post_construction_route_preflights_freshness(self):
        from aiwf_core.commands.flow import _task_next
        from aiwf_core.core.task_records import load_task_record

        implementation = self._record_implementation()
        record = load_task_record(self.root, "TASK-001")
        base = {
            "implementation_ref": implementation["implementation_ref"],
            "implementation_tree": "tree-current",
            "branch_head_ref": self.origin,
            "tree_changes": [],
        }
        unavailable = dict(
            base, candidate_tree="", candidate_tree_status="unavailable",
            candidate_tree_error="sandbox denied temporary Git index",
        )
        with patch(
            "aiwf_core.core.git_snapshots.snapshot_binding",
            return_value=unavailable,
        ):
            role, action = _task_next(
                self.task, record, self.root, host="codex",
            )
        self.assertEqual(role, "Main-session freshness preflight")
        self.assertIn("permission needed", action)
        self.assertIn(implementation["implementation_ref"], action)
        self.assertIn("do not dispatch a child", action)

        matched = dict(
            base, candidate_tree="tree-current", candidate_tree_status="matched",
            candidate_tree_error="",
        )
        with patch(
            "aiwf_core.core.git_snapshots.snapshot_binding",
            return_value=matched,
        ):
            role, action = _task_next(
                self.task, record, self.root, host="codex",
            )
        self.assertEqual(role, "Main-session dispatch")
        self.assertIn("exact Codex main-session freshness packet", action)
        self.assertIn("implementation_tree=tree-current", action)
        self.assertIn("candidate_tree=tree-current", action)

        changed = dict(
            base, candidate_tree="tree-drift", candidate_tree_status="changed",
            candidate_tree_error="", tree_changes=[{"status": "M", "path": "app.txt"}],
        )
        with patch(
            "aiwf_core.core.git_snapshots.snapshot_binding",
            return_value=changed,
        ):
            role, action = _task_next(
                self.task, record, self.root, host="codex",
            )
        self.assertEqual(role, "Implementation repair")
        self.assertIn("modified: app.txt", action)

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

    def test_accepted_requires_explicit_complete_story_assertion(self):
        from aiwf_core.core.state.review_ops import record_review

        self._record_implementation()
        with self.assertRaisesRegex(ValueError, "complete-story assertion"):
            record_review(
                str(self.root), "accepted", summary="candidate seems acceptable",
                task_id="TASK-001",
            )
        with self.assertRaisesRegex(ValueError, "only accepted review"):
            record_review(
                str(self.root), "needs_change", closure_allowed=True,
                blockers=["story link is missing"], summary="incomplete story",
                task_id="TASK-001",
            )

    def test_inconsistent_accepted_record_routes_reviewer_reconciliation(self):
        from aiwf_core.commands.flow import _task_next
        from aiwf_core.core.task_records import load_task_record

        implementation = self._record_implementation()
        record = load_task_record(self.root, "TASK-001")
        record["review"].update({
            "result": "accepted",
            "closure_allowed": False,
            "reviewed_ref": implementation["implementation_ref"],
            "summary": "accepted even though the story assertion is absent",
        })

        role, action = _task_next(self.task, record, self.root)

        self.assertEqual(role, "Reviewer reconciliation")
        self.assertIn("lacks the explicit complete-story assertion", action)
        self.assertIn("appropriate non-accepted verdict", action)
        self.assertIn("main session must not supply this judgment", action)

    def test_status_prompt_exposes_inconsistent_acceptance_without_closing(self):
        from aiwf_core.core.task_records import load_task_record, update_task_record

        (self.root / ".claude").mkdir()
        (self.root / ".claude/settings.json").write_text("{}\n", encoding="utf-8")
        implementation = self._record_implementation()

        def make_inconsistent(record):
            record["review"].update({
                "result": "accepted",
                "closure_allowed": False,
                "reviewed_ref": implementation["implementation_ref"],
                "summary": "accepted without the complete-story assertion",
            })

        update_task_record(self.root, "TASK-001", make_inconsistent)
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])

        status = subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", "status", "--prompt"],
            cwd=self.root, env=env, capture_output=True, text=True,
        )

        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("Required skills: /aiwf-review", status.stdout)
        self.assertIn("Next role: Reviewer reconciliation", status.stdout)
        self.assertIn("story=unasserted", status.stdout)
        self.assertIn("Reviewer owns the complete-story judgment", status.stdout)
        self.assertIn("--story-complete", status.stdout)
        self.assertNotIn("/aiwf-close", status.stdout)
        self.assertFalse(load_task_record(self.root, "TASK-001")["review"]["closure_allowed"])

    def test_needs_change_routes_executor_then_reviewer_acceptance_resolves(self):
        from aiwf_core.commands.flow import _task_next
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
        role, action = _task_next(
            self.task, load_task_record(self.root, "TASK-001"), self.root,
        )
        self.assertEqual(role, "Main-session dispatch")
        self.assertIn("Task.md Dispatch Decisions", action)
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
