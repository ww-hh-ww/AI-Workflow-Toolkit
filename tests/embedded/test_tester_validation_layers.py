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

    def test_l2_unit_test_only_is_not_enough_to_close(self):
        from aiwf_core.core.task_ledger import _l2_l3_completion_blockers
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["workflow_level"] = "L2_standard_team"
        _write(self.tmp / ".aiwf" / "state" / "state.json", state)
        testing = json.loads((self.tmp / ".aiwf" / "quality" / "testing.json").read_text())
        testing.update({"status": "adequate", "commands": ["pytest tests/unit/test_one.py"]})
        _write(self.tmp / ".aiwf" / "quality" / "testing.json", testing)

        blockers = _l2_l3_completion_blockers(str(self.tmp), {"id": "TASK-1", "status": "active"})
        text = " ".join(blockers)
        self.assertIn("targeted validation layer", text)
        self.assertIn("full project suite", text)
        self.assertIn("real user-facing entrypoint", text)

    def test_explicit_environmental_deferral_avoids_layer_blockers(self):
        from aiwf_core.core.task_ledger import _l2_l3_completion_blockers
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["workflow_level"] = "L2_standard_team"
        _write(self.tmp / ".aiwf" / "state" / "state.json", state)
        testing = json.loads((self.tmp / ".aiwf" / "quality" / "testing.json").read_text())
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
        _write(self.tmp / ".aiwf" / "quality" / "testing.json", testing)

        blockers = _l2_l3_completion_blockers(str(self.tmp), {"id": "TASK-1", "status": "active"})
        text = " ".join(blockers)
        self.assertNotIn("full project suite", text)
        self.assertNotIn("real user-facing entrypoint", text)
        self.assertNotIn("deferral requires", text)

    def test_installed_claude_and_reasonix_tester_prompts_require_real_usage(self):
        for mode, prompt_path in (
            ("claude", ".claude/agents/aiwf-tester.md"),
            ("reasonix", ".reasonix/skills/aiwf-test/SKILL.md"),
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
            self.assertIn("actual user-facing", text)
            self.assertIn("full", text.lower())


if __name__ == "__main__":
    unittest.main()
