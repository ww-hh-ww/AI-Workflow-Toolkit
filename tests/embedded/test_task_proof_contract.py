import shutil
import tempfile
import unittest
from pathlib import Path


class TestTaskProofContract(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="aiwf_proof_"))
        (self.root / ".aiwf/tasks").mkdir(parents=True)
        (self.root / ".aiwf/records/tasks").mkdir(parents=True)
        self.task = {"id": "TASK-001", "doc_path": ".aiwf/tasks/TASK-001.md"}
        self.path = self.root / self.task["doc_path"]
        self.path.write_text(self._doc(), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    @staticmethod
    def _doc(command="python3 -c \"print('ok')\"", expected="stdout is ok", row_id="V-001", note=""):
        return f"""---
id: TASK-001
type: task
title: Proof
contract_status: ready
goal_id: GOAL-001
plan_id: PLAN-001
executor_required: true
reviewer_required: true
---

# TASK-001

## Fixed Contract

### Structural Home

Plan-owned behavior.

### Objective

Prove the entrypoint.

### Contract Responsibility

Own behavior and construction evidence.

### Proof Standard

Done When:

- [Running] The real entrypoint works.

Verification Commands:

| ID | Command | Expected Observable Output |
|----|---------|----------------------------|
| {row_id} | {command} | {expected} |

### Dispatch Decisions

Independent roles.

## Known Context

{note}
"""

    @staticmethod
    def _result(identity="V-001", matched=True, observed="ok"):
        return {
            "verification_id": identity,
            "command": "python3 -c \"print('ok')\"",
            "expected": "stdout is ok",
            "observed": observed,
            "matched": matched,
            "verdict": "matched" if matched else "mismatched",
            "basis": "semantic comparison",
        }

    def test_structured_v_id_is_executor_evidence_identity(self):
        from aiwf_core.core.task_proof import (
            construction_proof_gaps,
            read_task_proof_contract,
            validate_implementation_against_task,
        )

        contract = read_task_proof_contract(str(self.root), self.task)
        proof = validate_implementation_against_task(
            str(self.root), self.task,
            {"verification_results": [self._result()]},
        )
        self.assertEqual(contract.verification_commands[0].verification_id, "V-001")
        self.assertEqual(construction_proof_gaps(proof), [])

    def test_command_text_cannot_replace_stable_id(self):
        from aiwf_core.core.task_proof import (
            construction_proof_gaps, validate_implementation_against_task,
        )

        result = self._result()
        result.pop("verification_id")
        proof = validate_implementation_against_task(
            str(self.root), self.task, {"verification_results": [result]},
        )
        self.assertTrue(proof["legacy_unbound_results"])
        self.assertTrue(construction_proof_gaps(proof))

    def test_mismatched_and_blocked_results_are_gaps(self):
        from aiwf_core.core.task_proof import (
            construction_proof_gaps, validate_implementation_against_task,
        )

        mismatch = validate_implementation_against_task(
            str(self.root), self.task,
            {"verification_results": [self._result(matched=False, observed="wrong")]},
        )
        blocked_result = self._result(observed="")
        blocked_result.update({"matched": False, "verdict": "blocked", "basis": "no runtime"})
        blocked = validate_implementation_against_task(
            str(self.root), self.task, {"verification_results": [blocked_result]},
        )
        self.assertTrue(mismatch["mismatched_results"])
        self.assertTrue(blocked["blocked_results"])
        self.assertTrue(construction_proof_gaps(mismatch))
        self.assertTrue(construction_proof_gaps(blocked))

    def test_unknown_id_does_not_satisfy_required_row(self):
        from aiwf_core.core.task_proof import validate_implementation_against_task

        proof = validate_implementation_against_task(
            str(self.root), self.task,
            {"verification_results": [self._result(identity="V-999")]},
        )
        self.assertEqual(proof["unknown_verification_ids"], ["V-999"])
        self.assertTrue(proof["missing_verification_results"])

    def test_missing_or_unidentified_rows_fail_activation(self):
        from aiwf_core.core.task_proof import activation_proof_blockers

        self.path.unlink()
        self.assertTrue(activation_proof_blockers(str(self.root), self.task))
        self.path.write_text(self._doc(row_id=""), encoding="utf-8")
        self.assertTrue(any(
            "stable ID" in item
            for item in activation_proof_blockers(str(self.root), self.task)
        ))

    def test_proof_fingerprint_ignores_explanatory_prose_but_tracks_v_table(self):
        from aiwf_core.core.task_proof import proof_contract_fingerprint

        first = proof_contract_fingerprint(str(self.root), self.task)
        self.path.write_text(self._doc(note="A later explanatory note."), encoding="utf-8")
        second = proof_contract_fingerprint(str(self.root), self.task)
        self.path.write_text(
            self._doc(command="python3 -c \"print('different')\""), encoding="utf-8",
        )
        third = proof_contract_fingerprint(str(self.root), self.task)
        self.assertEqual(first, second)
        self.assertNotEqual(second, third)


if __name__ == "__main__":
    unittest.main()
