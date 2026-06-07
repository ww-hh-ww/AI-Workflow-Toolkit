"""External research bridge: low-trust inputs require Planner promotion."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 15


class TestExternalResearch(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="awresearch_"))
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

    def test_record_and_promote_research_without_mutating_goal(self):
        goal_path = self.tmp / ".aiwf" / "state" / "goal.json"
        before_goal = json.loads(goal_path.read_text())

        out = self._run_ok(
            "research", "record",
            "--source", "x",
            "--query", "dynamic workflows",
            "--claim", "Use topology only when uncertainty requires it",
            "--link", "https://example.com/thread",
            "--confidence", "low",
        ).stdout
        research_id = out.split("External research recorded: ")[1].splitlines()[0].strip()
        store = json.loads((self.tmp / ".aiwf" / "research" / "external.json").read_text())
        self.assertEqual(store["records"][0]["status"], "raw")
        self.assertEqual(store["records"][0]["confidence"], "low")

        self._run_ok("research", "promote", research_id, "--decision", "Adopt only as advisory topology routing")
        store = json.loads((self.tmp / ".aiwf" / "research" / "external.json").read_text())
        self.assertEqual(store["records"][0]["status"], "promoted")
        self.assertIn("Adopt only", store["records"][0]["used_for_decision"])
        self.assertEqual(before_goal, json.loads(goal_path.read_text()))

    def test_process_guidance_mentions_required_external_research(self):
        from aiwf_core.core.process_contract import planner_process_guidance

        self._run_ok(
            "state", "set-workflow-mode",
            "--request-mode", "research",
            "--workflow-pattern", "research_first",
            "--external-research-required",
        )
        guidance = planner_process_guidance(str(self.tmp))

        self.assertTrue(guidance["external_research_required"])
        self.assertTrue(any("External research is marked required" in c for c in guidance["conditional"]))


if __name__ == "__main__":
    unittest.main()
