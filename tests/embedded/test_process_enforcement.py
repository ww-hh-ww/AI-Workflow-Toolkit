"""Mechanical enforcement for L2/L3 completion and periodic architecture review."""
import json
import tempfile
import unittest
from pathlib import Path


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


class TestProcessEnforcement(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aiwf_process_"))
        from aiwf_core.core.state_schema import MVP_STATE_FILES
        for rel, factory in MVP_STATE_FILES.items():
            _write(self.tmp / ".aiwf" / rel, factory())

    def _set_l2(self):
        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["workflow_level"] = "L2_standard_team"
        _write(state_path, state)
        self._seed_planning_contracts()

    def _seed_planning_contracts(self):
        goal_path = self.tmp / ".aiwf" / "state" / "goal.json"
        goal = json.loads(goal_path.read_text())
        brief = goal["quality_brief"]
        brief["evaluation_contract"].update({
            "user_visible_outcome": "Requested behavior works",
            "acceptance_criteria": ["behavior verified"],
            "test_obligations": ["run focused and regression tests"],
            "review_obligations": ["review scope and correctness"],
        })
        brief["architecture_brief"]["target_structure"] = "Preserve declared module boundaries"
        _write(goal_path, goal)

    def _seed_complete_quality_chain(self):
        _write(self.tmp / ".aiwf" / "quality" / "testing.json", {
            "status": "adequate", "commands": ["pytest"],
            "validation_layers": ["targeted", "full_regression", "real_usage"],
            "full_suite_status": "passed",
            "real_usage_status": "passed",
            "real_usage_reason": "project CLI smoke passed",
        })
        _write(self.tmp / ".aiwf" / "quality" / "review.json", {
            "result": "accepted",
            "closure_allowed": True,
            "accepted_evidence_ids": ["EV-1", "EV-2", "EV-3"],
            "cleanup_status": "fresh",
            "cleanup_verified_at": "2026-01-01T00:00:00+00:00",
            "stale_items": [],
            "cleanup_blockers": [],
            "structure_status": "accepted",
            "structure_blockers": [],
            "adversarial_observations": [],
        })
        _write(self.tmp / ".aiwf" / "evidence" / "records.json", {"records": [
            {"id": "EV-1", "trust": "machine_observed", "session_id": "executor-session", "agent_id": "executor", "timestamp": "2026-01-01T00:00:01+00:00"},
            {"id": "EV-2", "trust": "machine_observed", "session_id": "tester-session", "agent_id": "tester", "timestamp": "2026-01-01T00:00:02+00:00"},
            {"id": "EV-3", "trust": "machine_observed", "session_id": "reviewer-session", "agent_id": "reviewer", "timestamp": "2026-01-01T00:00:03+00:00"},
        ]})
        goal_path = self.tmp / ".aiwf" / "state" / "goal.json"
        goal = json.loads(goal_path.read_text())
        goal["decisions"] = [{"source": "planner", "decision": "Meta-critique completed"}]
        goal["meta_critique"] = {
            "status": "completed", "summary": "Review signals dispositioned",
            "recorded_by": "planner", "recorded_at": "2026-01-01T00:00:04+00:00",
        }
        _write(goal_path, goal)

    def test_active_l2_task_cannot_close_when_quality_chain_was_skipped(self):
        from aiwf_core.core.task_ledger import activate_task, close_task, upsert_task
        self._set_l2()
        upsert_task(str(self.tmp), "TASK-1", "Feature", status="ready")
        self.assertTrue(activate_task(str(self.tmp), "TASK-1")["activated"])

        result = close_task(str(self.tmp), "TASK-1")

        self.assertFalse(result["closed"])
        text = " ".join(result["blockers"])
        self.assertIn("independent testing", text)
        self.assertIn("independent review", text)
        self.assertIn("meta-critique", text)
        self.assertIn("3 distinct sessions", text)

    def test_active_l2_task_closes_after_complete_quality_chain(self):
        from aiwf_core.core.task_ledger import activate_task, close_task, upsert_task
        self._set_l2()
        self._seed_complete_quality_chain()
        upsert_task(str(self.tmp), "TASK-1", "Feature", status="ready")
        self.assertTrue(activate_task(str(self.tmp), "TASK-1")["activated"])

        result = close_task(str(self.tmp), "TASK-1")

        self.assertTrue(result["closed"], result["blockers"])

    def test_periodic_architecture_review_blocks_ordinary_activation(self):
        from aiwf_core.core.task_ledger import activate_task, upsert_task
        _write(self.tmp / ".aiwf" / "history" / "task-history.json", {
            "tasks": [{"id": f"TASK-{i}", "title": "Done"} for i in range(10)]
        })
        upsert_task(str(self.tmp), "TASK-NEXT", "Next feature", status="ready")

        result = activate_task(str(self.tmp), "TASK-NEXT")

        self.assertFalse(result["activated"])
        self.assertTrue(any("periodic architecture review due" in b for b in result["blockers"]))

    def test_architecture_review_task_can_activate_when_review_is_due(self):
        from aiwf_core.core.task_ledger import activate_task, upsert_task
        _write(self.tmp / ".aiwf" / "history" / "task-history.json", {
            "tasks": [{"id": f"TASK-{i}", "title": "Done"} for i in range(10)]
        })
        upsert_task(str(self.tmp), "ARCH-010", "[Architect] milestone review", status="ready")

        result = activate_task(str(self.tmp), "ARCH-010")

        self.assertTrue(result["activated"], result["blockers"])

    def test_activation_mechanically_routes_cross_module_semantic_task_to_l2(self):
        from aiwf_core.core.task_ledger import activate_task, upsert_task
        self._seed_planning_contracts()
        upsert_task(
            str(self.tmp), "TASK-ROUTE", "Cross module change", status="ready",
            allowed_write=["api/handler.py", "core/service.py"],
        )

        result = activate_task(str(self.tmp), "TASK-ROUTE")

        self.assertTrue(result["activated"], result["blockers"])
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        self.assertEqual(state["workflow_level"], "L2_standard_team")
        self.assertEqual(state["test_template"], "regression_plus_boundary_adverse")
        self.assertEqual(state["review_template"], "standard_review")
        self.assertEqual(state["exploration_budget"], "asset_first_affected_files")

    def test_l2_activation_rejects_missing_planning_contracts(self):
        from aiwf_core.core.task_ledger import activate_task, upsert_task
        self._set_l2()
        goal_path = self.tmp / ".aiwf" / "state" / "goal.json"
        goal = json.loads(goal_path.read_text())
        goal["quality_brief"]["evaluation_contract"] = {}
        goal["quality_brief"]["architecture_brief"] = {}
        _write(goal_path, goal)
        upsert_task(str(self.tmp), "TASK-NO-CONTRACT", "Missing contract", status="ready")

        result = activate_task(str(self.tmp), "TASK-NO-CONTRACT")

        self.assertFalse(result["activated"])
        self.assertTrue(any("Evaluation" in b or "evaluation_contract" in b for b in result["blockers"]))
        self.assertTrue(any("Architecture Brief" in b for b in result["blockers"]))

    def test_cleanup_must_precede_reviewer_evidence(self):
        from aiwf_core.core.task_ledger import activate_task, close_task, upsert_task
        self._set_l2()
        self._seed_complete_quality_chain()
        review_path = self.tmp / ".aiwf" / "quality" / "review.json"
        review = json.loads(review_path.read_text())
        review["cleanup_verified_at"] = "2026-01-01T00:00:05+00:00"
        _write(review_path, review)
        upsert_task(str(self.tmp), "TASK-ORDER", "Order", status="ready")
        self.assertTrue(activate_task(str(self.tmp), "TASK-ORDER")["activated"])

        result = close_task(str(self.tmp), "TASK-ORDER")

        self.assertFalse(result["closed"])
        self.assertTrue(any("cleanup must be verified before Reviewer" in b for b in result["blockers"]))

    def test_l3_requires_checkpoint_or_explicit_skip(self):
        from aiwf_core.core.task_ledger import activate_task, close_task, upsert_task
        self._set_l2()
        self._seed_complete_quality_chain()
        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["workflow_level"] = "L3_full_power"
        _write(state_path, state)
        upsert_task(str(self.tmp), "TASK-L3", "Critical", status="ready")
        self.assertTrue(activate_task(str(self.tmp), "TASK-L3")["activated"])

        result = close_task(str(self.tmp), "TASK-L3")

        self.assertFalse(result["closed"])
        self.assertTrue(any("checkpoint" in b for b in result["blockers"]))

    def test_prepare_close_cannot_bypass_active_task_completion_contract(self):
        from aiwf_core.core.state_ops import prepare_close
        from aiwf_core.core.task_ledger import activate_task, upsert_task
        self._set_l2()
        upsert_task(str(self.tmp), "TASK-BYPASS", "Cannot bypass", status="ready")
        self.assertTrue(activate_task(str(self.tmp), "TASK-BYPASS")["activated"])
        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["phase"] = "reviewing"
        _write(state_path, state)

        result = prepare_close(str(self.tmp))

        self.assertFalse(result["close_attempt_set"])
        self.assertTrue(any("independent testing" in b for b in result["blockers"]))

    def test_planner_guidance_explains_routing_and_next_required_step(self):
        from aiwf_core.core.process_contract import planner_process_guidance
        guidance = planner_process_guidance(str(self.tmp))
        self.assertEqual(guidance["workflow_level"], "L1_review_light")
        self.assertTrue(any("activate one task" in x for x in guidance["required_now"]))
        self.assertTrue(any("Explorer" in x for x in guidance["advisory"]))
        self.assertTrue(any("minimum depth" in x for x in guidance["advisory"]))

    def test_planner_guidance_reports_stale_tier1_assets(self):
        from aiwf_core.assets.schema import init_assets
        from aiwf_core.core.process_contract import planner_process_guidance
        source = self.tmp / "src" / "stale.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("VALUE = 1\n", encoding="utf-8")
        init_assets(str(self.tmp))
        source.write_text("VALUE = 2\n", encoding="utf-8")

        guidance = planner_process_guidance(str(self.tmp))

        self.assertTrue(any("Tier 1 assets are stale" in x for x in guidance["conditional"]))

    def test_planner_guidance_explains_scope_recovery_and_freeze_reason(self):
        from aiwf_core.core.process_contract import planner_process_guidance
        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["scope_violation"] = True
        _write(state_path, state)
        review_path = self.tmp / ".aiwf" / "quality" / "review.json"
        review = json.loads(review_path.read_text())
        review["scope_violation_events"] = [{"path": "outside.py", "status": "recorded"}]
        _write(review_path, review)

        guidance = planner_process_guidance(str(self.tmp))

        self.assertTrue(any("Scope recovery" in x and "outside.py" in x for x in guidance["required_now"]))
        self.assertIn("scope_violation=true", guidance["contract_freeze_reasons"])

    def test_structured_meta_critique_command_records_planner_provenance(self):
        from aiwf_core.core.state_ops import record_meta_critique
        record_meta_critique(str(self.tmp), "Accepted review after disposition")
        goal = json.loads((self.tmp / ".aiwf" / "state" / "goal.json").read_text())
        self.assertEqual(goal["meta_critique"]["status"], "completed")
        self.assertEqual(goal["meta_critique"]["recorded_by"], "planner")

    def test_activation_and_close_refresh_tier1_assets(self):
        from aiwf_core.core.task_ledger import activate_task, close_task, upsert_task
        source = self.tmp / "src" / "feature.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("VALUE = 1\n", encoding="utf-8")
        upsert_task(str(self.tmp), "TASK-ASSET", "Asset refresh", status="ready",
                    allowed_write=["src/feature.py"])
        self.assertTrue(activate_task(str(self.tmp), "TASK-ASSET")["activated"])
        project_map = self.tmp / ".aiwf" / "assets" / "project-map.json"
        self.assertTrue(project_map.exists())
        self.assertIn("src/feature.py", project_map.read_text())

        source.write_text("VALUE = 2\n", encoding="utf-8")
        # Mechanical routing promotes this semantic task to L1, whose close remains light.
        self.assertTrue(close_task(str(self.tmp), "TASK-ASSET")["closed"])
        asset = json.loads(project_map.read_text())
        module = next(m for m in asset["modules"] if m["path"] == "src/feature.py")
        self.assertEqual(module["hash"], asset["_asset"]["source_hashes"][str(source)])


if __name__ == "__main__":
    unittest.main()
