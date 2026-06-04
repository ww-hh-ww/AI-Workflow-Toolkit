"""Source trust, freshness, lifecycle guardrails: cleanup, report, skills, status."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 15


class TestSourceTrustFreshness(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awstf_"))
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
        for f in ["PROJECT-MAP.md", "ideas.md", "project-rules.md"]:
            p = self.tmp / ".aiwf" / f
            if p.exists(): p.unlink()

    def _run(self, *args):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run([sys.executable, "-m", "aiwf_core.cli"] + list(args),
                              capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    def _run_script(self, script_rel):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run([sys.executable, str(self.tmp / script_rel)],
                              capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    # ═══════════════════════════════════════════════════════════════
    # Freshness: ideas
    # ═══════════════════════════════════════════════════════════════

    def test_expired_idea_stale(self):
        self._run("idea", "capture", "--text", "stale idea", "--expires-days", "0")
        out = self._run("cleanup", "check").stdout
        self.assertIn("stale", out.lower())

    def test_too_many_ideas_warning(self):
        for i in range(25):
            self._run("idea", "capture", "--text", f"idea {i}", "--expires-days", "365")
        out = self._run("cleanup", "check").stdout
        self.assertIn("active ideas", out.lower())

    # ═══════════════════════════════════════════════════════════════
    # Freshness: PROJECT-MAP
    # ═══════════════════════════════════════════════════════════════

    def test_project_map_missing_sections(self):
        pm = self.tmp / ".aiwf" / "reports" / "项目地图.md"
        pm.write_text("# AIWF Project Map\n\n## Project Snapshot\n- OK\n\n## Active Direction\n- Unknown yet.\n")
        out = self._run("cleanup", "check").stdout
        self.assertIn("missing section", out.lower())

    def test_project_map_raw_ideas_pollution(self):
        pm = self.tmp / ".aiwf" / "reports" / "项目地图.md"
        pm.write_text("# AIWF Project Map\n\n## Project Snapshot\n- OK\n\n# AIWF Ideas\n### IDEA-2026 | raw\n- leaked\n")
        out = self._run("cleanup", "check").stdout
        self.assertIn("raw ideas", out.lower())

    # ═══════════════════════════════════════════════════════════════
    # Freshness: deferred risks
    # ═══════════════════════════════════════════════════════════════

    def test_deferred_risks_missing_from_project_map(self):
        rv = json.loads((self.tmp / ".aiwf" / "quality" / "review.json").read_text())
        rv["followups"] = ["Consider separate overflow policy task."]
        (self.tmp / ".aiwf" / "quality" / "review.json").write_text(json.dumps(rv, indent=2))
        self._run("project-map", "init")
        out = self._run("cleanup", "check").stdout
        self.assertIn("Deferred Risks still None yet", out)

    # ═══════════════════════════════════════════════════════════════
    # Freshness: rules count
    # ═══════════════════════════════════════════════════════════════

    def test_too_many_rules_warning(self):
        for i in range(35):
            self._run("rule", "add", "--text", f"rule {i}")
        out = self._run("cleanup", "check").stdout
        self.assertIn("active project rules", out.lower())

    # ═══════════════════════════════════════════════════════════════
    # Non-mutation
    # ═══════════════════════════════════════════════════════════════

    def test_cleanup_no_modify_ideas(self):
        self._run("idea", "capture", "--text", "test", "--expires-days", "0")
        before = (self.tmp / ".aiwf" / "reports" / "ideas.md").read_text()
        self._run("cleanup", "check")
        self.assertEqual(before, (self.tmp / ".aiwf" / "reports" / "ideas.md").read_text())

    def test_cleanup_no_modify_project_map(self):
        self._run("project-map", "init")
        before = (self.tmp / ".aiwf" / "reports" / "项目地图.md").read_text()
        self._run("cleanup", "check")
        self.assertEqual(before, (self.tmp / ".aiwf" / "reports" / "项目地图.md").read_text())

    def test_cleanup_no_modify_rules(self):
        self._run("rule", "add", "--text", "test rule")
        before = (self.tmp / ".aiwf" / "project-rules.md").read_text()
        self._run("cleanup", "check")
        self.assertEqual(before, (self.tmp / ".aiwf" / "project-rules.md").read_text())

    # ═══════════════════════════════════════════════════════════════
    # Report
    # ═══════════════════════════════════════════════════════════════

    def test_report_includes_source_trust_freshness(self):
        self._run("project-map", "init")
        self._run("idea", "capture", "--text", "stale", "--expires-days", "0")
        r = self._run_script("scripts/aiwf_export_report.py")
        rpt = (self.tmp / ".aiwf" / "reports" / "闭合报告.md").read_text()
        self.assertIn("source trust", rpt.lower())

    # ═══════════════════════════════════════════════════════════════
    # Status / UserPromptSubmit
    # ═══════════════════════════════════════════════════════════════

    def test_status_no_raw_dump(self):
        self._run("idea", "capture", "--text", "secret-raw-xyz", "--expires-days", "0")
        out = self._run("status").stdout
        self.assertNotIn("secret-raw-xyz", out)

    def test_userpromptsubmit_no_dump(self):
        self._run("idea", "capture", "--text", "secret-prompt-xyz", "--expires-days", "0")
        inp = json.dumps({"session_id": "t", "cwd": str(self.tmp), "hook_event_name": "UserPromptSubmit"})
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, str(self.tmp / "scripts" / "aiwf_status.py")],
                           input=inp, capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        ctx = json.loads(r.stdout.strip())["hookSpecificOutput"]["additionalContext"]
        self.assertNotIn("secret-prompt-xyz", ctx)

    # ═══════════════════════════════════════════════════════════════
    # Skills
    # ═══════════════════════════════════════════════════════════════

    def test_planner_source_trust_classification(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-planner" / "SKILL.md").read_text()
        self.assertIn("Source Trust Classification", c)

    def test_planner_raw_idea_low_trust(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-planner" / "SKILL.md").read_text()
        self.assertIn("raw ideas as roadmap", c.lower())

    def test_reviewer_staleness_check(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-review" / "SKILL.md").read_text()
        self.assertIn("Staleness Check", c)

    def test_reviewer_raw_ideas_not_requirements(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-review" / "SKILL.md").read_text()
        self.assertIn("raw ideas as requirements", c.lower())

    def test_close_freshness_mention(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-close" / "SKILL.md").read_text()
        self.assertIn("stale ideas", c.lower())

    # ═══════════════════════════════════════════════════════════════
    # compile
    # ═══════════════════════════════════════════════════════════════

    def test_compileall_passes(self):
        import py_compile
        py_compile.compile(str(PROJECT_ROOT / "aiwf_core" / "core" / "lifecycle_cleanup.py"), doraise=True)
        py_compile.compile(str(PROJECT_ROOT / "aiwf_core" / "install_claude.py"), doraise=True)

    def test_scripts_py_compile_passes(self):
        import py_compile
        py_compile.compile(str(self.tmp / "scripts" / "aiwf_export_report.py"), doraise=True)


if __name__ == "__main__":
    unittest.main()
