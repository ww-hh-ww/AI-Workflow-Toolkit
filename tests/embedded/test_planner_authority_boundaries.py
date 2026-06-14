"""Planner cannot rewrite mechanical truth to make a failing cycle look clean."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path


class TestPlannerAuthorityBoundaries(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aiwf-authority-"))
        from aiwf_core.core.state_schema import MVP_STATE_FILES
        for rel, factory in MVP_STATE_FILES.items():
            path = self.tmp / ".aiwf" / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(factory(), indent=2) + "\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _read(self, rel):
        return json.loads((self.tmp / ".aiwf" / rel).read_text())

    def _write(self, rel, data):
        path = self.tmp / ".aiwf" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n")

    def test_context_boundary_can_change_before_task_activation_and_records_revision(self):
        from aiwf_core.core.state_ops import start_context
        start_context(str(self.tmp), "CTX-1", allowed_write=["src/a.py"])
        result = start_context(str(self.tmp), "CTX-1", allowed_write=["src/a.py", "reports/out.md"])
        ctx = result["contexts"][0]
        self.assertEqual(ctx["allowed_write"], ["src/a.py", "reports/out.md"])
        self.assertEqual(len(ctx["revision_history"]), 1)
        self.assertEqual(ctx["revision_history"][0]["previous_boundary"]["allowed_write"], ["src/a.py"])

    def test_active_task_freezes_context_write_boundary(self):
        from aiwf_core.core.state_ops import start_context
        start_context(str(self.tmp), "CTX-1", allowed_write=["src/a.py"])
        state = self._read("state/state.json")
        state["active_task_id"] = "TASK-1"
        self._write("state/state.json", state)

        with self.assertRaisesRegex(ValueError, "freeze reasons: active_task=TASK-1"):
            start_context(str(self.tmp), "CTX-1", allowed_write=["src/a.py", "reports/out.md"])

        ctx = self._read("state/contexts.json")["contexts"][0]
        self.assertEqual(ctx["allowed_write"], ["src/a.py"])

    def test_active_task_freezes_context_identity(self):
        from aiwf_core.core.state_ops import start_context
        start_context(str(self.tmp), "CTX-1", allowed_write=["src/a.py"])
        state = self._read("state/state.json")
        state["active_task_id"] = "TASK-1"
        self._write("state/state.json", state)

        with self.assertRaisesRegex(ValueError, "freezes context identity"):
            start_context(str(self.tmp), "CTX-2", allowed_write=["reports/out.md"])

        self.assertEqual(self._read("state/state.json")["active_context_id"], "CTX-1")

    def test_scope_violation_prevents_retroactive_boundary_change(self):
        from aiwf_core.core.state_ops import start_context
        start_context(str(self.tmp), "CTX-1", allowed_write=["src/a.py"])
        state = self._read("state/state.json")
        state["scope_violation"] = True
        self._write("state/state.json", state)

        with self.assertRaisesRegex(ValueError, "cannot legalize it retrospectively"):
            start_context(str(self.tmp), "CTX-1", allowed_write=["src/a.py", "reports/out.md"])

    def test_scope_violation_event_keeps_original_boundary_snapshot(self):
        from aiwf_core.hooks.common.evidence_writer import check_and_record_scope_violations
        import json
        context = {"id": "CTX-1", "forbidden_write": ["secrets/"]}
        # Task with allowed_write is the authoritative scope source
        (self.tmp / ".aiwf" / "runtime" / "history").mkdir(parents=True, exist_ok=True)
        (self.tmp / ".aiwf" / "runtime" / "history" / "task-ledger.json").write_text(
            json.dumps({"tasks": [
                {"id": "TASK-001", "status": "active", "allowed_write": ["src/a.py"]}
            ]}))
        state = self._read("state/state.json")
        state["active_task_id"] = "TASK-001"
        self._write("state/state.json", state)
        violations = check_and_record_scope_violations(["reports/out.md"], context, self.tmp)
        self.assertEqual(violations, ["reports/out.md"])
        event = self._read("artifacts/quality/review.json")["scope_violation_events"][0]
        self.assertEqual(event["path"], "reports/out.md")
        self.assertEqual(event["allowed_write_snapshot"], ["src/a.py"])

    def test_active_task_cannot_lower_workflow_level(self):
        from aiwf_core.core.state_ops import record_quality_policy
        state = self._read("state/state.json")
        state["workflow_level"] = "L2_standard_team"
        state["active_task_id"] = "TASK-1"
        self._write("state/state.json", state)

        with self.assertRaisesRegex(ValueError, "cannot lower workflow level"):
            record_quality_policy(str(self.tmp), "small_function", "L0_direct")
        self.assertEqual(self._read("state/state.json")["workflow_level"], "L2_standard_team")

    def test_failed_testing_cannot_lower_workflow_level_after_task_stops(self):
        from aiwf_core.core.state_ops import record_quality_policy
        state = self._read("state/state.json")
        state["workflow_level"] = "L2_standard_team"
        state["active_task_id"] = None
        self._write("state/state.json", state)
        testing = self._read("artifacts/quality/testing.json")
        testing["status"] = "failed"
        self._write("artifacts/quality/testing.json", testing)

        with self.assertRaisesRegex(ValueError, "cannot lower workflow level"):
            record_quality_policy(str(self.tmp), "small_function", "L0_direct")

    def test_active_task_contract_cannot_be_replanned(self):
        from aiwf_core.core.task_ledger import upsert_task
        upsert_task(str(self.tmp), "TASK-1", status="active", dependencies=["TASK-0"])
        with self.assertRaisesRegex(ValueError, "active task contract is frozen"):
            upsert_task(str(self.tmp), "TASK-1", status="active", dependencies=["TASK-0", "TASK-X"])

    def test_frozen_quality_contract_allows_addition_but_not_removal(self):
        from aiwf_core.core.state_ops import record_quality_brief
        record_quality_brief(
            str(self.tmp),
            acceptance_criteria=["old criterion"],
            test_obligations=["old test"],
        )
        state = self._read("state/state.json")
        state["active_task_id"] = "TASK-1"
        self._write("state/state.json", state)

        record_quality_brief(
            str(self.tmp),
            acceptance_criteria=["old criterion", "new criterion"],
            test_obligations=["old test", "new test"],
        )
        with self.assertRaisesRegex(ValueError, "allowed now: add constraints or record evidence"):
            record_quality_brief(str(self.tmp), acceptance_criteria=["new criterion"])
        with self.assertRaisesRegex(ValueError, "cannot remove existing items"):
            record_quality_brief(str(self.tmp), test_obligations=["new test"])

    def test_blocking_review_freezes_context_after_active_task_is_closed(self):
        from aiwf_core.core.state_ops import start_context
        start_context(str(self.tmp), "CTX-1", allowed_write=["src/a.py"])
        state = self._read("state/state.json")
        state["active_task_id"] = None
        self._write("state/state.json", state)
        review = self._read("artifacts/quality/review.json")
        review["result"] = "needs_fix"
        self._write("artifacts/quality/review.json", review)

        with self.assertRaisesRegex(ValueError, "freezes allowed_write"):
            start_context(str(self.tmp), "CTX-1", allowed_write=["src/a.py", "reports/"])

    def test_open_fix_loop_cannot_lower_workflow_level(self):
        from aiwf_core.core.state_ops import open_fix_loop, record_quality_policy
        state = self._read("state/state.json")
        state["workflow_level"] = "L2_standard_team"
        self._write("state/state.json", state)
        open_fix_loop(str(self.tmp), "executor", "bug")

        with self.assertRaisesRegex(ValueError, "cannot lower workflow level"):
            record_quality_policy(str(self.tmp), "small_function", "L1_review_light")

    def test_fix_loop_required_verification_must_be_recorded_before_resolve(self):
        from aiwf_core.core.state_ops import open_fix_loop, record_testing, resolve_fix_loop
        open_fix_loop(
            str(self.tmp), "executor", "bug",
            required_verification=["rerun regression suite"],
        )
        with self.assertRaisesRegex(ValueError, "adequate/passed testing"):
            resolve_fix_loop(str(self.tmp), "claimed fixed")

        record_testing(str(self.tmp), status="passed", commands=["pytest"],
                      acceptance_coverage=["rerun regression suite: covered"])
        resolved = resolve_fix_loop(str(self.tmp), "verified fixed")
        self.assertEqual(resolved["status"], "resolved")

    def test_fix_loop_cannot_resolve_while_scope_violation_remains(self):
        from aiwf_core.core.state_ops import open_fix_loop, resolve_fix_loop
        from unittest.mock import patch
        open_fix_loop(str(self.tmp), "planner", "scope violation")
        state = self._read("state/state.json")
        state["scope_violation"] = True
        self._write("state/state.json", state)
        review = self._read("artifacts/quality/review.json")
        review["scope_violation_events"] = [{"path": "outside.py", "status": "recorded"}]
        self._write("artifacts/quality/review.json", review)

        with patch(
            "aiwf_core.hooks.common.diff_snapshot.detect_changed_files",
            return_value={"files": ["outside.py"], "source": "git_diff"},
        ):
            with self.assertRaisesRegex(ValueError, "scope-violating files remain changed"):
                resolve_fix_loop(str(self.tmp), "expanded context")
        self.assertEqual(self._read("state/fix-loop.json")["status"], "open")

    def test_reverted_scope_violation_can_be_mechanically_resolved(self):
        from aiwf_core.core.state_ops import open_fix_loop, resolve_fix_loop
        from unittest.mock import patch
        open_fix_loop(str(self.tmp), "planner", "scope violation")
        state = self._read("state/state.json")
        state["scope_violation"] = True
        self._write("state/state.json", state)
        review = self._read("artifacts/quality/review.json")
        review["scope_violation_events"] = [{"path": "outside.py", "status": "recorded"}]
        review["blockers"] = ["scope_violation: 'outside.py' modified outside CTX-1 scope"]
        self._write("artifacts/quality/review.json", review)

        with patch(
            "aiwf_core.hooks.common.diff_snapshot.detect_changed_files",
            return_value={"files": [], "source": "git_diff"},
        ):
            result = resolve_fix_loop(str(self.tmp), "reverted outside.py")
        self.assertEqual(result["status"], "resolved")
        self.assertFalse(self._read("state/state.json")["scope_violation"])
        event = self._read("artifacts/quality/review.json")["scope_violation_events"][0]
        self.assertEqual(event["status"], "resolved_reverted")

    def test_fix_loop_escalation_cannot_be_self_resolved(self):
        from aiwf_core.core.state_ops import open_fix_loop, resolve_fix_loop
        state = self._read("state/state.json")
        state["workflow_level"] = "L0_direct"
        self._write("state/state.json", state)
        open_fix_loop(str(self.tmp), "executor", "first")
        open_fix_loop(str(self.tmp), "executor", "second")

        with self.assertRaisesRegex(ValueError, "cannot self-resolve escalation"):
            resolve_fix_loop(str(self.tmp), "claimed fixed")

    def test_scope_violation_blocks_next_task_activation(self):
        from aiwf_core.core.task_ledger import activation_blockers, upsert_task
        state = self._read("state/state.json")
        state["scope_violation"] = True
        self._write("state/state.json", state)
        upsert_task(str(self.tmp), "TASK-2", "Next", status="ready", allowed_write=["src/b.py"])

        blockers = activation_blockers(str(self.tmp), "TASK-2")
        self.assertTrue(any("revert the originally violating files" in blocker for blocker in blockers))

    def test_review_acceptance_cannot_erase_scope_violation_event(self):
        from aiwf_core.core.review_contract import set_review_accepted
        review = self._read("artifacts/quality/review.json")
        review["scope_violation_events"] = [{"path": "outside.py", "status": "recorded"}]
        review["blockers"] = ["scope_violation: 'outside.py' modified outside CTX-1 scope"]
        accepted = set_review_accepted(review, [], [])
        self.assertEqual(accepted["result"], "scope_violation")
        self.assertFalse(accepted["closure_allowed"])
        self.assertTrue(accepted["blockers"])


if __name__ == "__main__":
    unittest.main()
