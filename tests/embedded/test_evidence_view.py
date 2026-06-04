"""Evidence view: accepted-only summaries, concise status, raw preserved."""
import json, unittest
from aiwf_core.core.evidence_view import (
    get_accepted_evidence, summarize_evidence,
    build_closure_evidence_summary, format_evidence_for_status,
)


class TestEvidenceView(unittest.TestCase):
    """Evidence view helpers produce concise, accepted-only summaries."""

    def setUp(self):
        self.ev = {"records": [
            {"id": "EV-001", "status": "pending", "changed_files": ["src/a.py"],
             "command": "npm test", "exit_code": 0, "trust": "machine_observed"},
            {"id": "EV-002", "status": "pending", "changed_files": ["test/a.test.js"],
             "command": "node test.js", "exit_code": 0, "trust": "machine_observed"},
            {"id": "EV-003", "status": "pending", "changed_files": ["danger/x.py"],
             "command": "echo hack", "exit_code": 1, "trust": "machine_observed"},
            {"id": "EV-004", "status": "accepted", "changed_files": ["src/b.py"],
             "trust": "machine_observed"},
            {"id": "EV-005", "status": "pending", "trust": "machine_observed"},
        ]}
        self.review = {
            "result": "accepted", "closure_allowed": True,
            "accepted_evidence_ids": ["EV-001", "EV-002"],
            "rejected_evidence_ids": ["EV-003"],
            "blockers": []
        }
        self.testing = {
            "status": "adequate", "commands": ["npm test"],
            "untested_risks": ["large overflow"], "deferred_out_of_scope": []
        }

    def test_get_accepted_by_review_ids(self):
        accepted = get_accepted_evidence(self.ev, self.review)
        ids = {r["id"] for r in accepted}
        self.assertIn("EV-001", ids)
        self.assertIn("EV-002", ids)
        # EV-004 has status="accepted" even if not in review ids
        self.assertIn("EV-004", ids)
        # EV-003 is rejected, EV-005 is pending
        self.assertNotIn("EV-003", ids)
        self.assertNotIn("EV-005", ids)

    def test_pending_not_included(self):
        self.review["accepted_evidence_ids"] = []
        accepted = get_accepted_evidence(self.ev, self.review)
        ids = {r["id"] for r in accepted}
        self.assertEqual(ids, {"EV-004"})  # Only the one with status=accepted

    def test_changed_files_deduplicated(self):
        summary = summarize_evidence(
            get_accepted_evidence(self.ev, self.review), raw_total=5)
        self.assertIn("src/a.py", summary["changed_files"])
        self.assertIn("test/a.test.js", summary["changed_files"])
        self.assertIn("src/b.py", summary["changed_files"])
        # danger/x.py is NOT in accepted evidence
        self.assertNotIn("danger/x.py", summary["changed_files"])

    def test_commands_summarized(self):
        summary = summarize_evidence(
            get_accepted_evidence(self.ev, self.review), raw_total=5)
        cmds = [c["command"] for c in summary["commands"]]
        self.assertIn("npm test", cmds)
        # Only accepted evidence commands are included
        self.assertNotIn("echo hack", cmds)

    def test_raw_count_preserved(self):
        summary = build_closure_evidence_summary(self.ev, self.review, self.testing)
        self.assertEqual(summary["raw_count"], 5)
        self.assertEqual(summary["accepted_count"], 3)  # EV-001, EV-002, EV-004

    def test_review_and_testing_in_summary(self):
        summary = build_closure_evidence_summary(self.ev, self.review, self.testing)
        self.assertEqual(summary["review_result"], "accepted")
        self.assertTrue(summary["closure_allowed"])
        self.assertEqual(summary["testing_status"], "adequate")
        self.assertIn("large overflow", summary["untested_risks"])

    def test_format_for_status_is_concise(self):
        summary = build_closure_evidence_summary(self.ev, self.review, self.testing)
        lines = format_evidence_for_status(summary)
        text = "\n".join(lines)
        self.assertIn("raw records: 5", text)
        self.assertIn("accepted: 3", text)
        self.assertIn("src/a.py", text)
        self.assertIn("npm test", text)
        # Should NOT dump all 5 raw records
        self.assertLess(len(text), 500)

    def test_raw_evidence_unchanged(self):
        """Calling view helpers does not mutate the original evidence dict."""
        orig = self.ev["records"][0]["status"]
        build_closure_evidence_summary(self.ev, self.review, self.testing)
        self.assertEqual(self.ev["records"][0]["status"], orig)


if __name__ == "__main__":
    unittest.main()
