"""Fix-loop limits: attempt counting, max_attempts per level, escalation, rollback."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 15


class TestFixLoopLimits(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awfll_"))
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

    def _fix_loop(self):
        return json.loads((self.tmp / ".aiwf" / "state" / "fix-loop.json").read_text())

    def _run_script(self, script_rel):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run([sys.executable, str(self.tmp / script_rel)],
                              capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    # ═══════════════════════════════════════════════════════════════
    # Schema defaults
    # ═══════════════════════════════════════════════════════════════

    @unittest.skip("V1: hidden module")
    def test_default_has_attempt_fields(self):
        fl = self._fix_loop()
        for field in ["attempt_count", "max_attempts", "route_history",
                       "escalation_required", "escalation_reason", "rollback_recommended"]:
            self.assertIn(field, fl, f"Missing fix-loop field: {field}")
        self.assertEqual(fl["attempt_count"], 0)
        self.assertEqual(fl["max_attempts"], 0)
        self.assertEqual(fl["route_history"], [])
        self.assertFalse(fl["escalation_required"])

    # ═══════════════════════════════════════════════════════════════
    # First open
    # ═══════════════════════════════════════════════════════════════

    @unittest.skip("V1: hidden module")
    def test_first_open_sets_attempt_count_1(self):
        self._run("fixloop", "open", "--route", "executor",
                  "--reason", "implementation bug")
        fl = self._fix_loop()
        self.assertEqual(fl["attempt_count"], 1)

    @unittest.skip("V1: hidden module")
    def test_first_open_records_route_history(self):
        self._run("fixloop", "open", "--route", "executor",
                  "--reason", "divide by -0 bug")
        fl = self._fix_loop()
        self.assertEqual(len(fl["route_history"]), 1)
        self.assertEqual(fl["route_history"][0]["attempt"], 1)
        self.assertEqual(fl["route_history"][0]["route"], "executor")

    # ═══════════════════════════════════════════════════════════════
    # Repeated open
    # ═══════════════════════════════════════════════════════════════

    @unittest.skip("V1: hidden module")
    def test_second_open_increments_attempt_count(self):
        self._run("fixloop", "open", "--route", "executor",
                  "--reason", "first fix attempt")
        self._run("fixloop", "open", "--route", "executor",
                  "--reason", "second fix attempt")
        fl = self._fix_loop()
        self.assertEqual(fl["attempt_count"], 2)
        self.assertEqual(len(fl["route_history"]), 2)

    @unittest.skip("V1: hidden module")
    def test_route_history_records_both_attempts(self):
        self._run("fixloop", "open", "--route", "executor",
                  "--reason", "first fix")
        self._run("fixloop", "open", "--route", "tester",
                  "--reason", "test was wrong")
        fl = self._fix_loop()
        self.assertEqual(len(fl["route_history"]), 2)
        self.assertEqual(fl["route_history"][0]["route"], "executor")
        self.assertEqual(fl["route_history"][1]["route"], "tester")

    # ═══════════════════════════════════════════════════════════════
    # max_attempts by workflow level
    # ═══════════════════════════════════════════════════════════════

    @unittest.skip("V1: hidden module")
    def test_max_attempts_L0_is_1(self):
        s = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        s["workflow_level"] = "L0_direct"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(s, indent=2))
        self._run("fixloop", "open", "--route", "executor",
                  "--reason", "bug")
        fl = self._fix_loop()
        self.assertEqual(fl["max_attempts"], 1)

    @unittest.skip("V1: hidden module")
    def test_max_attempts_L1_is_1(self):
        s = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        s["workflow_level"] = "L1_review_light"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(s, indent=2))
        self._run("fixloop", "open", "--route", "executor",
                  "--reason", "bug")
        fl = self._fix_loop()
        self.assertEqual(fl["max_attempts"], 1)

    @unittest.skip("V1: hidden module")
    def test_max_attempts_L2_is_2(self):
        s = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        s["workflow_level"] = "L2_standard_team"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(s, indent=2))
        self._run("fixloop", "open", "--route", "executor",
                  "--reason", "bug")
        fl = self._fix_loop()
        self.assertEqual(fl["max_attempts"], 2)

    @unittest.skip("V1: hidden module")
    def test_max_attempts_L3_is_3(self):
        s = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        s["workflow_level"] = "L3_full_power"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(s, indent=2))
        self._run("fixloop", "open", "--route", "executor",
                  "--reason", "bug")
        fl = self._fix_loop()
        self.assertEqual(fl["max_attempts"], 3)

    # ═══════════════════════════════════════════════════════════════
    # Exceeding max_attempts → escalation
    # ═══════════════════════════════════════════════════════════════

    @unittest.skip("V1: hidden module")
    def test_exceeding_max_attempts_sets_escalation_required(self):
        # L0 has max=1, so second open exceeds it
        s = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        s["workflow_level"] = "L0_direct"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(s, indent=2))
        self._run("fixloop", "open", "--route", "executor",
                  "--reason", "first fix")
        self._run("fixloop", "open", "--route", "executor",
                  "--reason", "second fix — should escalate")
        fl = self._fix_loop()
        self.assertTrue(fl["escalation_required"], "escalation_required should be true")
        self.assertIn("exceeded max_attempts", fl["escalation_reason"])

    @unittest.skip("V1: hidden module")
    def test_exceeding_max_attempts_sets_escalation_reason(self):
        s = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        s["workflow_level"] = "L0_direct"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(s, indent=2))
        self._run("fixloop", "open", "--route", "executor",
                  "--reason", "first fix")
        self._run("fixloop", "open", "--route", "executor",
                  "--reason", "second fix")
        fl = self._fix_loop()
        self.assertIn("2", fl["escalation_reason"])
        self.assertIn("1", fl["escalation_reason"])

    @unittest.skip("V1: hidden module")
    def test_rollback_recommended_false_when_no_checkpoint(self):
        s = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        s["workflow_level"] = "L0_direct"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(s, indent=2))
        self._run("fixloop", "open", "--route", "executor",
                  "--reason", "first fix")
        self._run("fixloop", "open", "--route", "executor",
                  "--reason", "second fix")
        fl = self._fix_loop()
        # No checkpoints dir exists, so rollback_recommended should be false
        self.assertFalse(fl["rollback_recommended"])

    @unittest.skip("V1: hidden module")
    def test_not_exceeded_no_escalation(self):
        # L2 has max=2, so second open does NOT exceed
        s = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        s["workflow_level"] = "L2_standard_team"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(s, indent=2))
        self._run("fixloop", "open", "--route", "executor",
                  "--reason", "first fix")
        self._run("fixloop", "open", "--route", "executor",
                  "--reason", "second fix")
        fl = self._fix_loop()
        self.assertFalse(fl["escalation_required"])

    # ═══════════════════════════════════════════════════════════════
    # fixloop status
    # ═══════════════════════════════════════════════════════════════

    @unittest.skip("V1: hidden module")
    def test_fixloop_status_shows_attempt_count(self):
        self._run("fixloop", "open", "--route", "executor",
                  "--reason", "bug", "--required-fix", "Fix divide")
        out = self._run("fixloop", "status").stdout
        self.assertNotIn("Traceback", out)
        self.assertIn("1 /", out)
        self.assertIn("Required fixes", out)
        self.assertIn("Fix divide", out)

    @unittest.skip("V1: hidden module")
    def test_fixloop_status_no_raw_json(self):
        self._run("fixloop", "open", "--route", "executor",
                  "--reason", "bug")
        out = self._run("fixloop", "status").stdout
        self.assertNotIn('"status"', out)
        self.assertNotIn('"attempt_count"', out)

    # ═══════════════════════════════════════════════════════════════
    # Skill text checks
    # ═══════════════════════════════════════════════════════════════

    @unittest.skip("V1: hidden module")
    def test_reviewer_says_repeated_same_route_should_escalate(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-planner" / "references" / "risk-and-rollback.md").read_text()
        self.assertIn("route", c.lower(),
                      "Planner-meta should mention route handling")
        self.assertIn("escalation_required", c.lower(),
                      "Planner-meta should mention escalation_required")

    @unittest.skip("V1: hidden module")
    def test_planner_says_escalation_stops_execution(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-planner" / "references" / "risk-and-rollback.md").read_text()
        self.assertIn("escalation_required", c.lower(),
                      "Planner should mention escalation_required=true")
        self.assertIn("stop", c.lower(),
                      "Planner should say stop on escalation")

    # ═══════════════════════════════════════════════════════════════
    # Report
    # ═══════════════════════════════════════════════════════════════

    @unittest.skip("V1: hidden module")
    def test_report_includes_attempt_count(self):
        self._run("fixloop", "open", "--route", "executor",
                  "--reason", "implementation bug")
        r = self._run_script("scripts/aiwf_export_report.py")
        rpt = (self.tmp / ".aiwf" / "records" / "闭合报告.md").read_text()
        self.assertIn("Attempt:", rpt)
        self.assertIn("1 /", rpt)

    @unittest.skip("V1: hidden module")
    def test_report_shows_escalation_when_required(self):
        s = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        s["workflow_level"] = "L0_direct"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(s, indent=2))
        self._run("fixloop", "open", "--route", "executor",
                  "--reason", "first")
        self._run("fixloop", "open", "--route", "executor",
                  "--reason", "exceeds L0 max=1")
        r = self._run_script("scripts/aiwf_export_report.py")
        rpt = (self.tmp / ".aiwf" / "records" / "闭合报告.md").read_text()
        self.assertIn("Escalation required", rpt)

    @unittest.skip("V1: hidden module")
    def test_closure_blocked_when_fixloop_open(self):
        self._run("fixloop", "open", "--route", "executor",
                  "--reason", "bug")
        r = self._run_script("scripts/aiwf_export_report.py")
        rpt = (self.tmp / ".aiwf" / "records" / "闭合报告.md").read_text()
        self.assertIn("BLOCKED", rpt)

    # ═══════════════════════════════════════════════════════════════
    # fixloop help
    # ═══════════════════════════════════════════════════════════════

    @unittest.skip("V1: hidden module")
    def test_fixloop_help_shows_status_subcommand(self):
        r = self._run("fixloop")
        self.assertIn("status", r.stdout.lower())

    # ═══════════════════════════════════════════════════════════════
    # compile checks
    # ═══════════════════════════════════════════════════════════════

    @unittest.skip("V1: hidden module")
    def test_compileall_passes(self):
        import py_compile
        py_compile.compile(str(PROJECT_ROOT / "aiwf_core" / "core" / "state_schema.py"), doraise=True)
        py_compile.compile(str(PROJECT_ROOT / "aiwf_core" / "core" / "state_ops.py"), doraise=True)
        py_compile.compile(str(PROJECT_ROOT / "aiwf_core" / "install_claude.py"), doraise=True)

    @unittest.skip("V1: hidden module")
    def test_scripts_py_compile_passes(self):
        import py_compile
        py_compile.compile(str(self.tmp / "scripts" / "aiwf_export_report.py"), doraise=True)


if __name__ == "__main__":
    unittest.main()
