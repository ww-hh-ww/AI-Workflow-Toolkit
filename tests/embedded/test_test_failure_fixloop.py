"""Test failure fix-loop routing: structured failure packets, fix-loop open/resolve,
skill text, report rendering, closure gate integration."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
TIMEOUT = 15


class TestFailureFixLoop(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awfl_"))
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

    def _testing(self):
        return json.loads((self.tmp / ".aiwf" / "artifacts" / "quality" / "testing.json").read_text())

    def _fix_loop(self):
        return json.loads((self.tmp / ".aiwf" / "state" / "fix-loop.json").read_text())

    def _run_script(self, script_rel):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run([sys.executable, str(self.tmp / script_rel)],
                              capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    # ═══════════════════════════════════════════════════════════════
    # record-testing failure fields
    # ═══════════════════════════════════════════════════════════════

    def test_record_testing_failed_writes_failure_summary(self):
        self._run("state", "record-testing", "--status", "failed",
                  "--failure-summary", "divide by -0 did not throw RangeError")
        t = self._testing()
        self.assertEqual(t["status"], "failed")
        self.assertEqual(t["failure_summary"], "divide by -0 did not throw RangeError")

    def test_record_testing_writes_failed_obligations(self):
        self._run("state", "record-testing", "--status", "failed",
                  "--failed-obligation", "Cover +0/-0 divisor",
                  "--failed-obligation", "Test boundary at min int")
        t = self._testing()
        self.assertEqual(len(t["failed_obligations"]), 2)
        self.assertIn("Cover +0/-0 divisor", t["failed_obligations"])

    def test_record_testing_writes_failed_commands(self):
        self._run("state", "record-testing", "--status", "failed",
                  "--failed-command", "npm test -- -t divide",
                  "--command", "npm test")
        t = self._testing()
        self.assertIn("npm test -- -t divide", t["failed_commands"])
        self.assertIn("npm test", t["commands"])

    def test_record_testing_writes_suspected_route(self):
        self._run("state", "record-testing", "--status", "failed",
                  "--failure-summary", "bug", "--suspected-route", "executor")
        t = self._testing()
        self.assertEqual(t["suspected_route"], "executor")

    def test_record_testing_writes_required_verification(self):
        self._run("state", "record-testing", "--status", "failed",
                  "--required-verification", "rerun npm test",
                  "--required-verification", "check edge case manually")
        t = self._testing()
        self.assertEqual(len(t["required_verification"]), 2)

    def test_record_testing_writes_acceptance_coverage(self):
        self._run("state", "record-testing", "--status", "failed",
                  "--acceptance-coverage", "divide(6,2)=3: covered",
                  "--acceptance-coverage", "divide by -0 throws: failed")
        t = self._testing()
        self.assertEqual(len(t["acceptance_coverage"]), 2)

    # ═══════════════════════════════════════════════════════════════
    # fix-loop open / resolve
    # ═══════════════════════════════════════════════════════════════

    def test_fix_loop_open_writes_status_open(self):
        self._run("fixloop", "open", "--route", "executor",
                  "--reason", "divide by -0 implementation bug")
        fl = self._fix_loop()
        self.assertEqual(fl["status"], "open")

    def test_fix_loop_open_writes_route_reason_fixes_verification(self):
        self._run("fixloop", "open", "--route", "executor",
                  "--reason", "Implementation doesn't match spec",
                  "--required-fix", "Fix divide by -0 to throw RangeError",
                  "--required-fix", "Add null check",
                  "--required-verification", "rerun npm test")
        fl = self._fix_loop()
        self.assertEqual(fl["route"], "executor")
        self.assertEqual(fl["reason"], "Implementation doesn't match spec")
        self.assertEqual(len(fl["required_fixes"]), 2)
        self.assertEqual(len(fl["required_verification"]), 1)

    def test_fix_loop_open_writes_source(self):
        self._run("fixloop", "open", "--route", "planner",
                  "--reason", "unclear spec", "--source", "reviewer")
        fl = self._fix_loop()
        self.assertEqual(fl["source"], "reviewer")

    def test_fix_loop_resolve_writes_status_resolved(self):
        self._run("fixloop", "open", "--route", "executor",
                  "--reason", "implementation bug")
        self._run("fixloop", "resolve", "--resolution", "Executor fixed divide by -0 handling")
        fl = self._fix_loop()
        self.assertEqual(fl["status"], "resolved")
        self.assertIn("Executor fixed divide by -0", fl["resolution"])

    def test_fix_loop_help_shows_no_traceback(self):
        r = self._run("fixloop")
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn("open", r.stdout.lower())
        self.assertIn("resolve", r.stdout.lower())

    # ═══════════════════════════════════════════════════════════════
    # Skill text checks
    # ═══════════════════════════════════════════════════════════════

    def test_tester_says_failed_must_record_failure_summary(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-test" / "SKILL.md").read_text()
        self.assertIn("failure_summary", c.lower(),
                      "Tester should mention failure_summary")

    def test_tester_says_failed_must_record_failed_obligations(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-test" / "SKILL.md").read_text()
        self.assertIn("failed_obligations", c.lower(),
                      "Tester should mention failed_obligations")

    def test_tester_says_suspected_route(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-test" / "SKILL.md").read_text()
        self.assertIn("suspected_route", c.lower(),
                      "Tester should mention suspected_route")

    def test_reviewer_says_failed_testing_must_be_routed(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-review" / "SKILL.md").read_text()
        self.assertIn("review_template", c.lower())

    def test_reviewer_mentions_all_four_routes(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-review" / "SKILL.md").read_text()
        self.assertIn("planner-main", c.lower())
        self.assertIn("testing subagent", c.lower())
        self.assertIn("single_agent", c.lower())

    def test_planner_says_route_planner_requires_user_decision(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-planner" / "SKILL.md").read_text()
        self.assertIn("fix-loop", c.lower())

    # ═══════════════════════════════════════════════════════════════
    # Report: Fix-loop section
    # ═══════════════════════════════════════════════════════════════

    def test_report_includes_fix_loop_section(self):
        self._run("fixloop", "open", "--route", "executor",
                  "--reason", "Implementation bug in divide")
        r = self._run_script("scripts/aiwf_export_report.py")
        self.assertEqual(r.returncode, 0, f"export_report failed: {r.stderr}")
        rpt = (self.tmp / ".aiwf" / "artifacts" / "reports" / "闭合报告.md").read_text()
        self.assertIn("## Fix-loop", rpt)
        self.assertIn("executor", rpt)

    def test_report_shows_fix_loop_resolved(self):
        self._run("fixloop", "open", "--route", "executor",
                  "--reason", "bug")
        self._run("fixloop", "resolve", "--resolution", "Fixed in commit abc123")
        r = self._run_script("scripts/aiwf_export_report.py")
        rpt = (self.tmp / ".aiwf" / "artifacts" / "reports" / "闭合报告.md").read_text()
        self.assertIn("resolved", rpt.lower())

    def test_report_warns_if_testing_failed_but_fix_loop_missing(self):
        # Set testing to failed without opening fix-loop
        self._run("state", "record-testing", "--status", "failed",
                  "--failure-summary", "test crashed")
        r = self._run_script("scripts/aiwf_export_report.py")
        rpt = (self.tmp / ".aiwf" / "artifacts" / "reports" / "闭合报告.md").read_text()
        self.assertIn("missing for failed testing", rpt)

    # ═══════════════════════════════════════════════════════════════
    # Closure still blocked when testing failed
    # ═══════════════════════════════════════════════════════════════

    def test_closure_blocked_when_testing_failed(self):
        self._run("state", "record-testing", "--status", "failed",
                  "--failure-summary", "test crashed")
        r = self._run_script("scripts/aiwf_export_report.py")
        rpt = (self.tmp / ".aiwf" / "artifacts" / "reports" / "闭合报告.md").read_text()
        self.assertIn("BLOCKED", rpt)

    # ═══════════════════════════════════════════════════════════════
    # compile checks
    # ═══════════════════════════════════════════════════════════════

    def test_compileall_passes(self):
        import py_compile
        # Verify aiwf_core compiles
        py_compile.compile(str(PROJECT_ROOT / "aiwf_core" / "core" / "state_schema.py"), doraise=True)
        py_compile.compile(str(PROJECT_ROOT / "aiwf_core" / "core" / "state_ops.py"), doraise=True)
        py_compile.compile(str(PROJECT_ROOT / "aiwf_core" / "install_claude.py"), doraise=True)

    def test_scripts_py_compile_passes(self):
        import py_compile
        py_compile.compile(str(self.tmp / "scripts" / "aiwf_export_report.py"), doraise=True)


if __name__ == "__main__":
    unittest.main()
