"""Quality brief: task-specific goal.json brief, heavy-testing cleanup."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

def _install(cwd):
    env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
    subprocess.run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                   capture_output=True, text=True, cwd=str(cwd), env=env, timeout=20)

def _rj(path): return json.loads(path.read_text())

class TestQualityBrief(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awqb_"))
        _install(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        from aiwf_core.core.state_schema import MVP_STATE_FILES
        for fn, dfn in MVP_STATE_FILES.items():
            p = self.tmp / ".aiwf" / fn; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(dfn(), indent=2) + "\n")

    # ── goal schema ──
    def test_default_goal_has_quality_brief(self):
        g = _rj(self.tmp / ".aiwf" / "state" / "goal.json")
        self.assertIn("quality_brief", g)
        brief = g["quality_brief"]
        for field in ["acceptance_criteria", "test_focus", "review_focus",
                       "non_goals", "escalation_triggers"]:
            self.assertIn(field, brief, f"missing {field}")
            self.assertIsInstance(brief[field], list)

    # ── record_quality_brief ──
    def test_record_quality_brief_writes_goal(self):
        from aiwf_core.core.state_ops import record_quality_brief
        record_quality_brief(str(self.tmp),
            acceptance_criteria=["subtract returns a-b for finite numbers"],
            test_focus=["normal subtraction", "negative operands"],
            review_focus=["no unrelated numeric change"],
            non_goals=["do not redesign validation"],
            escalation_triggers=["shared validator change → L2"])
        g = _rj(self.tmp / ".aiwf" / "state" / "goal.json")
        brief = g["quality_brief"]
        self.assertEqual(len(brief["acceptance_criteria"]), 1)
        self.assertEqual(len(brief["test_focus"]), 2)
        self.assertEqual(brief["non_goals"][0], "do not redesign validation")

    def test_record_quality_brief_preserves_active_goal(self):
        from aiwf_core.core.state_ops import record_quality_brief
        # Pre-set goal
        g = _rj(self.tmp / ".aiwf" / "state" / "goal.json")
        g["active_goal"] = "add subtract to calculator"
        g["confirmed"] = True
        (self.tmp / ".aiwf" / "state" / "goal.json").write_text(json.dumps(g, indent=2))
        record_quality_brief(str(self.tmp), test_focus=["subtract"])
        g2 = _rj(self.tmp / ".aiwf" / "state" / "goal.json")
        self.assertEqual(g2["active_goal"], "add subtract to calculator")
        self.assertTrue(g2["confirmed"])

    def test_record_quality_brief_no_template_fulltext(self):
        from aiwf_core.core.state_ops import record_quality_brief
        record_quality_brief(str(self.tmp), test_focus=["test a"])
        g = _rj(self.tmp / ".aiwf" / "state" / "goal.json")
        text = json.dumps(g["quality_brief"])
        self.assertLess(len(text), 1000, "brief must be short")

    # ── skill text ──
    def test_planner_skill_mentions_quality_brief(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-planner" / "SKILL.md").read_text()
        self.assertIn("record-quality-brief", c)
        self.assertIn("quality", c.lower())

    def test_test_skill_reads_test_focus(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-test" / "SKILL.md").read_text()
        self.assertIn("test_focus", c)
        self.assertIn("use context.test_focus first", c.lower())

    def test_review_skill_reads_review_focus(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-review" / "SKILL.md").read_text()
        self.assertIn("review_focus", c)
        self.assertIn("non_goals", c)

    # ── heavy-testing cleanup ──
    def test_no_comprehensive_validation_language(self):
        for path in [".claude/skills/aiwf-test/SKILL.md",
                      ".claude/agents/aiwf-tester.md"]:
            c = (self.tmp / path).read_text()
            self.assertNotIn("comprehensive validation", c.lower(), f"{path} has old language")
            self.assertNotIn("deep testing: happy path", c.lower(), f"{path} has old language")

    def test_no_all_required_in_test_skill(self):
        c = (self.tmp / ".claude" / "skills" / "aiwf-test" / "SKILL.md").read_text()
        self.assertNotIn("all required", c.lower())

    def test_tester_agent_description_updated(self):
        c = (self.tmp / ".claude" / "agents" / "aiwf-tester.md").read_text()
        self.assertIn("template-guided", c.lower())

    # ── prompt cache ──
    def test_status_does_not_dump_quality_brief(self):
        """UserPromptSubmit must not inject the full quality_brief."""
        from aiwf_core.core.state_ops import record_quality_brief
        record_quality_brief(str(self.tmp),
            test_focus=["a","b","c"], review_focus=["x","y"],
            acceptance_criteria=["must work"], non_goals=["no redesign"],
            escalation_triggers=["if fail"])
        inp = json.dumps({"session_id":"t","cwd":str(self.tmp),"hook_event_name":"UserPromptSubmit"})
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, str(self.tmp/"scripts"/"aiwf_status.py")],
                          input=inp, capture_output=True, text=True,
                          cwd=str(self.tmp), env=env, timeout=10)
        out = json.loads(r.stdout.strip())
        ctx = out["hookSpecificOutput"]["additionalContext"]
        # Must NOT contain the full brief lists
        self.assertNotIn("must work", ctx)
        self.assertNotIn("no redesign", ctx)


if __name__ == "__main__":
    unittest.main()
