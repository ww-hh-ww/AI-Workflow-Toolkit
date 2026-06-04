"""Deterministic state operations: context, testing, cleanup, close."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

def _install(cwd):
    env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
    subprocess.run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                   capture_output=True, text=True, cwd=str(cwd), env=env, timeout=20)

def _rj(path): return json.loads(path.read_text())

class TestStateOps(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awso_"))
        _install(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        from aiwf_core.core.state_schema import MVP_STATE_FILES
        for fn, dfn in MVP_STATE_FILES.items():
            p = self.tmp / ".aiwf" / fn; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(dfn(), indent=2) + "\n")

    # ── context ──
    def test_start_context_creates_new_context(self):
        from aiwf_core.core.state_ops import start_context
        ctxs = start_context(str(self.tmp), "CTX-MOD", "Modulo feature",
                            allowed_write=["src/calc.js", "test/calc.test.js"],
                            note="Pilot context")
        self.assertTrue(any(c["id"] == "CTX-MOD" for c in ctxs["contexts"]))
        state = _rj(self.tmp / ".aiwf" / "state" / "state.json")
        self.assertEqual(state["active_context_id"], "CTX-MOD")
        self.assertEqual(state["phase"], "implementing")

    def test_start_context_upserts_existing(self):
        from aiwf_core.core.state_ops import start_context
        start_context(str(self.tmp), "CTX-MOD", allowed_write=["old.py"])
        ctxs = start_context(str(self.tmp), "CTX-MOD", label="Updated",
                            allowed_write=["new.py"])
        ctx = [c for c in ctxs["contexts"] if c["id"] == "CTX-MOD"][0]
        self.assertEqual(ctx["title"], "Updated")
        self.assertEqual(ctx["allowed_write"], ["new.py"])

    # ── testing ──
    def test_record_testing_writes_consistently(self):
        from aiwf_core.core.state_ops import record_testing
        t = record_testing(str(self.tmp), "CTX-MOD", "adequate",
                          commands=["pytest -xvs"], untested_risks=["overflow"])
        self.assertEqual(t["status"], "adequate")
        self.assertEqual(t["context_id"], "CTX-MOD")
        self.assertEqual(t["commands"], ["pytest -xvs"])
        self.assertIn("overflow", t["untested_risks"])

    # ── cleanup ──
    def test_mark_cleanup_fresh_clears_stale_items(self):
        from aiwf_core.core.state_ops import mark_cleanup_stale, mark_cleanup_fresh
        mark_cleanup_stale(str(self.tmp), ["old context CTX-OLD"],
                          blockers=["stale context"], notes=["stale warning"])
        r = _rj(self.tmp / ".aiwf" / "quality" / "review.json")
        self.assertEqual(r["cleanup_status"], "stale")
        self.assertEqual(len(r["stale_items"]), 1)

        mark_cleanup_fresh(str(self.tmp), resolved_notes=["Removed CTX-OLD"])
        r = _rj(self.tmp / ".aiwf" / "quality" / "review.json")
        self.assertEqual(r["cleanup_status"], "fresh")
        self.assertEqual(r["cleanup_blockers"], [])
        self.assertEqual(r["stale_items"], [])
        self.assertIn("Removed CTX-OLD", r["cleanup_notes"])

    def test_mark_cleanup_fresh_filters_stale_notes(self):
        from aiwf_core.core.state_ops import mark_cleanup_fresh
        # Pre-seed stale notes
        r = _rj(self.tmp / ".aiwf" / "quality" / "review.json")
        r["cleanup_notes"] = ["old stale context", "valid note", "STALE data"]
        r["stale_items"] = ["x"]
        (self.tmp / ".aiwf" / "quality" / "review.json").write_text(json.dumps(r, indent=2))

        mark_cleanup_fresh(str(self.tmp))  # No explicit resolved_notes
        r = _rj(self.tmp / ".aiwf" / "quality" / "review.json")
        # stale-related notes are filtered
        for n in r["cleanup_notes"]:
            self.assertNotIn("stale", n.lower())

    def test_cannot_be_fresh_while_stale_items_nonempty(self):
        """Cleanup invariant: fresh requires empty stale_items and no blockers."""
        from aiwf_core.core.state_ops import mark_cleanup_fresh
        # Pre-seed stale state, then mark fresh (which clears them)
        r = _rj(self.tmp / ".aiwf" / "quality" / "review.json")
        r["stale_items"] = ["stale-context"]
        r["cleanup_blockers"] = ["blocker"]
        (self.tmp / ".aiwf" / "quality" / "review.json").write_text(json.dumps(r, indent=2))

        mark_cleanup_fresh(str(self.tmp))
        r = _rj(self.tmp / ".aiwf" / "quality" / "review.json")
        self.assertEqual(r["cleanup_status"], "fresh")
        self.assertEqual(r["stale_items"], [])
        self.assertEqual(r["cleanup_blockers"], [])

    # ── close ──
    def test_prepare_close_promotes_evidence(self):
        s = _rj(self.tmp / ".aiwf" / "state" / "state.json")
        s["phase"] = "reviewing"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(s, indent=2))
        # Seed pending evidence + accepted review
        (self.tmp / ".aiwf" / "evidence" / "records.json").write_text(json.dumps({
            "records": [{"id": "EV-001", "status": "pending", "trust": "machine_observed"}]
        }, indent=2))
        (self.tmp / ".aiwf" / "quality" / "review.json").write_text(json.dumps({
            "result": "accepted", "closure_allowed": True,
            "accepted_evidence_ids": ["EV-001"], "rejected_evidence_ids": [],
            "blockers": [], "cleanup_status": "fresh", "structure_status": "accepted"
        }, indent=2))
        (self.tmp / ".aiwf" / "quality" / "testing.json").write_text(json.dumps({
            "status": "adequate", "commands": ["pytest"]
        }, indent=2))

        from aiwf_core.core.state_ops import prepare_close
        result = prepare_close(str(self.tmp))

        self.assertTrue(result["close_attempt_set"])
        self.assertEqual(result["state"]["phase"], "closing")

        ev = _rj(self.tmp / ".aiwf" / "evidence" / "records.json")
        self.assertEqual(ev["records"][0]["status"], "accepted")

    def test_prepare_close_fills_missing_review_fields(self):
        s = _rj(self.tmp / ".aiwf" / "state" / "state.json")
        s["phase"] = "reviewing"
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(s, indent=2))
        (self.tmp / ".aiwf" / "quality" / "review.json").write_text(json.dumps({
            "result": "accepted", "closure_allowed": True
        }, indent=2))
        (self.tmp / ".aiwf" / "evidence" / "records.json").write_text(json.dumps({
            "records": [{"id": "EV-001", "status": "accepted", "trust": "machine_observed"}]
        }, indent=2))
        (self.tmp / ".aiwf" / "quality" / "testing.json").write_text(json.dumps({
            "status": "adequate", "commands": ["pytest"]
        }, indent=2))

        from aiwf_core.core.state_ops import prepare_close
        result = prepare_close(str(self.tmp))
        self.assertTrue(result["auto_filled"])

        r = _rj(self.tmp / ".aiwf" / "quality" / "review.json")
        self.assertIn("cleanup_status", r)
        self.assertIn("structure_status", r)

    # ── state summary ──
    def test_get_state_summary(self):
        from aiwf_core.core.state_ops import get_state_summary
        s = get_state_summary(str(self.tmp))
        self.assertEqual(s["phase"], "discussing")
        self.assertEqual(s["complexity"], "standard")
        self.assertIn("review_result", s)
        self.assertIn("cleanup_status", s)


if __name__ == "__main__":
    unittest.main()
