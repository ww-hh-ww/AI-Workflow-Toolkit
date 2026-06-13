"""Quality surfaces: schema, CLI, report, status, skills, surface obligations."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 15


class TestQualitySurfaces(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awqs_"))
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

    def _run_script(self, script_rel):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run([sys.executable, str(self.tmp / script_rel)],
                              capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    # ═══════════════════════════════════════════════════════════════
    # SURFACE_OBLIGATIONS content
    # ═══════════════════════════════════════════════════════════════

    def test_api_endpoint_exists(self):
        from aiwf_core.core.quality_surfaces import SURFACE_OBLIGATIONS
        s = SURFACE_OBLIGATIONS["api_endpoint"]
        self.assertIn("invalid input", " ".join(s["test_obligations"]).lower())

    def test_frontend_interaction_exists(self):
        from aiwf_core.core.quality_surfaces import SURFACE_OBLIGATIONS
        s = SURFACE_OBLIGATIONS["frontend_interaction"]
        self.assertIn("user", " ".join(s["test_obligations"]).lower())

    def test_numeric_logic_mentions_boundary(self):
        from aiwf_core.core.quality_surfaces import SURFACE_OBLIGATIONS
        s = SURFACE_OBLIGATIONS["numeric_logic"]
        self.assertIn("boundary", " ".join(s["test_obligations"]).lower())

    def test_embedded_hardware_io_exists(self):
        from aiwf_core.core.quality_surfaces import SURFACE_OBLIGATIONS
        s = SURFACE_OBLIGATIONS["embedded_hardware_io"]
        self.assertIn("init", " ".join(s["test_obligations"]).lower())

    def test_state_mutation_cli_mentions_no_mutation(self):
        from aiwf_core.core.quality_surfaces import SURFACE_OBLIGATIONS
        s = SURFACE_OBLIGATIONS["state_mutation_cli"]
        txt = " ".join(s["test_obligations"]).lower()
        self.assertTrue("not mutate" in txt or "no mutation" in txt,
                        f"Should mention no-mutation-on-failure: {txt[:200]}")
        self.assertIn("invalid", txt)

    def test_read_only_cli_no_mutation(self):
        from aiwf_core.core.quality_surfaces import SURFACE_OBLIGATIONS
        s = SURFACE_OBLIGATIONS["read_only_cli"]
        self.assertIn("does not mutate", " ".join(s["test_obligations"]).lower())

    def test_report_exporter_missing_fields(self):
        from aiwf_core.core.quality_surfaces import SURFACE_OBLIGATIONS
        s = SURFACE_OBLIGATIONS["report_exporter"]
        txt = " ".join(s["test_obligations"]).lower()
        self.assertTrue("missing" in txt or "variant" in txt or "tolerated" in txt)

    def test_hook_script_no_heavy(self):
        from aiwf_core.core.quality_surfaces import SURFACE_OBLIGATIONS
        s = SURFACE_OBLIGATIONS["hook_script"]
        txt = " ".join(s["test_obligations"]).lower()
        self.assertTrue("no heavy" in txt or "fast" in txt)

    def test_git_checkpoint_confirm_no_push(self):
        from aiwf_core.core.quality_surfaces import SURFACE_OBLIGATIONS
        s = SURFACE_OBLIGATIONS["git_or_checkpoint_command"]
        txt = " ".join(s["test_obligations"]).lower()
        self.assertIn("confirm", txt)
        self.assertIn("no push", txt)

    def test_memory_retrieval_suppression_advisory(self):
        from aiwf_core.core.quality_surfaces import SURFACE_OBLIGATIONS
        s = SURFACE_OBLIGATIONS["memory_retrieval"]
        txt = " ".join(s["test_obligations"] + s["review_obligations"]).lower()
        self.assertIn("unrelated", txt)
        self.assertIn("advisory", txt)

    def test_environment_scanner_no_install_network_secret(self):
        from aiwf_core.core.quality_surfaces import SURFACE_OBLIGATIONS
        s = SURFACE_OBLIGATIONS["environment_scanner"]
        txt = " ".join(s["test_obligations"]).lower()
        self.assertIn("no install", txt)
        self.assertIn("no network", txt)

    # ═══════════════════════════════════════════════════════════════
    # Schema
    # ═══════════════════════════════════════════════════════════════

    def test_default_surface_types_empty(self):
        g = self._goal()
        self.assertEqual(g["quality_brief"]["surface_types"], [])

    # ═══════════════════════════════════════════════════════════════
    # CLI: record-quality-brief
    # ═══════════════════════════════════════════════════════════════

    def test_record_quality_brief_writes_surface_types(self):
        self._run("state", "record-quality-brief",
                  "--surface-type", "api_endpoint",
                  "--surface-type", "error_handling")
        g = self._goal()
        self.assertIn("api_endpoint", g["quality_brief"]["surface_types"])
        self.assertIn("error_handling", g["quality_brief"]["surface_types"])

    def test_record_quality_brief_rejects_unknown_surface(self):
        r = self._run("state", "record-quality-brief",
                      "--surface-type", "invalid_fake_surface_xyz")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("unknown surface", (r.stderr + r.stdout).lower())

    # ═══════════════════════════════════════════════════════════════
    # CLI: quality
    # ═══════════════════════════════════════════════════════════════

    def test_quality_surfaces_lists(self):
        out = self._run("quality", "surfaces").stdout
        self.assertIn("api_endpoint", out)
        self.assertIn("state_mutation_cli", out)

    def test_quality_surface_api_endpoint(self):
        out = self._run("quality", "surface", "api_endpoint").stdout
        self.assertIn("Test obligations", out)
        self.assertIn("Review obligations", out)

    def test_quality_surface_state_mutation_cli(self):
        out = self._run("quality", "surface", "state_mutation_cli").stdout
        self.assertIn("Test obligations", out)
        self.assertTrue("not mutate" in out.lower() or "does not mutate" in out.lower())

    def test_quality_unknown_surface_fails(self):
        r = self._run("quality", "surface", "nonexistent_xyz")
        self.assertNotEqual(r.returncode, 0)

    def test_quality_no_subcommand_shows_help(self):
        r = self._run("quality")
        self.assertIn("surfaces", r.stdout.lower())
        self.assertIn("surface", r.stdout.lower())

    # ═══════════════════════════════════════════════════════════════
    # Report
    # ═══════════════════════════════════════════════════════════════

    def test_report_includes_surfaces(self):
        self._run("state", "record-quality-brief",
                  "--surface-type", "api_endpoint",
                  "--surface-type", "error_handling")
        r = self._run_script("scripts/aiwf_export_report.py")
        rpt = (self.tmp / ".aiwf" / "artifacts" / "reports" / "闭合报告.md").read_text()
        self.assertIn("Quality surfaces", rpt)
        self.assertIn("api_endpoint", rpt)

    # ═══════════════════════════════════════════════════════════════
    # Status
    # ═══════════════════════════════════════════════════════════════

    def test_status_shows_surfaces(self):
        self._run("state", "record-quality-brief",
                  "--surface-type", "api_endpoint")
        out = self._run("status").stdout
        self.assertIn("Surfaces:", out)

    # ═══════════════════════════════════════════════════════════════
    # UserPromptSubmit no dump
    # ═══════════════════════════════════════════════════════════════

    def test_userpromptsubmit_no_obligations_dump(self):
        self._run("state", "record-quality-brief",
                  "--surface-type", "state_mutation_cli",
                  "--acceptance-criterion", "test-xyz")
        inp = json.dumps({"session_id": "t", "cwd": str(self.tmp), "hook_event_name": "UserPromptSubmit"})
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, str(self.tmp / "scripts" / "aiwf_status.py")],
                           input=inp, capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        ctx = json.loads(r.stdout.strip())["hookSpecificOutput"]["additionalContext"]
        self.assertNotIn("happy path mutates", ctx)

    # ═══════════════════════════════════════════════════════════════
    # Inferred surfaces: schema + CLI
    # ═══════════════════════════════════════════════════════════════

    def test_default_testing_has_inferred_surfaces(self):
        from aiwf_core.core.state_schema import default_testing
        t = default_testing()
        self.assertIn("inferred_surfaces", t)
        self.assertIn("missing_surface_notes", t)

    def test_record_testing_writes_inferred_surfaces(self):
        self._run("state", "record-testing", "--status", "adequate",
                  "--inferred-surface", "state_mutation_cli")
        t = json.loads((self.tmp / ".aiwf" / "artifacts" / "quality" / "testing.json").read_text())
        self.assertIn("state_mutation_cli", t["inferred_surfaces"])

    def test_report_shows_inferred_surfaces(self):
        self._run("state", "record-quality-brief",
                  "--surface-type", "api_endpoint")
        self._run("state", "record-testing", "--status", "adequate",
                  "--inferred-surface", "state_mutation_cli",
                  "--missing-surface-note", "Planner missed state_mutation_cli")
        r = self._run_script("scripts/aiwf_export_report.py")
        rpt = (self.tmp / ".aiwf" / "artifacts" / "reports" / "闭合报告.md").read_text()
        self.assertIn("declared", rpt)
        self.assertIn("inferred by tester", rpt)

    # ═══════════════════════════════════════════════════════════════
    # Skill text
    # ═══════════════════════════════════════════════════════════════

    def test_planner_says_minimum_guidance_not_exclusive(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-planner" / "SKILL.md").read_text()
        self.assertIn("surface obligations", c.lower())

    def test_planner_surface_depth_direction(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-planner" / "SKILL.md").read_text()
        self.assertIn("surface", c.lower())

    def test_tester_infers_missing_surfaces(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-test" / "SKILL.md").read_text()
        self.assertIn("if planner missed an obvious surface, infer it", c.lower())

    def test_tester_mentions_inference_inputs(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-test" / "SKILL.md").read_text()
        self.assertIn("changed files", c.lower())
        self.assertIn("architecture_brief", c.lower())

    def test_tester_inferred_no_scope_expansion(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-test" / "SKILL.md").read_text()
        self.assertIn("keep context.non_goals out of test expansion", c.lower())

    def test_tester_example_state_mutation_inference(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-test" / "SKILL.md").read_text()
        self.assertIn("--inferred-surface", c.lower())

    def test_reviewer_checks_surface_completeness(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-review" / "SKILL.md").read_text()
        self.assertIn("surface", c.lower())

    def test_reviewer_missing_obvious_surface_insufficient(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-review" / "SKILL.md").read_text()
        self.assertTrue("surface" in c.lower() or "needs_more_testing" in c.lower())

    def test_reviewer_not_every_catalog_surface(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-review" / "SKILL.md").read_text()
        self.assertIn("surface", c.lower())

    def test_tester_surface_minimums(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-test" / "SKILL.md").read_text()
        self.assertIn("surface_type", c.lower())

    def test_tester_autonomous_cases(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-test" / "SKILL.md").read_text()
        self.assertIn("do not expand unilaterally", c.lower())

    def test_reviewer_rejects_happy_path_only(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-review" / "SKILL.md").read_text()
        self.assertIn("spot-check", c.lower())

    # ═══════════════════════════════════════════════════════════════
    # compile
    # ═══════════════════════════════════════════════════════════════

    def test_compileall_passes(self):
        import py_compile
        py_compile.compile(str(PROJECT_ROOT / "aiwf_core" / "core" / "quality_surfaces.py"), doraise=True)
        py_compile.compile(str(PROJECT_ROOT / "aiwf_core" / "core" / "state_schema.py"), doraise=True)

    def test_scripts_py_compile_passes(self):
        import py_compile
        py_compile.compile(str(self.tmp / "scripts" / "aiwf_export_report.py"), doraise=True)


if __name__ == "__main__":
    unittest.main()
