import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent.parent


class TestNodeLinkContract(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aiwf_links_"))
        self.env = {"PYTHONPATH": str(ROOT)}
        self._run("install", "claude", "--force")

    def _run(self, *args):
        result = subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", *args],
            cwd=str(self.tmp), env=self.env,
            capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def test_goal_plan_task_links_are_visible_on_both_sides(self):
        self._run("goal", "create", "GOAL-001", "--title", "Capability")
        plan = self._run(
            "plan", "create", "PLAN-001", "--goal", "GOAL-001", "--title", "Mechanism"
        )
        task = self._run(
            "task", "create", "TASK-001", "--goal", "GOAL-001",
            "--plan", "PLAN-001", "--title", "Observable result",
        )

        goals = json.loads((self.tmp / ".aiwf/state/goals.json").read_text())
        plans = json.loads((self.tmp / ".aiwf/state/plans.json").read_text())
        tasks = json.loads((self.tmp / ".aiwf/state/tasks.json").read_text())
        self.assertEqual(goals["goals"][0]["attached_plan_ids"], ["PLAN-001"])
        self.assertEqual(plans["plans"][0]["goal_id"], "GOAL-001")
        self.assertEqual(plans["plans"][0]["task_ids"], ["TASK-001"])
        self.assertEqual(tasks["tasks"][0]["goal_id"], "GOAL-001")
        self.assertEqual(tasks["tasks"][0]["plan_id"], "PLAN-001")
        self.assertIn("Goal: GOAL-001", plan.stdout)
        self.assertIn("Goal: GOAL-001", task.stdout)


if __name__ == "__main__":
    unittest.main()
