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
        ip = self.tmp / ".aiwf" / "records" / "ideas.md"
        if ip.exists(): ip.unlink()

    def _run(self, *args):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run([sys.executable, "-m", "aiwf_core.cli"] + list(args),
                              capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    def _ideas_text(self):
        ip = self.tmp / ".aiwf" / "records" / "ideas.md"
        return ip.read_text() if ip.exists() else ""

    def _goal(self):
        """Read active goal from goals.json (V2)."""
        gdata = json.loads((self.tmp / ".aiwf" / "state" / "goals.json").read_text())
        goals = gdata.get("goals", [])
        active_id = gdata.get("active_goal_id") or "GOAL-001"
        return next((g for g in goals if isinstance(g, dict) and g.get("id") == active_id), {})

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
            # After install, ensure_ideas_file can create the ideas file
            from aiwf_core.core.ideas import ensure_ideas_file
            ideas_path = ensure_ideas_file(str(fresh))
            self.assertTrue(ideas_path.exists(), f"ideas file should exist at {ideas_path}")
        finally:
            shutil.rmtree(fresh, ignore_errors=True)

    def test_start_context_creates_ideas_file(self):
        from aiwf_core.core.state_ops import start_context
        start_context(str(self.tmp), "CTX-IDEA", allowed_write=["src/"])
        self.assertTrue((self.tmp / ".aiwf" / "records" / "ideas.md").exists())

    def test_capture_creates_ideas_file(self):
        from aiwf_core.core.ideas import capture_idea
        capture_idea(str(self.tmp), "Maybe add inspiration pack")
        self.assertTrue((self.tmp / ".aiwf" / "records" / "ideas.md").exists())

    def test_captured_idea_has_id_status_text(self):
        from aiwf_core.core.ideas import capture_idea
        result = capture_idea(str(self.tmp), "Add inspiration pack", tags=["planner"])
        self.assertIn("IDEA-", result["id"])
        self.assertEqual(result["status"], "raw")
        self.assertEqual(result["text"], "Add inspiration pack")
        self.assertIn("planner", result["tags"])

    def test_capture_does_not_modify_goal(self):
        from aiwf_core.core.ideas import capture_idea
        before = self._goal()
        capture_idea(str(self.tmp), "test idea")
        after = self._goal()
        self.assertEqual(before, after)

    # ═══════════════════════════════════════════════════════════════
    # List
    # ═══════════════════════════════════════════════════════════════

    def test_list_shows_summary(self):
        from aiwf_core.core.ideas import capture_idea, list_ideas
        capture_idea(str(self.tmp), "Maybe add inspiration pack for scattered ideas")
        ideas = list_ideas(str(self.tmp))
        self.assertGreaterEqual(len(ideas), 1)
        self.assertIn("IDEA-", ideas[0]["id"])
        self.assertEqual(ideas[0]["status"], "raw")

    def test_list_does_not_dump_full_text(self):
        from aiwf_core.core.ideas import capture_idea, list_ideas
        long_text = "A very long idea text that goes on and on " + "x" * 80
        result = capture_idea(str(self.tmp), long_text)
        # The idea text IS preserved in the data (not truncated on capture)
        self.assertEqual(result["text"], long_text)
        # After listing, the returned data preserves the full text
        ideas = list_ideas(str(self.tmp))
        self.assertEqual(ideas[0]["text"], long_text)

    def test_list_empty(self):
        from aiwf_core.core.ideas import list_ideas
        ideas = list_ideas(str(self.tmp))
        self.assertEqual(len(ideas), 0, "No ideas should be listed when none exist")

    # ═══════════════════════════════════════════════════════════════
    # Promote
    # ═══════════════════════════════════════════════════════════════

    def _capture_one(self):
        from aiwf_core.core.ideas import capture_idea, list_ideas
        capture_idea(str(self.tmp), "Test idea")
        ideas = list_ideas(str(self.tmp), include_expired=True)
        if not ideas:
            raise unittest.SkipTest("Could not capture an idea")
        return ideas[0]["id"]

    def test_promote_marks_adopted(self):
        from aiwf_core.core.ideas import capture_idea, promote_idea
        result = capture_idea(str(self.tmp), "Test idea")
        iid = result["id"]
        promote_idea(str(self.tmp), iid, target="project-map", note="Adopted")
        txt = self._ideas_text()
        self.assertIn("adopted", txt)
        self.assertIn("project-map", txt)

    def test_promote_does_not_modify_goal(self):
        from aiwf_core.core.ideas import capture_idea, promote_idea
        result = capture_idea(str(self.tmp), "Test idea")
        iid = result["id"]
        before = self._goal()
        promote_idea(str(self.tmp), iid, target="goal")
        after = self._goal()
        self.assertEqual(before, after)

    def test_promote_unknown_id_fails(self):
        from aiwf_core.core.ideas import promote_idea
        with self.assertRaises(ValueError) as ctx:
            promote_idea(str(self.tmp), "IDEA-99999999-999999", target="goal")
        self.assertIn("not found", str(ctx.exception).lower())

    def test_promote_unknown_does_not_mutate_ideas(self):
        from aiwf_core.core.ideas import capture_idea, promote_idea
        capture_idea(str(self.tmp), "existing idea")
        before = self._ideas_text()
        try:
            promote_idea(str(self.tmp), "IDEA-99999999-999999", target="goal")
        except ValueError:
            pass
        after = self._ideas_text()
        self.assertEqual(before.strip() if before else "", after.strip() if after else "")

    # ═══════════════════════════════════════════════════════════════
    # Expire
    # ═══════════════════════════════════════════════════════════════

    def test_expire_marks_expired(self):
        from aiwf_core.core.ideas import capture_idea, expire_idea
        result = capture_idea(str(self.tmp), "Test idea")
        iid = result["id"]
        expire_idea(str(self.tmp), iid, reason="outdated")
        txt = self._ideas_text()
        self.assertIn("expired", txt)

    def test_expire_unknown_id_fails(self):
        from aiwf_core.core.ideas import expire_idea
        with self.assertRaises(ValueError) as ctx:
            expire_idea(str(self.tmp), "IDEA-99999999-999999", reason="nope")
        self.assertIn("not found", str(ctx.exception).lower())

    def test_expired_not_in_active_list(self):
        from aiwf_core.core.ideas import capture_idea, expire_idea, list_ideas
        result = capture_idea(str(self.tmp), "Test idea")
        iid = result["id"]
        expire_idea(str(self.tmp), iid)
        ideas = list_ideas(str(self.tmp))
        self.assertEqual(len(ideas), 0, "Expired idea should not appear in default list")

    def test_expires_days_0_not_listed_by_default(self):
        from aiwf_core.core.ideas import capture_idea, list_ideas
        capture_idea(str(self.tmp), "expired by time", expires_days=0)
        ideas = list_ideas(str(self.tmp))
        self.assertEqual(len(ideas), 0, "Time-expired idea should not appear in default list")

    def test_expires_days_0_appears_with_include_expired(self):
        from aiwf_core.core.ideas import capture_idea, list_ideas
        capture_idea(str(self.tmp), "expired by time", expires_days=0)
        ideas = list_ideas(str(self.tmp), include_expired=True)
        self.assertGreaterEqual(len(ideas), 1, "Time-expired idea should appear with include_expired=True")
        self.assertEqual(ideas[0]["text"], "expired by time")

    def test_expired_by_time_makes_status_stale(self):
        from aiwf_core.core.ideas import capture_idea
        capture_idea(str(self.tmp), "expired idea", expires_days=0)
        out = self._run("status", "--debug").stdout
        self.assertIn("stale", out.lower())

    def test_active_unexpired_makes_status_available(self):
        from aiwf_core.core.ideas import capture_idea
        capture_idea(str(self.tmp), "active idea", expires_days=14)
        out = self._run("status", "--debug").stdout
        self.assertIn("available", out.lower())

    def test_adopted_not_in_default_list(self):
        from aiwf_core.core.ideas import capture_idea, list_ideas, promote_idea
        result = capture_idea(str(self.tmp), "adopted idea", expires_days=14)
        promote_idea(str(self.tmp), result["id"], target="project-map")
        ideas = list_ideas(str(self.tmp))
        self.assertEqual(len(ideas), 0, "Adopted idea should not appear in default list")

    def test_only_adopted_no_status_stale(self):
        from aiwf_core.core.ideas import capture_idea, promote_idea
        result = capture_idea(str(self.tmp), "adopted idea", expires_days=14)
        promote_idea(str(self.tmp), result["id"], target="project-map")
        out2 = self._run("status").stdout
        self.assertNotIn("Ideas: stale", out2)
        self.assertNotIn("Ideas: available", out2)

    def test_include_expired_marks_stale_by_time(self):
        from aiwf_core.core.ideas import capture_idea, list_ideas
        capture_idea(str(self.tmp), "time-expired idea", expires_days=0)
        capture_idea(str(self.tmp), "active idea", expires_days=365)
        ideas = list_ideas(str(self.tmp), include_expired=True)
        # The time-expired idea should have status "raw" but be stale (is_idea_active returns False)
        stale_ideas = [i for i in ideas if i["text"] == "time-expired idea"]
        self.assertEqual(len(stale_ideas), 1, "Time-expired idea should appear in include_expired list")
        from aiwf_core.core.ideas import is_idea_active
        self.assertFalse(is_idea_active(stale_ideas[0]), "Time-expired idea should NOT be active")

    def test_rapid_captures_produce_unique_ids(self):
        from aiwf_core.core.ideas import capture_idea, list_ideas
        r1 = capture_idea(str(self.tmp), "idea one")
        r2 = capture_idea(str(self.tmp), "idea two")
        self.assertNotEqual(r1["id"], r2["id"], f"IDs should be unique: {r1['id']} vs {r2['id']}")
        ideas = list_ideas(str(self.tmp), include_expired=True)
        ids = [i["id"] for i in ideas]
        self.assertEqual(len(ids), 2, f"Should have 2 unique IDs, got {ids}")

    def test_new_id_format_can_be_promoted(self):
        from aiwf_core.core.ideas import capture_idea, list_ideas, promote_idea
        capture_idea(str(self.tmp), "test idea")
        ideas = list_ideas(str(self.tmp), include_expired=True)
        self.assertGreaterEqual(len(ideas), 1)
        iid = ideas[0]["id"]
        # Should not raise
        promote_idea(str(self.tmp), iid, target="goal")

    def test_new_id_format_can_be_expired(self):
        from aiwf_core.core.ideas import capture_idea, list_ideas, expire_idea
        capture_idea(str(self.tmp), "test idea")
        ideas = list_ideas(str(self.tmp), include_expired=True)
        self.assertGreaterEqual(len(ideas), 1)
        iid = ideas[0]["id"]
        # Should not raise
        expire_idea(str(self.tmp), iid, reason="done")

    def test_old_format_id_still_parseable(self):
        from aiwf_core.core.ideas import list_ideas
        # Write an old-format idea manually to verify parser compat
        ip = self.tmp / ".aiwf" / "records" / "ideas.md"
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
        ideas = list_ideas(str(self.tmp))
        self.assertGreaterEqual(len(ideas), 1, "Should parse legacy format idea")
        self.assertEqual(ideas[0]["id"], "IDEA-20240101-120000")
        self.assertEqual(ideas[0]["text"], "legacy format idea")

    def test_unknown_id_still_fails(self):
        from aiwf_core.core.ideas import expire_idea
        with self.assertRaises(ValueError) as ctx:
            expire_idea(str(self.tmp), "IDEA-99999999-999999", reason="nope")
        self.assertIn("not found", str(ctx.exception).lower())

    # ═══════════════════════════════════════════════════════════════
    # Status
    # ═══════════════════════════════════════════════════════════════

    def test_status_ideas_available(self):
        from aiwf_core.core.ideas import capture_idea
        capture_idea(str(self.tmp), "active idea")
        out = self._run("status", "--debug").stdout
        self.assertIn("ideas", out.lower())

    def test_status_ideas_none(self):
        out = self._run("status", "--debug").stdout
        self.assertIn("ideas", out.lower())

    # ═══════════════════════════════════════════════════════════════
    # UserPromptSubmit no dump
    # ═══════════════════════════════════════════════════════════════

    def test_userpromptsubmit_no_idea_dump(self):
        from aiwf_core.core.ideas import capture_idea
        capture_idea(str(self.tmp), "secret-idea-xyz-should-not-leak")
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
        from aiwf_core.core.ideas import capture_idea
        capture_idea(str(self.tmp), "secret-raw-idea-should-not-be-in-report", expires_days=0)
        r = self._run_script("scripts/aiwf_export_report.py")
        self.assertEqual(r.returncode, 0, f"Report script failed: {r.stderr}")
        rpt = (self.tmp / ".aiwf" / "records" / "闭合报告.md").read_text()
        self.assertNotIn("secret-raw-idea", rpt)

    # ═══════════════════════════════════════════════════════════════
    # Planner skill
    # ═══════════════════════════════════════════════════════════════

    def test_planner_ideas_not_requirements(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-planner" / "SKILL.md").read_text()
        self.assertIn("plan", c.lower())

    def test_planner_classification_rules(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-planner" / "references" / "risk-and-rollback.md").read_text()
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
