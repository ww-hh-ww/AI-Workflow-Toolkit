"""Regression tests for P0 closure gate bugs.

Verifies that prepare_close and closure_conditions_met correctly block:
- Failed testing
- Rejected review
- closure_allowed=false
- phase=closed with live blockers
- cancel-close recovery
- L2 trust_level evidence requirements
"""
import json
import tempfile
import unittest
from pathlib import Path


def _make_state_dir(tmpdir, state=None, testing=None, review=None,
                    evidence=None, fix_loop=None):
    """Create a minimal .aiwf state tree and return the base path."""
    base = Path(tmpdir)
    for d in [".aiwf/state", ".aiwf/quality", ".aiwf/evidence"]:
        (base / d).mkdir(parents=True, exist_ok=True)

    (base / ".aiwf/state/state.json").write_text(json.dumps(state or {
        "phase": "reviewing", "workflow_level": "L1_review_light",
        "active_context_id": "ctx-1", "active_task_id": "task-1",
        "close_attempt": False, "closure_allowed": False,
        "scope_violation": False,
    }))
    (base / ".aiwf/quality/testing.json").write_text(json.dumps(testing or {
        "status": "passed", "commands": ["pytest"],
    }))
    (base / ".aiwf/quality/review.json").write_text(json.dumps(review or {
        "result": "accepted", "closure_allowed": True,
        "cleanup_status": "fresh", "blockers": [], "stale_items": [],
    }))
    (base / ".aiwf/evidence/records.json").write_text(json.dumps(evidence or {
        "records": [{
            "id": "EV-001", "status": "accepted",
            "trust_level": "command_observed", "session_id": "s1",
        }],
    }))
    (base / ".aiwf/state/fix-loop.json").write_text(json.dumps(fix_loop or {
        "status": "none",
    }))
    return str(base)


class TestPrepareCloseGates(unittest.TestCase):
    """prepare_close must block on quality failures."""

    def test_happy_path_passes(self):
        from aiwf_core.core.state_ops import prepare_close
        base = _make_state_dir(tempfile.mkdtemp())
        result = prepare_close(base)
        self.assertTrue(result["passed"], f"happy path blocked: {result['blockers']}")
        self.assertEqual(result["blockers"], [])

    def test_blocks_testing_failed(self):
        from aiwf_core.core.state_ops import prepare_close
        base = _make_state_dir(tempfile.mkdtemp(), testing={"status": "failed"})
        result = prepare_close(base)
        self.assertFalse(result["passed"],
                         "prepare_close must block testing.status=failed")
        self.assertTrue(any("failed" in b.lower() for b in result["blockers"]),
                        f"blockers should mention failed: {result['blockers']}")

    def test_blocks_testing_missing(self):
        from aiwf_core.core.state_ops import prepare_close
        base = _make_state_dir(tempfile.mkdtemp(), testing={"status": "missing"})
        result = prepare_close(base)
        self.assertFalse(result["passed"],
                         "prepare_close must block testing.status=missing")

    def test_blocks_review_rejected(self):
        from aiwf_core.core.state_ops import prepare_close
        base = _make_state_dir(tempfile.mkdtemp(), review={
            "result": "rejected", "closure_allowed": False,
            "cleanup_status": "fresh", "blockers": ["scope violation"],
        })
        result = prepare_close(base)
        self.assertFalse(result["passed"],
                         "prepare_close must block review.result=rejected")
        self.assertTrue(any("rejected" in b.lower() for b in result["blockers"]),
                        f"blockers should mention rejected: {result['blockers']}")

    def test_blocks_review_needs_fix(self):
        from aiwf_core.core.state_ops import prepare_close
        base = _make_state_dir(tempfile.mkdtemp(), review={
            "result": "needs_fix", "closure_allowed": False,
            "cleanup_status": "fresh",
        })
        result = prepare_close(base)
        self.assertFalse(result["passed"],
                         "prepare_close must block review.result=needs_fix")

    def test_blocks_closure_allowed_false(self):
        from aiwf_core.core.state_ops import prepare_close
        base = _make_state_dir(tempfile.mkdtemp(), review={
            "result": "accepted", "closure_allowed": False,
            "cleanup_status": "fresh",
        })
        result = prepare_close(base)
        self.assertFalse(result["passed"],
                         "prepare_close must block closure_allowed=false even when accepted")

    def test_blocks_cleanup_not_fresh(self):
        from aiwf_core.core.state_ops import prepare_close
        base = _make_state_dir(tempfile.mkdtemp(), review={
            "result": "accepted", "closure_allowed": True,
            "cleanup_status": "stale", "stale_items": ["tmp files"],
        })
        result = prepare_close(base)
        self.assertFalse(result["passed"],
                         "prepare_close must block stale cleanup")

    def test_blocks_no_evidence(self):
        from aiwf_core.core.state_ops import prepare_close
        base = _make_state_dir(tempfile.mkdtemp(), evidence={"records": []})
        result = prepare_close(base)
        self.assertFalse(result["passed"],
                         "prepare_close must block when no evidence records exist")


