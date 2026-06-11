"""Anti-regression: prevent rollback to legacy design patterns.

These tests enforce current design contracts:
- prompt shortness
- skill diet
- Impact-aware human docs
- silent side surfaces
- debug-only detailed diagnostics
- level-based Quality Verdict
- delta verification after fix-loop
"""
import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 15


class TestPromptShortness(unittest.TestCase):
    """UserPromptSubmit hook context must stay short."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awar_prompt_"))
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        subprocess.run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                       capture_output=True, text=True, cwd=str(cls.tmp), env=env, timeout=20)

    @classmethod
    def tearDownClass(cls):
        import shutil; shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        from aiwf_core.core.state_schema import MVP_STATE_FILES
        for fn, dfn in MVP_STATE_FILES.items():
            p = self.tmp / ".aiwf" / fn; p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(dfn(), indent=2) + "\n")

    def _hook_ctx(self):
        inp = json.dumps({"session_id": "t", "cwd": str(self.tmp), "hook_event_name": "UserPromptSubmit"})
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, str(self.tmp / "scripts" / "aiwf_status.py")],
                          input=inp, capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        return json.loads(r.stdout.strip())["hookSpecificOutput"]["additionalContext"]

    def _prompt_status(self):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, "-m", "aiwf_core.cli", "status", "--prompt"],
                          capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        return r.stdout

    def test_hook_context_under_800_chars(self):
        ctx = self._hook_ctx()
        self.assertLess(len(ctx), 800, f"hook context too long: {len(ctx)} chars")

    def test_prompt_status_under_500_chars(self):
        out = self._prompt_status()
        self.assertLess(len(out), 500, f"prompt status too long: {len(out)} chars")

    def test_hook_context_must_not_include_surface_obligations(self):
        ctx = self._hook_ctx()
        self.assertNotIn("surface obligation", ctx.lower())
        self.assertNotIn("test_obligations", ctx.lower())
        self.assertNotIn("review_obligations", ctx.lower())

    def test_hook_context_must_not_include_quality_dimensions(self):
        ctx = self._hook_ctx()
        self.assertNotIn("quality_dimensions", ctx.lower())
        self.assertNotIn("quality dimension", ctx.lower())

    def test_hook_context_must_not_include_full_capability_list(self):
        ctx = self._hook_ctx()
        self.assertNotIn("capabilities", ctx.lower())


class TestSkillDiet(unittest.TestCase):
    """Parent skills delegate to sub-skills; they don't contain full detail."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awar_skill_"))
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        subprocess.run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                       capture_output=True, text=True, cwd=str(cls.tmp), env=env, timeout=20)

    @classmethod
    def tearDownClass(cls):
        import shutil; shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_planner_parent_skill_must_not_contain_full_surface_table(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-planner" / "SKILL.md").read_text()
        self.assertNotIn("api_endpoint", c.lower())
        self.assertNotIn("state_mutation_cli", c.lower())
        self.assertNotIn("| surface | test_obligations |", c.lower())
        # But must mention surfaces briefly
        self.assertIn("surface", c.lower())

    def test_planner_parent_must_not_contain_fix_loop_route_details(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-planner" / "SKILL.md").read_text()
        self.assertNotIn("route=executor", c.lower())
        self.assertNotIn("route=tester", c.lower())

    def test_reviewer_parent_must_not_contain_surface_catalog(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-review" / "SKILL.md").read_text()
        self.assertNotIn("api_endpoint", c.lower())
        self.assertNotIn("numeric_logic", c.lower())

    def test_planner_skill_delegates_to_sub_skills(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-planner" / "SKILL.md").read_text()
        self.assertIn("aiwf-planner-contracts", c.lower())
        self.assertIn("aiwf-planner-execute", c.lower())
        self.assertIn("aiwf-planner-meta", c.lower())


class TestImpactAwareHumanDocs(unittest.TestCase):
    """Human docs (quality-digest) require Impact.quality_summary=yes."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awar_impact_"))
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        subprocess.run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                       capture_output=True, text=True, cwd=str(cls.tmp), env=env, timeout=20)

    @classmethod
    def tearDownClass(cls):
        import shutil; shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        from aiwf_core.core.state_schema import MVP_STATE_FILES
        for fn, dfn in MVP_STATE_FILES.items():
            p = self.tmp / ".aiwf" / fn; p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(dfn(), indent=2) + "\n")

    def _run(self, *args):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run([sys.executable, "-m", "aiwf_core.cli"] + list(args),
                             capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    def test_quality_digest_blocked_when_impact_quality_summary_no(self):
        plan_dir = self.tmp / ".aiwf" / "plans"
        plan_dir.mkdir(parents=True, exist_ok=True)
        (plan_dir / "TASK-QD.md").write_text(
            "# TASK-QD\n\n## Impact\n- quality_summary: no — test\n", encoding="utf-8")
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["active_plan_id"] = "TASK-QD"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(state, indent=2))

        r = self._run("quality", "digest")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Impact.quality_summary is not 'yes'", r.stderr)

    def test_quality_digest_allowed_with_force(self):
        plan_dir = self.tmp / ".aiwf" / "plans"
        plan_dir.mkdir(parents=True, exist_ok=True)
        (plan_dir / "TASK-QD.md").write_text(
            "# TASK-QD\n\n## Impact\n- quality_summary: no — test\n", encoding="utf-8")
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        state["active_plan_id"] = "TASK-QD"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(state, indent=2))

        r = self._run("quality", "digest", "--force")
        self.assertEqual(r.returncode, 0)


class TestSilentSideSurfaces(unittest.TestCase):
    """Surfaces are stored in goal.json, shown as one-line in human status,
    but never dumped into prompt context."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awar_surf_"))
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        subprocess.run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                       capture_output=True, text=True, cwd=str(cls.tmp), env=env, timeout=20)

    @classmethod
    def tearDownClass(cls):
        import shutil; shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        from aiwf_core.core.state_schema import MVP_STATE_FILES
        for fn, dfn in MVP_STATE_FILES.items():
            p = self.tmp / ".aiwf" / fn; p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(dfn(), indent=2) + "\n")

    def _run(self, *args):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run([sys.executable, "-m", "aiwf_core.cli"] + list(args),
                             capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    def _hook_ctx(self):
        inp = json.dumps({"session_id": "t", "cwd": str(self.tmp), "hook_event_name": "UserPromptSubmit"})
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, str(self.tmp / "scripts" / "aiwf_status.py")],
                          input=inp, capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        return json.loads(r.stdout.strip())["hookSpecificOutput"]["additionalContext"]

    def test_human_status_shows_one_line_surfaces(self):
        self._run("state", "record-quality-brief",
                  "--surface-type", "api_endpoint")
        # Human status must show Surfaces line
        r = self._run("status")
        self.assertIn("Surfaces:", r.stdout)
        self.assertIn("api_endpoint", r.stdout)

    def test_prompt_context_must_not_include_surface_obligations(self):
        self._run("state", "record-quality-brief",
                  "--surface-type", "state_mutation_cli")
        ctx = self._hook_ctx()
        self.assertNotIn("state_mutation_cli", ctx)
        self.assertNotIn("no mutation on failure", ctx.lower())


