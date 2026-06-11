"""Lifecycle cleanup check: blockers, warnings, staleness, read-only, non-mutation."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 15


class TestLifecycleCleanup(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awlc_"))
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
        # Clean up extra files from previous tests (shared tmp via setUpClass)
        for sub in [".aiwf/reports", ".aiwf/plans"]:
            d = self.tmp / sub
            if d.exists():
                for pf in d.glob("*"):
                    if pf.is_file():
                        pf.unlink()
        for f in ["PROJECT-MAP.md", "ideas.md"]:
            p = self.tmp / ".aiwf" / f
            if p.exists(): p.unlink()

    def _run(self, *args):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run([sys.executable, "-m", "aiwf_core.cli"] + list(args),
                              capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    def _write_ideas_md(self, ideas):
        """Write ideas.md fixture. ideas: list of {status, text, expires}. expires: 'past' or 'future'."""
        header = (
            "# AIWF Ideas\n\n"
            "Ideas are volatile, low-trust planning inputs.\n"
            "They are not requirements, decisions, roadmap items, or execution contracts until promoted by Planner.\n"
            "Expired ideas should not guide planning unless revived by user/Planner.\n"
        )

        def _block(i, idx):
            status = i.get("status", "raw")
            text = i.get("text", "")
            expires = i.get("expires", "future")
            exp_str = "2020-01-01T00:00:00+00:00" if expires == "past" else "2099-12-31T23:59:59+00:00"
            lines = [f"### IDEA-20200101-000000-{idx:06d} | {status}"]
            if text:
                lines.append(f"- text: {text}")
            lines.append("- created: 2020-01-01T00:00:00+00:00")
            lines.append(f"- expires: {exp_str}")
            lines.append("")
            return "\n".join(lines)

        active = [i for i in ideas if i.get("status") in ("raw", "candidate")]
        adopted = [i for i in ideas if i.get("status") == "adopted"]
        expired = [i for i in ideas if i.get("status") == "expired"]

        sections = [header]
        for title, group in [("Active Ideas", active), ("Adopted Ideas", adopted), ("Expired Ideas", expired)]:
            sections.append(f"## {title}\n")
            if group:
                for idx, idea in enumerate(group):
                    sections.append(_block(idea, idx))
            else:
                sections.append("(none)\n")

        path = self.tmp / ".aiwf" / "reports" / "ideas.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(sections), encoding="utf-8")

    def _run_script(self, script_rel):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run([sys.executable, str(self.tmp / script_rel)],
                              capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    # ═══════════════════════════════════════════════════════════════
    # Basic
    # ═══════════════════════════════════════════════════════════════

    def test_cleanup_check_runs_no_traceback(self):
        r = self._run("cleanup", "check")
        self.assertNotIn("Traceback", r.stderr)

    def test_clean_default_no_hard_blockers(self):
        r = self._run("cleanup", "check")
        out = r.stdout
        # No hard blockers on clean state without active plan
        self.assertNotIn("fix-loop", out.lower())

    # ═══════════════════════════════════════════════════════════════
    # Fix-loop blockers
    # ═══════════════════════════════════════════════════════════════

    def test_open_fixloop_blocker(self):
        self._run("fixloop", "open", "--route", "executor", "--reason", "bug")
        out = self._run("cleanup", "check").stdout
        self.assertIn("fix-loop", out.lower())

    def test_escalation_required_blocker(self):
        s = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        s["workflow_level"] = "L0_direct"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(s, indent=2))
        self._run("fixloop", "open", "--route", "executor", "--reason", "first")
        self._run("fixloop", "open", "--route", "executor", "--reason", "exceeds L0 max")
        out = self._run("cleanup", "check").stdout
        self.assertIn("escalation", out.lower())

    # ═══════════════════════════════════════════════════════════════
    # ACR blockers
    # ═══════════════════════════════════════════════════════════════

    def test_proposed_acr_blocker(self):
        self._run("arch-change", "request", "--source", "executor",
                  "--reason", "Need module", "--proposed-change", "Add file")
        out = self._run("cleanup", "check").stdout
        self.assertIn("ACR", out)

    # ═══════════════════════════════════════════════════════════════
    # PROJECT-MAP warnings
    # ═══════════════════════════════════════════════════════════════

    def test_project_map_missing_warning_only_when_impact_yes(self):
        """PROJECT-MAP missing is only warned when Impact.project_map=yes."""
        # No active plan — no PROJECT-MAP warning
        out = self._run("cleanup", "check").stdout
        self.assertNotIn("PROJECT-MAP", out,
                        "Should not warn about PROJECT-MAP without active plan Impact")
        # Create active plan with project_map=yes
        plan_dir = self.tmp / ".aiwf" / "plans"
        plan_dir.mkdir(parents=True, exist_ok=True)
        (plan_dir / "T-1.md").write_text(
            "# T-1\n\n## Impact\n"
            "- docs: no -- no docs\n"
            "- project_map: yes -- structure changes\n"
            "- environment: no -- same env\n"
            "- capabilities: no -- no deps\n"
            "- quality_summary: no -- no digest\n",
            encoding="utf-8")
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["active_task_id"] = "T-1"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(state, indent=2))
        out = self._run("cleanup", "check").stdout
        self.assertIn("PROJECT-MAP", out,
                     "Should warn about PROJECT-MAP when Impact.project_map=yes")


    def test_project_map_missing_no_warning_when_impact_no(self):
        """PROJECT-MAP missing is silent when Impact.project_map=no."""
        plan_dir = self.tmp / ".aiwf" / "plans"
        plan_dir.mkdir(parents=True, exist_ok=True)
        (plan_dir / "T-pm-no.md").write_text(
            "# T-pm-no\n\n## Impact\n"
            "- docs: no -- no docs\n"
            "- project_map: no -- no structure changes\n"
            "- environment: no -- same env\n"
            "- capabilities: no -- no deps\n"
            "- quality_summary: no -- no digest\n",
            encoding="utf-8")
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["active_task_id"] = "T-pm-no"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(state, indent=2))
        out = self._run("cleanup", "check").stdout
        self.assertNotIn("PROJECT-MAP", out,
                         "Should not warn about PROJECT-MAP when Impact.project_map=no")

    def test_project_map_missing_section_warns(self):
        pm_path = self.tmp / ".aiwf" / "reports" / "项目地图.md"
        pm_path.write_text("# AIWF Project Map\n\n## Project Snapshot\n- OK\n")
        out = self._run("cleanup", "check").stdout
        self.assertIn("missing section", out.lower())

    def test_project_map_raw_ideas_pollution_warns(self):
        pm_path = self.tmp / ".aiwf" / "reports" / "项目地图.md"
        pm_path.write_text("# AIWF Project Map\n\n## Project Snapshot\n- OK\n\n# AIWF Ideas\n### IDEA-20260531-000000 | raw\n- text: leaked idea\n")
        out = self._run("cleanup", "check").stdout
        self.assertIn("raw ideas", out.lower())

    def test_project_map_evidence_dump_warns(self):
        pm_path = self.tmp / ".aiwf" / "reports" / "项目地图.md"
        pm_path.write_text("# AIWF Project Map\n\n## Project Snapshot\n- OK\n\n" + '"records":[]\n"tool_name":"x"\nRaw records: 5\nAccepted IDs: EV-001 EV-002 EV-003 EV-004 EV-005 EV-006 EV-007 EV-008 EV-009 EV-010 EV-011 EV-012 EV-013 EV-014 EV-015 EV-016 EV-017 EV-018 EV-019 EV-020 EV-021\n')
        out = self._run("cleanup", "check").stdout
        self.assertIn("evidence", out.lower())

    def test_project_map_overlong_rejected_routes_warns(self):
        pm_path = self.tmp / ".aiwf" / "reports" / "项目地图.md"
        long_rr = "- " + "x" * 2600
        sections = "\n".join([f"## {s}\n- OK" for s in ["Project Snapshot", "Current Stage", "Completed Milestones", "Active Direction", "Next Candidate Tasks", "Architecture Direction", "Environment Summary", "Open Decisions", "Deferred Risks", "Ideas to Review"]])
        pm_path.write_text(f"# AIWF Project Map\n\n{sections}\n\n## Not-now / Rejected Routes\n{long_rr}\n")
        out = self._run("cleanup", "check").stdout
        self.assertIn("long", out.lower())

    # ═══════════════════════════════════════════════════════════════
    # Environment warnings (Impact-aware)
    # ═══════════════════════════════════════════════════════════════

    def test_environment_missing_no_warning_when_impact_no(self):
        """Environment.json missing is silent when Impact.environment=no."""
        plan_dir = self.tmp / ".aiwf" / "plans"
        plan_dir.mkdir(parents=True, exist_ok=True)
        (plan_dir / "T-env-no.md").write_text(
            "# T-env-no\n\n## Impact\n"
            "- docs: no -- no docs\n"
            "- project_map: no -- no structure\n"
            "- environment: no -- same env\n"
            "- capabilities: no -- no deps\n"
            "- quality_summary: no -- no digest\n",
            encoding="utf-8")
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["active_task_id"] = "T-env-no"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(state, indent=2))
        out = self._run("cleanup", "check").stdout
        self.assertNotIn("environment.json", out.lower(),
                         "Should not warn about environment.json when Impact.environment=no")

    def test_environment_missing_warning_when_impact_yes(self):
        """Environment.json missing warns when Impact.environment=yes."""
        plan_dir = self.tmp / ".aiwf" / "plans"
        plan_dir.mkdir(parents=True, exist_ok=True)
        (plan_dir / "T-env-yes.md").write_text(
            "# T-env-yes\n\n## Impact\n"
            "- docs: no -- no docs\n"
            "- project_map: no -- no structure\n"
            "- environment: yes -- new deps added\n"
            "- capabilities: no -- no deps\n"
            "- quality_summary: no -- no digest\n",
            encoding="utf-8")
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["active_task_id"] = "T-env-yes"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(state, indent=2))
        out = self._run("cleanup", "check").stdout
        self.assertIn("environment", out.lower(),
                      "Should warn about environment.json when Impact.environment=yes")

    # ═══════════════════════════════════════════════════════════════
    # Current-state checks (phase-aware)
    # ═══════════════════════════════════════════════════════════════

    def test_current_state_not_checked_during_execution(self):
        """Current-state check is silent during reviewing/implementing phase."""
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["phase"] = "reviewing"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(state, indent=2))
        out = self._run("cleanup", "check").stdout
        self.assertNotIn("current-state", out.lower(),
                         "Should not check current-state during reviewing phase")

    def test_current_state_checked_when_closed(self):
        """Current-state is checked when phase is closed."""
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["phase"] = "closed"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(state, indent=2))
        out = self._run("cleanup", "check").stdout
        self.assertIn("current-state", out.lower(),
                      "Should check current-state when phase is closed")

    # ═══════════════════════════════════════════════════════════════
    # Idea issues
    # ═══════════════════════════════════════════════════════════════

    def test_expired_idea_stale(self):
        self._write_ideas_md([{"status": "raw", "text": "temporary idea", "expires": "past"}])
        out = self._run("cleanup", "check").stdout
        self.assertIn("stale", out.lower())

    def test_many_ideas_warning(self):
        self._write_ideas_md([
            {"status": "raw", "text": f"idea {i}", "expires": "future"}
            for i in range(25)
        ])
        out = self._run("cleanup", "check").stdout
        self.assertIn("active ideas", out.lower())

    # ═══════════════════════════════════════════════════════════════
    # Non-mutation
    # ═══════════════════════════════════════════════════════════════

    def test_cleanup_check_no_modify_project_map(self):
        self._run("project-map", "init")
        before = (self.tmp / ".aiwf" / "reports" / "项目地图.md").read_text()
        self._run("cleanup", "check")
        after = (self.tmp / ".aiwf" / "reports" / "项目地图.md").read_text()
        self.assertEqual(before, after)

    def test_cleanup_check_no_modify_ideas(self):
        self._write_ideas_md([{"status": "raw", "text": "test idea", "expires": "future"}])
        before = (self.tmp / ".aiwf" / "reports" / "ideas.md").read_text()
        self._run("cleanup", "check")
        after = (self.tmp / ".aiwf" / "reports" / "ideas.md").read_text()
        self.assertEqual(before, after)

    def test_cleanup_check_no_modify_goal(self):
        before = json.loads((self.tmp / ".aiwf" / "state" / "goal.json").read_text())
        self._run("cleanup", "check")
        after = json.loads((self.tmp / ".aiwf" / "state" / "goal.json").read_text())
        self.assertEqual(before, after)

    # ═══════════════════════════════════════════════════════════════
    # CLI output
    # ═══════════════════════════════════════════════════════════════

    def test_output_no_raw_json(self):
        self._run("fixloop", "open", "--route", "executor", "--reason", "bug")
        out = self._run("cleanup", "check").stdout
        self.assertNotIn('"blockers"', out)

    def test_stale_items_shows_details(self):
        self._write_ideas_md([{"status": "raw", "text": "temporary stale idea", "expires": "past"}])
        out = self._run("cleanup", "check").stdout
        self.assertIn("expired idea:", out)
        self.assertIn("text=omitted", out)
        self.assertNotIn("temporary stale idea", out)

    # ═══════════════════════════════════════════════════════════════
    # Report
    # ═══════════════════════════════════════════════════════════════

    def test_report_includes_lifecycle_cleanup(self):
        r = self._run_script("scripts/aiwf_export_report.py")
        rpt = (self.tmp / ".aiwf" / "reports" / "闭合报告.md").read_text()
        self.assertIn("Lifecycle Cleanup", rpt)

    def test_report_includes_stale_items(self):
        self._write_ideas_md([{"status": "raw", "text": "temporary stale idea", "expires": "past"}])
        r = self._run_script("scripts/aiwf_export_report.py")
        rpt = (self.tmp / ".aiwf" / "reports" / "闭合报告.md").read_text()
        self.assertIn("expired idea:", rpt)
        self.assertIn("text=omitted", rpt)
        self.assertNotIn("temporary stale idea", rpt)

    def test_report_shows_warnings_even_with_blockers(self):
        self._run("fixloop", "open", "--route", "executor", "--reason", "bug")
        # Also create a PROJECT-MAP with missing sections to trigger warnings
        pm_path = self.tmp / ".aiwf" / "reports" / "项目地图.md"
        pm_path.write_text("# AIWF Project Map\n\n## Project Snapshot\n- OK\n")
        r = self._run_script("scripts/aiwf_export_report.py")
        rpt = (self.tmp / ".aiwf" / "reports" / "闭合报告.md").read_text()
        self.assertIn("Blockers:", rpt)
        self.assertIn("missing section", rpt.lower())

    # ═══════════════════════════════════════════════════════════════
    # Skill text
    # ═══════════════════════════════════════════════════════════════

    def test_planner_mentions_impact(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-planner" / "SKILL.md").read_text()
        self.assertIn("Impact", c)
        self.assertIn("aiwf status", c)

    # ═══════════════════════════════════════════════════════════════
    # compile
    # ═══════════════════════════════════════════════════════════════

    def test_compileall_passes(self):
        import py_compile
        py_compile.compile(str(PROJECT_ROOT / "aiwf_core" / "core" / "lifecycle_cleanup.py"), doraise=True)

    def test_scripts_py_compile_passes(self):
        import py_compile
        py_compile.compile(str(self.tmp / "scripts" / "aiwf_export_report.py"), doraise=True)


if __name__ == "__main__":
    unittest.main()
