"""V2 path layout and governance gate regression contracts."""
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


def _env():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    return env


def _seed_state(root: Path):
    from aiwf_core.core.state_schema import MVP_STATE_FILES
    (root / ".aiwf").mkdir(parents=True, exist_ok=True)
    for rel, default_fn in MVP_STATE_FILES.items():
        p = root / ".aiwf" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(default_fn(), indent=2) + "\n")


class TestV2PathGovernanceContract(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="awv2_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", *args],
            cwd=str(self.tmp),
            env=_env(),
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )

    def test_init_creates_v2_paths_not_flat_state_files(self):
        result = self._run_cli("init")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.tmp / ".aiwf" / "state" / "state.json").exists())
        self.assertTrue((self.tmp / ".aiwf" / "quality" / "review.json").exists())
        self.assertTrue((self.tmp / ".aiwf" / "evidence" / "records.json").exists())
        self.assertFalse((self.tmp / ".aiwf" / "state.json").exists())
        self.assertFalse((self.tmp / ".aiwf" / "review.json").exists())

    def test_embedded_templates_do_not_instruct_core_flat_paths(self):
        offenders = []
        old_paths = [
            ".aiwf/state.json", ".aiwf/goal.json", ".aiwf/contexts.json",
            ".aiwf/evidence.json", ".aiwf/testing.json", ".aiwf/review.json",
            ".aiwf/fix-loop.json", ".aiwf/task-history.json",
            ".aiwf/current-state.md", ".aiwf/report.md", ".aiwf/quality-digest.md",
            ".aiwf/PROJECT-MAP.md",
        ]
        for path in (PROJECT_ROOT / "aiwf_core" / "embedded_templates").rglob("*"):
            if path.is_file():
                text = path.read_text(encoding="utf-8", errors="ignore")
                for old in old_paths:
                    if old in text:
                        offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {old}")
        self.assertEqual(offenders, [])

    def test_start_context_update_existing_persists_auto_notes(self):
        _seed_state(self.tmp)
        from aiwf_core.core.state_ops import start_context
        start_context(str(self.tmp), "CTX-001", allowed_write=["src/"], note="first")
        start_context(str(self.tmp), "CTX-001", allowed_write=["src/"], note="second")
        contexts = json.loads((self.tmp / ".aiwf" / "state" / "contexts.json").read_text())
        ctx = contexts["contexts"][0]
        notes = "\n".join(ctx.get("notes", []))
        self.assertIn("second", notes)
        self.assertTrue("[DRIFT]" in notes or "[ASSET]" in notes or "[GRAVITY]" in notes)

    def test_record_quality_policy_applies_gravity_escalation(self):
        _seed_state(self.tmp)
        history_path = self.tmp / ".aiwf" / "history" / "task-history.json"
        history_path.parent.mkdir(parents=True, exist_ok=True)
        history_path.write_text(json.dumps({
            "tasks": [
                {"id": "T1", "changed_files": ["src/core.py"], "fix_loop_attempt_count": 0},
                {"id": "T2", "changed_files": ["src/core.py"], "fix_loop_attempt_count": 0},
                {"id": "T3", "changed_files": ["src/core.py"], "fix_loop_attempt_count": 0},
            ]
        }, indent=2))
        from aiwf_core.core.state_ops import record_quality_policy
        record_quality_policy(str(self.tmp), "feature", "L1_review_light")
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        self.assertTrue(state["quality_escalation_required"])
        self.assertEqual(state["recommended_minimum_level"], "L2_standard_team")
        self.assertIn("gravity suggests", state["quality_escalation_reason"])

    def test_prepare_close_does_not_auto_accept_pending_evidence(self):
        _seed_state(self.tmp)
        (self.tmp / ".aiwf" / "evidence" / "records.json").write_text(json.dumps({
            "records": [{"id": "EV-001", "status": "pending", "session_id": "executor"}]
        }, indent=2))
        (self.tmp / ".aiwf" / "quality" / "review.json").write_text(json.dumps({
            "result": "accepted", "closure_allowed": True,
            "accepted_evidence_ids": [], "rejected_evidence_ids": [],
            "cleanup_status": "fresh", "structure_status": "accepted",
            "adversarial_observations": [],
        }, indent=2))
        (self.tmp / ".aiwf" / "quality" / "testing.json").write_text(json.dumps({
            "status": "adequate", "commands": ["pytest"], "untested_risks": []
        }, indent=2))
        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["phase"] = "reviewing"
        state_path.write_text(json.dumps(state, indent=2))
        from aiwf_core.core.state_ops import prepare_close
        result = prepare_close(str(self.tmp))
        evidence = json.loads((self.tmp / ".aiwf" / "evidence" / "records.json").read_text())
        self.assertFalse(result["close_attempt_set"])
        self.assertIn("no accepted evidence", result["blockers"])
        self.assertEqual(evidence["records"][0]["status"], "pending")

    def test_l2_empty_adversarial_observations_are_allowed_but_pending_blocks(self):
        from aiwf_core.core.closure_contract import closure_conditions_met
        state = {
            "close_attempt": True, "phase": "closing", "workflow_level": "L2_standard_team",
            "scope_violation": False,
        }
        evidence = {"records": [
            {"id": "EV-001", "status": "accepted", "session_id": "executor"},
            {"id": "EV-002", "status": "accepted", "session_id": "tester"},
            {"id": "EV-003", "status": "accepted", "session_id": "reviewer"},
        ]}
        testing = {"status": "adequate"}
        fix_loop = {"status": "none"}
        review = {
            "result": "accepted", "closure_allowed": True,
            "cleanup_status": "fresh", "structure_status": "accepted",
            "stale_items": [], "cleanup_blockers": [], "adversarial_observations": [],
        }
        self.assertTrue(closure_conditions_met(state, evidence, testing, review, fix_loop)["passed"])
        review["adversarial_observations"] = [{"id": "ADV-001", "disposition": "pending"}]
        gates = closure_conditions_met(state, evidence, testing, review, fix_loop)
        self.assertFalse(gates["passed"])
        self.assertIn("adversarial observation", " ".join(gates["blockers"]))

    def test_l2_requires_three_distinct_accepted_evidence_sessions(self):
        from aiwf_core.core.closure_contract import closure_conditions_met
        gates = closure_conditions_met(
            {"close_attempt": True, "workflow_level": "L2_standard_team"},
            {"records": [
                {"id": "EV-001", "status": "accepted", "session_id": "same"},
                {"id": "EV-002", "status": "accepted", "session_id": "same"},
            ]},
            {"status": "adequate"},
            {"result": "accepted", "closure_allowed": True, "cleanup_status": "fresh", "structure_status": "accepted"},
            {"status": "none"},
        )
        self.assertFalse(gates["passed"])
        self.assertFalse(gates["session_diversity_ok"])
        self.assertIn("3 distinct sessions", " ".join(gates["blockers"]))

    def test_adversarial_disposition_requires_reason(self):
        _seed_state(self.tmp)
        review_path = self.tmp / ".aiwf" / "quality" / "review.json"
        review = json.loads(review_path.read_text())
        review["adversarial_observations"] = [{"id": "ADV-001", "disposition": "pending"}]
        review_path.write_text(json.dumps(review, indent=2))
        from aiwf_core.core.state_ops import disposition_adversarial_observation
        with self.assertRaises(ValueError):
            disposition_adversarial_observation(str(self.tmp), "ADV-001", "accepted", "")

    def test_export_report_writes_v2_report_path(self):
        result = self._run_cli("install", "claude", "--force")
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self._run_cli("export-report")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.tmp / ".aiwf" / "reports" / "闭合报告.md").exists())
        self.assertFalse((self.tmp / ".aiwf" / "report.md").exists())


if __name__ == "__main__":
    unittest.main()
