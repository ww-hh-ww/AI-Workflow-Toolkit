import json
import tempfile
import unittest
from pathlib import Path


def _write_task(base: Path, task_id: str, body: str) -> dict:
    (base / ".aiwf/tasks").mkdir(parents=True, exist_ok=True)
    (base / ".aiwf/state").mkdir(parents=True, exist_ok=True)
    path = base / ".aiwf/tasks" / f"{task_id}.md"
    path.write_text(body, encoding="utf-8")
    task = {"id": task_id, "status": "ready", "doc_path": f".aiwf/tasks/{task_id}.md"}
    (base / ".aiwf/state/tasks.json").write_text(
        json.dumps({"schema_version": 1, "default_max_active": 1, "tasks": [task]}),
        encoding="utf-8",
    )
    return task


class TestTaskProofContract(unittest.TestCase):
    def test_strict_task_packet_blocks_unfilled_proof_before_activation(self):
        from aiwf_core.core.task_proof import activation_proof_blockers

        base = Path(tempfile.mkdtemp(prefix="awproof_"))
        task = _write_task(
            base,
            "TASK-001",
            """# TASK-001

## Fixed Contract

### Structural Home

(fill)

### Objective

Ship the route.

### Forbidden Write

(fill)

### Proof Standard

Done When:

(fill - each item tagged Built/Wired/Running)

Verification Commands:

| Command | Expected Observable Output |
|---------|----------------------------|
| (fill) | (fill) |
""",
        )

        blockers = activation_proof_blockers(str(base), task)
        joined = "\n".join(blockers)
        self.assertIn("unfilled proof contract fields", joined)
        self.assertIn("no Built/Wired/Running proof level", joined)

    def test_wired_or_running_proof_requires_recorded_verification_commands(self):
        from aiwf_core.core.task_proof import (
            activation_proof_blockers,
            validate_testing_against_task,
        )

        base = Path(tempfile.mkdtemp(prefix="awproof_"))
        task = _write_task(
            base,
            "TASK-002",
            """# TASK-002

## Fixed Contract

### Structural Home

Goal GOAL-001 / Plan PLAN-001; this task wires the CLI route.

### Objective

CLI route is reachable from the supported entry path.

### Forbidden Write

legacy-runner/**

### Proof Standard

Done When:

- [Wired] `aiwf status` consumes the new route from the CLI parser.

Verification Commands:

| Command | Expected Observable Output |
|---------|----------------------------|
| python3 -m aiwf_core.cli status --prompt | lists required skill routing |
""",
        )

        self.assertEqual(activation_proof_blockers(str(base), task), [])
        proof = validate_testing_against_task(
            str(base),
            task,
            {"status": "passed", "commands": ["python3 -m pytest tests/embedded -q"]},
        )
        self.assertEqual(
            proof["missing_commands"],
            ["python3 -m aiwf_core.cli status --prompt"],
        )
        self.assertEqual(
            proof["missing_verification_results"],
            ["python3 -m aiwf_core.cli status --prompt"],
        )

        proof = validate_testing_against_task(
            str(base),
            task,
            {
                "status": "passed",
                "commands": ["python3 -m aiwf_core.cli status --prompt"],
                "verification_results": [{
                    "command": "python3 -m aiwf_core.cli status --prompt",
                    "expected": "lists required skill routing",
                    "observed": "lists required skill routing",
                    "matched": True,
                }],
            },
        )
        self.assertEqual(proof["missing_commands"], [])
        self.assertEqual(proof["missing_verification_results"], [])
        self.assertEqual(proof["mismatched_results"], [])

    def test_prepare_close_blocks_passed_testing_missing_task_packet_command(self):
        from aiwf_core.core.state_ops import prepare_close
        from aiwf_core.core.state_schema import QUALITY_DIMENSIONS, REVIEW_BASIS

        base = Path(tempfile.mkdtemp(prefix="awproof_"))
        for rel in (".aiwf/state", ".aiwf/records", ".aiwf/tasks"):
            (base / rel).mkdir(parents=True, exist_ok=True)
        (base / "README.md").write_text("test\n", encoding="utf-8")
        task = _write_task(
            base,
            "TASK-003",
            """# TASK-003

## Fixed Contract

### Structural Home

Goal GOAL-001 / Plan PLAN-001.

### Objective

CLI route is reachable from the supported entry path.

### Forbidden Write

legacy-runner/**

### Proof Standard

Done When:

- [Running] `aiwf status --prompt` runs through the installed CLI.

Verification Commands:

| Command | Expected Observable Output |
|---------|----------------------------|
| python3 -m aiwf_core.cli status --prompt | prints prompt routing |
""",
        )
        task["status"] = "active"
        (base / ".aiwf/state/tasks.json").write_text(
            json.dumps({"schema_version": 1, "default_max_active": 1, "tasks": [task]}),
            encoding="utf-8",
        )
        (base / ".aiwf/state/state.json").write_text(json.dumps({
            "phase": "reviewing",
            "workflow_level": "L1_review_light",
            "active_task_id": "TASK-003",
            "close_attempt": False,
            "closure_allowed": False,
            "scope_violation": False,
        }), encoding="utf-8")
        (base / ".aiwf/state/fix-loop.json").write_text(
            json.dumps({"status": "none"}),
            encoding="utf-8",
        )
        (base / ".aiwf/state/goals.json").write_text(json.dumps({
            "goals": [{
                "id": "GOAL-001",
                "meta_critique": {"status": "recorded"},
                "quality_brief": {"non_goals": ["test"]},
            }],
        }), encoding="utf-8")
        (base / ".aiwf/records/evidence.json").write_text(json.dumps({
            "records": [{
                "id": "EV-001",
                "status": "accepted",
                "trust_level": "role_recorded",
                "session_id": "s1",
                "task_id": "TASK-003",
            }],
        }), encoding="utf-8")
        (base / ".aiwf/records/testing.json").write_text(json.dumps({
            "status": "passed",
            "commands": ["python3 -m pytest tests/embedded -q"],
            "evidence_ids": ["EV-001"],
        }), encoding="utf-8")
        (base / ".aiwf/records/review.json").write_text(json.dumps({
            "verdict": "PASS",
            "result": "accepted",
            "closure_allowed": True,
            "cleanup_status": "fresh",
            "blockers": [],
            "stale_items": [],
            "accepted_evidence_ids": ["EV-001"],
            "quality_dimensions": {
                dim: {"score": "PASS", "note": ""} for dim in QUALITY_DIMENSIONS
            },
            "review_basis": {
                name: {"status": "covered", "note": ""} for name in REVIEW_BASIS
            },
        }), encoding="utf-8")

        result = prepare_close(str(base))

        self.assertFalse(result["passed"])
        self.assertTrue(
            any("Task Packet proof not covered" in blocker for blocker in result["blockers"]),
            result["blockers"],
        )

    def test_prepare_close_blocks_mismatched_verification_result(self):
        from aiwf_core.core.task_proof import validate_testing_against_task

        base = Path(tempfile.mkdtemp(prefix="awproof_"))
        task = _write_task(
            base,
            "TASK-004",
            """# TASK-004

## Fixed Contract

### Structural Home

Goal GOAL-001 / Plan PLAN-001.

### Objective

Route runs.

### Forbidden Write

none

### Proof Standard

Done When:

- [Running] route runs.

Verification Commands:

| Command | Expected Observable Output |
|---------|----------------------------|
| pytest tests/test_route.py | 1 passed |
""",
        )
        proof = validate_testing_against_task(str(base), task, {
            "status": "passed",
            "commands": ["pytest tests/test_route.py"],
            "verification_results": [{
                "command": "pytest tests/test_route.py",
                "expected": "1 passed",
                "observed": "failed",
                "matched": False,
            }],
        })

        self.assertEqual(proof["missing_commands"], [])
        self.assertEqual(proof["mismatched_results"], ["pytest tests/test_route.py"])


if __name__ == "__main__":
    unittest.main()
