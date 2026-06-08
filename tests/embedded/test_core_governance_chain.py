"""Core governance chain qualification.

This test intentionally spans the main machine-readable chain instead of
checking isolated helpers only:

context -> testing -> evidence -> review -> cleanup/structure -> prepare-close
-> closure gate -> installed Stop gate script.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 20


def _install(cwd: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    result = subprocess.run(
        [sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
        timeout=TIMEOUT,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr + result.stdout)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n")


class TestCoreGovernanceChain(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="awgc_chain_"))
        _install(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        from aiwf_core.core.state_schema import MVP_STATE_FILES

        for filename, default_factory in MVP_STATE_FILES.items():
            _write_json(self.tmp / ".aiwf" / filename, default_factory())

    def _seed_accepted_review_with_pending_evidence(self):
        _write_json(
            self.tmp / ".aiwf" / "evidence" / "records.json",
            {
                "records": [
                    {
                        "id": "EV-CHAIN",
                        "status": "pending",
                        "trust": "machine_observed",
                        "summary": "governance chain qualification evidence",
                    }
                ]
            },
        )
        _write_json(
            self.tmp / ".aiwf" / "quality" / "review.json",
            {
                "result": "accepted",
                "closure_allowed": True,
                "accepted_evidence_ids": ["EV-CHAIN"],
                "rejected_evidence_ids": [],
                "blockers": [],
                "cleanup_status": "fresh",
                "cleanup_blockers": [],
                "stale_items": [],
                "structure_status": "accepted",
                "structure_blockers": [],
            },
        )
        _write_json(
            self.tmp / ".aiwf" / "state" / "fix-loop.json",
            {"status": "none", "route": None, "required_fixes": []},
        )

    def _complete_chain_until_close(self):
        from aiwf_core.core.state_ops import prepare_close, record_testing, start_context

        start_context(
            str(self.tmp),
            "CTX-CHAIN",
            "Core governance chain",
            allowed_write=["aiwf_core/core/state_ops.py"],
            purpose="Prove governance chain state moves coherently",
            test_focus=["state transition continuity"],
            review_focus=["closure gate completeness"],
        )
        record_testing(
            str(self.tmp),
            "CTX-CHAIN",
            "adequate",
            commands=["python3 tests/embedded/test_core_governance_chain.py"],
            untested_risks=[],
            acceptance_coverage=["context, testing, evidence, review, cleanup, close"],
            system_coverage=["installed Stop gate script"],
        )
        self._seed_accepted_review_with_pending_evidence()
        return prepare_close(str(self.tmp))

    def _run_stop_gate(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        payload = json.dumps(
            {
                "session_id": "chain",
                "cwd": str(self.tmp),
                "hook_event_name": "Stop",
            }
        )
        return subprocess.run(
            [sys.executable, str(self.tmp / "scripts" / "aiwf_review_gate.py")],
            input=payload,
            capture_output=True,
            text=True,
            cwd=str(self.tmp),
            env=env,
            timeout=TIMEOUT,
        )

    def test_complete_chain_passes_core_and_installed_stop_gate(self):
        result = self._complete_chain_until_close()
        self.assertTrue(result["can_proceed_to_gate"])
        self.assertTrue(result["close_attempt_set"])
        self.assertEqual(result["state"]["phase"], "closed")

        evidence = _read_json(self.tmp / ".aiwf" / "evidence" / "records.json")
        self.assertEqual(evidence["records"][0]["status"], "accepted")

        from aiwf_core.hooks.common.gate_checker import eval_closure_gates

        gates = eval_closure_gates(self.tmp)
        self.assertTrue(gates["passed"], gates["blockers"])
        self.assertTrue(gates["evidence_accepted"])
        self.assertTrue(gates["testing_adequate"])
        self.assertTrue(gates["review_accepted"])
        self.assertTrue(gates["cleanup_fresh"])
        self.assertTrue(gates["structure_accepted"])

        stop = self._run_stop_gate()
        self.assertEqual(stop.returncode, 0, stop.stderr)
        self.assertNotIn('"decision": "block"', stop.stdout)

    def test_chain_breaks_when_testing_is_missing(self):
        from aiwf_core.core.state_ops import prepare_close

        self._seed_accepted_review_with_pending_evidence()
        state = _read_json(self.tmp / ".aiwf" / "state" / "state.json")
        state["phase"] = "reviewing"
        _write_json(self.tmp / ".aiwf" / "state" / "state.json", state)
        result = prepare_close(str(self.tmp))

        self.assertFalse(result["close_attempt_set"])
        self.assertTrue(any("testing not adequate: missing" in b for b in result["blockers"]))
        state = _read_json(self.tmp / ".aiwf" / "state" / "state.json")
        self.assertFalse(state.get("close_attempt"))
        self.assertEqual(state.get("phase"), "reviewing")

    def test_chain_breaks_when_cleanup_is_stale(self):
        from aiwf_core.core.state_ops import mark_cleanup_stale, record_testing
        from aiwf_core.hooks.common.gate_checker import eval_closure_gates

        record_testing(str(self.tmp), "CTX-CHAIN", "adequate", commands=["pytest"])
        self._seed_accepted_review_with_pending_evidence()
        mark_cleanup_stale(str(self.tmp), ["obsolete context"], blockers=["cleanup required"])
        state = _read_json(self.tmp / ".aiwf" / "state" / "state.json")
        state["phase"] = "closing"
        state["close_attempt"] = True
        _write_json(self.tmp / ".aiwf" / "state" / "state.json", state)

        gates = eval_closure_gates(self.tmp)
        self.assertFalse(gates["passed"])
        self.assertTrue(any("cleanup not fresh" in b for b in gates["blockers"]))

    def test_chain_breaks_when_fix_loop_is_open(self):
        from aiwf_core.core.state_ops import open_fix_loop, prepare_close

        self._complete_chain_until_close()
        open_fix_loop(
            str(self.tmp),
            route="executor",
            reason="qualification injected blocker",
            required_fixes=["resolve injected blocker"],
            required_verification=["rerun governance chain"],
        )

        result = prepare_close(str(self.tmp))
        self.assertFalse(result["can_proceed_to_gate"])
        self.assertTrue(any("fix-loop is open" in b for b in result["blockers"]))


if __name__ == "__main__":
    unittest.main()
