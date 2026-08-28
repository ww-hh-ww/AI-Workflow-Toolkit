"""Release-gate smoke tests for the current embedded AIWF install surface."""
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


def _run(args, cwd):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "aiwf_core.cli", *args],
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
        timeout=TIMEOUT,
    )


class TestV1ReleaseGate(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aiwf_release_gate_"))
        result = _run(["install", "claude", "--force"], self.tmp)
        self.assertEqual(result.returncode, 0, result.stderr)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_install_surface_has_current_roles_and_no_tester(self):
        agents = {path.name for path in (self.tmp / ".claude/agents").glob("*.md")}
        self.assertTrue({
            "aiwf-executor.md", "aiwf-experimenter.md", "aiwf-reviewer.md",
        }.issubset(agents))
        self.assertNotIn("aiwf-tester.md", agents)

        skills = {path.name for path in (self.tmp / ".claude/skills").iterdir()}
        self.assertTrue({
            "aiwf-implement", "aiwf-experiment", "aiwf-review",
        }.issubset(skills))
        self.assertNotIn("aiwf-test", skills)

    def test_generated_hooks_are_executable(self):
        scripts = sorted((self.tmp / "scripts").glob("aiwf_*.py"))
        self.assertGreaterEqual(len(scripts), 1)
        for script in scripts:
            self.assertTrue(script.stat().st_mode & 0o111, f"not executable: {script.name}")

    def test_state_surface_uses_task_and_experiment_records(self):
        for relative in (
            "state/state.json", "state/goals.json", "state/plans.json",
            "state/tasks.json", "state/milestones.json", "records/events.json",
        ):
            self.assertTrue((self.tmp / ".aiwf" / relative).exists(), relative)
        self.assertTrue((self.tmp / ".aiwf/records/tasks").is_dir())
        self.assertTrue((self.tmp / ".aiwf/records/experiments").is_dir())
        self.assertFalse((self.tmp / ".aiwf/records/testing.json").exists())
        self.assertFalse((self.tmp / ".aiwf/state/fix-loop.json").exists())

    def test_task_template_assigns_v_evidence_to_executor(self):
        for args in (
            ["goal", "create", "GOAL-001", "--title", "Goal"],
            ["plan", "create", "PLAN-001", "--goal", "GOAL-001", "--title", "Plan"],
            ["task", "create", "TASK-001", "--plan", "PLAN-001", "--goal", "GOAL-001", "--title", "Task"],
        ):
            result = _run(args, self.tmp)
            self.assertEqual(result.returncode, 0, result.stderr)

        content = (self.tmp / ".aiwf/tasks/TASK-001.md").read_text(encoding="utf-8")
        self.assertIn("executor_required: true", content)
        self.assertIn("reviewer_required: true", content)
        self.assertIn("Executor owns these V-* obligations", content)
        self.assertNotIn("tester_required", content)
        self.assertNotIn("tester_write", content)

    def test_cli_exposes_experiments_and_rejects_record_testing(self):
        help_result = _run(["--help", "--all"], self.tmp)
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("experiment", help_result.stdout)
        self.assertIn("record", help_result.stdout)

        retired = _run(["record", "testing", "--status", "passed"], self.tmp)
        self.assertNotEqual(retired.returncode, 0)
        self.assertIn("invalid choice", retired.stderr)

    def test_sync_and_doctor_are_healthy(self):
        sync = _run(["sync", "--check"], self.tmp)
        self.assertEqual(sync.returncode, 0, sync.stderr)
        doctor = _run(["doctor"], self.tmp)
        self.assertEqual(doctor.returncode, 0, doctor.stderr)
        self.assertIn("healthy", doctor.stdout.lower())

    def test_default_task_record_has_no_testing_stage(self):
        from aiwf_core.core.task_records import default_task_record

        record = default_task_record("TASK-001")
        self.assertEqual(record["experiment_ids"], [])
        self.assertNotIn("testing", record)
        self.assertEqual(record["review"]["result"], "unknown")

    def test_installed_configuration_names_only_current_task_roles(self):
        models = json.loads(
            (self.tmp / ".aiwf/config/agent-models.json").read_text(encoding="utf-8")
        )
        serialized = json.dumps(models)
        for role in ("aiwf-executor", "aiwf-experimenter", "aiwf-reviewer"):
            self.assertIn(role, serialized)
        self.assertNotIn("aiwf-tester", serialized)


if __name__ == "__main__":
    unittest.main()
