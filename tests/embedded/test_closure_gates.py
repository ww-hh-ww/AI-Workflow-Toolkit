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
    for d in [".aiwf/state", ".aiwf/artifacts/quality", ".aiwf/artifacts/evidence"]:
        (base / d).mkdir(parents=True, exist_ok=True)

    (base / ".aiwf/state/state.json").write_text(json.dumps(state or {
        "phase": "reviewing", "workflow_level": "L1_review_light",
        "active_context_id": "ctx-1", "active_task_id": "",
        "close_attempt": False, "closure_allowed": False,
        "scope_violation": False,
    }))
    (base / ".aiwf/artifacts/quality/testing.json").write_text(json.dumps(testing or {
        "status": "passed", "commands": ["pytest"],
    }))
    (base / ".aiwf/artifacts/quality/review.json").write_text(json.dumps(review or {
        "verdict": "PASS",
        "result": "accepted",
        "closure_allowed": True,
        "cleanup_status": "fresh",
        "blockers": [],
        "stale_items": [],
        "quality_dimensions": _full_quality_dimensions(),
        "review_basis": _full_review_basis(),
    }))
    (base / ".aiwf/artifacts/evidence/records.json").write_text(json.dumps(evidence or {
        "records": [
            {"id": "EV-001", "status": "accepted", "trust": "machine_observed",
             "attribution": "strong", "tool_name": "Write",
             "trust_level": "command_observed",
             "session_id": "exec-session", "agent_type": "aiwf-executor"},
            {"id": "EV-002", "status": "accepted", "trust": "machine_observed",
             "attribution": "strong", "tool_name": "Bash",
             "trust_level": "command_observed",
             "session_id": "test-session", "agent_type": "aiwf-tester"},
            {"id": "EV-003", "status": "accepted", "trust": "machine_observed",
             "attribution": "strong", "tool_name": "Bash",
             "trust_level": "command_observed",
             "session_id": "review-session", "agent_type": "aiwf-reviewer",
             "timestamp": "2026-01-02T00:00:00+00:00"},
        ],
    }))
    (base / ".aiwf/state/fix-loop.json").write_text(json.dumps(fix_loop or {
        "status": "none",
    }))
    (base / ".aiwf/state/goal.json").write_text(json.dumps({
        "meta_critique": {"status": "recorded", "summary": "test"},
        "quality_brief": {"non_goals": ["test"]},
    }))
    return str(base)


def _full_quality_dimensions(risk_dim=None):
    from aiwf_core.core.state_schema import QUALITY_DIMENSIONS
    result = {}
    for dim in QUALITY_DIMENSIONS:
        score = "RISK" if dim == risk_dim else "PASS"
        result[dim] = {"score": score, "note": "minor concern" if score == "RISK" else ""}
    return result


