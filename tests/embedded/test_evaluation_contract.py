"""Evaluation contract: schema, CLI, skill text, report, no raw dump."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 15

class TestEvaluationContract(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awec_"))
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

    # ── schema ──
    def test_default_quality_brief_has_evaluation_contract(self):
        g = self._goal()
        ec = g["quality_brief"]["evaluation_contract"]
        for field in ["user_visible_outcome", "acceptance_criteria", "non_goals",
                       "test_obligations", "review_obligations", "known_risks", "closure_question"]:
            self.assertIn(field, ec, f"Missing: {field}")

    # ── CLI write ──
    def test_cli_writes_user_visible_outcome(self):
        self._run("state", "record-quality-brief", "--user-visible-outcome", "divide works")
        ec = self._goal()["quality_brief"]["evaluation_contract"]
        self.assertEqual(ec["user_visible_outcome"], "divide works")

    def test_cli_writes_acceptance_criteria(self):
        self._run("state", "record-quality-brief", "--acceptance-criterion", "divide(6,2)=3", "--acceptance-criterion", "divide by 0 throws")
        ec = self._goal()["quality_brief"]["evaluation_contract"]
        self.assertEqual(len(ec["acceptance_criteria"]), 2)

    def test_cli_writes_test_obligations(self):
        self._run("state", "record-quality-brief", "--test-obligation", "cover +0/-0")
        ec = self._goal()["quality_brief"]["evaluation_contract"]
        self.assertIn("cover +0/-0", ec["test_obligations"])

    def test_cli_writes_review_obligations(self):
        self._run("state", "record-quality-brief", "--review-obligation", "check consistency")
        ec = self._goal()["quality_brief"]["evaluation_contract"]
        self.assertIn("check consistency", ec["review_obligations"])

    def test_cli_writes_closure_question(self):
        self._run("state", "record-quality-brief", "--closure-question", "Does it satisfy?")
        ec = self._goal()["quality_brief"]["evaluation_contract"]
        self.assertEqual(ec["closure_question"], "Does it satisfy?")

    # ── report ──
    def test_report_includes_evaluation_contract(self):
        self._run("state", "record-quality-brief", "--user-visible-outcome", "divide works", "--acceptance-criterion", "AC1")
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        subprocess.run([sys.executable, str(self.tmp / "scripts" / "aiwf_export_report.py")],
                       capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        rpt = (self.tmp / ".aiwf" / "reports" / "闭合报告.md").read_text()
        self.assertIn("Evaluation Contract", rpt)
        self.assertIn("divide works", rpt)

    def test_report_shows_missing_when_no_contract(self):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        subprocess.run([sys.executable, str(self.tmp / "scripts" / "aiwf_export_report.py")],
                       capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        rpt = (self.tmp / ".aiwf" / "reports" / "闭合报告.md").read_text()
        self.assertIn("missing", rpt.lower())

    # ── CLI: non_goals and known_risks ──
    def test_cli_writes_non_goals_to_evaluation_contract(self):
        self._run("state", "record-quality-brief", "--non-goal", "Do not redesign overflow")
        ec = self._goal()["quality_brief"]["evaluation_contract"]
        self.assertIn("Do not redesign overflow", ec["non_goals"])

    def test_cli_writes_known_risks_to_evaluation_contract(self):
        self._run("state", "record-quality-brief", "--known-risk", "Shared validation can broaden scope")
        ec = self._goal()["quality_brief"]["evaluation_contract"]
        self.assertIn("Shared validation can broaden scope", ec["known_risks"])

    # ── report: non_goals, known_risks, closure_question ──
    def test_report_includes_non_goals(self):
        self._run("state", "record-quality-brief",
                  "--user-visible-outcome", "divide works",
                  "--non-goal", "Do not redesign overflow policy")
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        subprocess.run([sys.executable, str(self.tmp / "scripts" / "aiwf_export_report.py")],
                       capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        rpt = (self.tmp / ".aiwf" / "reports" / "闭合报告.md").read_text()
        self.assertIn("Non-goals:", rpt)
        self.assertIn("Do not redesign overflow policy", rpt)

    def test_report_includes_known_risks(self):
        self._run("state", "record-quality-brief",
                  "--user-visible-outcome", "divide works",
                  "--known-risk", "Shared validation changes can broaden scope")
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        subprocess.run([sys.executable, str(self.tmp / "scripts" / "aiwf_export_report.py")],
                       capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        rpt = (self.tmp / ".aiwf" / "reports" / "闭合报告.md").read_text()
        self.assertIn("Known risks:", rpt)
        self.assertIn("Shared validation changes can broaden scope", rpt)

    def test_report_includes_closure_question(self):
        self._run("state", "record-quality-brief",
                  "--user-visible-outcome", "divide works",
                  "--closure-question", "Does divide satisfy requested behavior?")
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        subprocess.run([sys.executable, str(self.tmp / "scripts" / "aiwf_export_report.py")],
                       capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        rpt = (self.tmp / ".aiwf" / "reports" / "闭合报告.md").read_text()
        self.assertIn("Closure question:", rpt)
        self.assertIn("Does divide satisfy requested behavior?", rpt)

    # ── status no dump ──
    def test_status_does_not_dump_full_evaluation_contract(self):
        self._run("state", "record-quality-brief",
                  "--user-visible-outcome", "secret-outcome-xyz",
                  "--acceptance-criterion", "secret-ac-xyz")
        out = self._run("status").stdout
        self.assertNotIn("secret-outcome-xyz", out,
                         "aiwf status must not dump full evaluation contract")
        self.assertNotIn("secret-ac-xyz", out,
                         "aiwf status must not dump acceptance criteria")

    # ── report: structured lessons dict ──
    def test_report_handles_structured_lessons_dict(self):
        # Write structured dict lessons to review.json
        rv = json.loads((self.tmp / ".aiwf" / "quality" / "review.json").read_text())
        rv["lessons"] = [
            {"lesson": "Division tasks must test +0 and -0.", "applies_to": ["numeric_semantics"], "affects": ["test_focus"], "source": "previous blocker", "status": "active"}
        ]
        (self.tmp / ".aiwf" / "quality" / "review.json").write_text(json.dumps(rv, indent=2))
        # Must not crash
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, str(self.tmp / "scripts" / "aiwf_export_report.py")],
                           capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        self.assertEqual(r.returncode, 0, f"export_report crashed on dict lessons: {r.stderr}")
        rpt = (self.tmp / ".aiwf" / "reports" / "闭合报告.md").read_text()
        self.assertIn("Division tasks must test +0 and -0", rpt)
        self.assertIn("applies_to: numeric_semantics", rpt)
        self.assertIn("affects: test_focus", rpt)

    def test_report_does_not_dump_raw_lesson_dict_json(self):
        rv = json.loads((self.tmp / ".aiwf" / "quality" / "review.json").read_text())
        rv["lessons"] = [
            {"lesson": "Test lesson", "applies_to": ["x"], "affects": ["test_focus"], "source": "src", "status": "active"}
        ]
        (self.tmp / ".aiwf" / "quality" / "review.json").write_text(json.dumps(rv, indent=2))
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        subprocess.run([sys.executable, str(self.tmp / "scripts" / "aiwf_export_report.py")],
                       capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        rpt = (self.tmp / ".aiwf" / "reports" / "闭合报告.md").read_text()
        self.assertNotIn('"lesson"', rpt, "Report must not dump raw lesson dict JSON")
        self.assertNotIn('"applies_to"', rpt, "Report must not dump raw dict JSON keys")
        self.assertNotIn('"source"', rpt)

    def test_report_handles_string_and_dict_lessons(self):
        rv = json.loads((self.tmp / ".aiwf" / "quality" / "review.json").read_text())
        rv["lessons"] = [
            "Simple string lesson",
            {"lesson": "Dict lesson with applies_to", "applies_to": ["refactor"]}
        ]
        (self.tmp / ".aiwf" / "quality" / "review.json").write_text(json.dumps(rv, indent=2))
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, str(self.tmp / "scripts" / "aiwf_export_report.py")],
                           capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        self.assertEqual(r.returncode, 0, f"Should handle mixed string+dict lessons: {r.stderr}")

    # ── report: negative_patterns / followups dict compat ──
    def test_report_handles_dict_negative_patterns(self):
        rv = json.loads((self.tmp / ".aiwf" / "quality" / "review.json").read_text())
        rv["negative_patterns"] = [{"pattern": "Do not silently redesign shared validation."}]
        (self.tmp / ".aiwf" / "quality" / "review.json").write_text(json.dumps(rv, indent=2))
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, str(self.tmp / "scripts" / "aiwf_export_report.py")],
                           capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        self.assertEqual(r.returncode, 0, f"export_report crashed on dict negative_patterns: {r.stderr}")

    def test_report_handles_dict_followups(self):
        rv = json.loads((self.tmp / ".aiwf" / "quality" / "review.json").read_text())
        rv["followups"] = [{"followup": "Consider separate overflow policy task."}]
        (self.tmp / ".aiwf" / "quality" / "review.json").write_text(json.dumps(rv, indent=2))
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, str(self.tmp / "scripts" / "aiwf_export_report.py")],
                           capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        self.assertEqual(r.returncode, 0, f"export_report crashed on dict followups: {r.stderr}")

    # ── Evaluation Coverage section ──
    def test_report_includes_evaluation_coverage_section(self):
        self._run("state", "record-quality-brief",
                  "--user-visible-outcome", "divide works",
                  "--acceptance-criterion", "AC1")
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        subprocess.run([sys.executable, str(self.tmp / "scripts" / "aiwf_export_report.py")],
                       capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        rpt = (self.tmp / ".aiwf" / "reports" / "闭合报告.md").read_text()
        self.assertIn("Evaluation Coverage", rpt)
        self.assertIn("Acceptance coverage", rpt)
        self.assertIn("System coverage", rpt)
        self.assertIn("Known risks handled/deferred", rpt)

    # ── skills ──
    def test_planner_mentions_acceptance_criteria(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-planner" / "SKILL.md").read_text()
        self.assertIn("acceptance criteria", c.lower())

    def test_planner_says_ec_not_raw_discussion(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-planner" / "SKILL.md").read_text()
        self.assertIn("not raw discussion", c.lower(),
                       "Planner skill should say Evaluation Contract is not raw discussion")

    def test_tester_mentions_acceptance_coverage(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-test" / "SKILL.md").read_text()
        self.assertTrue("acceptance coverage" in c.lower() or "Acceptance Coverage" in c,
                        "Tester should mention acceptance coverage")

    def test_tester_says_criteria_must_be_mapped_to_coverage(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-test" / "SKILL.md").read_text()
        self.assertIn("map acceptance criteria", c.lower().replace("  ", " "),
                       "Tester should say acceptance criteria must be mapped to coverage")

    def test_reviewer_mentions_contract_insufficient(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-review" / "SKILL.md").read_text()
        self.assertIn("contract", c.lower())

    def test_reviewer_says_insufficient_ec_can_be_blocker(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-review" / "SKILL.md").read_text()
        self.assertIn("insufficient", c.lower(),
                       "Reviewer should say insufficient Evaluation Contract can be blocker")
        self.assertIn("blocker", c.lower(),
                       "Reviewer should mention blocker for insufficient contract")


if __name__ == "__main__":
    unittest.main()
