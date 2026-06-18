"""Risk findings must drive rework in daily and periodic reviews."""
import json
import tempfile
import unittest
from pathlib import Path


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


class TestReviewRiskRework(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aiwf_review_risk_"))
        from aiwf_core.core.state_schema import MVP_STATE_FILES
        for rel, factory in MVP_STATE_FILES.items():
            _write(self.tmp / ".aiwf" / rel, factory())

    def _set_phase(self, phase: str) -> None:
        path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(path.read_text())
        state["phase"] = phase
        _write(path, state)

    def _seed_task(self, task_id: str, title: str, status: str = "ready") -> None:
        from aiwf_core.core.state.plan_ops import upsert_plan
        from aiwf_core.core.task_ledger import upsert_task

        upsert_task(str(self.tmp), task_id, title, status=status)
        plan_id = f"PLAN-{task_id}"
        plan_path = self.tmp / ".aiwf" / "plans" / f"{plan_id}.md"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(
            f"# {plan_id}\n\nPlan ID: {plan_id}\nParent Goal: GOAL-001\n"
            f"Task IDs: {task_id}\n\n## Goal\nReview risk\n\n## Route\n- review\n\n"
            "## Scope\n- architecture\n\n## Risks\n- architecture drift\n\n"
            "## Verification\n- Machine-verifiable: yes\n\n"
            "## Impact\n- docs: no — test\n- project_map: no — test\n"
            "- environment: no — test\n- capabilities: no — test\n"
            "- quality_summary: no — test\n\n## Done Means\n- review recorded\n\n"
            "## Goal Progress\n- reviewed\n\n## Next Steps\n1. done\n",
            encoding="utf-8",
        )
        upsert_plan(
            str(self.tmp),
            plan_id,
            goal_id="GOAL-001",
            task_ids=[task_id],
            allowed_write=["src/"],
            purpose="Review architecture risk",
            work_intent="verification",
        )
        ledger_path = self.tmp / ".aiwf" / "state" / "tasks.json"
        ledger = json.loads(ledger_path.read_text())
        for task in ledger["tasks"]:
            if task["id"] == task_id:
                task["plan_id"] = plan_id
                task["parent_plan"] = plan_id
        _write(ledger_path, ledger)

    def test_daily_review_high_observation_cannot_pass_or_defer(self):
        from aiwf_core.core.state.adversarial_ops import disposition_adversarial_observation
        from aiwf_core.core.state.review_ops import record_review

        self._set_phase("closing")
        observation = {
            "id": "ADV-001",
            "severity": "critical",
            "kind": "main_path",
            "message": "authentication rejects the main path",
            "disposition": "pending",
        }
        with self.assertRaisesRegex(ValueError, "cannot pass"):
            record_review(
                str(self.tmp),
                verdict="PASS_WITH_RISK",
                adversarial_observations=[observation],
            )

        record_review(
            str(self.tmp),
            verdict="REVISE",
            blockers=["main path is broken"],
            adversarial_observations=[observation],
        )
        with self.assertRaisesRegex(ValueError, "only be dispositioned as resolved"):
            disposition_adversarial_observation(
                str(self.tmp), "ADV-001", "deferred", "fix next cycle"
            )

    def test_daily_revise_requires_retest_resolution_and_evidence(self):
        from aiwf_core.core.state.review_ops import record_review
        from aiwf_core.core.state.testing_ops import record_testing

        self._set_phase("closing")
        record_review(str(self.tmp), verdict="REVISE", blockers=["broken auth path"])
        with self.assertRaisesRegex(ValueError, "requires --resolution"):
            record_review(str(self.tmp), verdict="PASS")

        record_testing(str(self.tmp), status="adequate", commands=["pytest"])
        with self.assertRaisesRegex(ValueError, "resolution-evidence-id"):
            record_review(str(self.tmp), verdict="PASS", resolution="auth path repaired")
        evidence_path = self.tmp / ".aiwf" / "records" / "evidence.jsonl"
        evidence = json.loads(evidence_path.read_text())
        evidence["records"].append({"id": "EV-FIX", "status": "accepted"})
        _write(evidence_path, evidence)

        result = record_review(
            str(self.tmp),
            verdict="PASS",
            resolution="auth path repaired",
            resolution_evidence_ids=["EV-FIX"],
        )
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["review_history"][-1]["verdict"], "REVISE")

    def test_periodic_issues_block_ordinary_tasks_until_fix_and_rereview(self):
        from aiwf_core.core.state.architecture_review_ops import record_architecture_review
        from aiwf_core.core.task_ledger import activate_task

        history = {
            "tasks": [{"id": f"TASK-{i}", "title": "Done"} for i in range(10)]
        }
        _write(
            self.tmp / ".aiwf" / "state" / "tasks.json",
            history,
        )
        # V1: Architect is read-only, no ARCH-* task needed
        record_architecture_review(
            str(self.tmp),
            status="issues_found",
            findings=[{"severity": "critical", "description": "main auth path is disconnected"}],
        )
        # V1: Periodic architecture review does NOT block ordinary task activation
        self._seed_task("TASK-NEXT", "ordinary feature")
        result = activate_task(str(self.tmp), "TASK-NEXT")
        self.assertTrue(result["activated"], result.get("blockers", []))

    def test_periodic_intact_requires_closed_fix_task_and_evidence(self):
        from aiwf_core.core.state.architecture_review_ops import record_architecture_review

        # V1: Architect is read-only. Record issues directly, no ARCH-* task.
        record_architecture_review(
            str(self.tmp),
            status="issues_found",
            findings=[{"severity": "high", "description": "coupling breaks boundary"}],
        )
        # V1: Transition issues_found → intact requires resolution + evidence
        with self.assertRaisesRegex(ValueError, "require a resolution"):
            record_architecture_review(
                str(self.tmp),
                status="intact",
            )
        with self.assertRaisesRegex(ValueError, "requires evidence"):
            record_architecture_review(
                str(self.tmp),
                status="intact",
                resolution="boundary repaired",
            )
        evidence_path = self.tmp / ".aiwf" / "records" / "evidence.jsonl"
        _write(evidence_path, {"records": [{"id": "EV-ARCH", "status": "accepted"}]})
        result = record_architecture_review(
            str(self.tmp),
            status="intact",
            resolution="boundary repaired and verified",
            resolution_evidence_ids=["EV-ARCH"],
        )
        self.assertEqual(result["status"], "intact")
        self.assertEqual(result["review_history"][-1]["status"], "issues_found")


if __name__ == "__main__":
    unittest.main()
