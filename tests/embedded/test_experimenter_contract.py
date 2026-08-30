import json
import io
import os
import shutil
import subprocess
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch


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
            ".aiwf/plans",
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
        self._write_json(
            ".aiwf/state/plans.json",
            {"schema_version": 1, "plans": [{
                "id": "PLAN-001",
                "plan_id": "PLAN-001",
                "status": "open",
                "task_ids": ["TASK-001"],
                "task_status": {"TASK-001": "active"},
                "experiment_ids": [],
                "git_head_ref": self.origin,
            }]},
        )
        (self.root / ".aiwf/plans/PLAN-001.md").write_text(
            "# PLAN-001\n\nResolve the delivery direction.\n", encoding="utf-8",
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

    def test_codex_experiment_record_does_not_require_dispatch_marker(self):
        from aiwf_core.commands.experiment_commands import _cmd_experiment_record
        from aiwf_core.core.experiment_records import (
            load_experiment, open_experiment, start_experiment,
        )

        (self.root / ".codex").mkdir(parents=True, exist_ok=True)
        (self.root / ".codex/hooks.json").write_text("{}\n", encoding="utf-8")
        planner_skill = self.root / ".agents/skills/aiwf-planner/SKILL.md"
        planner_skill.parent.mkdir(parents=True, exist_ok=True)
        planner_skill.write_text("---\nname: aiwf-planner\n---\n", encoding="utf-8")

        open_experiment(
            str(self.root), "EXP-CODEX", "What does the disposable runtime show?",
            task_id="TASK-001",
        )
        running = start_experiment(str(self.root), "EXP-CODEX")
        worktree = Path(running["worktree_path"])
        (worktree / "probe.txt").write_text("observed\n", encoding="utf-8")
        dispatch = self.root / ".aiwf/runtime/internal/agent-dispatch.jsonl"
        dispatch.unlink(missing_ok=True)

        previous = Path.cwd()
        try:
            os.chdir(worktree)
            with patch.dict(os.environ, {"CODEX_THREAD_ID": "codex-exp"}, clear=False):
                with redirect_stdout(io.StringIO()):
                    _cmd_experiment_record(Namespace(
                        experiment_id="EXP-CODEX",
                        conclusion="supported",
                        summary="the disposable runtime exposed the fact",
                        commands=["probe runtime"],
                        observations=["runtime returned observed"],
                        promotion_candidates=[],
                    ))
        finally:
            os.chdir(previous)

        self.assertFalse(dispatch.exists())
        self.assertTrue(load_experiment(str(self.root), "EXP-CODEX")["experiment_ref"])

    def test_non_codex_experiment_record_still_requires_dispatch_marker(self):
        from aiwf_core.commands.experiment_commands import _cmd_experiment_record
        from aiwf_core.core.experiment_records import (
            load_experiment, open_experiment, start_experiment,
        )

        open_experiment(
            str(self.root), "EXP-CLAUDE", "What does the disposable runtime show?",
            task_id="TASK-001",
        )
        running = start_experiment(str(self.root), "EXP-CLAUDE")
        previous = Path.cwd()
        try:
            os.chdir(running["worktree_path"])
            with patch.dict(os.environ, {
                "CODEX_THREAD_ID": "",
                "CODEX_SESSION_ID": "",
                "CODEX_SHELL": "",
                "AIWF_HOST": "",
            }, clear=False):
                with redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit):
                        _cmd_experiment_record(Namespace(
                            experiment_id="EXP-CLAUDE",
                            conclusion="supported",
                            summary="would otherwise be valid",
                            commands=["probe runtime"],
                            observations=["runtime returned observed"],
                            promotion_candidates=[],
                        ))
        finally:
            os.chdir(previous)

        self.assertEqual(load_experiment(str(self.root), "EXP-CLAUDE")["status"], "running")

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

    def test_main_session_can_route_completed_executor_directly_to_experimenter(self):
        from aiwf_core.commands.flow import _task_next
        from aiwf_core.core.experiment_records import open_experiment
        from aiwf_core.core.task_records import load_task_record

        implementation = self._implementation()
        role, action = _task_next(
            self.task, load_task_record(self.root, "TASK-001"), self.root,
        )
        self.assertEqual(role, "Main-session dispatch")
        self.assertIn("read Task.md Dispatch Decisions", action)
        self.assertIn("If it selects Experimenter", action)
        self.assertIn("If it selects review", action)
        self.assertIn("Do not delegate this route choice", action)

        open_experiment(
            str(self.root), "EXP-DIRECT", "Does the declared runtime property hold?",
            task_id="TASK-001", subject_ref=implementation["implementation_ref"],
            timing="post_implementation",
        )
        role, action = _task_next(
            self.task, load_task_record(self.root, "TASK-001"), self.root,
        )
        self.assertEqual(role, "Experimenter")
        self.assertIn("aiwf experiment start EXP-DIRECT", action)

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

    def test_plan_experiment_links_lists_and_requires_disposition(self):
        from aiwf_core.commands.flow import _plan_experiment_attention
        from aiwf_core.core.experiment_records import (
            disposition_experiment,
            finish_experiment,
            list_experiments,
            open_experiment,
            record_experiment,
            start_experiment,
        )
        from aiwf_core.core.state.plan_ops import get_plan

        opened = open_experiment(
            str(self.root), "EXP-PLAN", "Which runtime boundary is real?",
            plan_id="PLAN-001",
        )
        self.assertTrue(opened["disposition"]["required"])
        self.assertIn("EXP-PLAN", get_plan(str(self.root), "PLAN-001")["experiment_ids"])
        self.assertEqual(
            [item["experiment_id"] for item in list_experiments(
                self.root, plan_id="PLAN-001",
            )],
            ["EXP-PLAN"],
        )
        with self.assertRaisesRegex(ValueError, "finish experiment"):
            disposition_experiment(
                str(self.root), "EXP-PLAN", "proceed", "too early",
            )
        running = start_experiment(str(self.root), "EXP-PLAN")
        record_experiment(
            running["worktree_path"], "EXP-PLAN", "supported",
            "the runtime boundary is observable", commands=["probe runtime"],
            observations=["boundary=worker"],
        )
        finish_experiment(str(self.root), "EXP-PLAN")
        self.assertEqual(
            _plan_experiment_attention(self.root)["experiment_id"], "EXP-PLAN",
        )
        governed = disposition_experiment(
            str(self.root), "EXP-PLAN", "proceed", "use the observed worker boundary",
        )
        self.assertEqual(governed["disposition"]["status"], "recorded")
        self.assertEqual(_plan_experiment_attention(self.root), {})

    def test_pre_implementation_conclusion_routes_planner_before_executor(self):
        from aiwf_core.commands.flow import _task_next
        from aiwf_core.core.experiment_records import (
            disposition_experiment,
            finish_experiment,
            open_experiment,
            record_experiment,
            start_experiment,
        )
        from aiwf_core.core.task_records import load_task_record

        open_experiment(
            str(self.root), "EXP-PRE", "Does the assumed API behavior hold?",
            task_id="TASK-001",
        )
        running = start_experiment(str(self.root), "EXP-PRE")
        record_experiment(
            running["worktree_path"], "EXP-PRE", "falsified",
            "the API uses a different boundary", observations=["returned boundary=B"],
        )
        finish_experiment(str(self.root), "EXP-PRE")
        record = load_task_record(self.root, "TASK-001")
        role, action = _task_next(self.task, record, self.root)
        self.assertEqual(role, "Planner decision")
        self.assertIn("experiment disposition EXP-PRE", action)
        with self.assertRaisesRegex(ValueError, "interrupt active Task"):
            disposition_experiment(
                str(self.root), "EXP-PRE", "replan", "the contract premise is invalid",
            )

        disposition_experiment(
            str(self.root), "EXP-PRE", "proceed", "implementation can use boundary B",
        )
        role, _ = _task_next(
            self.task, load_task_record(self.root, "TASK-001"), self.root,
        )
        self.assertEqual(role, "Inline implementation")

    def test_review_and_close_block_any_unfinished_task_experiment(self):
        from aiwf_core.core.experiment_records import open_experiment
        from aiwf_core.core.state.review_ops import record_review
        from aiwf_core.core.task_ledger import close_task

        implementation = self._implementation()
        open_experiment(
            str(self.root), "EXP-OLD-SUBJECT", "Is an earlier assumption still relevant?",
            task_id="TASK-001", subject_ref=self.origin,
            timing="pre_implementation",
        )
        with self.assertRaisesRegex(ValueError, "empirical work"):
            record_review(str(self.root), "accepted", task_id="TASK-001")
        result = close_task(str(self.root), "TASK-001")
        self.assertFalse(result["closed"])
        self.assertTrue(any(
            "EXP-OLD-SUBJECT=open" in blocker for blocker in result["blockers"]
        ))
        self.assertTrue(implementation["implementation_ref"])

    def test_promoted_experiment_asset_routes_executor_until_fresh_implementation(self):
        from aiwf_core.commands.flow import _task_next
        from aiwf_core.core.experiment_records import (
            disposition_experiment,
            finish_experiment,
            open_experiment,
            record_experiment,
            start_experiment,
        )
        from aiwf_core.core.task_records import load_task_record

        open_experiment(
            str(self.root), "EXP-PROMOTE", "Is the probe worth retaining?",
            task_id="TASK-001",
        )
        running = start_experiment(str(self.root), "EXP-PROMOTE")
        record_experiment(
            running["worktree_path"], "EXP-PROMOTE", "supported",
            "the probe catches the boundary", observations=["probe caught boundary"],
            promotion_candidates=["probe.py"],
        )
        finish_experiment(str(self.root), "EXP-PROMOTE")
        disposition_experiment(
            str(self.root), "EXP-PROMOTE", "promote", "retain the probe as a formal tool",
        )
        role, _ = _task_next(
            self.task, load_task_record(self.root, "TASK-001"), self.root,
        )
        self.assertEqual(role, "Executor")

        self._implementation("candidate with promoted probe\n")
        role, _ = _task_next(
            self.task, load_task_record(self.root, "TASK-001"), self.root,
        )
        self.assertEqual(role, "Main-session dispatch")

    def test_post_experiment_must_target_current_implementation(self):
        from aiwf_core.core.experiment_records import open_experiment

        self._implementation()
        with self.assertRaisesRegex(ValueError, "current implementation ref"):
            open_experiment(
                str(self.root), "EXP-WRONG-REF", "Does the old tree behave?",
                task_id="TASK-001", subject_ref=self.origin,
                timing="post_implementation",
            )

    def test_post_experiment_allows_different_head_but_blocks_tree_drift(self):
        from aiwf_core.core.experiment_records import open_experiment

        implementation = self._implementation()
        self.assertNotEqual(self._git("rev-parse", "HEAD"), implementation["implementation_ref"])
        allowed = open_experiment(
            str(self.root), "EXP-TREE-MATCH", "Does the frozen candidate behave?",
            task_id="TASK-001", subject_ref=implementation["implementation_ref"],
            timing="post_implementation",
        )
        self.assertEqual(allowed["status"], "open")

        (self.root / "app.txt").write_text("drifted after snapshot\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "project tree to match"):
            open_experiment(
                str(self.root), "EXP-TREE-DRIFT", "Does the changed tree behave?",
                task_id="TASK-001", subject_ref=implementation["implementation_ref"],
                timing="post_implementation",
            )

    def test_experiment_show_is_a_complete_proof_surface(self):
        from aiwf_core.commands.experiment_commands import _cmd_experiment_show
        from aiwf_core.core.experiment_records import (
            finish_experiment,
            open_experiment,
            record_experiment,
            start_experiment,
        )

        open_experiment(
            str(self.root), "EXP-SHOW", "Can the real path be observed?",
            hypothesis="trace reaches worker", task_id="TASK-001",
        )
        running = start_experiment(str(self.root), "EXP-SHOW")
        record_experiment(
            running["worktree_path"], "EXP-SHOW", "supported", "trace reached worker",
            commands=["trace app"], observations=["worker called once"],
            promotion_candidates=["trace_probe.py"],
        )
        finish_experiment(str(self.root), "EXP-SHOW")
        output = io.StringIO()
        previous = Path.cwd()
        try:
            import os
            os.chdir(self.root)
            with redirect_stdout(output):
                _cmd_experiment_show(Namespace(experiment_id="EXP-SHOW"))
        finally:
            os.chdir(previous)
        proof = output.getvalue()
        for expected in (
            "Scope: task:TASK-001", "Timing: pre_implementation",
            "Hypothesis: trace reaches worker", "Command: trace app",
            "Observation: worker called once", "Conclusion: supported",
            "Promotion candidate: trace_probe.py", "Disposition: pending",
        ):
            self.assertIn(expected, proof)

    def test_rejected_review_routes_to_planner_not_executor(self):
        from aiwf_core.core.state.review_ops import record_review
        from aiwf_core.core.task_records import load_task_record

        self._implementation()
        record_review(
            str(self.root), "rejected", summary="contract premise is structurally false",
            blockers=["the required owner cannot host this behavior"], task_id="TASK-001",
        )
        fix_loop = load_task_record(self.root, "TASK-001")["fix_loop"]
        self.assertEqual(fix_loop["status"], "open")
        self.assertEqual(fix_loop["route"], "planner")


if __name__ == "__main__":
    unittest.main()
