"""Focused gate contract — Stop hook mechanical, close_attempt-based only."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 10


def _run_script(script_path, stdin_json, cwd):
    env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
    return subprocess.run([sys.executable, str(script_path)], input=stdin_json,
                          capture_output=True, text=True,
                          cwd=str(cwd), env=env, timeout=TIMEOUT)


class TestGates(unittest.TestCase):
    """Stop gate: mechanical, only on close_attempt=true."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awgt_"))
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        subprocess.run([sys.executable, "-m", "aiwf_core.cli",
                        "install", "claude", "--force"],
                       capture_output=True, text=True,
                       cwd=str(cls.tmp), env=env, timeout=20)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        from aiwf_core.core.state_schema import MVP_STATE_FILES
        for fn, dfn in MVP_STATE_FILES.items():
            p = self.tmp / ".aiwf" / fn; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(dfn(), indent=2) + "\n")

    def _set_close_attempt(self):
        s = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        s["phase"] = "closing"
        s["close_attempt"] = True
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(s, indent=2))

    def _stop(self):
        inp = json.dumps({"session_id": "t", "cwd": str(self.tmp),
                         "hook_event_name": "Stop"})
        return _run_script(self.tmp / "scripts" / "aiwf_review_gate.py", inp, self.tmp)

    def _accept_all(self):
        (self.tmp / ".aiwf" / "quality" / "review.json").write_text(json.dumps(
            {"result": "accepted", "closure_allowed": True,
             "accepted_evidence_ids": ["EV-001"], "rejected_evidence_ids": [],
             "blockers": [], "cleanup_status": "fresh", "structure_status": "accepted"}, indent=2))
        (self.tmp / ".aiwf" / "evidence" / "records.json").write_text(json.dumps(
            {"records": [{"id": "EV-001", "status": "accepted",
                          "trust": "machine_observed"}]}, indent=2))
        (self.tmp / ".aiwf" / "quality" / "testing.json").write_text(json.dumps(
            {"status": "adequate", "commands": ["pytest"], "untested_risks": []},
            indent=2))
        (self.tmp / ".aiwf" / "state" / "fix-loop.json").write_text(json.dumps(
            {"status": "none", "route": None, "required_fixes": []}, indent=2))

    def test_no_close_attempt_does_not_block(self):
        r = self._stop()
        self.assertNotIn('"decision"', r.stdout)

    def test_close_attempt_without_gates_blocks(self):
        self._set_close_attempt()
        r = self._stop()
        out = json.loads(r.stdout.strip())
        self.assertEqual(out["decision"], "block")

    def test_close_attempt_with_all_gates_passes(self):
        self._set_close_attempt()
        self._accept_all()
        r = self._stop()
        self.assertNotIn('"decision"', r.stdout.strip() or "{}")

    def test_core_closure_contract_blocks_on_missing_review(self):
        """Direct core logic test — no subprocess needed."""
        self._set_close_attempt()
        from aiwf_core.core.closure_contract import closure_conditions_met
        gates = closure_conditions_met(
            json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text()),
            json.loads((self.tmp / ".aiwf" / "evidence" / "records.json").read_text()),
            json.loads((self.tmp / ".aiwf" / "quality" / "testing.json").read_text()),
            json.loads((self.tmp / ".aiwf" / "quality" / "review.json").read_text()),
            json.loads((self.tmp / ".aiwf" / "state" / "fix-loop.json").read_text()),
        )
        self.assertTrue(gates["close_attempt"])
        self.assertFalse(gates["passed"])
        self.assertIn("review not accepted", gates["blockers"])


if __name__ == "__main__":
    unittest.main()
