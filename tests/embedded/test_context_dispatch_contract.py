"""Context dispatch contract: per-context purpose, hints, non_goals, focus, triggers."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

def _install(cwd):
    env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
    subprocess.run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                   capture_output=True, text=True, cwd=str(cwd), env=env, timeout=20)

class TestContextDispatch(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awcd_"))
        _install(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        from aiwf_core.core.state_schema import MVP_STATE_FILES
        for fn, dfn in MVP_STATE_FILES.items():
            p = self.tmp / ".aiwf" / fn; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(dfn(), indent=2) + "\n")

    def test_start_context_creates_dispatch_fields(self):
        from aiwf_core.core.state_ops import start_context
        ctxs = start_context(str(self.tmp), "CTX-MOD", "Modulo feature",
                            allowed_write=["src/calc.js"])
        ctx = [c for c in ctxs["contexts"] if c["id"] == "CTX-MOD"][0]
        for field in ["purpose", "read_hints", "non_goals", "dependencies",
                       "interface_contract", "test_focus", "review_focus",
                       "escalation_triggers"]:
            self.assertIn(field, ctx, f"Missing dispatch field: {field}")
        # Defaults
        self.assertEqual(ctx["purpose"], "")
        self.assertEqual(ctx["read_hints"], [])
        self.assertEqual(ctx["non_goals"], [])

    def test_start_context_writes_dispatch_values(self):
        from aiwf_core.core.state_ops import start_context
        ctxs = start_context(str(self.tmp), "CTX-DISP", "Dispatch test",
                            allowed_write=["src/a.py"],
                            purpose="Test subtract feature",
                            read_hints=["src/calc.js", "test/calc.test.js"],
                            non_goals=["do not touch auth"],
                            interface_contract="function subtract(a,b) returns number")
        ctx = [c for c in ctxs["contexts"] if c["id"] == "CTX-DISP"][0]
        self.assertEqual(ctx["purpose"], "Test subtract feature")
        self.assertEqual(ctx["read_hints"], ["src/calc.js", "test/calc.test.js"])
        self.assertEqual(ctx["non_goals"], ["do not touch auth"])
        self.assertEqual(ctx["interface_contract"], "function subtract(a,b) returns number")

    def test_start_context_update_preserves_existing_dispatch(self):
        from aiwf_core.core.state_ops import start_context
        start_context(str(self.tmp), "CTX-UPD", "Original", allowed_write=["src/a.py"],
                     purpose="original purpose", test_focus=["old test"])
        ctxs = start_context(str(self.tmp), "CTX-UPD", "Updated",
                            review_focus=["new review"], escalation_triggers=["new trigger"])
        ctx = [c for c in ctxs["contexts"] if c["id"] == "CTX-UPD"][0]
        self.assertEqual(ctx["title"], "Updated")
        self.assertEqual(ctx["purpose"], "original purpose")  # preserved
        self.assertEqual(ctx["test_focus"], ["old test"])  # preserved
        self.assertEqual(ctx["review_focus"], ["new review"])  # updated
        self.assertEqual(ctx["escalation_triggers"], ["new trigger"])  # updated

    def test_dispatch_fields_do_not_affect_scope_policy(self):
        """allowed_write still controls scope; dispatch fields are advisory."""
        from aiwf_core.core.state_ops import start_context
        ctxs = start_context(str(self.tmp), "CTX-TEST",
                            allowed_write=["src/calc.js"])
        ctx = [c for c in ctxs["contexts"] if c["id"] == "CTX-TEST"][0]
        self.assertEqual(ctx["allowed_write"], ["src/calc.js"])
        self.assertEqual(ctx["read_hints"], [])  # advisory, not scope

    def test_planner_skill_has_dispatch_fields(self):
        content = (self.tmp / ".claude" / "skills" / "aiwf-planner" / "SKILL.md").read_text()
        for field in ["read_hints", "non_goals", "dependencies", "interface_contract",
                       "test_focus", "review_focus", "escalation_triggers"]:
            self.assertIn(field, content.lower(),
                         f"Planner skill should mention '{field}'")

    def test_test_skill_has_context_dispatch_refs(self):
        content = (self.tmp / ".claude" / "skills" / "aiwf-test" / "SKILL.md").read_text()
        self.assertIn("context.test_focus", content.lower())
        self.assertIn("context.escalation_triggers", content.lower())

    def test_review_skill_has_plan_scope_refs(self):
        content = (self.tmp / ".claude" / "skills" / "aiwf-review" / "SKILL.md").read_text()
        self.assertIn("review_focus", content.lower())
        self.assertIn("non_goals", content.lower())
        self.assertIn("interface_contract", content.lower())
        self.assertIn("plans.json", content.lower())

    def test_status_does_not_dump_context_dispatch(self):
        from aiwf_core.core.state_ops import start_context
        start_context(str(self.tmp), "CTX-X", "Test",
                     allowed_write=["src/x.js"])
        inp = json.dumps({"session_id":"t","cwd":str(self.tmp),"hook_event_name":"UserPromptSubmit"})
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, str(self.tmp/"scripts"/"aiwf_status.py")],
                          input=inp, capture_output=True, text=True,
                          cwd=str(self.tmp), env=env, timeout=10)
        out = json.loads(r.stdout.strip())
        ctx_text = out["hookSpecificOutput"]["additionalContext"]
        self.assertNotIn("read_hints", ctx_text)
        self.assertNotIn("interface_contract", ctx_text)


if __name__ == "__main__":
    unittest.main()
