"""Closure report basis: Quality Policy/Brief, Git Summary (untracked+governance),
Evidence separation, Closure Gate blocked/allowed, no raw JSON, no side effects."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 20


class TestClosureReportBasis(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awcr_"))
        # Git repo + initial commit
        subprocess.run(["git", "init", "-b", "main"], cwd=str(cls.tmp),
                       capture_output=True, timeout=10)
        subprocess.run(["git", "config", "user.email", "a@b.c"],
                       cwd=str(cls.tmp), capture_output=True, timeout=10)
        subprocess.run(["git", "config", "user.name", "t"],
                       cwd=str(cls.tmp), capture_output=True, timeout=10)
        (cls.tmp / "README.md").write_text("# Test\n")
        subprocess.run(["git", "add", "README.md"], cwd=str(cls.tmp),
                       capture_output=True, timeout=10)
        subprocess.run(["git", "commit", "-m", "init"], cwd=str(cls.tmp),
                       capture_output=True, timeout=10)

        # Install via Python subprocess (not interactive Bash)
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        subprocess.run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                       capture_output=True, text=True, cwd=str(cls.tmp), env=env, timeout=30)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        from aiwf_core.core.state_schema import MVP_STATE_FILES
        (self.tmp / ".aiwf").mkdir(parents=True, exist_ok=True)
        for fn, dfn in MVP_STATE_FILES.items():
            p = self.tmp / ".aiwf" / fn; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(dfn(), indent=2) + "\n")

    def _run(self, *args):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run([sys.executable, "-m", "aiwf_core.cli"] + list(args),
                              capture_output=True, text=True,
                              cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    def _run_script(self, script_rel):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run([sys.executable, str(self.tmp / script_rel)],
                              capture_output=True, text=True,
                              cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    def _report(self):
        r = self._run_script("scripts/aiwf_export_report.py")
        self.assertEqual(r.returncode, 0, f"export_report failed: {r.stderr}")
        return (self.tmp / ".aiwf" / "reports" / "闭合报告.md").read_text()

    def _seed_quality(self):
        self._run("state", "record-quality-policy", "--task-type", "small_function",
                  "--workflow-level", "L1_review_light", "--reason", "test")
        self._run("state", "record-quality-brief", "--acceptance", "must work",
                  "--test-focus", "normal subtraction", "--review-focus", "no regression")

    def _seed_full_accept(self):
        """Set all gate fields to accepted/passing values."""
        (self.tmp / ".aiwf" / "evidence" / "records.json").write_text(json.dumps({
            "records": [{
                "id": "EV-001", "status": "accepted", "trust": "machine_observed",
                "changed_files": ["src/calc.js"],
                "governance_changed_files": [".aiwf/state/state.json", ".aiwf/reports/闭合报告.md"]
            }]
        }, indent=2))
        (self.tmp / ".aiwf" / "quality" / "testing.json").write_text(json.dumps(
            {"status": "adequate", "commands": ["pytest"], "untested_risks": []}, indent=2))
        (self.tmp / ".aiwf" / "quality" / "review.json").write_text(json.dumps({
            "result": "accepted", "closure_allowed": True, "cleanup_status": "fresh",
            "structure_status": "accepted", "stale_items": [], "cleanup_blockers": [],
            "blockers": [], "accepted_evidence_ids": ["EV-001"], "rejected_evidence_ids": []
        }, indent=2))
        s = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        s["close_attempt"] = True
        s["phase"] = "closing"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(s, indent=2))

    # ═══════════════════════════════════════════════════════════════
    # Sections present
    # ═══════════════════════════════════════════════════════════════

    def test_report_has_quality_policy_section(self):
        self._seed_quality()
        r = self._report()
        self.assertIn("## Quality Policy", r)
        self.assertIn("L1_review_light", r)
        self.assertIn("small_function", r)
        self.assertIn("targeted_plus_small_regression", r)
        self.assertIn("reviewer_light", r)

    def test_report_has_quality_brief_section(self):
        self._seed_quality()
        r = self._report()
        self.assertIn("## Quality Brief", r)
        self.assertIn("must work", r)
        self.assertIn("normal subtraction", r)

    def test_report_has_git_summary_section(self):
        r = self._report()
        self.assertIn("## Git Summary", r)

    def test_report_has_task_history_trend_section(self):
        (self.tmp / ".aiwf" / "history" / "task-history.json").write_text(json.dumps({
            "tasks": [
                {"id": "t1", "fix_loop_attempt_count": 1, "untested_risk_count": 0,
                 "changed_files": ["src/calc.js"]},
                {"id": "t2", "fix_loop_attempt_count": 2, "untested_risk_count": 1,
                 "changed_files": ["src/calc.js", "src/parser.js"]},
            ]
        }, indent=2))
        r = self._report()
        self.assertIn("## Task History Trend", r)
        self.assertIn("Closed tasks recorded: 2", r)
        self.assertIn("Recent fix-loop attempts: 3", r)
        self.assertIn("src/calc.js", r)

    # ═══════════════════════════════════════════════════════════════
    # Git Summary: untracked + governance listing
    # ═══════════════════════════════════════════════════════════════

    def test_git_summary_includes_untracked_file(self):
        (self.tmp / "src").mkdir(exist_ok=True)
        (self.tmp / "src" / "untracked.js").write_text("// untracked\n")
        r = self._report()
        self.assertIn("src/untracked.js", r,
                      "Untracked file must appear in Git Summary")

    def test_git_summary_lists_governance_files(self):
        r = self._report()
        self.assertIn("Governance/support changes:", r,
                      "Must list governance files separately")
        self.assertIn(".aiwf", r,
                      "AIWF governance files must appear in governance list")

    # ═══════════════════════════════════════════════════════════════
    # Evidence separation
    # ═══════════════════════════════════════════════════════════════

    def test_evidence_separates_project_and_governance(self):
        self._seed_full_accept()
        r = self._report()
        self.assertIn("Changed project files:", r)
        self.assertIn("Changed governance/support files:", r)
        self.assertIn("src/calc.js", r)
        self.assertIn(".aiwf/state/state.json", r)
        self.assertIn(".aiwf/reports/闭合报告.md", r)

    # ═══════════════════════════════════════════════════════════════
    # No raw JSON dump
    # ═══════════════════════════════════════════════════════════════

    def test_report_no_raw_json_dump(self):
        self._seed_quality()
        r = self._report()
        self.assertNotIn('"records"', r)
        self.assertNotIn('"state"', r)
        # But summary lines like "Raw records: N" are fine
        self.assertIn("Raw records:", r)

    # ═══════════════════════════════════════════════════════════════
    # Closure Gate blocked / allowed
    # ═══════════════════════════════════════════════════════════════

    def test_closure_gate_blocked_when_missing(self):
        r = self._report()
        self.assertIn("## Closure Gate", r)
        self.assertIn("BLOCKED", r)
        self.assertIn("Blockers:", r)

    def test_closure_gate_allowed_when_all_satisfied(self):
        self._seed_full_accept()
        r = self._report()
        self.assertIn("## Closure Gate", r)
        self.assertIn("ALLOWED", r)

    # ═══════════════════════════════════════════════════════════════
    # Skill text
    # ═══════════════════════════════════════════════════════════════

    def test_close_skill_mentions_export_report(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-close" / "SKILL.md").read_text()
        self.assertIn("export_report", c.lower(),
                      "Close skill should mention export_report script")

    def test_close_skill_no_duplicate_auto_commit(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-close" / "SKILL.md").read_text()
        count = c.lower().count("auto-commit")
        self.assertLessEqual(count, 2,
                            f"auto-commit appears {count} times; should be ≤ 2")

    # ═══════════════════════════════════════════════════════════════
    # No side effects
    # ═══════════════════════════════════════════════════════════════

    def test_report_no_modify_claude_md(self):
        before = (self.tmp / "CLAUDE.md").read_text()
        self._report()
        after = (self.tmp / "CLAUDE.md").read_text()
        self.assertEqual(before, after)

    def test_report_no_modify_settings_json(self):
        before = (self.tmp / ".claude" / "settings.json").read_text()
        self._report()
        after = (self.tmp / ".claude" / "settings.json").read_text()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
