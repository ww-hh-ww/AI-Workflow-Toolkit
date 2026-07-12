import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent.parent


class TestGovernanceFiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="aiwf_governance_"))
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT)
        result = subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
            cwd=str(cls.tmp), env=env, capture_output=True, text=True, timeout=20,
        )
        if result.returncode:
            raise AssertionError(result.stderr)

    def _scope_check(self, path):
        payload = json.dumps({
            "session_id": "test",
            "cwd": str(self.tmp),
            "tool_name": "Write",
            "tool_input": {"file_path": path},
        })
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT)
        result = subprocess.run(
            [sys.executable, str(self.tmp / "scripts" / "aiwf_scope_check.py")],
            input=payload, cwd=str(self.tmp), env=env,
            capture_output=True, text=True, timeout=10,
        )
        return json.loads(result.stdout) if result.stdout.strip() else {}

    def test_narrative_governance_is_writable_without_active_task(self):
        for path in [
            ".aiwf/mission.md",
            ".aiwf/goals/GOAL-001.md",
            ".aiwf/plans/PLAN-001.md",
            ".aiwf/tasks/TASK-001.md",
            ".aiwf/memory/project-facts.md",
            ".aiwf/config/write-policy.json",
        ]:
            self.assertNotIn("permissionDecision", self._scope_check(path), path)

    def test_machine_truth_requires_cli(self):
        for path in [
            ".aiwf/state/state.json",
            ".aiwf/state/tasks.json",
            ".aiwf/records/review.json",
        ]:
            output = self._scope_check(path)
            decision = output.get("hookSpecificOutput", {}).get("permissionDecision")
            self.assertEqual(decision, "deny", path)

    def test_project_write_without_active_task_is_denied(self):
        output = self._scope_check("src/main.py")
        self.assertEqual(
            output.get("hookSpecificOutput", {}).get("permissionDecision"),
            "deny",
        )

if __name__ == "__main__":
    unittest.main()