class TestClosureConditionsMet(unittest.TestCase):
    """closure_conditions_met must enforce the same quality gates."""

    def test_happy_path_passes(self):
        from aiwf_core.core.closure_contract import closure_conditions_met
        result = closure_conditions_met(
            {"phase": "reviewing", "close_attempt": True, "workflow_level": "L1_review_light"},
            {"records": [{"id": "EV-001", "status": "accepted"}]},
            {"status": "passed"},
            {"result": "accepted", "closure_allowed": True, "cleanup_status": "fresh"},
            {"status": "none"},
        )
        self.assertTrue(result["passed"], f"happy path blocked: {result['blockers']}")
        self.assertEqual(result["blockers"], [])

    def test_blocks_testing_failed(self):
        from aiwf_core.core.closure_contract import closure_conditions_met
        result = closure_conditions_met(
            {"phase": "reviewing", "close_attempt": True},
            {"records": [{"id": "EV-001", "status": "accepted"}]},
            {"status": "failed"},
            {"result": "accepted", "closure_allowed": True, "cleanup_status": "fresh"},
            {"status": "none"},
        )
        self.assertFalse(result["passed"],
                         "closure_conditions_met must block testing=failed")

    def test_blocks_review_rejected(self):
        from aiwf_core.core.closure_contract import closure_conditions_met
        result = closure_conditions_met(
            {"phase": "reviewing", "close_attempt": True},
            {"records": [{"id": "EV-001", "status": "accepted"}]},
            {"status": "passed"},
            {"result": "rejected", "closure_allowed": False, "cleanup_status": "fresh"},
            {"status": "none"},
        )
        self.assertFalse(result["passed"],
                         "closure_conditions_met must block review=rejected")

    def test_blocks_closure_allowed_false(self):
        from aiwf_core.core.closure_contract import closure_conditions_met
        result = closure_conditions_met(
            {"phase": "reviewing", "close_attempt": True},
            {"records": [{"id": "EV-001", "status": "accepted"}]},
            {"status": "passed"},
            {"result": "accepted", "closure_allowed": False, "cleanup_status": "fresh"},
            {"status": "none"},
        )
        self.assertFalse(result["passed"],
                         "closure_conditions_met must block closure_allowed=false")

    def test_closed_with_blockers_does_not_pass(self):
        from aiwf_core.core.closure_contract import closure_conditions_met
        result = closure_conditions_met(
            {"phase": "closed", "close_attempt": False},
            {"records": []},
            {"status": "missing"},
            {"result": "unknown", "closure_allowed": False, "cleanup_status": "unknown"},
            {"status": "none"},
        )
        self.assertFalse(result["passed"],
                         "phase=closed with blockers must not return passed=True")
        self.assertTrue(len(result["blockers"]) > 0,
                        "should have blockers when quality gates fail")

    def test_closed_clean_passes(self):
        from aiwf_core.core.closure_contract import closure_conditions_met
        result = closure_conditions_met(
            {"phase": "closed", "close_attempt": False},
            {"records": [{"id": "EV-001", "status": "accepted"}]},
            {"status": "passed"},
            {"result": "accepted", "closure_allowed": True, "cleanup_status": "fresh"},
            {"status": "none"},
        )
        self.assertTrue(result["passed"],
                        "phase=closed with clean gates should pass revalidation")

    def test_no_close_attempt_no_phase_skips_checks(self):
        """Without close_attempt or closed phase, no gates are evaluated.
        passed=False is correct: closure should not proceed without close_attempt.
        blockers is empty because no gates were checked — no false positives."""
        from aiwf_core.core.closure_contract import closure_conditions_met
        result = closure_conditions_met(
            {"phase": "reviewing", "close_attempt": False},
            {"records": []},
            {"status": "missing"},
            {"result": "unknown", "closure_allowed": False, "cleanup_status": "unknown"},
            {"status": "none"},
        )
        # passed=False: closure was not attempted, so nothing to pass
        self.assertFalse(result["passed"])
        # blockers=[]: gates not evaluated, no false accusations
        self.assertEqual(result["blockers"], [])


