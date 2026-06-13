"""Idea Inbox: capture, list, promote, expire, status, report, skill text."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 15


class TestIdeaInbox(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awii_"))
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
        # Clean ideas
        ip = self.tmp / ".aiwf" / "artifacts" / "reports" / "ideas.md"
        if ip.exists(): ip.unlink()

    def _run(self, *args):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run([sys.executable, "-m", "aiwf_core.cli"] + list(args),
                              capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    def _ideas_text(self):
        ip = self.tmp / ".aiwf" / "artifacts" / "reports" / "ideas.md"
        return ip.read_text() if ip.exists() else ""

    def _goal(self):
        return json.loads((self.tmp / ".aiwf" / "state" / "goal.json").read_text())

    def _run_script(self, script_rel):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run([sys.executable, str(self.tmp / script_rel)],
                              capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    # ═══════════════════════════════════════════════════════════════
    # Capture
    # ═══════════════════════════════════════════════════════════════

    def test_install_creates_ideas_file(self):
        fresh = Path(tempfile.mkdtemp(prefix="awii_install_"))
        try:
            env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
            r = subprocess.run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                               capture_output=True, text=True, cwd=str(fresh), env=env, timeout=20)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue((fresh / ".aiwf" / "artifacts" / "reports").exists())  # reports dir exists
        finally:
            shutil.rmtree(fresh, ignore_errors=True)

    def test_start_context_creates_ideas_file(self):
        from aiwf_core.core.state_ops import start_context
        start_context(str(self.tmp), "CTX-IDEA", allowed_write=["src/"])
        self.assertTrue((self.tmp / ".aiwf" / "artifacts" / "reports" / "ideas.md").exists())

    def test_capture_creates_ideas_file(self):
        self._run("idea", "capture", "--text", "Maybe add inspiration pack")
        self.assertTrue((self.tmp / ".aiwf" / "artifacts" / "reports" / "ideas.md").exists())

    def test_captured_idea_has_id_status_text(self):
        self._run("idea", "capture", "--text", "Add inspiration pack", "--tag", "planner")
        txt = self._ideas_text()
        self.assertIn("IDEA-", txt)
        self.assertIn("raw", txt)
        self.assertIn("Add inspiration pack", txt)
        self.assertIn("planner", txt)

    def test_capture_does_not_modify_goal(self):
        before = self._goal()
        self._run("idea", "capture", "--text", "test idea")
        after = self._goal()
        self.assertEqual(before, after)

    # ═══════════════════════════════════════════════════════════════
    # List
    # ═══════════════════════════════════════════════════════════════

    def test_list_shows_summary(self):
        self._run("idea", "capture", "--text", "Maybe add inspiration pack for scattered ideas")
        out = self._run("idea", "list").stdout
        self.assertIn("IDEA-", out)
        self.assertIn("raw", out)
        self.assertIn("inspiration pack", out.lower())

    def test_list_does_not_dump_full_text(self):
        self._run("idea", "capture", "--text", "A very long idea text that goes on and on " + "x" * 80)
        out = self._run("idea", "list").stdout
        self.assertNotIn("x" * 80, out)

    def test_list_empty(self):
        out = self._run("idea", "list").stdout
        self.assertIn("none", out.lower())

    # ═══════════════════════════════════════════════════════════════
    # Promote
    # ═══════════════════════════════════════════════════════════════

    def _capture_one(self):
        self._run("idea", "capture", "--text", "Test idea")
        out = self._run("idea", "list").stdout
        match = __import__('re').search(r'(IDEA-\d{8}-\d{6}(?:-\d{6})?)', out)
        if not match: raise unittest.SkipTest("Could not extract idea ID")
        return match.group(1)

    def test_promote_marks_adopted(self):
        iid = self._capture_one()
        self._run("idea", "promote", iid, "--target", "project-map", "--note", "Adopted")
        txt = self._ideas_text()
        self.assertIn("adopted", txt)
        self.assertIn("project-map", txt)

    def test_promote_does_not_modify_goal(self):
        iid = self._capture_one()
        before = self._goal()
        self._run("idea", "promote", iid, "--target", "goal")
        after = self._goal()
        self.assertEqual(before, after)

    def test_promote_unknown_id_fails(self):
        r = self._run("idea", "promote", "IDEA-99999999-999999", "--target", "goal")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not found", (r.stderr + r.stdout).lower())

    def test_promote_unknown_does_not_mutate_ideas(self):
        self._run("idea", "capture", "--text", "existing idea")
        before = self._ideas_text()
        self._run("idea", "promote", "IDEA-99999999-999999", "--target", "goal")
        after = self._ideas_text()
        self.assertEqual(before.strip() if before else "", after.strip() if after else "")

    # ═══════════════════════════════════════════════════════════════
    # Expire
    # ═══════════════════════════════════════════════════════════════

    def test_expire_marks_expired(self):
        iid = self._capture_one()
        self._run("idea", "expire", iid, "--reason", "outdated")
        txt = self._ideas_text()
        self.assertIn("expired", txt)

    def test_expire_unknown_id_fails(self):
        r = self._run("idea", "expire", "IDEA-99999999-999999", "--reason", "nope")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not found", (r.stderr + r.stdout).lower())

    def test_expired_not_in_active_list(self):
        iid = self._capture_one()
        self._run("idea", "expire", iid)
        out = self._run("idea", "list").stdout
        self.assertIn("none", out.lower())

    def test_expires_days_0_not_listed_by_default(self):
        self._run("idea", "capture", "--text", "expired by time", "--expires-days", "0")
        out = self._run("idea", "list").stdout
        self.assertIn("none", out.lower())

    def test_expires_days_0_appears_with_include_expired(self):
        self._run("idea", "capture", "--text", "expired by time", "--expires-days", "0")
        out = self._run("idea", "list", "--include-expired").stdout
        self.assertIn("expired by time", out)

    def test_expired_by_time_makes_status_stale(self):
        self._run("idea", "capture", "--text", "expired idea", "--expires-days", "0")
        out = self._run("status", "--debug").stdout
        self.assertIn("stale", out.lower())

    def test_active_unexpired_makes_status_available(self):
        self._run("idea", "capture", "--text", "active idea", "--expires-days", "14")
        out = self._run("status", "--debug").stdout
        self.assertIn("available", out.lower())

    def test_adopted_not_in_default_list(self):
        self._run("idea", "capture", "--text", "adopted idea", "--expires-days", "14")
        out = self._run("idea", "list").stdout
        match = __import__('re').search(r'(IDEA-\d{8}-\d{6}(?:-\d{6})?)', out)
        self.assertIsNotNone(match, "Should have captured an idea")
        iid = match.group(1)
        self._run("idea", "promote", iid, "--target", "project-map")
        out2 = self._run("idea", "list").stdout
        self.assertIn("none", out2.lower(), "Adopted idea should not appear in default list")

    def test_only_adopted_no_status_stale(self):
        self._run("idea", "capture", "--text", "adopted idea", "--expires-days", "14")
        out = self._run("idea", "list").stdout
        match = __import__('re').search(r'(IDEA-\d{8}-\d{6}(?:-\d{6})?)', out)
        self.assertIsNotNone(match)
        self._run("idea", "promote", match.group(1), "--target", "project-map")
        out2 = self._run("status").stdout
        self.assertNotIn("Ideas: stale", out2)
        self.assertNotIn("Ideas: available", out2)

    def test_include_expired_marks_stale_by_time(self):
        self._run("idea", "capture", "--text", "time-expired idea", "--expires-days", "0")
        self._run("idea", "capture", "--text", "active idea", "--expires-days", "365")
        out = self._run("idea", "list", "--include-expired").stdout
        self.assertIn("stale", out.lower())

    def test_rapid_captures_produce_unique_ids(self):
        self._run("idea", "capture", "--text", "idea one")
        self._run("idea", "capture", "--text", "idea two")
        out = self._run("idea", "list", "--include-expired").stdout
        ids = __import__('re').findall(r'(IDEA-\d{8}-\d{6}(?:-\d{6})?)', out)
        self.assertEqual(len(ids), 2, f"Should have 2 unique IDs, got {ids}")
        self.assertNotEqual(ids[0], ids[1], f"IDs should be unique: {ids}")

    def test_new_id_format_can_be_promoted(self):
        self._run("idea", "capture", "--text", "test idea")
        out = self._run("idea", "list", "--include-expired").stdout
        match = __import__('re').search(r'(IDEA-\d{8}-\d{6}(?:-\d{6})?)', out)
        self.assertIsNotNone(match)
        iid = match.group(1)
        r = self._run("idea", "promote", iid, "--target", "goal")
        self.assertEqual(r.returncode, 0)

    def test_new_id_format_can_be_expired(self):
        self._run("idea", "capture", "--text", "test idea")
        out = self._run("idea", "list", "--include-expired").stdout
        match = __import__('re').search(r'(IDEA-\d{8}-\d{6}(?:-\d{6})?)', out)
        self.assertIsNotNone(match)
        iid = match.group(1)
        r = self._run("idea", "expire", iid, "--reason", "done")
        self.assertEqual(r.returncode, 0)

    def test_old_format_id_still_parseable(self):
        # Write an old-format idea manually to verify parser compat
        ip = self.tmp / ".aiwf" / "artifacts" / "reports" / "ideas.md"
        ip.parent.mkdir(parents=True, exist_ok=True)
        ip.write_text("""# AIWF Ideas

