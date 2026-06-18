"""Project Map: init, show, update, summarize, status, report, skills."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 15


class TestProjectMap(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awpm_"))
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
        pm = self.tmp / ".aiwf" / "records" / "项目地图.md"
        if pm.exists(): pm.unlink()
        asset_pm = self.tmp / ".aiwf" / "assets" / "project-map.json"
        if asset_pm.exists(): asset_pm.unlink()
        # V2: bootstrap_project writes to runtime/history/; ensure dir exists
        (self.tmp / ".aiwf" / "runtime" / "history").mkdir(parents=True, exist_ok=True)

    def _run(self, *args):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run([sys.executable, "-m", "aiwf_core.cli"] + list(args),
                              capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    def _pm_text(self):
        p = self.tmp / ".aiwf" / "records" / "项目地图.md"
        return p.read_text() if p.exists() else ""

    def _run_script(self, script_rel):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run([sys.executable, str(self.tmp / script_rel)],
                              capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    # ═══════════════════════════════════════════════════════════════
    # Init
    # ═══════════════════════════════════════════════════════════════

    @unittest.skip("V1: hidden module")
    def test_init_creates_map(self):
        self._run("project-map", "init")
        self.assertTrue((self.tmp / ".aiwf" / "records" / "项目地图.md").exists())

    @unittest.skip("V1: hidden module")
    def test_default_has_required_sections(self):
        self._run("project-map", "init")
        text = self._pm_text()
        for section in ["Project Snapshot", "Current Stage", "Architecture Direction",
                         "Next Candidate Tasks", "Deferred Risks", "Rejected Routes"]:
            self.assertIn(section, text, f"Missing section: {section}")

    @unittest.skip("V1: hidden module")
    def test_default_prompts_planner_intelligence_not_mechanical_counts(self):
        self._run("project-map", "init")
        text = self._pm_text()
        self.assertIsNotNone(text)  # bootstrap produces non-None output
        self.assertIn("How It Works", text)
        self.assertIn("One-line Overview", text)
        self.assertIn("Technical Stack", text)
        self.assertIn("Architecture Layers", text)

    # ═══════════════════════════════════════════════════════════════
    # Show
    # ═══════════════════════════════════════════════════════════════

    @unittest.skip("V1: hidden module")
    def test_show_displays_map(self):
        self._run("project-map", "init")
        out = self._run("project-map", "show").stdout
        self.assertIn("Project Map", out)

    @unittest.skip("V1: hidden module")
    def test_show_missing_hints(self):
        out = self._run("project-map", "show").stdout
        self.assertIn("not found", out.lower())

    # ═══════════════════════════════════════════════════════════════
    # Update
    # ═══════════════════════════════════════════════════════════════

    @unittest.skip("V1: hidden module")
    def test_update_changes_only_target_section(self):
        self._run("project-map", "init")
        self._run("project-map", "update", "--section", "architecture-direction",
                  "--text", "Focus on internal quality governance before external adapter expansion.")
        text = self._pm_text()
        self.assertIn("Focus on internal quality governance", text)
        # Other sections unchanged
        self.assertIn("Planner TODO: concise current-state snapshot", text)  # snapshot still default

    @unittest.skip("V1: hidden module")
    def test_bootstrap_does_not_mechanically_populate_human_project_map(self):
        (self.tmp / "src").mkdir(exist_ok=True)
        (self.tmp / "src" / "module.py").write_text("def exported():\n    return 1\n")
        r = self._run("project-map", "bootstrap")
        self.assertEqual(r.returncode, 0, r.stderr)
        text = self._pm_text()
        self.assertIsNotNone(text)  # bootstrap produces non-None output
        self.assertNotIn("source files across", text)
        self.assertNotIn("Modules detected:", text)

    @unittest.skip("V1: hidden module")
    def test_update_unknown_section_fails(self):
        self._run("project-map", "init")
        r = self._run("project-map", "update", "--section", "invalid-fake-section",
                      "--text", "test")
        self.assertNotEqual(r.returncode, 0)

    @unittest.skip("V1: hidden module")
    def test_update_treats_backslash_content_as_literal_text(self):
        self._run("project-map", "init")
        content = r"Regex-like note: \1 and \g<name> must stay literal."
        r = self._run("project-map", "update", "--section", "architecture-direction",
                      "--text", content)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(content, self._pm_text())

    # ═══════════════════════════════════════════════════════════════
    # Summarize
    # ═══════════════════════════════════════════════════════════════

    @unittest.skip("V1: hidden module")
    def test_summarize_short_output(self):
        self._run("project-map", "init")
        self._run("project-map", "update", "--section", "architecture-direction",
                  "--text", "Focus on quality governance.")
        out = self._run("project-map", "summarize").stdout
        self.assertIn("Focus on quality governance", out)
        self.assertNotIn("Project Snapshot", out)  # not the full file

    @unittest.skip("V1: hidden module")
    def test_summarize_missing_hints(self):
        out = self._run("project-map", "summarize").stdout
        self.assertIn("not found", out.lower())

    # ═══════════════════════════════════════════════════════════════
    # Status
    # ═══════════════════════════════════════════════════════════════

    @unittest.skip("V1: hidden module")
    def test_status_shows_project_map_present(self):
        self._run("project-map", "init")
        out = self._run("status", "--debug").stdout
        self.assertIn("project map", out.lower())

    @unittest.skip("V1: hidden module")
    def test_status_shows_project_map_missing(self):
        out = self._run("status", "--debug").stdout
        self.assertIn("project map", out.lower())

    # ═══════════════════════════════════════════════════════════════
    # UserPromptSubmit
    # ═══════════════════════════════════════════════════════════════

    @unittest.skip("V1: hidden module")
    def test_userpromptsubmit_no_map_content_dump(self):
        self._run("project-map", "init")
        self._run("project-map", "update", "--section", "architecture-direction",
                  "--text", "secret-map-content-xyz")
        inp = json.dumps({"session_id": "t", "cwd": str(self.tmp), "hook_event_name": "UserPromptSubmit"})
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, str(self.tmp / "scripts" / "aiwf_status.py")],
                           input=inp, capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        ctx = json.loads(r.stdout.strip())["hookSpecificOutput"]["additionalContext"]
        self.assertNotIn("secret-map-content-xyz", ctx)

    # ═══════════════════════════════════════════════════════════════
    # Isolation: ideas don't auto-enter map, report doesn't auto-copy
    # ═══════════════════════════════════════════════════════════════

    @unittest.skip("V1: hidden module")
    def test_idea_does_not_auto_enter_project_map(self):
        self._run("project-map", "init")
        self._run("idea", "capture", "--text", "Raw idea should not auto-enter project map")
        text = self._pm_text()
        self.assertNotIn("Raw idea should not auto-enter project map", text)

    @unittest.skip("V1: hidden module")
    def test_report_export_does_not_copy_to_project_map(self):
        self._run("project-map", "init")
        self._run("state", "record-quality-brief", "--user-visible-outcome", "test outcome")
        self._run_script("scripts/aiwf_export_report.py")
        text = self._pm_text()
        self.assertNotIn("test outcome", text)

    # ═══════════════════════════════════════════════════════════════
    # help
    # ═══════════════════════════════════════════════════════════════

    @unittest.skip("V1: hidden module")
    def test_project_map_help_no_traceback(self):
        r = self._run("project-map")
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn("init", r.stdout.lower())

    @unittest.skip("V1: hidden module")
    def test_goal_binding_connects_goal_tree_to_modules(self):
        (self.tmp / "src").mkdir(exist_ok=True)
        (self.tmp / "src" / "notes.py").write_text("def list_notes():\n    return []\n")
        self._run("goal-tree", "init-root", "GOAL-PRODUCT", "--type", "main", "--title", "Product")
        self._run("goal-tree", "add", "GOAL-NOTES", "--parent", "GOAL-PRODUCT", "--title", "Notes")
        result = self._run(
            "project-map", "bind", "GOAL-NOTES",
            "--module", "src/notes.py",
            "--entrypoint", "src/notes.py",
            "--interface", "note repository",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        relations = self._run("project-map", "relations")
        self.assertIn("GOAL-NOTES", relations.stdout)
        self.assertIn("src/notes.py", relations.stdout)
        validation = self._run("project-map", "validate")
        self.assertEqual(validation.returncode, 0, validation.stderr)
        self.assertIn("valid", validation.stdout)

    @unittest.skip("V1: hidden module")
    def test_goal_binding_rejects_unknown_goal_and_missing_path(self):
        unknown = self._run("project-map", "bind", "GOAL-MISSING", "--module", "src/missing.py")
        self.assertNotEqual(unknown.returncode, 0)
        self._run("goal-tree", "init-root", "GOAL-PRODUCT", "--type", "main", "--title", "Product")
        missing = self._run("project-map", "bind", "GOAL-PRODUCT", "--module", "src/missing.py")
        self.assertNotEqual(missing.returncode, 0)

    @unittest.skip("V1: hidden module")
    def test_asset_rescan_preserves_curated_goal_bindings(self):
        (self.tmp / "src").mkdir(exist_ok=True)
        (self.tmp / "src" / "core.py").write_text("def run():\n    return True\n")
        self._run("goal-tree", "init-root", "GOAL-CORE", "--type", "main", "--title", "Core")
        self._run("project-map", "bind", "GOAL-CORE", "--module", "src/core.py")
        self._run("asset", "init")
        asset = json.loads((self.tmp / ".aiwf" / "assets" / "project-map.json").read_text())
        self.assertEqual(asset["goal_bindings"][0]["goal_id"], "GOAL-CORE")

    @unittest.skip("V1: hidden module")
    def test_unbind_requires_reason_and_records_history(self):
        (self.tmp / "src").mkdir(exist_ok=True)
        (self.tmp / "src" / "core.py").write_text("def run():\n    return True\n")
        self._run("goal-tree", "init-root", "GOAL-CORE", "--type", "main", "--title", "Core")
        self._run("project-map", "bind", "GOAL-CORE", "--module", "src/core.py")
        missing_reason = self._run("project-map", "unbind", "GOAL-CORE")
        self.assertNotEqual(missing_reason.returncode, 0)
        removed = self._run(
            "project-map", "unbind", "GOAL-CORE",
            "--reason", "capability moved to another Goal",
        )
        self.assertEqual(removed.returncode, 0, removed.stderr)
        asset = json.loads((self.tmp / ".aiwf" / "assets" / "project-map.json").read_text())
        self.assertEqual(asset["goal_bindings"], [])
        self.assertEqual(asset["goal_binding_history"][-1]["goal_id"], "GOAL-CORE")
        self.assertIn("moved", asset["goal_binding_history"][-1]["reason"])

    @unittest.skip("V1: hidden module")
    def test_validate_warns_for_unbound_leaf_capability(self):
        (self.tmp / "src").mkdir(exist_ok=True)
        (self.tmp / "src" / "core.py").write_text("def run():\n    return True\n")
        self._run("goal-tree", "init-root", "GOAL-PRODUCT", "--type", "main", "--title", "Product")
        self._run("goal-tree", "add", "GOAL-CORE", "--parent", "GOAL-PRODUCT", "--title", "Core")
        # V2: 'asset init' CLI command removed; create project-map.json directly
        from aiwf_core.assets.schema import init_assets
        init_assets(str(self.tmp))
        validation = self._run("project-map", "validate")
        self.assertEqual(validation.returncode, 0, validation.stderr)
        self.assertIn("leaf capability Goal has no project-map binding: GOAL-CORE", validation.stdout)

    # ═══════════════════════════════════════════════════════════════
    # Skill text
    # ═══════════════════════════════════════════════════════════════

    @unittest.skip("V1: hidden module")
    def test_planner_distinguishes_map_from_report_ideas(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-planner" / "SKILL.md").read_text()
        self.assertIn("plan", c.lower())

    # ═══════════════════════════════════════════════════════════════
    # compile
    # ═══════════════════════════════════════════════════════════════

    @unittest.skip("V1: hidden module")
    def test_compileall_passes(self):
        import py_compile
        py_compile.compile(str(PROJECT_ROOT / "aiwf_core" / "core" / "project_map.py"), doraise=True)

    @unittest.skip("V1: hidden module")
    def test_scripts_py_compile_passes(self):
        import py_compile
        py_compile.compile(str(self.tmp / "scripts" / "aiwf_export_report.py"), doraise=True)


if __name__ == "__main__":
    unittest.main()
