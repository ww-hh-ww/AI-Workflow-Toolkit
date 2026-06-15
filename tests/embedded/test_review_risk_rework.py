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
        plan_path = self.tmp / ".aiwf" / "artifacts" / "plans" / f"{plan_id}.md"
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
        ledger_path = self.tmp / ".aiwf" / "runtime" / "history" / "task-ledger.json"
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
        evidence_path = self.tmp / ".aiwf" / "artifacts" / "evidence" / "records.json"
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
            self.tmp / ".aiwf" / "runtime" / "history" / "task-history.json",
            history,
        )
        self._seed_task("ARCH-010", "[Architect] periodic review")
        activated = activate_task(str(self.tmp), "ARCH-010")
        self.assertTrue(activated["activated"], activated["blockers"])
        record_architecture_review(
            str(self.tmp),
            task_id="ARCH-010",
            status="issues_found",
            issues=[{"severity": "critical", "description": "main auth path is disconnected"}],
        )

        ledger_path = self.tmp / ".aiwf" / "runtime" / "history" / "task-ledger.json"
        ledger = json.loads(ledger_path.read_text())
        for task in ledger["tasks"]:
            if task["id"] == "ARCH-010":
                task["status"] = "closed"
        ledger["active_task_id"] = None
        _write(ledger_path, ledger)
        self._set_phase("closed")

        self._seed_task("TASK-NEXT", "ordinary feature")
        blocked = activate_task(str(self.tmp), "TASK-NEXT")
        self.assertFalse(blocked["activated"])
        self.assertTrue(any("unresolved issues" in item for item in blocked["blockers"]))

        self._seed_task("ARCH-FIX-001", "[Architecture Fix] repair auth")
        remediation = activate_task(str(self.tmp), "ARCH-FIX-001")
        self.assertTrue(remediation["activated"], remediation["blockers"])

    def test_periodic_intact_requires_closed_fix_task_and_evidence(self):
        from aiwf_core.core.state.architecture_review_ops import record_architecture_review
        from aiwf_core.core.task_ledger import activate_task

        self._seed_task("ARCH-001", "[Architect] initial review")
        activated = activate_task(str(self.tmp), "ARCH-001")
        self.assertTrue(activated["activated"], activated["blockers"])
        record_architecture_review(
            str(self.tmp),
            task_id="ARCH-001",
            status="issues_found",
            issues=[{"severity": "high", "description": "coupling breaks boundary"}],
        )

        ledger_path = self.tmp / ".aiwf" / "runtime" / "history" / "task-ledger.json"
        ledger = json.loads(ledger_path.read_text())
        for task in ledger["tasks"]:
            if task["id"] == "ARCH-001":
                task["status"] = "closed"
        ledger["active_task_id"] = None
        _write(ledger_path, ledger)
        self._set_phase("closed")

        self._seed_task("ARCH-002", "[Architect] follow-up review")
        self.assertTrue(activate_task(str(self.tmp), "ARCH-002")["activated"])
        with self.assertRaisesRegex(ValueError, "closed ARCH-FIX"):
            record_architecture_review(
                str(self.tmp),
                task_id="ARCH-002",
                status="intact",
                resolution="boundary repaired",
                resolution_evidence_ids=["EV-ARCH"],
                resolved_task_ids=["ARCH-FIX-001"],
            )
        ledger = json.loads(ledger_path.read_text())
        ledger["tasks"].append({
            "id": "ARCH-FIX-001",
            "title": "[Architecture Fix] repair boundary",
            "status": "closed",
        })
        _write(ledger_path, ledger)
        evidence_path = self.tmp / ".aiwf" / "artifacts" / "evidence" / "records.json"
        _write(evidence_path, {"records": [{"id": "EV-ARCH", "status": "accepted"}]})
        result = record_architecture_review(
            str(self.tmp),
            task_id="ARCH-002",
            status="intact",
            resolution="boundary repaired and verified",
            resolution_evidence_ids=["EV-ARCH"],
            resolved_task_ids=["ARCH-FIX-001"],
        )
        self.assertEqual(result["status"], "intact")
        self.assertEqual(result["review_history"][-1]["status"], "issues_found")


if __name__ == "__main__":
    unittest.main()
