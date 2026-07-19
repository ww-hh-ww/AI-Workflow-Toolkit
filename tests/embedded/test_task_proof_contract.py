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
        json.dumps({"schema_version": 1, "tasks": [task]}),
        encoding="utf-8",
    )
    return task


class TestTaskProofContract(unittest.TestCase):
    def test_task_proof_exposes_current_fix_loop_to_follow_up_roles(self):
        from aiwf_core.core.task_proof import build_task_proof

        base = Path(tempfile.mkdtemp(prefix="awproof_"))
        record_path = base / ".aiwf/records/tasks/TASK-FIX.json"
        record_path.parent.mkdir(parents=True)
        record_path.write_text(json.dumps({
            "task_id": "TASK-FIX",
            "implementation": {"task_id": "TASK-FIX", "implementation_ref": "abc"},
            "testing": {"task_id": "TASK-FIX", "status": "missing"},
            "review": {"task_id": "TASK-FIX", "result": "unknown"},
            "fix_loop": {
                "status": "open",
                "route": "tester",
                "reason": "old path still bypasses the fix",
                "required_verification": ["prove the old path is closed"],
            },
        }), encoding="utf-8")

        proof = build_task_proof(str(base), {"id": "TASK-FIX", "status": "active"})

        self.assertEqual(proof["fix_loop"]["route"], "tester")
        self.assertEqual(
            proof["fix_loop"]["required_verification"],
            ["prove the old path is closed"],
        )

    def test_forbidden_write_is_optional(self):
        from aiwf_core.core.task_proof import activation_proof_blockers

        base = Path(tempfile.mkdtemp(prefix="aiwf_proof_"))
        task_dir = base / ".aiwf/tasks"
        task_dir.mkdir(parents=True)
        (task_dir / "TASK-OPTIONAL.md").write_text(
            "# TASK-OPTIONAL\n\n"
            "## Fixed Contract\n\n"
            "### Structural Home\n\nGoal and Plan.\n\n"
            "### Objective\n\nObservable output.\n\n"
            "### Contract Responsibility\n\nOwn the entry path.\n\n"
            "### Proof Standard\n\n"
            "Done When:\n\n- Running: command prints hello.\n\n"
            "Verification Commands:\n\n"
            "| Command | Expected Observable Output |\n"
            "|---|---|\n| python3 app.py | hello |\n",
            encoding="utf-8",
        )
        task = {"id": "TASK-OPTIONAL", "doc_path": ".aiwf/tasks/TASK-OPTIONAL.md"}
        self.assertEqual(activation_proof_blockers(str(base), task), [])

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

### Contract Responsibility

(fill)

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

### Contract Responsibility

The CLI status route is reachable and proves prompt routing from the supported entry path.

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

    def test_task_close_blocks_passed_testing_missing_task_command(self):
        from aiwf_core.core.task_ledger import close_task
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

### Contract Responsibility

The installed CLI status prompt route is reachable and produces prompt routing.

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
        task["requirements"] = {"tester_required": True, "reviewer_required": True}
        (base / ".aiwf/state/tasks.json").write_text(
            json.dumps({"schema_version": 1, "tasks": [task]}),
            encoding="utf-8",
        )
        (base / ".aiwf/state/state.json").write_text(json.dumps({
            "phase": "reviewing",
            "active_task_id": "TASK-003",
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
            }],
        }), encoding="utf-8")
        (base / ".aiwf/records/implementation.json").write_text(json.dumps({
            "task_id": "TASK-003", "implementation_ref": "abc",
        }), encoding="utf-8")
        (base / ".aiwf/records/testing.json").write_text(json.dumps({
            "status": "passed",
            "commands": ["python3 -m pytest tests/embedded -q"],
            "task_id": "TASK-003", "based_on_ref": "abc", "tested_ref": "def",
        }), encoding="utf-8")
        (base / ".aiwf/records/review.json").write_text(json.dumps({
            "result": "accepted",
            "closure_allowed": True,
            "cleanup_status": "fresh",
            "blockers": [],
            "stale_items": [],
            "task_id": "TASK-003", "reviewed_ref": "def",
        }), encoding="utf-8")

        result = close_task(str(base), "TASK-003")

        self.assertFalse(result["closed"])
        self.assertTrue(
            any("missing Verification Command" in blocker for blocker in result["blockers"]),
            result["blockers"],
        )

    def test_proof_validation_reports_mismatched_result(self):
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

### Contract Responsibility

The route command runs and reports the expected passing test result.

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