def _full_review_basis():
    from aiwf_core.core.state_schema import REVIEW_BASIS
    return {name: {"status": "covered", "note": ""} for name in REVIEW_BASIS}


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

    def test_blocks_pass_verdict_with_unscored_quality_dimensions(self):
        from aiwf_core.core.state_ops import prepare_close
        base = _make_state_dir(tempfile.mkdtemp(), review={
            "verdict": "PASS",
            "result": "accepted",
            "closure_allowed": True,
            "cleanup_status": "fresh",
            "blockers": [],
            "stale_items": [],
            "quality_dimensions": {
                "requirement_fit": {"score": "PASS", "note": ""},
            },
            "review_basis": _full_review_basis(),
        })
        result = prepare_close(base)
        self.assertFalse(result["passed"])
        self.assertTrue(any("unscored quality dimensions" in b for b in result["blockers"]),
                        result["blockers"])

    def test_blocks_pass_verdict_missing_review_basis(self):
        from aiwf_core.core.state_ops import prepare_close
        base = _make_state_dir(tempfile.mkdtemp(), review={
            "verdict": "PASS",
            "result": "accepted",
            "closure_allowed": True,
            "cleanup_status": "fresh",
            "blockers": [],
            "stale_items": [],
            "quality_dimensions": _full_quality_dimensions(),
        })
        result = prepare_close(base)
        self.assertFalse(result["passed"])
        self.assertTrue(any("missing review basis coverage" in b for b in result["blockers"]),
                        result["blockers"])

    def test_blocks_accepted_symptom_only_review(self):
        from aiwf_core.core.state_ops import prepare_close
        base = _make_state_dir(tempfile.mkdtemp(), review={
            "result": "accepted",
            "closure_allowed": True,
            "cleanup_status": "fresh",
            "blockers": [],
            "stale_items": [],
            "root_cause": "symptom_only",
        })
        result = prepare_close(base)
        self.assertFalse(result["passed"])
        self.assertTrue(any("symptom_only" in b for b in result["blockers"]),
                        result["blockers"])


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

    def test_blocks_quality_verdict_contradiction(self):
        from aiwf_core.core.closure_contract import closure_conditions_met
        result = closure_conditions_met(
            {"phase": "reviewing", "close_attempt": True},
            {"records": [{"id": "EV-001", "status": "accepted"}]},
            {"status": "passed"},
            {
                "verdict": "PASS",
                "result": "accepted",
                "closure_allowed": True,
                "cleanup_status": "fresh",
                "quality_dimensions": _full_quality_dimensions("architecture_fit"),
                "review_basis": _full_review_basis(),
            },
            {"status": "none"},
        )
        self.assertFalse(result["passed"])
        self.assertTrue(any("PASS has RISK" in b for b in result["blockers"]),
                        result["blockers"])

    def test_blocks_quality_verdict_missing_review_basis(self):
        from aiwf_core.core.closure_contract import closure_conditions_met
        result = closure_conditions_met(
            {"phase": "reviewing", "close_attempt": True},
            {"records": [{"id": "EV-001", "status": "accepted"}]},
            {"status": "passed"},
            {
                "verdict": "PASS",
                "result": "accepted",
                "closure_allowed": True,
                "cleanup_status": "fresh",
                "quality_dimensions": _full_quality_dimensions(),
            },
            {"status": "none"},
        )
        self.assertFalse(result["passed"])
        self.assertTrue(any("missing review basis coverage" in b for b in result["blockers"]),
                        result["blockers"])

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
                   "active_context_id": "c1",
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
                   "active_context_id": "c1",
                   "close_attempt": False, "closure_allowed": False,
                   "scope_violation": False},
            evidence={"records": [
                {"id": "EV-001", "status": "accepted", "trust": "machine_observed",
                 "tool_name": "Write", "trust_level": "command_observed",
                 "session_id": "s1", "agent_type": "aiwf-executor"},
                {"id": "EV-002", "status": "accepted", "trust": "machine_observed",
                 "tool_name": "Bash", "trust_level": "command_observed",
                 "session_id": "s2", "agent_type": "aiwf-tester"},
                {"id": "EV-003", "status": "accepted", "trust": "machine_observed",
                 "tool_name": "Bash", "trust_level": "command_observed",
                 "session_id": "s3", "agent_type": "aiwf-reviewer"},
            ]},
        )
        result = prepare_close(base)
        self.assertTrue(result["passed"],
                        f"L2 should pass with command_observed evidence: {result['blockers']}")

    def test_l1_passes_role_recorded_evidence(self):
        from aiwf_core.core.state_ops import prepare_close
        base = _make_state_dir(tempfile.mkdtemp(),
            state={"phase": "reviewing", "workflow_level": "L1_review_light",
                   "active_context_id": "c1",
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
                   "active_context_id": "c1",
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

class TestImpactCloseGates(unittest.TestCase):
    """Impact review check must block prepare_close when Impact=no but files changed."""

    def setUp(self):
        import tempfile, json
        self.tmp = tempfile.mkdtemp()
        self.base = Path(self.tmp)
        for d in [".aiwf/state", ".aiwf/artifacts/quality", ".aiwf/artifacts/evidence", ".aiwf/artifacts/plans",
                   ".aiwf/runtime/history", ".aiwf/artifacts/reports"]:
            (self.base / d).mkdir(parents=True, exist_ok=True)
        # Default clean state
        self._write_state({"phase": "reviewing", "workflow_level": "L1_review_light",
                           "active_task_id": "TASK-001", "close_attempt": False})
        self._write_testing({"status": "passed"})
        self._write_review({"verdict": "PASS", "result": "accepted", "closure_allowed": True,
                           "cleanup_status": "fresh", "stale_items": [],
                           "quality_dimensions": _full_quality_dimensions(),
                           "review_basis": _full_review_basis()})
        self._write_fixloop({"status": "none"})
        self._write_evidence({"records": [
            {"id": "EV-001", "status": "accepted", "trust_level": "role_recorded",
             "session_id": "s1", "changed_files": ["README.md"]}
        ]})
        self._write_plan("TASK-001",
            "- docs: no — no doc changes\n"
            "- project_map: no — no structure change\n"
            "- environment: no — same env\n"
            "- capabilities: no — no new deps\n"
            "- quality_summary: no — no quality impact\n")
        self._write_ledger()
        self._write_goal()

    def _write_state(self, d): (self.base / ".aiwf/state/state.json").write_text(json.dumps(d))
    def _write_testing(self, d): (self.base / ".aiwf/artifacts/quality/testing.json").write_text(json.dumps(d))
    def _write_review(self, d): (self.base / ".aiwf/artifacts/quality/review.json").write_text(json.dumps(d))
    def _write_fixloop(self, d): (self.base / ".aiwf/state/fix-loop.json").write_text(json.dumps(d))
    def _write_evidence(self, d): (self.base / ".aiwf/artifacts/evidence/records.json").write_text(json.dumps(d))
    def _write_ledger(self):
        (self.base / ".aiwf/runtime/history/task-ledger.json").write_text(
            json.dumps({"tasks": [], "execution_window": {"active_task_ids": []}}))
        (self.base / ".aiwf/runtime/history/task-history.json").write_text(json.dumps({"tasks": []}))
    def _write_active_ledger_task(self):
        (self.base / ".aiwf/runtime/history/task-ledger.json").write_text(
            json.dumps({
                "tasks": [{"id": "TASK-001", "title": "Impact task", "status": "active"}],
                "execution_window": {"active_task_ids": ["TASK-001"]},
            }))
    def _write_goal(self):
        (self.base / ".aiwf/state/goal.json").write_text(json.dumps({
            "quality_brief": {"non_goals": ["test"]},
            "meta_critique": {"status": "recorded", "summary": "test"}
        }))
    def _write_plan(self, task_id, impact_body):
        (self.base / ".aiwf/artifacts/plans" / f"{task_id}.md").write_text(
            f"# {task_id}\n\n## Impact\n{impact_body}\n")

    def test_prepare_close_blocks_impact_docs_no_but_docs_changed(self):
        """Impact.docs=no but accepted evidence changed README.md — must block."""
        import json
        from aiwf_core.core.state.closure_ops import prepare_close
        result = prepare_close(str(self.base))
        self.assertFalse(result["passed"],
            f"Impact.docs=no + README changed should block, got passed=True")
        self.assertTrue(any("Impact.docs=no" in b for b in result["blockers"]),
            f"Should have Impact blocker, got: {result['blockers']}")

    def test_task_close_cannot_bypass_prepare_close_impact_check(self):
        """Active task close must not clear active_task_id before Impact gate runs."""
        self._write_active_ledger_task()
        from aiwf_core.core.task_ledger import close_task
        from aiwf_core.core.state.closure_ops import prepare_close

        close_result = close_task(str(self.base), "TASK-001")
        self.assertFalse(close_result["closed"])
        self.assertTrue(any("prepare-close" in b for b in close_result["blockers"]))

        state = json.loads((self.base / ".aiwf/state/state.json").read_text())
        self.assertEqual(state["active_task_id"], "TASK-001")

        result = prepare_close(str(self.base))
        self.assertFalse(result["passed"])
        self.assertTrue(any("Impact.docs=no" in b for b in result["blockers"]),
            f"Impact blocker must remain after blocked task close, got: {result['blockers']}")

    def test_prepare_close_uses_task_plan_id_for_decoupled_plan_impact(self):
        """Plan registry decoupling means Impact belongs to task.plan_id, not TASK-ID."""
        (self.base / ".aiwf/artifacts/plans/TASK-001.md").unlink(missing_ok=True)
        self._write_plan("PLAN-001",
            "- docs: no — no doc changes\n"
            "- project_map: no — no structure change\n"
            "- environment: no — same env\n"
            "- capabilities: no — no new deps\n"
            "- quality_summary: no — no quality impact\n")
        self._write_evidence({"records": [
            {"id": "EV-001", "status": "accepted", "trust_level": "role_recorded",
             "session_id": "s1", "changed_files": ["src/a.py"]}
        ]})
        (self.base / ".aiwf/runtime/history/task-ledger.json").write_text(
            json.dumps({
                "tasks": [{
                    "id": "TASK-001",
                    "title": "Decoupled plan task",
                    "status": "active",
                    "plan_id": "PLAN-001",
                    "goal_id": "GOAL-001",
                }],
                "execution_window": {"active_task_ids": ["TASK-001"]},
            }))
        from aiwf_core.core.state.closure_ops import prepare_close

        result = prepare_close(str(self.base))

        self.assertTrue(result["passed"], result["blockers"])
        self.assertEqual(result["state"]["close_prepared_task_id"], "TASK-001")

    def test_prepare_close_blocks_impact_project_map_no_but_changed(self):
        """Impact.project_map=no but project-map file changed — must block."""
        import json
        self._write_evidence({"records": [
            {"id": "EV-001", "status": "accepted", "trust_level": "role_recorded",
             "session_id": "s1", "changed_files": [".aiwf/artifacts/reports/PROJECT-MAP.md"]}
        ]})
        from aiwf_core.core.state.closure_ops import prepare_close
        result = prepare_close(str(self.base))
        self.assertFalse(result["passed"],
            f"Impact.project_map=no + PROJECT-MAP changed should block")
        self.assertTrue(any("Impact.project_map=no" in b for b in result["blockers"]))

    def test_prepare_close_blocks_impact_qs_no_but_digest_written(self):
        """Impact.quality_summary=no but digest file changed — must block."""
        import json
        self._write_evidence({"records": [
            {"id": "EV-001", "status": "accepted", "trust_level": "role_recorded",
             "session_id": "s1", "changed_files": [".aiwf/artifacts/reports/质量摘要.md"]}
        ]})
        from aiwf_core.core.state.closure_ops import prepare_close
        result = prepare_close(str(self.base))
        self.assertFalse(result["passed"],
            f"Impact.quality_summary=no + digest changed should block")
        self.assertTrue(any("Impact.quality_summary=no" in b for b in result["blockers"]))

    def test_prepare_close_passes_when_impact_matches_changes(self):
        """Impact=yes + matching changes — no blocker."""
        import json
        self._write_plan("TASK-001",
            "- docs: yes — doc updates needed\n"
            "- project_map: no — no structure change\n"
            "- environment: no — same env\n"
            "- capabilities: no — no new deps\n"
            "- quality_summary: no — no quality impact\n")
        from aiwf_core.core.state.closure_ops import prepare_close
        result = prepare_close(str(self.base))
        impact_blockers = [b for b in result["blockers"] if "Impact" in b]
        self.assertEqual([], impact_blockers,
            f"Impact=yes + docs changed should not block, got: {impact_blockers}")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
