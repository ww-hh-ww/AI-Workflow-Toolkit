import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent.parent


class TestNoExternalOrchestration(unittest.TestCase):
    def test_removed_runtime_commands_are_not_public(self):
        result = subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", "--help", "--all"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for removed in ["handoff", "action", "runner", "managed runtime"]:
            self.assertNotIn(removed, result.stdout.lower())

    def test_removed_runtime_directories_are_absent(self):
        for path in [
            ROOT / ".ai-workflow",
            ROOT / "aiwf_core" / "runner",
            ROOT / "aiwf_core" / "managed_runtime",
        ]:
            self.assertFalse(path.exists(), str(path))


if __name__ == "__main__":
    unittest.main()
