"""Quality policy operational: CLI, status injection, prompt cache, smoke."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 15

def _install(cwd):
    env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
    subprocess.run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                   capture_output=True, text=True, cwd=str(cwd), env=env, timeout=20)

def _rj(path): return json.loads(path.read_text())

class TestQualityPolicyOperational(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awqpo_"))
        _install(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        from aiwf_core.core.state_schema import MVP_STATE_FILES
        for fn, dfn in MVP_STATE_FILES.items():
            p = self.tmp / ".aiwf" / fn; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(dfn(), indent=2) + "\n")

    def _run(self, *args):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run([sys.executable, "-m", "aiwf_core.cli"] + list(args),
                              capture_output=True, text=True,
                              cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    # ── CLI writes state ──
    def test_cli_writes_quality_policy_keys(self):
        r = self._run("state", "record-quality-policy",
                      "--task-type", "small_function",
                      "--workflow-level", "L1_review_light",
                      "--risk-flag", "prior_fix_loop",
                      "--reason", "smoke test")
        self.assertEqual(r.returncode, 0)
        s = _rj(self.tmp / ".aiwf" / "state" / "state.json")
        self.assertEqual(s["task_type"], "small_function")
        self.assertEqual(s["workflow_level"], "L1_review_light")
        self.assertEqual(s["test_template"], "regression_plus_boundary_adverse")  # upgraded by prior_fix_loop risk
        self.assertEqual(s["review_template"], "reviewer_light")
        self.assertEqual(s["git_policy"], "no_auto_commit")
        self.assertIn("prior_fix_loop", s["risk_flags"])

    def test_cli_output_is_short_summary(self):
        r = self._run("state", "record-quality-policy",
                      "--task-type", "small_function",
                      "--workflow-level", "L1_review_light",
                      "--reason", "test")
        # Output is short, not full template
        self.assertLess(len(r.stdout), 1000)
        self.assertIn("Quality policy recorded", r.stdout)
        self.assertIn("Test:", r.stdout)
        self.assertIn("Review:", r.stdout)

    def test_cli_does_not_touch_claude_md(self):
        claude_md_before = (self.tmp / "CLAUDE.md").read_text()
        self._run("state", "record-quality-policy",
                  "--task-type", "bug_fix", "--workflow-level", "L2_standard_team",
                  "--reason", "test")
        claude_md_after = (self.tmp / "CLAUDE.md").read_text()
        self.assertEqual(claude_md_before, claude_md_after)

    def test_cli_does_not_touch_settings_json(self):
        settings_before = (self.tmp / ".claude" / "settings.json").read_text()
        self._run("state", "record-quality-policy",
                  "--task-type", "api_endpoint", "--workflow-level", "L2_standard_team",
                  "--reason", "test")
        settings_after = (self.tmp / ".claude" / "settings.json").read_text()
        self.assertEqual(settings_before, settings_after)

    # ── Status injection ──
    def test_status_injects_quality_policy_summary(self):
        self._run("state", "record-quality-policy",
                  "--task-type", "small_function",
                  "--workflow-level", "L1_review_light",
                  "--reason", "test")
        inp = json.dumps({"session_id": "t", "cwd": str(self.tmp),
                         "hook_event_name": "UserPromptSubmit"})
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, str(self.tmp / "scripts" / "aiwf_status.py")],
                          input=inp, capture_output=True, text=True,
                          cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        out = json.loads(r.stdout.strip())
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Quality:", ctx)
        self.assertIn("L1_review_light", ctx)
        self.assertIn("small_function", ctx)
        self.assertIn("Templates:", ctx)
        self.assertIn("test=", ctx)
        self.assertIn("review=", ctx)
        # Must NOT contain raw JSON or full template text
        self.assertNotIn('"test_template"', ctx)

    def test_status_shows_not_selected_when_missing(self):
        inp = json.dumps({"session_id": "t", "cwd": str(self.tmp),
                         "hook_event_name": "UserPromptSubmit"})
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, str(self.tmp / "scripts" / "aiwf_status.py")],
                          input=inp, capture_output=True, text=True,
                          cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        out = json.loads(r.stdout.strip())
        ctx = out["hookSpecificOutput"]["additionalContext"]
        # Phase is "discussing" so it should NOT say "not selected yet" (only for implementing+)
        self.assertNotIn("not selected yet", ctx)

    def test_status_injection_is_short(self):
        self._run("state", "record-quality-policy",
                  "--task-type", "small_function",
                  "--workflow-level", "L1_review_light",
                  "--reason", "test")
        inp = json.dumps({"session_id": "t", "cwd": str(self.tmp),
                         "hook_event_name": "UserPromptSubmit"})
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, str(self.tmp / "scripts" / "aiwf_status.py")],
                          input=inp, capture_output=True, text=True,
                          cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        out = json.loads(r.stdout.strip())
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertLess(len(ctx), 600)  # Still short — prompt cache safe

    # ── Skill text ──
    def test_planner_skill_mentions_cli_not_hand_edit(self):
        content = (self.tmp / ".claude" / "skills" / "aiwf-planner" / "SKILL.md").read_text()
        self.assertIn("record-quality-policy", content)
        self.assertIn("Do NOT hand-edit", content)



    # ── escalation fields ──

    def test_security_sensitive_writes_escalation_fields(self):
        self._run("state", "record-quality-policy",
                  "--task-type", "security_sensitive",
                  "--workflow-level", "L0_direct",
                  "--reason", "test")
        s = _rj(self.tmp / ".aiwf" / "state" / "state.json")
        self.assertEqual(s["recommended_minimum_level"], "L3_full_power")
        self.assertTrue(s["requires_user_decision"])
        self.assertTrue(s["quality_escalation_required"])
        self.assertNotEqual(s["quality_escalation_reason"], "")

    def test_small_function_no_escalation(self):
        self._run("state", "record-quality-policy",
                  "--task-type", "small_function",
                  "--workflow-level", "L1_review_light",
                  "--reason", "test")
        s = _rj(self.tmp / ".aiwf" / "state" / "state.json")
        self.assertFalse(s["quality_escalation_required"])
        self.assertFalse(s["requires_user_decision"])

    def test_status_shows_quality_policy(self):
        self._run("state", "record-quality-policy",
                  "--task-type", "api_endpoint",
                  "--workflow-level", "L2_standard_team",
                  "--reason", "test")
        r = self._run("status")
        self.assertIn("Task type: api_endpoint", r.stdout)
        self.assertIn("Test:", r.stdout)
        self.assertIn("Review:", r.stdout)
        self.assertIn("Git:", r.stdout)

    def test_status_shows_escalation_warning(self):
        self._run("state", "record-quality-policy",
                  "--task-type", "security_sensitive",
                  "--workflow-level", "L0_direct",
                  "--reason", "test")
        r = self._run("status")
        self.assertIn("Escalation required", r.stdout)
        self.assertIn("L3_full_power", r.stdout)

    def test_state_no_subcommand_no_traceback(self):
        env = __import__('os').environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = __import__('subprocess').run(
            [__import__('sys').executable, "-m", "aiwf_core.cli", "state"],
            capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=10)
        # Must not be a traceback
        self.assertNotIn("Traceback", r.stderr)
        self.assertNotIn("AttributeError", r.stderr)
        self.assertIn("State Operations", r.stdout)

    def test_get_state_summary_has_quality_fields(self):
        self._run("state", "record-quality-policy",
                  "--task-type", "small_function",
                  "--workflow-level", "L1_review_light",
                  "--reason", "test")
        from aiwf_core.core.state_ops import get_state_summary
        summary = get_state_summary(str(self.tmp))
        self.assertEqual(summary["task_type"], "small_function")
        self.assertEqual(summary["test_template"], "targeted_plus_small_regression")
        self.assertIn("quality_escalation_required", summary)


if __name__ == "__main__":
    unittest.main()
