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

    def _seed_architecture_migration_contract(self):
        goal_path = self.tmp / ".aiwf" / "state" / "goal.json"
        goal = json.loads(goal_path.read_text())
        ab = goal["quality_brief"]["architecture_brief"]
        ab["target_structure"] = "New mainline is the only supported flow"
        ab["migration_source_of_truth"] = "README.md + scripts/new-flow.sh"
        ab["legacy_paths"] = ["scripts/old-flow.sh"]
        ab["legacy_terms"] = ["old_handoff"]
        ab["default_entrypoints"] = ["scripts/new-flow.sh"]
        ab["validators"] = ["scripts/validate.sh"]
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

    def test_historical_pressure_does_not_turn_small_current_task_into_l3(self):
        from aiwf_core.core.task_ledger import activate_task, upsert_task
        self._seed_planning_contracts()
        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["cross_task_quality_escalation_required"] = True
        _write(state_path, state)
        _write(self.tmp / ".aiwf" / "state" / "fix-loop.json", {
            "status": "resolved", "attempt_count": 5, "route": "executor",
            "required_fixes": [], "verification": [],
        })
        upsert_task(
            str(self.tmp), "TASK-SMALL", "Rename script section labels",
            status="ready",
            allowed_write=["scripts/install.sh", "scripts/check.sh"],
        )

        result = activate_task(str(self.tmp), "TASK-SMALL")

        self.assertTrue(result["activated"], result["blockers"])
        routed = json.loads(state_path.read_text())
        self.assertEqual(routed["workflow_level"], "L1_review_light")
        self.assertEqual(routed["recommended_minimum_level"], "L1_review_light")
        self.assertIn("semantic_change", routed["routing_factors"])
        self.assertNotIn("prior_fix_loop", routed["routing_factors"])
        self.assertNotIn("architecture_impact", routed["routing_factors"])
        self.assertIn("prior_fix_loop_history", routed["routing_background_factors"])
        self.assertIn("historical_deferred_risk", routed["routing_background_factors"])
        self.assertIn("architecture_brief_present", routed["routing_background_factors"])

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

    def test_planner_guidance_explains_routing_and_next_required_step(self):
        from aiwf_core.core.process_contract import planner_process_guidance
        guidance = planner_process_guidance(str(self.tmp))
        self.assertEqual(guidance["workflow_level"], "L1_review_light")
        self.assertTrue(any("activate one task" in x for x in guidance["required_now"]))
        self.assertEqual(guidance["recovery"]["state"], "blocked")
        self.assertEqual(guidance["recovery"]["category"], "missing_step")
        self.assertEqual(guidance["recovery"]["primary"], "plan and activate one scoped task")
        self.assertTrue(any("Explorer" in x for x in guidance["advisory"]))
        self.assertTrue(any("minimum depth" in x for x in guidance["advisory"]))

    def test_recovery_guidance_for_missing_l2_tester(self):
        from aiwf_core.core.process_contract import planner_process_guidance
        from aiwf_core.core.task_ledger import activate_task, upsert_task
        self._set_l2()
        upsert_task(str(self.tmp), "TASK-REC", "Needs tester", status="ready")
        self.assertTrue(activate_task(str(self.tmp), "TASK-REC")["activated"])

        recovery = planner_process_guidance(str(self.tmp))["recovery"]

        self.assertEqual(recovery["state"], "blocked")
        self.assertEqual(recovery["category"], "missing_step")
        self.assertEqual(recovery["owner"], "tester")
        self.assertEqual(recovery["primary"], "dispatch independent Tester")
        self.assertFalse(recovery["user_decision_required"])
        self.assertTrue(any("roleplay Tester" in item for item in recovery["forbidden"]))

    def test_recovery_guidance_for_review_before_cleanup(self):
        from aiwf_core.core.process_contract import planner_process_guidance
        from aiwf_core.core.task_ledger import activate_task, upsert_task
        self._set_l2()
        _write(self.tmp / ".aiwf" / "quality" / "testing.json", {
            "status": "adequate",
            "commands": ["pytest"],
            "full_suite_status": "passed",
            "real_usage_status": "passed",
        })
        upsert_task(str(self.tmp), "TASK-CLEAN", "Needs cleanup", status="ready")
        self.assertTrue(activate_task(str(self.tmp), "TASK-CLEAN")["activated"])

        recovery = planner_process_guidance(str(self.tmp))["recovery"]

        self.assertEqual(recovery["category"], "wrong_order")
        self.assertEqual(recovery["owner"], "planner")
        self.assertEqual(recovery["primary"], "verify cleanup before Reviewer")
        self.assertTrue(any("cleanup" in item for item in recovery["forbidden"]))

    def test_recovery_guidance_for_pending_adversarial_disposition(self):
        from aiwf_core.core.process_contract import planner_process_guidance
        from aiwf_core.core.task_ledger import activate_task, upsert_task
        self._set_l2()
        self._seed_complete_quality_chain()
        review_path = self.tmp / ".aiwf" / "quality" / "review.json"
        review = json.loads(review_path.read_text())
        review["adversarial_observations"] = [{"id": "ADV-1", "disposition": "pending"}]
        _write(review_path, review)
        upsert_task(str(self.tmp), "TASK-ADV", "Needs meta", status="ready")
        self.assertTrue(activate_task(str(self.tmp), "TASK-ADV")["activated"])

        recovery = planner_process_guidance(str(self.tmp))["recovery"]

        self.assertEqual(recovery["category"], "missing_step")
        self.assertEqual(recovery["owner"], "planner")
        self.assertEqual(recovery["primary"], "disposition adversarial observations")
        self.assertTrue(any("prepare-close" in item for item in recovery["forbidden"]))

    def test_l2_task_closes_with_cli_role_delivery_evidence(self):
        from aiwf_core.core.state_ops import (
            mark_cleanup_fresh,
            record_meta_critique,
            record_review,
            record_role_evidence,
            record_testing,
        )
        from aiwf_core.core.task_ledger import activate_task, close_task, upsert_task
        self._set_l2()
        upsert_task(str(self.tmp), "TASK-ROLE", "Role evidence", status="ready")
        self.assertTrue(activate_task(str(self.tmp), "TASK-ROLE")["activated"])

        exec_ev = record_role_evidence(
            str(self.tmp), "executor", summary="implemented scoped change",
            changed_files=["src/a.py"],
        )
        testing = record_testing(
            str(self.tmp),
            status="adequate",
            commands=["pytest"],
            validation_layers=["targeted", "full_regression", "real_usage"],
            full_suite_status="passed",
            real_usage_status="passed",
            real_usage_reason="pytest exercised CLI entrypoint",
        )
        mark_cleanup_fresh(str(self.tmp), ["cleanup checked"])
        record_review(
            str(self.tmp),
            result="accepted",
            closure_allowed=True,
            accepted_evidence_ids=[exec_ev["id"], testing["evidence_id"]],
            cleanup_status="fresh",
            structure_status="accepted",
            summary="reviewed role delivery evidence",
        )
        record_meta_critique(str(self.tmp), "Review accepted after adversarial disposition")

        result = close_task(str(self.tmp), "TASK-ROLE")

        self.assertTrue(result["closed"], result["blockers"])

    def test_architecture_migration_task_closes_with_migration_evidence(self):
        from aiwf_core.core.task_ledger import activate_task, close_task, upsert_task
        self._set_l2()
        self._seed_architecture_migration_contract()
        self._seed_complete_quality_chain()
        evidence_path = self.tmp / ".aiwf" / "evidence" / "records.json"
        evidence = json.loads(evidence_path.read_text())
        evidence["records"].extend([
            {
                "id": "EV-4", "trust": "machine_observed", "session_id": "tester-session",
                "agent_id": "tester", "timestamp": "2026-01-01T00:00:04+00:00",
                "command": "rg \"old_handoff|scripts/old-flow.sh\" .", "exit_code": 0,
            },
            {
                "id": "EV-5", "trust": "machine_observed", "session_id": "tester-session",
                "agent_id": "tester", "timestamp": "2026-01-01T00:00:05+00:00",
                "command": "scripts/new-flow.sh --dry-run", "exit_code": 0,
            },
            {
                "id": "EV-6", "trust": "machine_observed", "session_id": "tester-session",
                "agent_id": "tester", "timestamp": "2026-01-01T00:00:06+00:00",
                "command": "scripts/validate.sh", "exit_code": 0,
            },
        ])
        _write(evidence_path, evidence)
        review_path = self.tmp / ".aiwf" / "quality" / "review.json"
        review = json.loads(review_path.read_text())
        review["accepted_evidence_ids"].extend(["EV-4", "EV-5", "EV-6"])
        _write(review_path, review)
        upsert_task(str(self.tmp), "TASK-MIG", "Migration", status="ready")
        self.assertTrue(activate_task(str(self.tmp), "TASK-MIG")["activated"])

        result = close_task(str(self.tmp), "TASK-MIG")

        self.assertTrue(result["closed"], result["blockers"])

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
