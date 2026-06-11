"""Lesson admission: quality gates for recording lessons, not general summaries."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

def _install(cwd):
    env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
    subprocess.run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                   capture_output=True, text=True, cwd=str(cwd), env=env, timeout=20)

class TestLessonAdmission(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awla_"))
        _install(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_admission_doc_exists(self):
        doc = PROJECT_ROOT / "docs" / "AIWF-LESSON-ADMISSION-POLICY.md"
        self.assertTrue(doc.exists(), "Lesson admission doc missing")
        content = doc.read_text()
        self.assertIn("applies_to", content)
        self.assertIn("affects", content)
        self.assertIn("source", content)
        self.assertIn("expires_when", content)
        self.assertIn("not record", content.lower())

    def test_admission_doc_rejects_general_summaries(self):
        doc = (PROJECT_ROOT / "docs" / "AIWF-LESSON-ADMISSION-POLICY.md").read_text()
        self.assertIn("Task completed successfully", doc)
        self.assertIn("Tests passed", doc)
        self.assertIn("future", doc.lower())
        self.assertIn("applies_to", doc)
        self.assertIn("affects", doc)
        self.assertIn("source", doc)
        self.assertIn("expires_when", doc)

    def test_review_skill_mentions_lesson_admission(self):
        content = (self.tmp / ".claude" / "skills" / "aiwf-review" / "SKILL.md").read_text()
        self.assertIn("planner", content.lower())
        self.assertIn("review", content.lower())

    def test_curator_agent_no_legacy_files(self):
        content = (self.tmp / ".claude" / "agents" / "aiwf-curator.md").read_text()
        self.assertNotIn(".aiwf/lessons.md", content)
        self.assertNotIn(".aiwf/negative-memory.md", content)
        self.assertIn("review.json", content)

    def test_curator_agent_when_unsure_do_not_record(self):
        content = (self.tmp / ".claude" / "agents" / "aiwf-curator.md").read_text()
        self.assertIn("lesson", content.lower())

    def test_status_does_not_dump_all_lessons(self):
        from aiwf_core.core.state_schema import MVP_STATE_FILES
        for fn, dfn in MVP_STATE_FILES.items():
            p = self.tmp / ".aiwf" / fn; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(dfn(), indent=2) + "\n")
        r = json.loads((self.tmp / ".aiwf" / "quality" / "review.json").read_text())
        r["lessons"] = ["secret lesson abc", "another secret xyz"]
        (self.tmp / ".aiwf" / "quality" / "review.json").write_text(json.dumps(r, indent=2))
        inp = json.dumps({"session_id":"t","cwd":str(self.tmp),"hook_event_name":"UserPromptSubmit"})
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r2 = subprocess.run([sys.executable, str(self.tmp/"scripts"/"aiwf_status.py")],
                           input=inp, capture_output=True, text=True,
                           cwd=str(self.tmp), env=env, timeout=10)
        out = json.loads(r2.stdout.strip())
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertNotIn("secret lesson abc", ctx)
        self.assertNotIn("another secret xyz", ctx)


if __name__ == "__main__":
    unittest.main()
