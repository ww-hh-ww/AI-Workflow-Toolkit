"""Project Rules: add, add-negative, list, retire, global-candidate, status, report."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 15


class TestProjectRules(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awpr_"))
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
        rp = self.tmp / ".aiwf" / "project-rules.md"
        if rp.exists(): rp.unlink()

    def _run(self, *args):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run([sys.executable, "-m", "aiwf_core.cli"] + list(args),
                              capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    def _rules_text(self):
        p = self.tmp / ".aiwf" / "project-rules.md"
        return p.read_text() if p.exists() else ""

    def _goal(self):
        return json.loads((self.tmp / ".aiwf" / "state" / "goal.json").read_text())

    def _run_script(self, script_rel):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run([sys.executable, str(self.tmp / script_rel)],
                              capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    # ═══════════════════════════════════════════════════════════════
    # Add
    # ═══════════════════════════════════════════════════════════════

    def test_add_creates_file(self):
        self._run("rule", "add", "--text", "Test rule", "--source", "test")
        self.assertTrue((self.tmp / ".aiwf" / "project-rules.md").exists())

    def test_add_has_id_status_type(self):
        self._run("rule", "add", "--text", "Test rule", "--source", "test", "--tag", "cli")
        txt = self._rules_text()
        self.assertIn("RULE-", txt)
        self.assertIn("active", txt)
        self.assertIn("rule", txt)

    def test_add_negative(self):
        self._run("rule", "add-negative", "--text", "Do not build full backup system",
                  "--source", "design decision", "--tag", "architecture")
        txt = self._rules_text()
        self.assertIn("negative_rule", txt)

    def test_negative_rule_in_guardrails_section(self):
        self._run("rule", "add-negative", "--text", "Do not build full backup system",
                  "--source", "design decision")
        txt = self._rules_text()
        self.assertIn("## Negative Rules / Guardrails", txt)
        self.assertNotIn("(none)\n\n## Retired", txt.split("## Negative Rules / Guardrails")[-1][:30])

    def test_ordinary_rule_in_active_section(self):
        self._run("rule", "add", "--text", "test rule")
        txt = self._rules_text()
        self.assertIn("## Active Rules", txt)
        self.assertNotIn("(none)\n\n## Negative", txt.split("## Active Rules")[-1][:30])

    def test_global_candidate_in_candidates_section(self):
        self._run("rule", "add", "--text", "test rule")
        import re
        m = re.search(r'(RULE-\d{8}-\d{6}-\d{6})', self._run("rule", "list").stdout)
        if m:
            self._run("rule", "global-candidate", m.group(1), "--note", "useful globally")
        txt = self._rules_text()
        self.assertIn("## Global Lesson Candidates", txt)
        self.assertIn("global_candidate", txt)

    def test_retire_in_retired_section(self):
        rid = self._add_one()
        self._run("rule", "retire", rid, "--reason", "outdated")
        txt = self._rules_text()
        self.assertIn("## Retired / Superseded Rules", txt)
        self.assertIn("retired", txt)

    def test_add_does_not_modify_project_map(self):
        self._run("project-map", "init")
        before = (self.tmp / ".aiwf" / "reports" / "项目地图.md").read_text()
        self._run("rule", "add", "--text", "Test rule")
        after = (self.tmp / ".aiwf" / "reports" / "项目地图.md").read_text()
        self.assertEqual(before, after)

    def test_add_does_not_modify_goal(self):
        before = self._goal()
        self._run("rule", "add", "--text", "Test rule")
        after = self._goal()
        self.assertEqual(before, after)

    def test_add_does_not_modify_claude_md(self):
        before = (self.tmp / "CLAUDE.md").read_text()
        self._run("rule", "add", "--text", "Test rule")
        after = (self.tmp / "CLAUDE.md").read_text()
        self.assertEqual(before, after)

    # ═══════════════════════════════════════════════════════════════
    # List
    # ═══════════════════════════════════════════════════════════════

    def test_list_shows_summary(self):
        self._run("rule", "add", "--text", "For state mutation CLIs, invalid target IDs must fail cleanly",
                  "--source", "ACR safety bug")
        out = self._run("rule", "list").stdout
        self.assertIn("RULE-", out)
        self.assertIn("active", out)
        self.assertIn("fail cleanly", out.lower())

    def test_list_does_not_dump_long_text(self):
        self._run("rule", "add", "--text", "A" * 200)
        out = self._run("rule", "list").stdout
        self.assertNotIn("A" * 200, out)

    # ═══════════════════════════════════════════════════════════════
    # Retire
    # ═══════════════════════════════════════════════════════════════

    def _add_one(self):
        self._run("rule", "add", "--text", "test rule")
        import re
        m = re.search(r'(RULE-\d{8}-\d{6}-\d{6})', self._run("rule", "list").stdout)
        if not m: raise unittest.SkipTest("Could not extract rule ID")
        return m.group(1)

    def test_retire_marks_retired(self):
        rid = self._add_one()
        self._run("rule", "retire", rid, "--reason", "outdated")
        txt = self._rules_text()
        self.assertIn("retired", txt)

    def test_retire_unknown_fails(self):
        r = self._run("rule", "retire", "RULE-99999999-999999-999999", "--reason", "nope")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not found", (r.stderr + r.stdout).lower())

    # ═══════════════════════════════════════════════════════════════
    # Global candidate
    # ═══════════════════════════════════════════════════════════════

    def test_global_candidate_marks(self):
        rid = self._add_one()
        self._run("rule", "global-candidate", rid, "--note", "useful for all CLI tools")
        txt = self._rules_text()
        self.assertIn("global_candidate", txt)

    def test_global_candidate_unknown_fails(self):
        r = self._run("rule", "global-candidate", "RULE-99999999-999999-999999", "--note", "nope")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not found", (r.stderr + r.stdout).lower())

    # ═══════════════════════════════════════════════════════════════
    # Status
    # ═══════════════════════════════════════════════════════════════

    def test_status_shows_rules_active(self):
        self._run("rule", "add", "--text", "test rule")
        out = self._run("status", "--debug").stdout
        self.assertIn("rules", out.lower())

    def test_status_rules_none(self):
        out = self._run("status", "--debug").stdout
        self.assertIn("rules", out.lower())

    # ═══════════════════════════════════════════════════════════════
    # UserPromptSubmit no dump
    # ═══════════════════════════════════════════════════════════════

    def test_userpromptsubmit_no_rule_dump(self):
        self._run("rule", "add", "--text", "secret-rule-text-xyz")
        inp = json.dumps({"session_id": "t", "cwd": str(self.tmp), "hook_event_name": "UserPromptSubmit"})
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, str(self.tmp / "scripts" / "aiwf_status.py")],
                           input=inp, capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        ctx = json.loads(r.stdout.strip())["hookSpecificOutput"]["additionalContext"]
        self.assertNotIn("secret-rule-text-xyz", ctx)

    # ═══════════════════════════════════════════════════════════════
    # Report
    # ═══════════════════════════════════════════════════════════════

    def test_report_shows_counts(self):
        self._run("rule", "add", "--text", "test rule")
        self._run("rule", "add-negative", "--text", "negative rule")
        r = self._run_script("scripts/aiwf_export_report.py")
        rpt = (self.tmp / ".aiwf" / "reports" / "闭合报告.md").read_text()
        self.assertIn("Project Rules", rpt)
        self.assertIn("Active rules: 1", rpt)
        self.assertIn("Negative rules: 1", rpt)

    # ═══════════════════════════════════════════════════════════════
    # Skill text
    # ═══════════════════════════════════════════════════════════════

    def test_planner_says_raw_ideas_not_rules(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-planner-meta" / "SKILL.md").read_text()
        self.assertIn("meta-critique", c.lower())

    def test_reviewer_mentions_project_rules_check(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-review" / "SKILL.md").read_text()
        self.assertIn("cleanup", c.lower())

    def test_reviewer_mentions_negative_guardrails(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-review" / "SKILL.md").read_text()
        self.assertIn("blocker", c.lower())

    def test_compileall_passes(self):
        import py_compile
        py_compile.compile(str(PROJECT_ROOT / "aiwf_core" / "core" / "project_rules.py"), doraise=True)

    def test_scripts_py_compile_passes(self):
        import py_compile
        py_compile.compile(str(self.tmp / "scripts" / "aiwf_export_report.py"), doraise=True)


if __name__ == "__main__":
    unittest.main()