class TestDebugOnlyDiagnostics(unittest.TestCase):
    """Detailed diagnostics only appear in --debug mode, not in human status."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awar_debug_"))
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        subprocess.run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                       capture_output=True, text=True, cwd=str(cls.tmp), env=env, timeout=20)

    @classmethod
    def tearDownClass(cls):
        import shutil; shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        from aiwf_core.core.state_schema import MVP_STATE_FILES
        for fn, dfn in MVP_STATE_FILES.items():
            p = self.tmp / ".aiwf" / fn; p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(dfn(), indent=2) + "\n")

    def _run(self, *args):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run([sys.executable, "-m", "aiwf_core.cli"] + list(args),
                             capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    def test_human_status_must_not_have_gravity_section(self):
        r = self._run("status")
        self.assertNotIn("Gravity", r.stdout)

    def test_human_status_must_not_have_awareness_section(self):
        r = self._run("status")
        self.assertNotIn("Awareness", r.stdout)

    def test_human_status_must_not_have_control_panel_section(self):
        r = self._run("status")
        self.assertNotIn("Control Panel", r.stdout)

    def test_debug_status_has_gravity_section(self):
        r = self._run("status", "--debug")
        self.assertIn("Gravity", r.stdout)

    def test_debug_status_has_awareness_section(self):
        r = self._run("status", "--debug")
        self.assertIn("Awareness", r.stdout)

    def test_human_status_is_under_1200_chars(self):
        r = self._run("status")
        self.assertLess(len(r.stdout), 1200, f"human status too long: {len(r.stdout)} chars")


class TestLevelBasedQualityVerdict(unittest.TestCase):
    """L1 review_lite must not require full V2 Quality Verdict."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awar_level_"))
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        subprocess.run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                       capture_output=True, text=True, cwd=str(cls.tmp), env=env, timeout=20)

    @classmethod
    def tearDownClass(cls):
        import shutil; shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        from aiwf_core.core.state_schema import MVP_STATE_FILES
        for fn, dfn in MVP_STATE_FILES.items():
            p = self.tmp / ".aiwf" / fn; p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(dfn(), indent=2) + "\n")

    def _run(self, *args):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run([sys.executable, "-m", "aiwf_core.cli"] + list(args),
                             capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    def test_L1_record_review_accepts_v1_accepted_result(self):
        # Set up L1 context
        self._run("state", "record-quality-policy",
                  "--task-type", "small_function",
                  "--workflow-level", "L1_review_light",
                  "--reason", "test")
        # V1 accepted result must work on L1
        r = self._run("state", "record-review",
                      "--result", "accepted",
                      "--closure-allowed",
                      "--cleanup-code", "clean",
                      "--docs-checked", "not_applicable",
                      "--root-cause", "fixed")
        self.assertEqual(r.returncode, 0)

    def test_L1_reviewer_skill_mentions_review_lite(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-review" / "SKILL.md").read_text()
        self.assertIn("review_lite", c.lower())

    def test_L1_reviewer_skill_mentions_v1_fallback(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-review" / "SKILL.md").read_text()
        self.assertIn("review_lite", c.lower())


class TestDeltaVerificationAfterFixLoop(unittest.TestCase):
    """Fix-loop resolve enforces coverage and delta review."""

    def test_resolve_blocks_when_required_verification_uncovered(self):
        from aiwf_core.core.state.fixloop_ops import open_fix_loop, resolve_fix_loop
        base = tempfile.mkdtemp()
        try:
            for d in [".aiwf/state", ".aiwf/quality", ".aiwf/evidence"]:
                Path(base, d).mkdir(parents=True, exist_ok=True)
            Path(base, ".aiwf/state/state.json").write_text(json.dumps({
                "phase": "reviewing", "workflow_level": "L1_review_light",
            }))
            Path(base, ".aiwf/quality/testing.json").write_text(json.dumps({
                "status": "passed", "commands": ["pytest"],
                "acceptance_coverage": ["some test"],
            }))
            Path(base, ".aiwf/quality/review.json").write_text(json.dumps({
                "result": "accepted", "closure_allowed": True,
            }))

            open_fix_loop(
                base, route="planner", reason="test",
                required_verification=["verify_thing_not_in_coverage_xyz"],
            )
            with self.assertRaises(ValueError):
                resolve_fix_loop(base, resolution="done", source="planner", force=True)
        finally:
            import shutil; shutil.rmtree(base, ignore_errors=True)

    def test_executor_route_invalidates_review(self):
        from aiwf_core.core.state.fixloop_ops import open_fix_loop, resolve_fix_loop
        base = tempfile.mkdtemp()
        try:
            for d in [".aiwf/state", ".aiwf/quality", ".aiwf/evidence"]:
                Path(base, d).mkdir(parents=True, exist_ok=True)
            Path(base, ".aiwf/state/state.json").write_text(json.dumps({
                "phase": "reviewing", "workflow_level": "L1_review_light",
            }))
            Path(base, ".aiwf/quality/testing.json").write_text(json.dumps({
                "status": "passed", "commands": ["pytest"],
            }))
            Path(base, ".aiwf/quality/review.json").write_text(json.dumps({
                "result": "accepted", "closure_allowed": True, "cleanup_status": "fresh",
            }))

            open_fix_loop(
                base, route="executor", reason="bug fix",
                required_fixes=["fix calc.js"],
                invalidated_files=["src/calc.js"],
            )
            resolve_fix_loop(base, resolution="fixed", source="executor", force=True)
            review = json.loads(Path(base, ".aiwf/quality/review.json").read_text())
            self.assertEqual(review["result"], "unknown")
            self.assertTrue(review.get("delta_review_required"))
        finally:
            import shutil; shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
