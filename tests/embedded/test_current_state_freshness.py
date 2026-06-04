"""Current-state freshness contract."""
import json, os, shutil, subprocess, sys, tempfile, time, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class TestCurrentStateFreshness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awcsf_"))
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        subprocess.run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                       capture_output=True, text=True, cwd=str(cls.tmp), env=env, timeout=20)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        from aiwf_core.core.state_schema import MVP_STATE_FILES
        for fn, dfn in MVP_STATE_FILES.items():
            p = self.tmp / ".aiwf" / fn; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(dfn(), indent=2) + "\n")
        cs = self.tmp / ".aiwf" / "reports" / "当前状态.md"
        if cs.exists():
            cs.unlink()

    def test_missing_current_state_is_reported(self):
        from aiwf_core.core.current_state import current_state_freshness

        result = current_state_freshness(str(self.tmp))

        self.assertEqual(result["status"], "missing")

    def test_current_state_fresh_when_newer_than_sources(self):
        from aiwf_core.core.current_state import current_state_freshness

        time.sleep(0.02)
        (self.tmp / ".aiwf" / "reports" / "当前状态.md").write_text(
            "\n".join([
                "# AIWF Current State",
                "## Goal & Intent",
                "- Goal: done",
                "## Current Status",
                "- src/a.py",
                "## Quality Snapshot",
                "- Test result: adequate",
                "- Review result: accepted",
                "## Raw References",
                "- Recent closed tasks: 1",
                "- .aiwf/reports/闭合报告.md",
            ]) + "\n"
        )

        result = current_state_freshness(str(self.tmp))

        self.assertEqual(result["status"], "fresh")
        self.assertEqual(result["stale_sources"], [])

    def test_current_state_incomplete_when_structure_missing(self):
        from aiwf_core.core.current_state import current_state_freshness

        time.sleep(0.02)
        (self.tmp / ".aiwf" / "reports" / "当前状态.md").write_text("# summary\n")

        result = current_state_freshness(str(self.tmp))

        self.assertEqual(result["status"], "incomplete")
        self.assertTrue(result["structure_issues"])

    def test_current_state_stale_when_state_changes_after_summary(self):
        from aiwf_core.core.current_state import current_state_freshness

        (self.tmp / ".aiwf" / "reports" / "当前状态.md").write_text("# summary\n")
        time.sleep(0.02)
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["phase"] = "implementing"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(state, indent=2))

        result = current_state_freshness(str(self.tmp))

        self.assertEqual(result["status"], "stale")
        self.assertIn("state/state.json", result["stale_sources"])


if __name__ == "__main__":
    unittest.main()