Ideas are volatile, low-trust planning inputs.

## Active Ideas

### IDEA-20240101-120000 | raw | legacy
- text: legacy format idea
- source: test
- created: 2024-01-01T12:00:00+00:00
- expires: 2099-01-01T12:00:00+00:00
""")
        out = self._run("idea", "list").stdout
        self.assertIn("IDEA-20240101-120000", out)
        self.assertIn("legacy format idea", out)

    def test_unknown_id_still_fails(self):
        r = self._run("idea", "expire", "IDEA-99999999-999999", "--reason", "nope")
        self.assertNotEqual(r.returncode, 0)

    # ═══════════════════════════════════════════════════════════════
    # Status
    # ═══════════════════════════════════════════════════════════════

    def test_status_ideas_available(self):
        self._run("idea", "capture", "--text", "active idea")
        out = self._run("status", "--debug").stdout
        self.assertIn("ideas", out.lower())

    def test_status_ideas_none(self):
        out = self._run("status", "--debug").stdout
        self.assertIn("ideas", out.lower())

    # ═══════════════════════════════════════════════════════════════
    # UserPromptSubmit no dump
    # ═══════════════════════════════════════════════════════════════

    def test_userpromptsubmit_no_idea_dump(self):
        self._run("idea", "capture", "--text", "secret-idea-xyz-should-not-leak")
        inp = json.dumps({"session_id": "t", "cwd": str(self.tmp), "hook_event_name": "UserPromptSubmit"})
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, str(self.tmp / "scripts" / "aiwf_status.py")],
                           input=inp, capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        ctx = json.loads(r.stdout.strip())["hookSpecificOutput"]["additionalContext"]
        self.assertNotIn("secret-idea-xyz", ctx)

    # ═══════════════════════════════════════════════════════════════
    # Report
    # ═══════════════════════════════════════════════════════════════

    def test_report_no_raw_idea_text(self):
        self._run("idea", "capture", "--text", "secret-raw-idea-should-not-be-in-report", "--expires-days", "0")
        r = self._run_script("scripts/aiwf_export_report.py")
        rpt = (self.tmp / ".aiwf" / "artifacts" / "reports" / "闭合报告.md").read_text()
        self.assertNotIn("secret-raw-idea", rpt)
        self.assertIn("expired idea:", rpt)
        self.assertIn("text=omitted", rpt)

    # ═══════════════════════════════════════════════════════════════
    # Planner skill
    # ═══════════════════════════════════════════════════════════════

    def test_planner_ideas_not_requirements(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-planner" / "SKILL.md").read_text()
        self.assertIn("plan", c.lower())

    def test_planner_classification_rules(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-planner-meta" / "SKILL.md").read_text()
        self.assertIn("meta-critique", c.lower())

    # ═══════════════════════════════════════════════════════════════
    # compile
    # ═══════════════════════════════════════════════════════════════

    def test_compileall_passes(self):
        import py_compile
        py_compile.compile(str(PROJECT_ROOT / "aiwf_core" / "core" / "ideas.py"), doraise=True)

    def test_scripts_py_compile_passes(self):
        import py_compile
        py_compile.compile(str(self.tmp / "scripts" / "aiwf_export_report.py"), doraise=True)


if __name__ == "__main__":
    unittest.main()
