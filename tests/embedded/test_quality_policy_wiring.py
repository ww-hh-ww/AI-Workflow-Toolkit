"""Quality policy wiring: state ops, security upgrade, skill text, prompt cache."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

def _install(cwd):
    env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
    subprocess.run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                   capture_output=True, text=True, cwd=str(cwd), env=env, timeout=20)

def _rj(path): return json.loads(path.read_text())

class TestQualityPolicyWiring(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awqpw_"))
        _install(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        from aiwf_core.core.state_schema import MVP_STATE_FILES
        for fn, dfn in MVP_STATE_FILES.items():
            p = self.tmp / ".aiwf" / fn; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(dfn(), indent=2) + "\n")

    # ── state schema ──

    def test_default_state_has_quality_policy_fields(self):
        from aiwf_core.core.state_schema import default_state
        s = default_state()
        for field in ["task_type", "test_template", "review_template", "git_policy"]:
            self.assertIn(field, s, f"Missing {field}")
        self.assertEqual(s["git_policy"], "no_auto_commit")
        # All quality fields are short strings or lists
        for field in ["test_template", "review_template", "exploration_budget",
                       "asset_policy", "cleanup_policy", "git_policy"]:
            val = s.get(field, "")
            self.assertLess(len(str(val)), 100, f"{field} too long: {len(str(val))}")

    # ── record_quality_policy ──

    def test_record_quality_policy_L1_small_function(self):
        from aiwf_core.core.state_ops import record_quality_policy
        record_quality_policy(str(self.tmp), "small_function", "L1_review_light",
                              routing_reason="2-file feature")
        s = _rj(self.tmp / ".aiwf" / "state" / "state.json")
        self.assertEqual(s["task_type"], "small_function")
        self.assertEqual(s["test_template"], "targeted_plus_small_regression")
        self.assertEqual(s["review_template"], "reviewer_light")
        self.assertEqual(s["git_policy"], "no_auto_commit")
        self.assertEqual(s["workflow_level"], "L1_review_light")

    def test_record_quality_policy_no_template_fulltext(self):
        from aiwf_core.core.state_ops import record_quality_policy
        record_quality_policy(str(self.tmp), "api_endpoint", "L2_standard_team")
        s = _rj(self.tmp / ".aiwf" / "state" / "state.json")
        # All values must be short keys, not full prose
        for k in ["test_template", "review_template", "exploration_budget"]:
            self.assertIn(s[k], ["regression_plus_boundary_adverse", "standard_review",
                                  "asset_first_affected_files", ""])

    # ── security_sensitive ──

    def test_security_sensitive_requires_full_review_and_user_decision(self):
        from aiwf_core.core.quality_policy import select_quality_policy
        p = select_quality_policy("security_sensitive", "L0_direct")
        self.assertTrue(p["requires_user_decision"])
        self.assertEqual(p["recommended_minimum_level"], "L3_full_power")
        self.assertIn("full_review", p["review_template"])

    # ── skill text checks ──

    def test_planner_skill_has_quality_policy_selection(self):
        content = (self.tmp / ".claude" / "skills" / "aiwf-planner" / "SKILL.md").read_text()
        self.assertIn("task_type", content)
        self.assertIn("test_template", content)
        self.assertIn("review_template", content)
        self.assertIn("exploration_budget", content)

    def test_test_skill_reads_test_template(self):
        content = (self.tmp / ".claude" / "skills" / "aiwf-test" / "SKILL.md").read_text()
        self.assertIn("test_template", content)

    def test_review_skill_reads_review_template(self):
        content = (self.tmp / ".claude" / "skills" / "aiwf-review" / "SKILL.md").read_text()
        self.assertIn("review_template", content)

    def test_close_skill_no_auto_commit(self):
        content = (self.tmp / ".claude" / "skills" / "aiwf-close" / "SKILL.md").read_text()
        self.assertIn("auto-commit", content.lower())
        self.assertIn("user", content.lower())

    # ── prompt cache compliance ──

    def test_quality_policy_no_claude_md_dynamic_ref(self):
        import inspect
        from aiwf_core.core import quality_policy
        src = inspect.getsource(quality_policy)
        self.assertNotIn("CLAUDE.md", src)
        self.assertNotIn("settings.json", src)
        self.assertNotIn("model", src.lower().split("def ")[0])

    def test_state_quality_fields_are_short_keys(self):
        s = _rj(self.tmp / ".aiwf" / "state" / "state.json")
        for k in ["task_type", "test_template", "review_template"]:
            val = s.get(k, "")
            self.assertLess(len(str(val)), 80, f"{k} too long for prompt cache: {len(str(val))}")


if __name__ == "__main__":
    unittest.main()
