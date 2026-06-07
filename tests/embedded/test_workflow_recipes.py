"""Workflow recipes are advisory route templates, not runtime gates."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 15


class TestWorkflowRecipes(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="awrecipe_"))
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                           capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, *args):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run([sys.executable, "-m", "aiwf_core.cli", *args],
                              capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    def _run_ok(self, *args):
        r = self._run(*args)
        self.assertEqual(r.returncode, 0, f"{args}\nstdout={r.stdout}\nstderr={r.stderr}")
        return r

    def test_recipe_list_show_and_recommend(self):
        listed = self._run_ok("recipe", "list").stdout
        self.assertIn("requirements_grill", listed)
        self.assertIn("tdd_vertical_slice", listed)

        shown = self._run_ok("recipe", "show", "requirements_grill").stdout
        self.assertIn("clarification_first", shown)
        self.assertIn("Advisory only", shown)

        rec = self._run_ok("recipe", "recommend", "--task-type", "bug_fix", "--risk-flag", "flaky").stdout
        self.assertIn("bug_fix", rec)
        self.assertIn("flaky_test_hunt", rec)

    def test_recipe_recommend_does_not_modify_state(self):
        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        before = json.loads(state_path.read_text())

        self._run_ok("recipe", "recommend", "--task-type", "api_endpoint", "--risk-flag", "external")
        after = json.loads(state_path.read_text())

        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
