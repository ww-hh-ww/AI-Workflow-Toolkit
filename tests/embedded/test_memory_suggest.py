"""Memory suggest: help safety, current-state.md, affects, non-mutation."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 15

class TestMemorySuggest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awms2_"))
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

    def _set_review(self, data):
        (self.tmp / ".aiwf" / "artifacts" / "quality" / "review.json").write_text(json.dumps(data, indent=2))

    def _set_cs(self, text):
        path = self.tmp / ".aiwf" / "artifacts" / "reports" / "当前状态.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    # help safety
    def test_memory_no_subcommand_shows_help(self):
        r = self._run("memory")
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn("suggest", r.stdout.lower())

    # review.json
    def test_retrieves_lesson(self):
        self._set_review({"lessons": [{"lesson": "Division tasks must test +0 and -0.", "applies_to": ["numeric_semantics"], "affects": ["test_focus"], "status": "active"}]})
        out = self._run("memory", "suggest", "--goal", "Add divide(a,b)", "--task-type", "numeric_semantics").stdout
        self.assertIn("Division", out)

    def test_reads_negative_patterns(self):
        r = json.loads((self.tmp / ".aiwf" / "artifacts" / "quality" / "review.json").read_text())
        r["negative_patterns"] = ["Do not redesign shared validation."]
        self._set_review(r)
        out = self._run("memory", "suggest", "--goal", "validation refactor").stdout
        self.assertIn("redesign", out.lower())

    def test_reads_followups(self):
        r = json.loads((self.tmp / ".aiwf" / "artifacts" / "quality" / "review.json").read_text())
        r["followups"] = ["Consider overflow policy task."]
        self._set_review(r)
        out = self._run("memory", "suggest", "--goal", "overflow policy").stdout
        self.assertIn("overflow", out.lower())

    # current-state.md
    def test_current_state_unrelated_not_retrieved(self):
        """Unrelated lesson must NOT be retrieved (stop words + min-length filter)."""
        self._set_cs("## Carry-forward lessons\n- Always use tabs for indentation.\n")
        out = self._run("memory", "suggest", "--goal", "Add divide(a,b)", "--task-type", "numeric_semantics").stdout
        self.assertNotIn("tabs", out.lower())
        self.assertNotIn("indentation", out.lower())

    def test_single_letter_tokens_no_match(self):
        """Single-letter tokens (a, b) should not cause false matches."""
        self._set_cs("## Carry-forward lessons\n- Always use tabs for indentation.\n")
        out = self._run("memory", "suggest", "--goal", "Add divide(a,b)", "--task-type", "numeric_semantics").stdout
        self.assertNotIn("tabs", out.lower())

    def test_stop_words_no_match(self):
        """Stop words like 'make', 'the' should not cause false matches."""
        self._set_cs("## Carry-forward lessons\n- Use tabs for indentation.\n")
        out = self._run("memory", "suggest", "--goal", "make the thing work", "--task-type", "small_function").stdout
        self.assertNotIn("tabs", out.lower())

    def test_applies_to_bonus_matches(self):
        """applies_to matching task_type provides strong relevance."""
        self._set_review({"lessons": [{"lesson": "Division boundary testing required.", "applies_to": ["numeric_semantics"], "affects": ["test_focus"], "status": "active"}]})
        out = self._run("memory", "suggest", "--goal", "write code", "--task-type", "numeric_semantics").stdout
        self.assertIn("Division", out)

    # affects -> suggested uses
    def test_affects_test_focus(self):
        self._set_review({"lessons": [{"lesson": "Division must test +0 and -0.", "applies_to": ["numeric_semantics"], "affects": ["test_focus"], "status": "active"}]})
        out = self._run("memory", "suggest", "--goal", "divide", "--task-type", "numeric_semantics").stdout
        self.assertIn("test_focus", out.lower())

    def test_affects_review_focus(self):
        self._set_review({"lessons": [{"lesson": "Review division boundary.", "applies_to": ["numeric_semantics"], "affects": ["review_focus"], "status": "active"}]})
        out = self._run("memory", "suggest", "--goal", "division boundary", "--task-type", "numeric_semantics").stdout
        self.assertIn("review_focus", out.lower())

    def test_affects_escalation(self):
        self._set_review({"lessons": [{"lesson": "Shared validation change escalates.", "applies_to": ["refactor"], "affects": ["escalation_triggers"], "status": "active"}]})
        out = self._run("memory", "suggest", "--goal", "validation refactor", "--task-type", "refactor").stdout
        self.assertIn("escalation_triggers", out.lower())

    # non-mutation
    def test_no_modify_goal_json(self):
        self._set_review({"lessons": [{"lesson": "test", "status": "active"}]})
        before = (self.tmp / ".aiwf" / "state" / "goal.json").read_text()
        self._run("memory", "suggest", "--goal", "test")
        self.assertEqual(before, (self.tmp / ".aiwf" / "state" / "goal.json").read_text())

    def test_no_modify_review_json(self):
        before = (self.tmp / ".aiwf" / "artifacts" / "quality" / "review.json").read_text()
        self._run("memory", "suggest", "--goal", "test")
        self.assertEqual(before, (self.tmp / ".aiwf" / "artifacts" / "quality" / "review.json").read_text())

    def test_no_modify_current_state(self):
        self._set_cs("## Carry-forward lessons\n- test\n")
        before = (self.tmp / ".aiwf" / "artifacts" / "reports" / "当前状态.md").read_text()
        self._run("memory", "suggest", "--goal", "test")
        self.assertEqual(before, (self.tmp / ".aiwf" / "artifacts" / "reports" / "当前状态.md").read_text())

    # output
    def test_output_advisory_footer(self):
        out = self._run("memory", "suggest", "--goal", "test").stdout
        self.assertIn("advisory", out.lower())

    # prompt cache
    def test_status_no_lesson_dump(self):
        self._set_review({"lessons": [{"lesson": "secret-lesson-xyz", "status": "active"}]})
        inp = json.dumps({"session_id": "t", "cwd": str(self.tmp), "hook_event_name": "UserPromptSubmit"})
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, str(self.tmp / "scripts" / "aiwf_status.py")],
                           input=inp, capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        ctx = json.loads(r.stdout.strip())["hookSpecificOutput"]["additionalContext"]
        self.assertNotIn("secret-lesson-xyz", ctx)



    # ── dedup ──
    def test_duplicate_lesson_appears_once_per_section(self):
        """Same lesson from review.json + current-state.md deduped in each section.
        API-level check: each section should contain the lesson at most once."""
        self._set_cs("## Carry-forward lessons\n- Division tasks must test +0 and -0.\n")
        self._set_review({"lessons": [{"lesson": "Division tasks must test +0 and -0.", "applies_to": ["numeric_semantics"], "affects": ["test_focus"], "status": "active"}]})
        from aiwf_core.core.memory import suggest_relevant_lessons
        result = suggest_relevant_lessons(str(self.tmp), goal="divide", task_type="numeric_semantics")
        needle = "Division tasks must test +0 and -0"
        # Relevant lessons: at most once
        rl_count = sum(1 for item in result["relevant_lessons"] if needle in item)
        self.assertEqual(rl_count, 1, f"Relevant lessons should have 1 occurrence, got {rl_count}")
        # Suggested test_focus: at most once (can appear here too — different purpose)
        st_count = sum(1 for item in result["suggested_test_focus"] if needle in item)
        self.assertLessEqual(st_count, 1, f"suggested_test_focus should have ≤1, got {st_count}")
        # Suggested review_focus: 0 (affects has test_focus, not review_focus)
        sr_count = sum(1 for item in result["suggested_review_focus"] if needle in item)
        self.assertEqual(sr_count, 0, f"suggested_review_focus should have 0, got {sr_count}")

    def test_dedup_within_suggested_test_focus(self):
        """Multiple affects=test_focus for same lesson should not duplicate in suggested_test_focus."""
        self._set_review({"lessons": [
            {"lesson": "Division must test +0 and -0.", "applies_to": ["numeric_semantics"], "affects": ["test_focus"], "status": "active"},
            {"lesson": "Review division boundary.", "applies_to": ["numeric_semantics"], "affects": ["test_focus"], "status": "active"},
        ]})
        from aiwf_core.core.memory import suggest_relevant_lessons
        result = suggest_relevant_lessons(str(self.tmp), goal="division boundary", task_type="numeric_semantics")
        c1 = sum(1 for item in result["suggested_test_focus"] if "Division must test" in item)
        c2 = sum(1 for item in result["suggested_test_focus"] if "Review division boundary" in item)
        self.assertLessEqual(c1, 1, f"Division lesson duplicated in suggested_test_focus: {c1}")
        self.assertLessEqual(c2, 1, f"Review lesson duplicated in suggested_test_focus: {c2}")

    # ── deferred risks ──
    def test_unrelated_deferred_risk_not_retrieved(self):
        self._set_cs("## Deferred risks\n- Always use tabs for indentation.\n")
        out = self._run("memory", "suggest", "--goal", "Add divide(a,b)", "--task-type", "numeric_semantics").stdout
        self.assertNotIn("tabs", out.lower())
