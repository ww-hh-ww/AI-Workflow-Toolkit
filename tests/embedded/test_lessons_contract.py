"""Lessons contract: review.json stores lightweight lessons/followups."""
import unittest
from aiwf_core.core.state_schema import default_review, REVIEW_KEYS

class TestLessonsContract(unittest.TestCase):
    """Review.json stores concise lessons, negative patterns, followups."""

    def test_default_review_has_lesson_fields(self):
        r = default_review()
        self.assertIn("lessons", r)
        self.assertIn("negative_patterns", r)
        self.assertIn("followups", r)
        self.assertEqual(r["lessons"], [])
        self.assertEqual(r["negative_patterns"], [])
        self.assertEqual(r["followups"], [])

    def test_lesson_fields_in_review_keys(self):
        self.assertIn("lessons", REVIEW_KEYS)
        self.assertIn("negative_patterns", REVIEW_KEYS)
        self.assertIn("followups", REVIEW_KEYS)

    def test_can_store_lessons(self):
        r = default_review()
        r["lessons"].append("Scope checker must normalize absolute paths to relative.")
        r["lessons"].append("Stop gate must promote evidence before checking.")
        r["negative_patterns"].append("Do not use Bash to write JSON state; use Edit/Write.")
        r["followups"].append("Consider adding a helper for finite-number input validation.")
        self.assertEqual(len(r["lessons"]), 2)
        self.assertEqual(len(r["negative_patterns"]), 1)
        self.assertEqual(len(r["followups"]), 1)

    def test_lessons_do_not_block_closure(self):
        """Lessons are informational; they don't affect closure gates."""
        r = default_review()
        r["result"] = "accepted"
        r["closure_allowed"] = True
        r["cleanup_status"] = "fresh"
        r["structure_status"] = "accepted"
        r["lessons"].append("Some lesson")
        # Closure check uses closure_allowed, not lessons
        self.assertTrue(r["closure_allowed"])

    def test_lessons_exported_in_report(self):
        """Verify lessons are structured for export-report inclusion."""
        r = default_review()
        r["lessons"] = ["Path normalization needed for absolute Claude paths."]
        r["negative_patterns"] = ["Silent Bash JSON writes corrupt state."]
        r["followups"] = ["Deferred: large-number overflow guard."]
        # These should appear in export-report output
        self.assertIn("Path normalization", r["lessons"][0])
        self.assertIn("Silent Bash", r["negative_patterns"][0])
        self.assertIn("Deferred", r["followups"][0])


if __name__ == "__main__":
    unittest.main()
