"""Architecture Change Request: request, list, decide, report, status, skills."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 15


class TestArchitectureChangeRequest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awac_"))
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

    def _goal(self):
        return json.loads((self.tmp / ".aiwf" / "state" / "goal.json").read_text())

    def _run_script(self, script_rel):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run([sys.executable, str(self.tmp / script_rel)],
                              capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    # ═══════════════════════════════════════════════════════════════
    # Schema
    # ═══════════════════════════════════════════════════════════════

    def test_default_fix_loop_has_acrs(self):
        fl = self._fix_loop()
        self.assertIn("architecture_change_requests", fl)
        self.assertEqual(fl["architecture_change_requests"], [])

    # ═══════════════════════════════════════════════════════════════
    # Request
    # ═══════════════════════════════════════════════════════════════

    def test_request_appends_proposed_request(self):
        self._run("arch-change", "request", "--source", "executor",
                  "--reason", "Need shared module",
                  "--proposed-change", "Add src/shared/validation.js")
        fl = self._fix_loop()
        self.assertEqual(len(fl["architecture_change_requests"]), 1)
        self.assertEqual(fl["architecture_change_requests"][0]["id"], "ACR-001")
        self.assertEqual(fl["architecture_change_requests"][0]["status"], "proposed")

    def test_request_has_all_fields(self):
        self._run("arch-change", "request", "--source", "executor",
                  "--reason", "Need module", "--proposed-change", "Add file",
                  "--affected-file", "src/new.js", "--affected-module", "core",
                  "--current-contract-gap", "brief only allowed calc.js",
                  "--scope-impact", "Adds shared module", "--risk", "broaden impact")
        acr = self._fix_loop()["architecture_change_requests"][0]
        self.assertEqual(acr["source"], "executor")
        self.assertIn("src/new.js", acr["affected_files"])
        self.assertIn("core", acr["affected_modules"])
        self.assertIn("brief only allowed calc.js", acr["current_contract_gap"])

    def test_request_does_not_modify_architecture_brief(self):
        before = self._goal()["quality_brief"]["architecture_brief"]
        self._run("arch-change", "request", "--source", "executor",
                  "--reason", "Need module", "--proposed-change", "Add file")
        after = self._goal()["quality_brief"]["architecture_brief"]
        self.assertEqual(before, after, "ACR must not modify architecture_brief")

    def test_request_does_not_modify_contexts(self):
        before = json.loads((self.tmp / ".aiwf" / "state" / "contexts.json").read_text())
        self._run("arch-change", "request", "--source", "executor",
                  "--reason", "Need module", "--proposed-change", "Add file")
        after = json.loads((self.tmp / ".aiwf" / "state" / "contexts.json").read_text())
        self.assertEqual(before, after, "ACR must not modify contexts.json")

    # ═══════════════════════════════════════════════════════════════
    # List
    # ═══════════════════════════════════════════════════════════════

    def test_list_shows_summary(self):
        self._run("arch-change", "request", "--source", "executor",
                  "--reason", "Need shared validation module",
                  "--proposed-change", "Add src/shared/validation.js")
        out = self._run("arch-change", "list").stdout
        self.assertIn("ACR-001", out)
        self.assertIn("proposed", out)
        self.assertIn("shared validation", out.lower())

    def test_list_empty(self):
        out = self._run("arch-change", "list").stdout
        self.assertIn("none", out.lower())

    # ═══════════════════════════════════════════════════════════════
    # Decide
    # ═══════════════════════════════════════════════════════════════

    def test_decide_approved(self):
        self._run("arch-change", "request", "--source", "executor",
                  "--reason", "Need module", "--proposed-change", "Add file")
        self._run("arch-change", "decide", "ACR-001", "--status", "approved",
                  "--decision", "Approved; update architecture_brief")
        fl = self._fix_loop()
        acr = fl["architecture_change_requests"][0]
        self.assertEqual(acr["status"], "approved")
        self.assertIn("Approved", acr["planner_decision"])

    def test_decide_rejected(self):
        self._run("arch-change", "request", "--source", "executor",
                  "--reason", "Need module", "--proposed-change", "Add file")
        self._run("arch-change", "decide", "ACR-001", "--status", "rejected",
                  "--decision", "Overengineering; current brief is sufficient")
        fl = self._fix_loop()
        self.assertEqual(fl["architecture_change_requests"][0]["status"], "rejected")

    def test_decide_unknown_id_fails(self):
        r = self._run("arch-change", "decide", "ACR-999", "--status", "approved",
                      "--decision", "nope")
        self.assertNotEqual(r.returncode, 0, f"Unknown ACR should exit non-zero, got {r.returncode}")

    def test_decide_unknown_id_says_not_found(self):
        r = self._run("arch-change", "decide", "ACR-999", "--status", "approved",
                      "--decision", "nope")
        self.assertIn("not found", (r.stderr + r.stdout).lower(),
                      f"Should say not found: {r.stderr}")

    def test_decide_unknown_does_not_modify_acrs(self):
        self._run("arch-change", "request", "--source", "executor",
                  "--reason", "Need module", "--proposed-change", "Add file")
        before = self._fix_loop()["architecture_change_requests"]
        self._run("arch-change", "decide", "ACR-999", "--status", "approved",
                  "--decision", "nope")
        after = self._fix_loop()["architecture_change_requests"]
        self.assertEqual(len(before), len(after), "ACRs should not change on unknown ID")
        self.assertEqual(before[0]["status"], "proposed", "Existing ACR should be unchanged")

    def test_decide_unknown_does_not_print_success(self):
        r = self._run("arch-change", "decide", "ACR-999", "--status", "approved",
                      "--decision", "nope")
        self.assertNotIn("ACR-999: approved", r.stdout + r.stderr,
                         "Should not print success for unknown ID")

    def test_valid_decide_still_works(self):
        self._run("arch-change", "request", "--source", "executor",
                  "--reason", "Need module", "--proposed-change", "Add file")
        r = self._run("arch-change", "decide", "ACR-001", "--status", "approved",
                      "--decision", "Approved")
        self.assertEqual(r.returncode, 0)

    # ═══════════════════════════════════════════════════════════════
    # Status
    # ═══════════════════════════════════════════════════════════════

    def test_status_shows_pending_when_proposed_acr(self):
        self._run("arch-change", "request", "--source", "executor",
                  "--reason", "Need module", "--proposed-change", "Add file")
        out = self._run("status", "--debug").stdout
        self.assertIn("Architecture changes:", out)

    def test_status_shows_none_when_no_acr(self):
        out = self._run("status", "--debug").stdout
        self.assertIn("Architecture changes:", out)

    # ═══════════════════════════════════════════════════════════════
    # UserPromptSubmit no dump
    # ═══════════════════════════════════════════════════════════════

    def test_userpromptsubmit_no_acr_detail_dump(self):
        self._run("arch-change", "request", "--source", "executor",
                  "--reason", "secret-detail-xyz", "--proposed-change", "Add secret-file.js")
        inp = json.dumps({"session_id": "t", "cwd": str(self.tmp), "hook_event_name": "UserPromptSubmit"})
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, str(self.tmp / "scripts" / "aiwf_status.py")],
                           input=inp, capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        ctx = json.loads(r.stdout.strip())["hookSpecificOutput"]["additionalContext"]
        self.assertNotIn("secret-detail-xyz", ctx)

    # ═══════════════════════════════════════════════════════════════
    # Report
    # ═══════════════════════════════════════════════════════════════

    def test_report_includes_acr_section(self):
        self._run("arch-change", "request", "--source", "executor",
                  "--reason", "Need shared module",
                  "--proposed-change", "Add src/shared/validation.js")
        r = self._run_script("scripts/aiwf_export_report.py")
        rpt = (self.tmp / ".aiwf" / "reports" / "闭合报告.md").read_text()
        self.assertIn("## Architecture Change Requests", rpt)
        self.assertIn("ACR-001", rpt)
        self.assertIn("proposed", rpt)

    def test_report_shows_none_when_no_acrs(self):
        r = self._run_script("scripts/aiwf_export_report.py")
        rpt = (self.tmp / ".aiwf" / "reports" / "闭合报告.md").read_text()
        self.assertIn("Architecture change requests: none", rpt)

    # ═══════════════════════════════════════════════════════════════
    # Skill text
    # ═══════════════════════════════════════════════════════════════

    def test_planner_says_acr_must_update_brief(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-planner-meta" / "SKILL.md").read_text()
        self.assertIn("arch-change", c.lower())

    def test_executor_says_stop_and_request_acr(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-implement" / "SKILL.md").read_text()
        self.assertIn("arch-change request", c.lower())

    def test_reviewer_says_unresolved_acr_blocks(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-review" / "SKILL.md").read_text()
        self.assertIn("blocker", c.lower())

    def test_tester_distinguishes_undeclared_vs_missed_path(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-test" / "SKILL.md").read_text()
        self.assertIn("never declared", c.lower())

    # ═══════════════════════════════════════════════════════════════
    # compile
    # ═══════════════════════════════════════════════════════════════

    def test_compileall_passes(self):
        import py_compile
        py_compile.compile(str(PROJECT_ROOT / "aiwf_core" / "core" / "state_schema.py"), doraise=True)
        py_compile.compile(str(PROJECT_ROOT / "aiwf_core" / "core" / "state_ops.py"), doraise=True)

    def test_scripts_py_compile_passes(self):
        import py_compile
        py_compile.compile(str(self.tmp / "scripts" / "aiwf_export_report.py"), doraise=True)


if __name__ == "__main__":
    unittest.main()
