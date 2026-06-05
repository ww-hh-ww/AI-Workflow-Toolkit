"""Human surface: status tiers, no raw JSON, reading notes, accuracy."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
TIMEOUT = 15

class TestHumanSurface(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awhs_"))
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        subprocess.run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                       capture_output=True, text=True, cwd=str(cls.tmp), env=env, timeout=20)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _status(self):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, "-m", "aiwf_core.cli", "status"],
                          capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        return r.stdout

    def _reset_state(self):
        from aiwf_core.core.state_schema import MVP_STATE_FILES
        for fn, dfn in MVP_STATE_FILES.items():
            p = self.tmp / ".aiwf" / fn; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(dfn(), indent=2)+"\n")

    # ── doc ──
    def test_human_surface_doc_exists(self):
        self.assertTrue((PROJECT_ROOT/"docs"/"AIWF-HUMAN-SURFACE.md").exists())

    def test_doc_mentions_three_entries(self):
        doc = (PROJECT_ROOT/"docs"/"AIWF-HUMAN-SURFACE.md").read_text()
        self.assertIn("aiwf status", doc)
        self.assertIn(".aiwf/reports/当前状态.md", doc)
        self.assertIn(".aiwf/reports/闭合报告.md", doc)

    # ── status tiers ──
    def test_status_has_control_panel(self):
        s = self._status()
        self.assertIn("Control Panel", s)
        for term in ["Goal:", "Phase:", "Health:", "Next:"]:
            self.assertIn(term, s, f"Missing: {term}")

    def test_status_has_quality_closure(self):
        s = self._status()
        self.assertIn("Quality & Closure", s)
        for term in ["Testing:", "Review:", "Evidence:", "Fix-loop:", "Cleanup:", "Structure:", "Closure:"]:
            self.assertIn(term, s, f"Missing: {term}")

    def test_status_has_awareness(self):
        s = self._status()
        self.assertIn("Awareness", s)
        for term in ["Workspace drift", "Ext capabilities", "Context dispatch", "Current state", "Report"]:
            self.assertIn(term, s, f"Missing: {term}")

    def test_status_explains_gravity(self):
        s = self._status()
        self.assertIn("Gravity", s)
        self.assertIn("historical pressure only", s)
        self.assertIn("Gates:", s)

    def test_status_has_detail_links(self):
        s = self._status()
        self.assertIn(".aiwf/reports/当前状态.md", s)
        self.assertIn(".aiwf/reports/闭合报告.md", s)

    # ── no raw JSON ──
    def test_status_no_raw_json(self):
        s = self._status()
        self.assertNotIn('"records"', s)
        self.assertNotIn('"state"', s)
        self.assertNotIn('{', s)

    def test_status_no_full_capability_list(self):
        s = self._status()
        self.assertNotIn("mcp_server", s)
        self.assertNotIn("skill:", s)

    def test_status_no_drift_file_names(self):
        s = self._status()
        self.assertNotIn("README.md", s)

    # ── context dispatch accuracy ──
    def test_context_dispatch_missing_when_only_quality_policy(self):
        """Quality policy (test_template) should NOT count as context dispatch."""
        self._reset_state()
        from aiwf_core.core.state_ops import record_quality_policy
        record_quality_policy(str(self.tmp), "small_function", "L1_review_light")
        s = self._status()
        self.assertIn("Context dispatch: missing", s)

    def test_context_dispatch_present_when_active_context_has_focus(self):
        self._reset_state()
        from aiwf_core.core.state_ops import start_context
        start_context(str(self.tmp), "CTX-TEST", "test", allowed_write=["src/a.py"],
                      purpose="test purpose", test_focus=["focus item"])
        s = self._status()
        self.assertIn("Context dispatch: present", s)

    # ── capabilities accuracy ──
    def test_capabilities_empty_shows_none(self):
        (self.tmp/".aiwf"/"capabilities.json").write_text(
            '{"schema_version":1,"capabilities":[]}')
        s = self._status()
        self.assertIn("Ext capabilities: none", s)

    def test_normal_capability_shows_available(self):
        (self.tmp/".aiwf"/"capabilities.json").write_text(
            '{"schema_version":1,"capabilities":[{"id":"skill:k","risk":"method_advisory","use_policy":"advisory"}]}')
        s = self._status()
        self.assertIn("Ext capabilities: available", s)

    def test_unknown_capability_shows_high_risk(self):
        (self.tmp/".aiwf"/"capabilities.json").write_text(
            '{"schema_version":1,"capabilities":[{"id":"skill:d","risk":"unknown","use_policy":"ask_before_use"}]}')
        s = self._status()
        self.assertIn("Ext capabilities: high-risk", s)

    def test_destructive_capability_shows_high_risk(self):
        (self.tmp/".aiwf"/"capabilities.json").write_text(
            '{"schema_version":1,"capabilities":[{"id":"skill:x","risk":"destructive_or_deploy","use_policy":"requires_user_decision"}]}')
        s = self._status()
        self.assertIn("Ext capabilities: high-risk", s)

    # ── reading notes ──
    def test_report_has_reading_note(self):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        subprocess.run([sys.executable, str(self.tmp/"scripts"/"aiwf_export_report.py")],
                       capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        rpt = (self.tmp/".aiwf" / "reports" / "闭合报告.md").read_text()
        self.assertIn("Human-readable closure basis", rpt)

    def test_current_state_has_reading_note(self):
        self._reset_state()
        s = json.loads((self.tmp/".aiwf" / "state" / "state.json").read_text())
        s["phase"] = "closed"; s["closure_allowed"] = True
        (self.tmp/".aiwf" / "state" / "state.json").write_text(json.dumps(s, indent=2))
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        subprocess.run([sys.executable, str(self.tmp/"scripts"/"aiwf_rebase_state.py")],
                       capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        cs = (self.tmp/".aiwf"/"reports"/"当前状态.md").read_text()
        self.assertIn("Carry-forward summary for Planner", cs)

    # ── planner skill ──
    def test_planner_skill_prioritizes_human_surface(self):
        c = (self.tmp/".claude"/"skills"/"aiwf-planner"/"SKILL.md").read_text()
        self.assertIn("current-state.md", c)
        self.assertIn("Summarize first", c)

    # ── compile ──
    def test_scripts_compile(self):
        import py_compile
        for s in sorted((self.tmp/"scripts").glob("aiwf_*.py")):
            py_compile.compile(str(s), doraise=True)


if __name__ == "__main__":
    unittest.main()