class TestCancelClose(unittest.TestCase):
    """cancel_close must reset close_attempt and unstick the state machine."""

    def test_cancel_close_resets_close_attempt(self):
        from aiwf_core.core.state_ops import cancel_close
        base = _make_state_dir(tempfile.mkdtemp(), state={
            "phase": "closing", "close_attempt": True, "closure_allowed": False,
            "workflow_level": "L1_review_light", "active_context_id": "c1",
        })
        result = cancel_close(base)
        state = json.loads((Path(base) / ".aiwf" / "state" / "state.json").read_text())
        self.assertFalse(state["close_attempt"],
                         "cancel_close must reset close_attempt to False")
        self.assertFalse(state["closure_allowed"],
                         "cancel_close must reset closure_allowed to False")
        self.assertEqual(state["phase"], "reviewing",
                         "cancel_close must revert phase to reviewing")
        self.assertIn("unblocked", result["message"].lower())

    def test_cancel_close_reverts_closed_phase(self):
        from aiwf_core.core.state_ops import cancel_close
        base = _make_state_dir(tempfile.mkdtemp(), state={
            "phase": "closed", "close_attempt": False, "closure_allowed": True,
            "workflow_level": "L1_review_light", "active_context_id": "c1",
        })
        result = cancel_close(base)
        state = json.loads((Path(base) / ".aiwf" / "state" / "state.json").read_text())
        self.assertEqual(state["phase"], "reviewing",
                         "cancel_close must revert closed phase to reviewing")
        self.assertFalse(state["closure_allowed"])


class TestEvidenceTrustLevel(unittest.TestCase):
    """L2/L3 must require adequate evidence trust_level."""

    def test_l2_blocks_claimed_evidence(self):
        from aiwf_core.core.state_ops import prepare_close
        base = _make_state_dir(tempfile.mkdtemp(),
            state={"phase": "reviewing", "workflow_level": "L2_standard_team",
                   "active_context_id": "c1", "active_task_id": "t1",
                   "close_attempt": False, "closure_allowed": False,
                   "scope_violation": False},
            evidence={"records": [
                {"id": "EV-001", "status": "accepted", "trust_level": "claimed",
                 "session_id": "s1"},
                {"id": "EV-002", "status": "accepted", "trust_level": "claimed",
                 "session_id": "s2"},
                {"id": "EV-003", "status": "accepted", "trust_level": "claimed",
                 "session_id": "s3"},
            ]},
        )
        result = prepare_close(base)
        self.assertFalse(result["passed"],
                         "L2 must block when all evidence is only 'claimed'")

    def test_l2_passes_command_observed_evidence(self):
        from aiwf_core.core.state_ops import prepare_close
        base = _make_state_dir(tempfile.mkdtemp(),
            state={"phase": "reviewing", "workflow_level": "L2_standard_team",
                   "active_context_id": "c1", "active_task_id": "t1",
                   "close_attempt": False, "closure_allowed": False,
                   "scope_violation": False},
            evidence={"records": [
                {"id": "EV-001", "status": "accepted", "trust_level": "command_observed",
                 "session_id": "s1"},
                {"id": "EV-002", "status": "accepted", "trust_level": "command_observed",
                 "session_id": "s2"},
                {"id": "EV-003", "status": "accepted", "trust_level": "command_observed",
                 "session_id": "s3"},
            ]},
        )
        result = prepare_close(base)
        self.assertTrue(result["passed"],
                        f"L2 should pass with command_observed evidence: {result['blockers']}")

    def test_l1_passes_role_recorded_evidence(self):
        from aiwf_core.core.state_ops import prepare_close
        base = _make_state_dir(tempfile.mkdtemp(),
            state={"phase": "reviewing", "workflow_level": "L1_review_light",
                   "active_context_id": "c1", "active_task_id": "t1",
                   "close_attempt": False, "closure_allowed": False,
                   "scope_violation": False},
            evidence={"records": [
                {"id": "EV-001", "status": "accepted", "trust_level": "role_recorded",
                 "session_id": "s1"},
            ]},
        )
        result = prepare_close(base)
        self.assertTrue(result["passed"],
                        f"L1 should pass with role_recorded evidence: {result['blockers']}")

    def test_evidence_without_trust_level_defaults_to_claimed(self):
        """Hook-style evidence missing trust_level is treated as 'claimed'."""
        from aiwf_core.core.state_ops import prepare_close
        base = _make_state_dir(tempfile.mkdtemp(),
            state={"phase": "reviewing", "workflow_level": "L2_standard_team",
                   "active_context_id": "c1", "active_task_id": "t1",
                   "close_attempt": False, "closure_allowed": False,
                   "scope_violation": False},
            evidence={"records": [
                {"id": "EV-001", "status": "accepted",
                 "trust": "machine_observed",  # no trust_level field
                 "session_id": "s1"},
                {"id": "EV-002", "status": "accepted",
                 "trust": "machine_observed",
                 "session_id": "s2"},
                {"id": "EV-003", "status": "accepted",
                 "trust": "machine_observed",
                 "session_id": "s3"},
            ]},
        )
        result = prepare_close(base)
        self.assertFalse(result["passed"],
                         "L2 must block hook evidence without trust_level (defaults to claimed)")


if __name__ == "__main__":
    unittest.main()
