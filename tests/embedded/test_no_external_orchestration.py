"""Removed external orchestration must not reappear."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _run(args, cwd):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    env["PYTHONPYCACHEPREFIX"] = str(Path(tempfile.gettempdir()) / "aiwf-pycache")
    return subprocess.run(
        [sys.executable, "-m", "aiwf_core.cli", *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )


class TestNoExternalOrchestration(unittest.TestCase):
    def test_help_exposes_only_embedded_mainline(self):
        with tempfile.TemporaryDirectory(prefix="aiwf_no_ext_") as td:
            result = _run(["--help"], Path(td))
            self.assertEqual(result.returncode, 0)
            out = result.stdout
            for removed in ["handoff", "executor", "tester", "reviewer", "actions", "action", "planner"]:
                self.assertNotIn(f" {removed} ", out)
            self.assertIn("install", out)
            self.assertIn("status", out)

    def test_init_creates_aiwf_not_ai_workflow(self):
        with tempfile.TemporaryDirectory(prefix="aiwf_no_ext_") as td:
            root = Path(td)
            result = _run(["init"], root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((root / ".aiwf" / "state" / "state.json").exists())
            self.assertFalse((root / ".ai-workflow").exists())

    def test_removed_commands_fail_without_side_effects(self):
        for cmd in ["planner", "handoff", "action", "actions", "executor"]:
            with tempfile.TemporaryDirectory(prefix="aiwf_no_ext_") as td:
                root = Path(td)
                result = _run([cmd], root)
                self.assertNotEqual(result.returncode, 0, cmd)
                self.assertFalse((root / ".ai-workflow").exists(), cmd)

    def test_removed_external_state_directory_is_not_present_in_repo(self):
        self.assertFalse((PROJECT_ROOT / ".ai-workflow").exists())

    def test_runtime_code_does_not_create_external_state_directory(self):
        forbidden = '".ai-workflow"'
        runtime_files = [
            p for p in (PROJECT_ROOT / "aiwf_core").rglob("*.py")
            if "__pycache__" not in p.parts
        ]
        offenders = []
        for path in runtime_files:
            text = path.read_text(encoding="utf-8")
            if forbidden in text:
                offenders.append(str(path.relative_to(PROJECT_ROOT)))
        self.assertEqual(offenders, [], f"runtime must not reference {forbidden}: {offenders}")


if __name__ == "__main__":
    unittest.main()
