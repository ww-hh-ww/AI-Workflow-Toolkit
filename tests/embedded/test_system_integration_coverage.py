"""System integration coverage: schema, CLI, report, skill text, L0-L3 rules."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
TIMEOUT = 15


class TestSystemIntegrationCoverage(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awsic_"))
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        subprocess.run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                       capture_output=True, text=True, cwd=str(cls.tmp), env=env, timeout=20)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        from aiwf_core.core.state_schema import MVP_STATE_FILES
        (self.tmp / ".aiwf").mkdir(parents=True, exist_ok=True)
        for fn, dfn in MVP_STATE_FILES.items():
            p = self.tmp / ".aiwf" / fn; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(dfn(), indent=2) + "\n")

    def _run(self, *args):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run([sys.executable, "-m", "aiwf_core.cli"] + list(args),
                              capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    def _goal(self):
        return json.loads((self.tmp / ".aiwf" / "state" / "goal.json").read_text())

    def _testing(self):
        return json.loads((self.tmp / ".aiwf" / "artifacts" / "quality" / "testing.json").read_text())

    def _run_script(self, script_rel):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run([sys.executable, str(self.tmp / script_rel)],
                              capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    # ═══════════════════════════════════════════════════════════════
    # Schema
    # ═══════════════════════════════════════════════════════════════

    def test_default_evaluation_contract_has_system_integration_obligations(self):
        g = self._goal()
        ec = g["quality_brief"]["evaluation_contract"]
        self.assertIn("system_integration_obligations", ec)
        self.assertEqual(ec["system_integration_obligations"], [])

    def test_default_testing_has_system_coverage(self):
        t = self._testing()
        self.assertIn("system_coverage", t)
        self.assertEqual(t["system_coverage"], [])

    # ═══════════════════════════════════════════════════════════════
    # CLI: record-quality-brief
    # ═══════════════════════════════════════════════════════════════

    def test_record_quality_brief_writes_system_integration_obligations(self):
        self._run("state", "record-quality-brief",
                  "--system-integration-obligation",
                  "Verify divide is exported through public API")
        ec = self._goal()["quality_brief"]["evaluation_contract"]
        self.assertIn("Verify divide is exported through public API",
                      ec["system_integration_obligations"])

    # ═══════════════════════════════════════════════════════════════
    # CLI: record-testing
    # ═══════════════════════════════════════════════════════════════

    def test_record_testing_writes_system_coverage(self):
        self._run("state", "record-testing", "--status", "adequate",
                  "--system-coverage", "Public calculator export path covered")
        t = self._testing()
        self.assertIn("Public calculator export path covered", t["system_coverage"])

    # ═══════════════════════════════════════════════════════════════
    # Report
    # ═══════════════════════════════════════════════════════════════

    def test_report_includes_system_integration_obligations(self):
        self._run("state", "record-quality-brief",
                  "--user-visible-outcome", "divide works",
                  "--system-integration-obligation",
                  "Verify divide exported through public API")
        r = self._run_script("scripts/aiwf_export_report.py")
        rpt = (self.tmp / ".aiwf" / "artifacts" / "reports" / "闭合报告.md").read_text()
        self.assertIn("System integration obligations", rpt)
        self.assertIn("Verify divide exported through public API", rpt)

    def test_report_includes_acceptance_coverage_from_testing(self):
        self._run("state", "record-quality-brief",
                  "--user-visible-outcome", "divide works")
        self._run("state", "record-testing", "--status", "adequate",
                  "--acceptance-coverage", "AC1 covered by calc.test.js")
        r = self._run_script("scripts/aiwf_export_report.py")
        rpt = (self.tmp / ".aiwf" / "artifacts" / "reports" / "闭合报告.md").read_text()
        self.assertIn("AC1 covered by calc.test.js", rpt)

    def test_report_includes_system_coverage_from_testing(self):
        self._run("state", "record-quality-brief",
                  "--user-visible-outcome", "divide works")
        self._run("state", "record-testing", "--status", "adequate",
                  "--system-coverage", "Public API export path covered by integration test")
        r = self._run_script("scripts/aiwf_export_report.py")
        rpt = (self.tmp / ".aiwf" / "artifacts" / "reports" / "闭合报告.md").read_text()
        self.assertIn("Public API export path covered by integration test", rpt)

    def test_report_includes_failed_obligations_from_testing(self):
        self._run("state", "record-quality-brief",
                  "--user-visible-outcome", "divide works")
        self._run("state", "record-testing", "--status", "failed",
                  "--failure-summary", "divide by -0 did not throw",
                  "--failed-obligation", "Cover +0/-0 divisor")
        r = self._run_script("scripts/aiwf_export_report.py")
        rpt = (self.tmp / ".aiwf" / "artifacts" / "reports" / "闭合报告.md").read_text()
        self.assertIn("Failed obligations", rpt)
        self.assertIn("Cover +0/-0 divisor", rpt)

    def test_report_no_placeholder_when_coverage_exists(self):
        """When coverage data exists, report should show real data."""
        self._run("state", "record-quality-brief",
                  "--user-visible-outcome", "divide works")
        self._run("state", "record-testing", "--status", "adequate",
                  "--acceptance-coverage", "AC1: covered",
                  "--system-coverage", "Sys1: covered")
        r = self._run_script("scripts/aiwf_export_report.py")
        rpt = (self.tmp / ".aiwf" / "artifacts" / "reports" / "闭合报告.md").read_text()
        self.assertIn("AC1: covered", rpt)
        self.assertIn("Sys1: covered", rpt)

    def test_report_shows_none_when_coverage_missing(self):
        self._run("state", "record-quality-brief",
                  "--user-visible-outcome", "divide works")
        r = self._run_script("scripts/aiwf_export_report.py")
        rpt = (self.tmp / ".aiwf" / "artifacts" / "reports" / "闭合报告.md").read_text()
        self.assertIn("none / not recorded", rpt.lower())

    # ═══════════════════════════════════════════════════════════════
    # Skill text checks
    # ═══════════════════════════════════════════════════════════════

    def test_planner_mentions_system_integration_obligations(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-planner-contracts" / "SKILL.md").read_text()
        self.assertIn("system", c.lower(),
                      "Planner-contracts should mention system integration")

    def test_planner_l0_l1_no_full_system_test_by_default(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-planner-execute" / "SKILL.md").read_text()
        self.assertIn("L0", c)
        self.assertIn("L1", c)

    def test_planner_l2_l3_requires_system_path(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-planner-execute" / "SKILL.md").read_text()
        self.assertIn("L3", c)
        self.assertIn("L1", c)

    def test_tester_mentions_system_coverage(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-test" / "SKILL.md").read_text()
        self.assertIn("System Coverage", c,
                      "Tester should mention System Coverage")
        self.assertIn("system-coverage", c.lower(),
                      "Tester should mention --system-coverage CLI flag")

    def test_reviewer_says_local_correctness_not_enough(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-review" / "SKILL.md").read_text()
        self.assertIn("test", c.lower())

    def test_reviewer_checks_system_integration(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-review" / "SKILL.md").read_text()
        self.assertIn("evidence", c.lower())

    # ═══════════════════════════════════════════════════════════════
    # CLI help text fix
    # ═══════════════════════════════════════════════════════════════

    def test_fixloop_help_no_traceback(self):
        r = self._run("fixloop")
        self.assertNotIn("Traceback", r.stderr)

    def test_fixloop_help_shows_fixloop_open_resolve(self):
        r = self._run("fixloop")
        self.assertIn("fixloop open", r.stdout.lower())
        self.assertIn("fixloop resolve", r.stdout.lower())

    # ═══════════════════════════════════════════════════════════════
    # compile checks
    # ═══════════════════════════════════════════════════════════════

    def test_compileall_passes(self):
        import py_compile
        py_compile.compile(str(PROJECT_ROOT / "aiwf_core" / "core" / "state_schema.py"), doraise=True)
        py_compile.compile(str(PROJECT_ROOT / "aiwf_core" / "core" / "state_ops.py"), doraise=True)
        py_compile.compile(str(PROJECT_ROOT / "aiwf_core" / "install_claude.py"), doraise=True)

    def test_scripts_py_compile_passes(self):
        import py_compile
        py_compile.compile(str(self.tmp / "scripts" / "aiwf_export_report.py"), doraise=True)


if __name__ == "__main__":
    unittest.main()
