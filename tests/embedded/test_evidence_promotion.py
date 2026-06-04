"""Evidence promotion: review auto-accepts/rejects evidence, closure flows clean."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 10


class TestEvidencePromotion(unittest.TestCase):
    """Review accepted_evidence_ids promote evidence status automatically."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="awpr_"))
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        subprocess.run([sys.executable, "-m", "aiwf_core.cli",
                        "install", "claude", "--force"],
                       capture_output=True, text=True,
                       cwd=str(self.tmp), env=env, timeout=20)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _read(self, rel):
        return json.loads((self.tmp / rel).read_text())

    def _write(self, rel, data):
        (self.tmp / rel).write_text(json.dumps(data, indent=2))

    def _stop(self):
        inp = json.dumps({"session_id": "t", "cwd": str(self.tmp),
                         "hook_event_name": "Stop"})
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable,
                           str(self.tmp / "scripts" / "aiwf_review_gate.py")],
                          input=inp, capture_output=True, text=True,
                          cwd=str(self.tmp), env=env, timeout=TIMEOUT)
        return r.returncode, r.stdout.strip()

    def test_promote_accepts_matching_evidence_ids(self):
        """Evidence records matching accepted_evidence_ids become accepted."""
        # Seed pending evidence
        self._write(".aiwf/evidence/records.json", {
            "records": [
                {"id": "EV-001", "status": "pending", "trust": "machine_observed",
                 "changed_files": ["src/a.py"]},
                {"id": "EV-002", "status": "pending", "trust": "machine_observed",
                 "changed_files": ["test/a.test.js"]},
                {"id": "EV-003", "status": "pending", "trust": "machine_observed",
                 "changed_files": ["danger/x.py"]},
            ]
        })
        # Set review with accepted IDs
        self._write(".aiwf/quality/review.json", {
            "result": "accepted", "closure_allowed": True,
            "accepted_evidence_ids": ["EV-001", "EV-002"],
            "rejected_evidence_ids": ["EV-003"],
            "blockers": [], "cleanup_status": "fresh", "structure_status": "accepted"
        })

        from aiwf_core.core.review_contract import promote_and_save
        result = promote_and_save(
            str(self.tmp), ".aiwf/evidence/records.json", ".aiwf/quality/review.json")
        self.assertIsNotNone(result)

        records = result["records"]
        ev1 = [r for r in records if r["id"] == "EV-001"][0]
        ev2 = [r for r in records if r["id"] == "EV-002"][0]
        ev3 = [r for r in records if r["id"] == "EV-003"][0]

        self.assertEqual(ev1["status"], "accepted")
        self.assertEqual(ev2["status"], "accepted")
        self.assertEqual(ev3["status"], "rejected")

    def test_no_accepted_ids_leaves_evidence_unchanged(self):
        """When review has no accepted/rejected IDs, evidence is not modified."""
        self._write(".aiwf/evidence/records.json", {
            "records": [{"id": "EV-001", "status": "pending"}]
        })
        self._write(".aiwf/quality/review.json", {
            "result": "unknown", "closure_allowed": False,
            "accepted_evidence_ids": [], "rejected_evidence_ids": [], "blockers": [], "cleanup_status": "fresh", "structure_status": "accepted"
        })

        from aiwf_core.core.review_contract import promote_and_save
        result = promote_and_save(
            str(self.tmp), ".aiwf/evidence/records.json", ".aiwf/quality/review.json")
        self.assertEqual(result["records"][0]["status"], "pending")

    def test_stop_gate_promotes_evidence_automatically(self):
        """Stop gate promotes evidence from review before checking gates."""
        # Seed pending evidence
        self._write(".aiwf/evidence/records.json", {
            "records": [
                {"id": "EV-001", "status": "pending", "trust": "machine_observed",
                 "changed_files": ["src/a.py"]},
                {"id": "EV-002", "status": "pending", "trust": "machine_observed",
                 "changed_files": ["danger/x.py"]},
            ]
        })
        # Review accepts EV-001, rejects EV-002
        self._write(".aiwf/quality/review.json", {
            "result": "accepted", "closure_allowed": True,
            "accepted_evidence_ids": ["EV-001"],
            "rejected_evidence_ids": ["EV-002"],
            "blockers": [], "cleanup_status": "fresh", "structure_status": "accepted"
        })
        self._write(".aiwf/quality/testing.json", {
            "status": "adequate", "commands": ["pytest"], "untested_risks": []
        })
        self._write(".aiwf/state/fix-loop.json", {
            "status": "none", "route": None, "required_fixes": []
        })
        state = self._read(".aiwf/state/state.json")
        state["phase"] = "closing"
        state["close_attempt"] = True
        self._write(".aiwf/state/state.json", state)

        # Evidence is pending BEFORE running stop gate
        ev = self._read(".aiwf/evidence/records.json")
        self.assertEqual(ev["records"][0]["status"], "pending")
        self.assertEqual(ev["records"][1]["status"], "pending")

        # Run stop gate — it should promote automatically
        rc, out = self._stop()

        # After stop gate: EV-001 promoted to accepted, EV-002 to rejected
        ev = self._read(".aiwf/evidence/records.json")
        self.assertEqual(ev["records"][0]["status"], "accepted",
                        "EV-001 should be auto-promoted to accepted by stop gate")
        self.assertEqual(ev["records"][1]["status"], "rejected",
                        "EV-002 should be auto-promoted to rejected by stop gate")

        # Closure should pass (evidence promoted + other gates valid)
        self.assertNotIn('block', out,
                        f"Close should pass after auto-promotion, got: {out}")

    def test_stop_gate_blocks_when_no_accepted_ids(self):
        """When review has zero accepted_evidence_ids, promotion still runs but gate blocks."""
        self._write(".aiwf/evidence/records.json", {
            "records": [
                {"id": "EV-001", "status": "pending", "trust": "machine_observed"},
            ]
        })
        self._write(".aiwf/quality/review.json", {
            "result": "accepted", "closure_allowed": True,
            "accepted_evidence_ids": [], "rejected_evidence_ids": [],
            "blockers": [], "cleanup_status": "fresh", "structure_status": "accepted"
        })
        self._write(".aiwf/quality/testing.json", {
            "status": "adequate", "commands": ["pytest"], "untested_risks": []
        })
        self._write(".aiwf/state/fix-loop.json", {
            "status": "none", "route": None, "required_fixes": []
        })
        state = self._read(".aiwf/state/state.json")
        state["phase"] = "closing"
        state["close_attempt"] = True
        self._write(".aiwf/state/state.json", state)

        rc, out = self._stop()
        # No accepted evidence → still blocks
        self.assertIn('block', out,
                     "Should block when no evidence IDs are accepted")

    def test_promotion_preserves_non_matching_records(self):
        """Records not in accepted or rejected IDs keep their original status."""
        self._write(".aiwf/evidence/records.json", {
            "records": [
                {"id": "EV-001", "status": "pending"},
                {"id": "EV-002", "status": "pending"},
                {"id": "EV-003", "status": "pending"},
            ]
        })
        self._write(".aiwf/quality/review.json", {
            "result": "accepted", "closure_allowed": True,
            "accepted_evidence_ids": ["EV-001"],
            "rejected_evidence_ids": [],
            "blockers": [], "cleanup_status": "fresh", "structure_status": "accepted"
        })

        from aiwf_core.core.review_contract import promote_and_save
        result = promote_and_save(
            str(self.tmp), ".aiwf/evidence/records.json", ".aiwf/quality/review.json")

        statuses = {r["id"]: r["status"] for r in result["records"]}
        self.assertEqual(statuses["EV-001"], "accepted")
        self.assertEqual(statuses["EV-002"], "pending")  # unchanged
        self.assertEqual(statuses["EV-003"], "pending")  # unchanged


if __name__ == "__main__":
    unittest.main()
