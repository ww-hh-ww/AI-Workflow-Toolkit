"""Structure gate: structure_status must be accepted for closure."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

def _install(cwd):
    env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
    subprocess.run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                   capture_output=True, text=True, cwd=str(cwd), env=env, timeout=20)

class TestStructureGate(unittest.TestCase):
    """Closure requires structure_status=accepted."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awst_"))
        _install(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        from aiwf_core.core.state_schema import MVP_STATE_FILES
        for fn, dfn in MVP_STATE_FILES.items():
            p = self.tmp / ".aiwf" / fn; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(dfn(), indent=2) + "\n")

    def _set_close_attempt(self):
        s = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        s["phase"] = "closing"; s["close_attempt"] = True
        (self.tmp / ".aiwf" / "state" / "state.json").write_text(json.dumps(s, indent=2))

    def _accept_evidence(self):
        (self.tmp / ".aiwf" / "evidence" / "records.json").write_text(json.dumps(
            {"records": [{"id": "EV-001", "status": "accepted",
                          "trust": "machine_observed"}]}, indent=2))
        (self.tmp / ".aiwf" / "quality" / "testing.json").write_text(json.dumps(
            {"status": "adequate", "commands": ["pytest"], "untested_risks": []}, indent=2))
        (self.tmp / ".aiwf" / "state" / "fix-loop.json").write_text(json.dumps(
            {"status": "none", "route": None, "required_fixes": []}, indent=2))

    def _set_review(self, structure_status="unknown"):
        r = json.loads((self.tmp / ".aiwf" / "quality" / "review.json").read_text())
        r["result"] = "accepted"; r["closure_allowed"] = True
        r["accepted_evidence_ids"] = ["EV-001"]; r["blockers"] = []
        r["cleanup_status"] = "fresh"
        r["structure_status"] = structure_status
        (self.tmp / ".aiwf" / "quality" / "review.json").write_text(json.dumps(r, indent=2))

    def test_structure_unknown_blocks(self):
        self._set_close_attempt(); self._accept_evidence()
        self._set_review("unknown")
        from aiwf_core.core.closure_contract import closure_conditions_met
        gates = closure_conditions_met(
            json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text()),
            json.loads((self.tmp / ".aiwf" / "evidence" / "records.json").read_text()),
            json.loads((self.tmp / ".aiwf" / "quality" / "testing.json").read_text()),
            json.loads((self.tmp / ".aiwf" / "quality" / "review.json").read_text()),
            json.loads((self.tmp / ".aiwf" / "state" / "fix-loop.json").read_text()),
        )
        self.assertFalse(gates["passed"])
        self.assertIn("structure review not accepted", gates["blockers"])

    def test_structure_needs_fix_blocks(self):
        self._set_close_attempt(); self._accept_evidence()
        self._set_review("needs_fix")
        from aiwf_core.core.closure_contract import closure_conditions_met
        gates = closure_conditions_met(
            json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text()),
            json.loads((self.tmp / ".aiwf" / "evidence" / "records.json").read_text()),
            json.loads((self.tmp / ".aiwf" / "quality" / "testing.json").read_text()),
            json.loads((self.tmp / ".aiwf" / "quality" / "review.json").read_text()),
            json.loads((self.tmp / ".aiwf" / "state" / "fix-loop.json").read_text()),
        )
        self.assertFalse(gates["passed"])

    def test_structure_accepted_passes_with_other_gates(self):
        self._set_close_attempt(); self._accept_evidence()
        self._set_review("accepted")
        from aiwf_core.core.closure_contract import closure_conditions_met
        gates = closure_conditions_met(
            json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text()),
            json.loads((self.tmp / ".aiwf" / "evidence" / "records.json").read_text()),
            json.loads((self.tmp / ".aiwf" / "quality" / "testing.json").read_text()),
            json.loads((self.tmp / ".aiwf" / "quality" / "review.json").read_text()),
            json.loads((self.tmp / ".aiwf" / "state" / "fix-loop.json").read_text()),
        )
        self.assertTrue(gates["passed"], f"Blockers: {gates['blockers']}")

    def test_review_default_has_structure_fields(self):
        """Fresh install creates review.json with cleanup+structure fields."""
        r = json.loads((self.tmp / ".aiwf" / "quality" / "review.json").read_text())
        self.assertEqual(r["cleanup_status"], "unknown")
        self.assertEqual(r["structure_status"], "unknown")
        self.assertIn("architecture_impact", r)


if __name__ == "__main__":
    unittest.main()
