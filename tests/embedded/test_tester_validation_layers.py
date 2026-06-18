"""Tester must distinguish unit tests, full regression, and real usage."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


class TestTesterValidationLayers(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aiwf_tester_layers_"))
        from aiwf_core.core.state_schema import MVP_STATE_FILES
        for rel, factory in MVP_STATE_FILES.items():
            _write(self.tmp / ".aiwf" / rel, factory())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_record_testing_stores_full_suite_and_real_usage(self):
        from aiwf_core.core.state_ops import record_testing
        result = record_testing(
            str(self.tmp),
            status="adequate",
            commands=["pytest tests/unit", "pytest", "mycli --version"],
            validation_layers=["targeted", "full_regression", "real_usage"],
            full_suite_status="passed",
            real_usage_status="passed",
            real_usage_reason="installed CLI returned its version",
        )
        self.assertEqual(result["full_suite_status"], "passed")
        self.assertEqual(result["real_usage_status"], "passed")
        self.assertIn("real_usage", result["validation_layers"])

    def test_tester_required_blocks_close_when_testing_not_adequate(self):
        """V2: close_task blocks when tester_required but testing not adequate/passed."""
        from aiwf_core.core.task_ledger import close_task

        # Write a task with tester_required=True in the ledger
        ledger = json.loads((self.tmp / ".aiwf" / "state" / "tasks.json").read_text())
        ledger["tasks"] = [{
            "id": "TASK-1", "status": "active",
            "frozen_doc_hash": "",
            "requirements": {"tester_required": True}
        }]
        _write(self.tmp / ".aiwf" / "state" / "tasks.json", ledger)

        # Set active_task_id so the task is the active one
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["active_task_id"] = "TASK-1"
        _write(self.tmp / ".aiwf" / "state" / "state.json", state)

        # Testing is missing (not adequate/passed)
        testing = json.loads((self.tmp / ".aiwf" / "records" / "testing.jsonl").read_text())
        testing["status"] = "missing"
        _write(self.tmp / ".aiwf" / "records" / "testing.jsonl", testing)

        result = close_task(str(self.tmp), "TASK-1")
        self.assertFalse(result["closed"])
        blockers_text = " ".join(result.get("blockers", []))
        self.assertIn("tester_required", blockers_text)
        self.assertIn("testing status", blockers_text.lower())

    def test_tester_required_passes_when_testing_adequate(self):
        """V2: close_task succeeds when tester_required and testing is adequate,
        even with environmental deferrals on full suite and real usage."""
        from aiwf_core.core.task_ledger import close_task

        # Write a task with tester_required=True
        ledger = json.loads((self.tmp / ".aiwf" / "state" / "tasks.json").read_text())
        ledger["tasks"] = [{
            "id": "TASK-1", "status": "active",
            "frozen_doc_hash": "",
            "requirements": {"tester_required": True}
        }]
        _write(self.tmp / ".aiwf" / "state" / "tasks.json", ledger)

        # Set active_task_id
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["active_task_id"] = "TASK-1"
        _write(self.tmp / ".aiwf" / "state" / "state.json", state)

        # Testing is adequate with environmental deferrals
        testing = json.loads((self.tmp / ".aiwf" / "records" / "testing.jsonl").read_text())
        testing.update({
            "status": "adequate",
            "commands": ["pytest tests/unit/test_one.py"],
            "validation_layers": ["targeted"],
            "full_suite_status": "not_feasible",
            "full_suite_reason": "requires unavailable GPU",
            "real_usage_status": "not_available",
            "real_usage_reason": "staging credentials unavailable",
            "untested_risks": ["GPU and staging paths remain unverified"],
        })
        _write(self.tmp / ".aiwf" / "records" / "testing.jsonl", testing)

        result = close_task(str(self.tmp), "TASK-1")
        self.assertTrue(result["closed"],
            f"Expected close to succeed, got blockers: {result.get('blockers', [])}")

    def test_installed_tester_templates_use_v2_task_packet_format(self):
        """V2: agent templates use Role/Read/Task/Boundaries/Output format;
        skill templates use Task.requirements for dispatch decisions."""
        for mode, prompt_path, is_agent in (
            ("claude", ".claude/agents/aiwf-tester.md", True),
            ("reasonix", ".reasonix/skills/aiwf-test/SKILL.md", False),
        ):
            target = self.tmp / mode
            target.mkdir()
            result = subprocess.run(
                [sys.executable, "-m", "aiwf_core.cli", "install", mode, "--force"],
                cwd=str(target),
                capture_output=True,
                text=True,
                timeout=30,
                env={"PYTHONPATH": str(PROJECT_ROOT)},
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            text = (target / prompt_path).read_text(encoding="utf-8")

            if is_agent:
                # V2 agent template uses task packet format with section headers
                self.assertIn("## Role", text)
                self.assertIn("## Read", text)
                self.assertIn("## Task", text)
                self.assertIn("## Boundaries", text)
                self.assertIn("## Output", text)
                self.assertIn("Do NOT modify code", text)
            else:
                # V2 skill template uses Task.requirements for dispatch decisions
                self.assertIn("tester_required", text)
                self.assertIn("Task.requirements", text)


if __name__ == "__main__":
    unittest.main()
