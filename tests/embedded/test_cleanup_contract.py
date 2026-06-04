"""Cleanup gate: cleanup_status must be fresh for closure."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 10

def _install(cwd):
    env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
    subprocess.run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                   capture_output=True, text=True, cwd=str(cwd), env=env, timeout=20)

class TestCleanupGate(unittest.TestCase):
    """Closure requires cleanup_status=fresh."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awcl_"))
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

    def _accept_all_except(self, skip_keys=None):
        skip_keys = skip_keys or set()
        r = json.loads((self.tmp / ".aiwf" / "quality" / "review.json").read_text())
        r["result"] = "accepted"; r["closure_allowed"] = True
        r["accepted_evidence_ids"] = ["EV-001"]; r["blockers"] = []
        if "cleanup" not in skip_keys: r["cleanup_status"] = "fresh"
        if "structure" not in skip_keys: r["structure_status"] = "accepted"
        (self.tmp / ".aiwf" / "quality" / "review.json").write_text(json.dumps(r, indent=2))
        (self.tmp / ".aiwf" / "evidence" / "records.json").write_text(json.dumps(
            {"records": [{"id": "EV-001", "status": "accepted", "trust": "machine_observed"}]}, indent=2))
        (self.tmp / ".aiwf" / "quality" / "testing.json").write_text(json.dumps(
            {"status": "adequate", "commands": ["pytest"], "untested_risks": []}, indent=2))
        (self.tmp / ".aiwf" / "state" / "fix-loop.json").write_text(json.dumps(
            {"status": "none", "route": None, "required_fixes": []}, indent=2))

    def test_cleanup_missing_blocks_close(self):
        """cleanup_status=unknown blocks closure."""
        self._set_close_attempt()
        # Default review has cleanup_status=unknown
        from aiwf_core.core.closure_contract import closure_conditions_met
        gates = closure_conditions_met(
            json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text()),
            json.loads((self.tmp / ".aiwf" / "evidence" / "records.json").read_text()),
            json.loads((self.tmp / ".aiwf" / "quality" / "testing.json").read_text()),
            json.loads((self.tmp / ".aiwf" / "quality" / "review.json").read_text()),
            json.loads((self.tmp / ".aiwf" / "state" / "fix-loop.json").read_text()),
        )
        self.assertFalse(gates["passed"])
        self.assertIn("cleanup not fresh", gates["blockers"])

    def test_cleanup_stale_blocks_close(self):
        """cleanup_status=stale blocks closure."""
        r = json.loads((self.tmp / ".aiwf" / "quality" / "review.json").read_text())
        r["cleanup_status"] = "stale"
        (self.tmp / ".aiwf" / "quality" / "review.json").write_text(json.dumps(r, indent=2))
        self._set_close_attempt()
        from aiwf_core.core.closure_contract import closure_conditions_met
        gates = closure_conditions_met(
            json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text()),
            json.loads((self.tmp / ".aiwf" / "evidence" / "records.json").read_text()),
            json.loads((self.tmp / ".aiwf" / "quality" / "testing.json").read_text()),
            json.loads((self.tmp / ".aiwf" / "quality" / "review.json").read_text()),
            json.loads((self.tmp / ".aiwf" / "state" / "fix-loop.json").read_text()),
        )
        self.assertFalse(gates["passed"])
        self.assertIn("cleanup not fresh", gates["blockers"])

    def test_cleanup_fresh_allows_close_with_other_gates_met(self):
        """cleanup_status=fresh passes when other gates are valid."""
        self._set_close_attempt()
        self._accept_all_except()
        from aiwf_core.core.closure_contract import closure_conditions_met
        gates = closure_conditions_met(
            json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text()),
            json.loads((self.tmp / ".aiwf" / "evidence" / "records.json").read_text()),
            json.loads((self.tmp / ".aiwf" / "quality" / "testing.json").read_text()),
            json.loads((self.tmp / ".aiwf" / "quality" / "review.json").read_text()),
            json.loads((self.tmp / ".aiwf" / "state" / "fix-loop.json").read_text()),
        )
        self.assertTrue(gates["passed"], f"Should pass, blockers: {gates['blockers']}")

    def test_fresh_with_stale_items_blocks(self):
        """cleanup_status=fresh + stale_items non-empty → blocked."""
        self._set_close_attempt(); self._accept_all_except()
        r = json.loads((self.tmp / ".aiwf" / "quality" / "review.json").read_text())
        r["cleanup_status"] = "fresh"
        r["stale_items"] = ["old-ctx"]
        (self.tmp / ".aiwf" / "quality" / "review.json").write_text(json.dumps(r, indent=2))
        from aiwf_core.core.closure_contract import closure_conditions_met
        gates = closure_conditions_met(
            json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text()),
            json.loads((self.tmp / ".aiwf" / "evidence" / "records.json").read_text()),
            json.loads((self.tmp / ".aiwf" / "quality" / "testing.json").read_text()),
            json.loads((self.tmp / ".aiwf" / "quality" / "review.json").read_text()),
            json.loads((self.tmp / ".aiwf" / "state" / "fix-loop.json").read_text()),
        )
        self.assertFalse(gates["passed"])
        self.assertIn("stale_items is not empty", gates["blockers"][0])

    def test_fresh_with_cleanup_blockers_blocks(self):
        """cleanup_status=fresh + cleanup_blockers non-empty → blocked."""
        self._set_close_attempt(); self._accept_all_except()
        r = json.loads((self.tmp / ".aiwf" / "quality" / "review.json").read_text())
        r["cleanup_status"] = "fresh"
        r["cleanup_blockers"] = ["still-has-stale-refs"]
        (self.tmp / ".aiwf" / "quality" / "review.json").write_text(json.dumps(r, indent=2))
        from aiwf_core.core.closure_contract import closure_conditions_met
        gates = closure_conditions_met(
            json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text()),
            json.loads((self.tmp / ".aiwf" / "evidence" / "records.json").read_text()),
            json.loads((self.tmp / ".aiwf" / "quality" / "testing.json").read_text()),
            json.loads((self.tmp / ".aiwf" / "quality" / "review.json").read_text()),
            json.loads((self.tmp / ".aiwf" / "state" / "fix-loop.json").read_text()),
        )
        self.assertFalse(gates["passed"])
        self.assertIn("cleanup_blockers is not empty", gates["blockers"][0])


if __name__ == "__main__":
    unittest.main()
