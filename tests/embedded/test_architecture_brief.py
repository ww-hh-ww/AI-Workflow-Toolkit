"""Architecture Brief: schema, CLI, report, status, skills, structure-first contract. (V2)"""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 15


class TestArchitectureBrief(unittest.TestCase):
    __unittest_skip__ = True  # V1: architecture brief removed

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awab_"))
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
        """V2: Read active goal from goals.json (single source of truth)."""
        goals = json.loads((self.tmp / ".aiwf" / "state" / "goals.json").read_text())
        active_id = goals.get("active_goal_id") or "GOAL-001"
        for g in (goals.get("goals") or []):
            if isinstance(g, dict) and g.get("id") == active_id:
                return g
        return {"id": active_id, "title": active_id, "status": "discussing"}

    def _run_script(self, script_rel, *extra_args):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run([sys.executable, str(self.tmp / script_rel)] + list(extra_args),
                              capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    def _status_ctx(self, *args):
        """Run aiwf_status.py and return the additionalContext string."""
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        inp = json.dumps({"session_id": "t", "cwd": str(self.tmp), "hook_event_name": "UserPromptSubmit"})
        r = subprocess.run([sys.executable, str(self.tmp / "scripts" / "aiwf_status.py")] + list(args),
                           input=inp, capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        return json.loads(r.stdout.strip())["hookSpecificOutput"]["additionalContext"]

    # ═══════════════════════════════════════════════════════════════
    # Schema defaults
    # ═══════════════════════════════════════════════════════════════

    @unittest.skip("V1: feature removed")
    def test_default_quality_brief_has_architecture_brief(self):
        # V2: Architecture brief lives in goals.json; populate via record-quality-brief
        self._run("state", "record-quality-brief",
                  "--target-structure", "test structure",
                  "--module-boundary", "test boundary",
                  "--allowed-file", "test.py",
                  "--protected-file", "protected.py",
                  "--allowed-new-file", "new.py",
                  "--public-api-change", "export test_func",
                  "--integration-point", "test point",
                  "--architecture-invariant", "invariant X must hold",
                  "--forbidden-restructure", "don't restructure X",
                  "--architecture-risk", "test risk",
                  "--migration-source-of-truth", "README.md",
                  "--legacy-path", "old.sh",
                  "--legacy-term", "old_term",
                  "--default-entrypoint", "new.sh",
                  "--validator", "validate.sh",
                  "--sample-output", "out.md")
        g = self._goal()
        ab = g["quality_brief"]["architecture_brief"]
        expected = ["target_structure", "module_boundaries", "allowed_files",
                     "protected_files", "allowed_new_files", "public_api_changes",
                     "integration_points", "architecture_invariants",
                     "forbidden_restructures", "architecture_risks",
                     "migration_source_of_truth", "legacy_paths", "legacy_terms",
                     "default_entrypoints", "validators", "sample_outputs"]
        for field in expected:
            self.assertIn(field, ab, f"Missing architecture_brief field: {field}")

    # ═══════════════════════════════════════════════════════════════
    # CLI writes
    # ═══════════════════════════════════════════════════════════════

    @unittest.skip("V1: feature removed")
    def test_writes_target_structure(self):
        self._run("state", "record-quality-brief",
                  "--target-structure", "Add divide as peer operation")
        ab = self._goal()["quality_brief"]["architecture_brief"]
        self.assertEqual(ab["target_structure"], "Add divide as peer operation")

    @unittest.skip("V1: feature removed")
    def test_writes_allowed_files(self):
        self._run("state", "record-quality-brief",
                  "--allowed-file", "src/calc.js",
                  "--allowed-file", "tests/calc.test.js")
        ab = self._goal()["quality_brief"]["architecture_brief"]
        self.assertIn("src/calc.js", ab["allowed_files"])
        self.assertIn("tests/calc.test.js", ab["allowed_files"])

    @unittest.skip("V1: feature removed")
    def test_writes_protected_files(self):
        self._run("state", "record-quality-brief",
                  "--protected-file", "src/shared/validation.js")
        ab = self._goal()["quality_brief"]["architecture_brief"]
        self.assertIn("src/shared/validation.js", ab["protected_files"])

    @unittest.skip("V1: feature removed")
    def test_writes_integration_points(self):
        self._run("state", "record-quality-brief",
                  "--integration-point", "calculator public export path")
        ab = self._goal()["quality_brief"]["architecture_brief"]
        self.assertIn("calculator public export path", ab["integration_points"])

    @unittest.skip("V1: feature removed")
    def test_writes_forbidden_restructures(self):
        self._run("state", "record-quality-brief",
                  "--forbidden-restructure", "Do not redesign shared validation")
        ab = self._goal()["quality_brief"]["architecture_brief"]
        self.assertIn("Do not redesign shared validation", ab["forbidden_restructures"])

    @unittest.skip("V1: feature removed")
    def test_writes_architecture_risks(self):
        self._run("state", "record-quality-brief",
                  "--architecture-risk", "Shared validation change broadens scope")
        ab = self._goal()["quality_brief"]["architecture_brief"]
        self.assertIn("Shared validation change broadens scope", ab["architecture_risks"])

    @unittest.skip("V1: feature removed")
    def test_writes_architecture_migration_contract(self):
        self._run("state", "record-quality-brief",
                  "--migration-source-of-truth", "README.md documents the new mainline",
                  "--legacy-path", "scripts/old-flow.sh",
                  "--legacy-term", "old_handoff",
                  "--default-entrypoint", "scripts/new-flow.sh",
                  "--validator", "scripts/validate.sh",
                  "--sample-output", "examples/new-output.md")
        ab = self._goal()["quality_brief"]["architecture_brief"]
        self.assertEqual(ab["migration_source_of_truth"], "README.md documents the new mainline")
        self.assertIn("scripts/old-flow.sh", ab["legacy_paths"])
        self.assertIn("old_handoff", ab["legacy_terms"])
        self.assertIn("scripts/new-flow.sh", ab["default_entrypoints"])
        self.assertIn("scripts/validate.sh", ab["validators"])
        self.assertIn("examples/new-output.md", ab["sample_outputs"])

    # ═══════════════════════════════════════════════════════════════
    # Report
    # ═══════════════════════════════════════════════════════════════

    @unittest.skip("V1: feature removed")
    def test_report_includes_architecture_brief(self):
        self._run("state", "record-quality-brief",
                  "--target-structure", "Add divide as peer calculator operation",
                  "--allowed-file", "src/calc.js",
                  "--integration-point", "calculator public export")
        r = self._run_script("scripts/aiwf_export_report.py")
        rpt = (self.tmp / ".aiwf" / "records" / "闭合报告.md").read_text()
        self.assertIn("## Architecture Brief", rpt)
        self.assertIn("Add divide as peer calculator operation", rpt)
        self.assertIn("src/calc.js", rpt)

    @unittest.skip("V1: feature removed")
    def test_report_shows_none_when_no_brief(self):
        r = self._run_script("scripts/aiwf_export_report.py")
        rpt = (self.tmp / ".aiwf" / "records" / "闭合报告.md").read_text()
        self.assertIn("Architecture brief: none", rpt)

    @unittest.skip("V1: feature removed")
    def test_report_no_raw_json_dump(self):
        self._run("state", "record-quality-brief",
                  "--target-structure", "test structure")
        r = self._run_script("scripts/aiwf_export_report.py")
        rpt = (self.tmp / ".aiwf" / "records" / "闭合报告.md").read_text()
        self.assertNotIn('"target_structure"', rpt)

    # ═══════════════════════════════════════════════════════════════
    # Status
    # ═══════════════════════════════════════════════════════════════

    @unittest.skip("V1: feature removed")
    def test_status_shows_architecture_present(self):
        self._run("state", "record-quality-brief",
                  "--target-structure", "Add peer operation")
        ctx = self._status_ctx("--debug")
        self.assertIn("Architecture: brief present", ctx)

    @unittest.skip("V1: feature removed")
    def test_status_shows_architecture_missing_by_default(self):
        ctx = self._status_ctx("--debug")
        self.assertIn("Architecture: missing", ctx)

    # ═══════════════════════════════════════════════════════════════
    # UserPromptSubmit
    # ═══════════════════════════════════════════════════════════════

    @unittest.skip("V1: feature removed")
    def test_userpromptsubmit_no_architecture_dump(self):
        self._run("state", "record-quality-brief",
                  "--target-structure", "secret-structure-detail-xyz",
                  "--allowed-file", "secret-file-xyz.js")
        inp = json.dumps({"session_id": "t", "cwd": str(self.tmp), "hook_event_name": "UserPromptSubmit"})
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, str(self.tmp / "scripts" / "aiwf_status.py")],
                           input=inp, capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        ctx = json.loads(r.stdout.strip())["hookSpecificOutput"]["additionalContext"]
        self.assertNotIn("secret-structure-detail-xyz", ctx)
        self.assertNotIn("secret-file-xyz.js", ctx)

    # ═══════════════════════════════════════════════════════════════
    # Skill text checks
    # ═══════════════════════════════════════════════════════════════

    @unittest.skip("V1: feature removed")
    def test_planner_says_structure_before_implementation(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-planner" / "SKILL.md").read_text()
        # V1: Planner reads project-map.json for structure context; doesn't teach Architecture Brief
        self.assertIn("project-map.json", c,
                      "Planner should read project-map.json for structure context")

    @unittest.skip("V1: feature removed")
    def test_executor_says_do_not_silently_restructure(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-implement" / "SKILL.md").read_text()
        self.assertIn("Do NOT expand scope", c,
                      "Executor should say do not expand scope")

    @unittest.skip("V1: feature removed")
    def test_executor_says_stop_and_report_architecture_change(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-implement" / "SKILL.md").read_text()
        self.assertIn("unresolved risks", c,
                      "Executor should say report unresolved risks")

    @unittest.skip("V1: feature removed")
    def test_reviewer_checks_allowed_protected_files(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-review" / "SKILL.md").read_text()
        self.assertIn("forbidden", c.lower(),
                      "Reviewer should check forbidden paths")

    @unittest.skip("V1: feature removed")
    def test_reviewer_says_missing_brief_can_be_blocker(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-review" / "SKILL.md").read_text()
        self.assertIn("blockers", c.lower(),
                      "Reviewer should mention blockers")

    @unittest.skip("V1: feature removed")
    def test_tester_mentions_integration_points(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-test" / "SKILL.md").read_text()
        self.assertIn("Tester Requirements", c,
                      "Tester should mention Tester Requirements")

    # ═══════════════════════════════════════════════════════════════
    # compile checks
    # ═══════════════════════════════════════════════════════════════

    @unittest.skip("V1: feature removed")
    def test_compileall_passes(self):
        import py_compile
        py_compile.compile(str(PROJECT_ROOT / "aiwf_core" / "core" / "state_schema.py"), doraise=True)
        py_compile.compile(str(PROJECT_ROOT / "aiwf_core" / "core" / "state_ops.py"), doraise=True)
        py_compile.compile(str(PROJECT_ROOT / "aiwf_core" / "install_claude.py"), doraise=True)

    @unittest.skip("V1: feature removed")
    def test_scripts_py_compile_passes(self):
        import py_compile
        py_compile.compile(str(self.tmp / "scripts" / "aiwf_export_report.py"), doraise=True)


if __name__ == "__main__":
    unittest.main()
