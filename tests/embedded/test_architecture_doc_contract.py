"""Architecture snapshot requirement contract tests."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 15


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


SNAPSHOT = """# Architecture Snapshot

## Project Overview
This project is a compact test application used to verify the architecture
snapshot contract. It has enough text to represent a real handoff summary,
instead of a placeholder file.

## Architecture Summary
The system separates workflow state, command handlers, and human reports. The
snapshot describes the current shape and explicitly cites the evidence used.

## Capability / Goal Tree Overview
The root capability owns planning, implementation, testing, review, and closure
governance. Child capabilities map to modules through PROJECT-MAP bindings.

## Module and Directory Responsibilities
Command modules expose CLI entrypoints. Core modules own validation and state
mutation. Reports are human projections, not machine authority.

## Key Flows
Planner marks a snapshot required, architecture documentation is written, then
validation checks required sections and evidence references before milestone
acceptance or close can proceed.

## Evidence Manifest
- Goal Tree: `.aiwf/state/goals.json`
- Project Map: `.aiwf/assets/project-map.json`
- Human Projection: `.aiwf/records/项目地图.md`
- Source: `aiwf_core/core/architecture_doc.py`
- Tests: `tests/embedded/test_architecture_doc_contract.py`
"""


class TestArchitectureDocContract(unittest.TestCase):
    __unittest_skip__ = True  # V1: architecture-doc removed
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aiwf_archdoc_"))
        from aiwf_core.core.state_schema import MVP_STATE_FILES
        for rel, factory in MVP_STATE_FILES.items():
            _write(self.tmp / ".aiwf" / rel, factory())
        (self.tmp / ".claude").mkdir(parents=True, exist_ok=True)
        _write(self.tmp / ".claude" / "settings.json", {"hooks": {}})

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, *args):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", *args],
            cwd=str(self.tmp),
            env=env,
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )

    def _run_ok(self, *args):
        r = self._run(*args)
        self.assertEqual(r.returncode, 0, f"{args}\nstdout={r.stdout}\nstderr={r.stderr}")
        return r

    def _write_snapshot(self):
        path = self.tmp / ".aiwf" / "records" / "架构详细设计.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(SNAPSHOT, encoding="utf-8")
        return path

    @unittest.skip("V1: feature removed")
    def test_require_status_validate_satisfy_lifecycle(self):
        required = self._run_ok("architecture-doc", "require", "--reason", "milestone handoff")
        self.assertIn("Architecture snapshot required", required.stdout)

        status = self._run_ok("architecture-doc", "status").stdout
        self.assertIn("Required: yes", status)
        self.assertIn("milestone handoff", status)

        invalid = self._run("architecture-doc", "validate")
        self.assertNotEqual(invalid.returncode, 0)
        self.assertIn("architecture snapshot missing", invalid.stdout)

        self._write_snapshot()
        valid = self._run_ok("architecture-doc", "validate").stdout
        self.assertIn("Architecture snapshot: valid", valid)

        satisfied = self._run_ok("architecture-doc", "satisfy").stdout
        self.assertIn("Architecture snapshot satisfied", satisfied)
        data = json.loads((self.tmp / ".aiwf" / "records" / "architecture-doc.json").read_text())
        self.assertEqual(data["status"], "satisfied")
        self.assertFalse(data["required"])

    @unittest.skip("V1: feature removed")
    def test_waive_requires_reason_and_clears_requirement(self):
        self._run_ok("architecture-doc", "require", "--reason", "handoff")
        blocked = self._run("architecture-doc", "waive")
        self.assertNotEqual(blocked.returncode, 0)
        waived = self._run_ok("architecture-doc", "waive", "--reason", "too unstable for snapshot")
        self.assertIn("Architecture snapshot waived", waived.stdout)
        status = self._run_ok("architecture-doc", "status").stdout
        self.assertIn("Required: no", status)
        self.assertIn("too unstable", status)

    @unittest.skip("V1: feature removed")
    def test_status_prompt_reports_required_snapshot(self):
        self._run_ok("architecture-doc", "require", "--reason", "release handoff")
        # architecture-doc status confirms the requirement is tracked
        arch_status = self._run_ok("architecture-doc", "status").stdout
        self.assertIn("Required: yes", arch_status)
        self.assertIn("release handoff", arch_status)
        # Prompt mode shows primary phase skill
        prompt = self._run_ok("status", "--prompt").stdout
        self.assertIn("/aiwf-planner", prompt)

    @unittest.skip("V1: feature removed")
    def test_milestone_confirm_blocks_until_required_snapshot_satisfied(self):
        from aiwf_core.core.state.milestone_ops import (
            confirm_milestone_acceptance,
            record_milestone_arch_review,
            record_milestone_assessment,
            record_milestone_integration,
            upsert_milestone,
        )
        from aiwf_core.core.architecture_doc import require_architecture_doc, satisfy_architecture_doc

        upsert_milestone(str(self.tmp), "MS-001", goal_id="GOAL-001", status="active")
        record_milestone_assessment(
            str(self.tmp), "MS-001", verdict="PASS",
            summary="Stage outcome is coherent.",
        )
        record_milestone_integration(
            str(self.tmp), "MS-001", status="passed", summary="Integration passed",
            coverage_mode="function_reverse_trace", main_path_status="passed",
            source_files=["src/main.py"],
            function_traces=[{
                "file": "src/main.py",
                "function": "main",
                "callers": [],
                "status": "entrypoint",
                "reason": "",
            }],
        )
        record_milestone_arch_review(str(self.tmp), "MS-001", status="intact")
        require_architecture_doc(str(self.tmp), "milestone handoff")

        blocked = confirm_milestone_acceptance(
            str(self.tmp), "MS-001", confirmed_by="user",
            summary="Accepted stage outcome",
        )
        self.assertTrue(blocked["confirmed"])

        self._write_snapshot()
        satisfy_architecture_doc(str(self.tmp))
        confirmed = confirm_milestone_acceptance(
            str(self.tmp), "MS-001", confirmed_by="user",
            summary="Accepted stage outcome",
        )
        self.assertTrue(confirmed["confirmed"], confirmed["blockers"])


if __name__ == "__main__":
    unittest.main()

