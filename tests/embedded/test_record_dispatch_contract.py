import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


class TestRecordDispatchContract(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="aiwf_dispatch_"))
        for rel in (
            ".aiwf/runtime/internal", ".aiwf/state", ".aiwf/tasks",
            ".aiwf/records/tasks", ".aiwf/records/experiments",
        ):
            (self.root / rel).mkdir(parents=True, exist_ok=True)
        self._write_json(".aiwf/state/state.json", {"active_task_id": "TASK-001"})
        self.task = {
            "id": "TASK-001", "status": "active", "phase": "executing",
            "worktree_path": str(self.root), "plan_id": "PLAN-001",
            "git_origin_ref": "origin",
            "requirements": {"executor_required": True, "reviewer_required": True},
        }
        self._write_json(".aiwf/state/tasks.json", {"tasks": [self.task]})

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _write_json(self, relative, value):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    def test_runtime_tracks_only_new_workflow_roles(self):
        from aiwf_core.core.agent_runtime import ROLE_REQUIRED_SKILL, WORKFLOW_ROLES

        self.assertEqual(
            WORKFLOW_ROLES,
            frozenset({"aiwf-executor", "aiwf-experimenter", "aiwf-reviewer"}),
        )
        self.assertEqual(ROLE_REQUIRED_SKILL["aiwf-experimenter"], "aiwf-experiment")
        self.assertNotIn("aiwf-tester", ROLE_REQUIRED_SKILL)

    def test_one_workflow_role_owns_a_scope_at_a_time(self):
        from aiwf_core.core.agent_runtime import running_dispatches, start_dispatch

        first = start_dispatch(
            self.root, "TASK-001", "aiwf-executor", "session-a",
            "PLAN-001", str(self.root),
        )
        blocked_by = start_dispatch(
            self.root, "TASK-001", "aiwf-reviewer", "session-b",
            "PLAN-001", str(self.root),
        )

        self.assertEqual(first, "")
        self.assertEqual(blocked_by, "aiwf-executor")
        self.assertEqual(len(running_dispatches(self.root, task_id="TASK-001")), 1)

    def test_experiment_dispatch_preserves_exp_identity(self):
        from aiwf_core.core.agent_runtime import (
            bind_dispatch_agent,
            latest_agent_dispatch,
            running_dispatches,
            start_dispatch,
        )

        start_dispatch(
            self.root, "TASK-001", "aiwf-experimenter", "session-exp",
            "PLAN-001", "/tmp/disposable", experiment_id="EXP-007",
        )
        self.assertTrue(bind_dispatch_agent(
            self.root, "aiwf-experimenter", "agent-7",
            task_id="TASK-001", session_id="session-exp",
        ))
        running = running_dispatches(self.root, task_id="TASK-001")[0]
        latest = latest_agent_dispatch(
            self.root, "aiwf-experimenter", "agent-7", task_id="TASK-001",
        )

        self.assertEqual(running["experiment_id"], "EXP-007")
        self.assertEqual(latest["experiment_id"], "EXP-007")

    def test_experimenter_is_never_resumed_as_a_different_experiment(self):
        from aiwf_core.core.agent_runtime import start_resumed_dispatch

        self.assertIsNone(start_resumed_dispatch(
            self.root, "aiwf-experimenter", "old-agent", "new-session",
        ))

    def test_construction_proof_file_has_no_independent_probe_schema(self):
        from aiwf_core.core.construction_evidence import load_construction_proof_file

        proof = self.root / "proof.json"
        proof.write_text(json.dumps({"results": [{
            "verification_id": "V-001",
            "observed": "ok",
            "verdict": "matched",
            "basis": "exact output",
        }]}), encoding="utf-8")
        result = load_construction_proof_file(str(proof))

        self.assertEqual(result[0]["verification_id"], "V-001")
        self.assertEqual(result[0]["verdict"], "matched")
        self.assertNotIn("independent_probes", result[0])

    def test_construction_proof_requires_explicit_verdict(self):
        from aiwf_core.core.construction_evidence import load_construction_proof_file

        proof = self.root / "proof.json"
        proof.write_text(json.dumps([{"verification_id": "V-001", "observed": "ok"}]))
        with self.assertRaisesRegex(ValueError, "verdict"):
            load_construction_proof_file(str(proof))

    def test_cli_has_implementation_and_review_records_but_no_testing_record(self):
        help_result = subprocess.run(
            ["python3", "-m", "aiwf_core.cli", "record", "--help"],
            cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True,
        )
        retired = subprocess.run(
            ["python3", "-m", "aiwf_core.cli", "record", "testing"],
            cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True,
        )

        self.assertEqual(help_result.returncode, 0)
        self.assertIn("implementation", help_result.stdout)
        self.assertIn("review", help_result.stdout)
        self.assertNotIn("testing", help_result.stdout)
        self.assertNotEqual(retired.returncode, 0)

    def test_review_verdict_surface_includes_empirical_request(self):
        help_result = subprocess.run(
            ["python3", "-m", "aiwf_core.cli", "record", "review", "--help"],
            cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True,
        )
        self.assertEqual(help_result.returncode, 0)
        for token in (
            "needs_change", "needs_experiment", "--experiment-question",
            "--story-complete",
        ):
            self.assertIn(token, help_result.stdout)
        self.assertNotIn("needs_more_testing", help_result.stdout)


if __name__ == "__main__":
    unittest.main()
