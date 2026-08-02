"""Plan list CLI display contracts."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent.parent


class TestPlanList(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aiwf_plan_list_"))
        (self.tmp / ".aiwf/plans").mkdir(parents=True)
        (self.tmp / ".aiwf/state").mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_closed_plan_uses_registry_status(self):
        (self.tmp / ".aiwf/plans/PLAN-001.md").write_text(
            "---\nid: PLAN-001\nstatus: closed\n---\n",
            encoding="utf-8",
        )
        (self.tmp / ".aiwf/state/plans.json").write_text(
            json.dumps({
                "schema_version": 1,
                "plans": [{
                    "id": "PLAN-001",
                    "plan_id": "PLAN-001",
                    "status": "closed",
                    "dependencies": [],
                    "task_ids": [],
                }],
            }),
            encoding="utf-8",
        )
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT)

        result = subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", "plan", "list"],
            cwd=self.tmp,
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PLAN-001 | closed", result.stdout)
        self.assertIn("| closed |", result.stdout)


if __name__ == "__main__":
    unittest.main()
