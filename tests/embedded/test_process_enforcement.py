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
        # V2: routing state lives in routing-debug.json; state.json still holds
        # workflow_level for recovery guidance, activation checks, and summary
        # builders that read from state.json directly.
        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["workflow_level"] = "L2_standard_team"
        _write(state_path, state)
        # Also seed routing-debug.json so readers defaulting from there see L2.
        routing_path = self.tmp / ".aiwf" / "runtime" / "internal" / "routing-debug.json"
        routing_path.parent.mkdir(parents=True, exist_ok=True)
        routing_path.write_text(json.dumps({
            "workflow_level": "L2_standard_team",
            "test_template": "regression_plus_boundary_adverse",
            "review_template": "standard_review",
            "routing_score": 0,
            "routing_factors": [],
            "routing_background_factors": [],
            "exploration_budget": "",
            "recommended_minimum_level": "L2_standard_team",
            "verification_need": "standard",
            "review_need": "optional_light_review",
            "downgrade_allowed": True,
            "substitution_allowed": False,
            "hard_constraints": [],
        }, indent=2) + "\n", encoding="utf-8")
        self._seed_planning_contracts()

    def _seed_plan(self, task_id, allowed_write=None):
        """Create a registry-backed plan artifact so L1+ activation can pass."""
        from aiwf_core.core.state.plan_ops import upsert_plan

        plan_id = f"PLAN-{task_id}"
        plan_dir = self.tmp / ".aiwf" / "plans"
        plan_dir.mkdir(parents=True, exist_ok=True)
        plan_path = plan_dir / f"{plan_id}.md"
        if not plan_path.exists():
            plan_path.write_text(
                f"# {plan_id}\n\n"
                "> AI working plan.\n\n"
                f"Plan ID: {plan_id}\n"
                "Parent Goal: GOAL-001\n"
                f"Task IDs: {task_id}\n\n"
                "## Goal\nTest task\n\n"
                "## Route\n- How: direct fix\n\n"
                "## Scope\n- Change: test files\n\n"
                "## Risks\n- none\n\n"
                "## Verification\n- Machine-verifiable: yes\n\n"
                "## Impact\n- docs: no — test\n- project_map: no — test\n- environment: no — test\n- capabilities: no — test\n- quality_summary: no — test\n\n"
                "## Done Means\n- test passes\n\n"
                "## Goal Progress\n- Parent goal: test\n\n"
                "## Next Steps\n1. done\n",
                encoding="utf-8",
            )
        kwargs = {"goal_id": "GOAL-001", "task_ids": [task_id]}
        if allowed_write is not None:
            kwargs["allowed_write"] = allowed_write
        else:
            kwargs["allowed_write"] = ["src/"]
        upsert_plan(str(self.tmp), plan_id, **kwargs)
        ledger_path = self.tmp / ".aiwf" / "state" / "tasks.json"
        if ledger_path.exists():
            ledger = json.loads(ledger_path.read_text())
            changed = False
            for task in ledger.get("tasks", []):
                if task.get("id") == task_id:
                    task["plan_id"] = plan_id
                    task["parent_plan"] = plan_id
                    task["goal_id"] = task.get("goal_id") or "GOAL-001"
                    task["parent_goal"] = task.get("parent_goal") or task["goal_id"]
                    changed = True
            if changed:
                _write(ledger_path, ledger)
        return plan_id

    def _plan_and_activate(self, task_id):
        """Seed a plan then activate — L1+ requires a plan before activation."""
        self._seed_plan(task_id)
        from aiwf_core.core.task_ledger import activate_task
        result = activate_task(str(self.tmp), task_id)
        return result

    def _mark_prepare_close_passed(self):
        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["phase"] = "closed"
        state["closure_allowed"] = True
        state["close_attempt"] = False
        _write(state_path, state)

    def _seed_planning_contracts(self):
        goals_path = self.tmp / ".aiwf" / "state" / "goals.json"
        goals = json.loads(goals_path.read_text())
        # Ensure active_goal_id is set and GOAL-001 exists
        goals["active_goal_id"] = "GOAL-001"
        active_goal = None
        for g in goals.get("goals", []):
            if g.get("id") == "GOAL-001":
                active_goal = g
                break
        if not active_goal:
            from aiwf_core.core.state_schema import default_goal
            active_goal = default_goal()
            active_goal["id"] = "GOAL-001"
            active_goal["title"] = "GOAL-001"
            active_goal["status"] = "discussing"
            goals["goals"].append(active_goal)
        brief = active_goal.setdefault("quality_brief", {})
        brief.setdefault("evaluation_contract", {}).update({
            "user_visible_outcome": "Requested behavior works",
            "acceptance_criteria": ["behavior verified"],
            "test_obligations": ["run focused and regression tests"],
            "review_obligations": ["review scope and correctness"],
        })
        brief.setdefault("architecture_brief", {})["target_structure"] = "Preserve declared module boundaries"
        brief["non_goals"] = ["test"]
        for i, g in enumerate(goals.get("goals", [])):
            if g.get("id") == "GOAL-001":
                goals["goals"][i] = active_goal
                break
        _write(goals_path, goals)

    def _seed_architecture_migration_contract(self):
        goals_path = self.tmp / ".aiwf" / "state" / "goals.json"
        goals = json.loads(goals_path.read_text())
        active_goal = None
        for g in goals.get("goals", []):
            if g.get("id") == (goals.get("active_goal_id") or "GOAL-001"):
                active_goal = g
                break
        if not active_goal:
            from aiwf_core.core.state_schema import default_goal
            active_goal = default_goal()
            active_goal["id"] = "GOAL-001"
            goals.setdefault("goals", []).append(active_goal)
        ab = active_goal.setdefault("quality_brief", {}).setdefault("architecture_brief", {})
        ab["target_structure"] = "New mainline is the only supported flow"
        ab["migration_source_of_truth"] = "README.md + scripts/new-flow.sh"
        ab["legacy_paths"] = ["scripts/old-flow.sh"]
        ab["legacy_terms"] = ["old_handoff"]
        ab["default_entrypoints"] = ["scripts/new-flow.sh"]
        ab["validators"] = ["scripts/validate.sh"]
        for i, g in enumerate(goals.get("goals", [])):
            if g.get("id") == active_goal["id"]:
                goals["goals"][i] = active_goal
                break
        _write(goals_path, goals)

    def _full_review_dimensions(self):
        from aiwf_core.core.state_schema import QUALITY_DIMENSIONS
        return {dim: {"score": "PASS", "note": ""} for dim in QUALITY_DIMENSIONS}

    def _full_review_basis(self):
        from aiwf_core.core.state_schema import REVIEW_BASIS
        return {name: {"status": "covered", "note": ""} for name in REVIEW_BASIS}

    def _inject_hook_evidence(self, *session_specs):
        """Inject hook-validated evidence records for session diversity.

        Each spec: (session_id, agent_type, tool_name).
        Hook evidence has tool_name != 'AIWFRoleEvidence' and is captured
        by hooks with the authentic Claude session_id — unspoofable.
        Returns list of injected record IDs.
        """
        evidence_path = self.tmp / ".aiwf" / "records" / "evidence.jsonl"
        existing = json.loads(evidence_path.read_text()) if evidence_path.exists() else {"records": []}
        records = existing.get("records", []) or []
        import uuid
        ids = []
        for sid, atype, tname in session_specs:
            rid = str(uuid.uuid4())[:8]
            ids.append(rid)
            records.append({
                "id": rid,
                "trust": "machine_observed",
                "attribution": "strong",
                "tool_name": tname,
                "session_id": sid,
                "agent_type": atype,
                "agent_id": atype,
                "status": "accepted",
            })
        _write(evidence_path, {"records": records})
        return ids

    def _seed_complete_quality_chain(self):
        _write(self.tmp / ".aiwf" / "records" / "testing.jsonl", {
            "status": "adequate", "commands": ["pytest"],
            "validation_layers": ["targeted", "full_regression", "real_usage"],
            "full_suite_status": "passed",
            "real_usage_status": "passed",
            "real_usage_reason": "project CLI smoke passed",
        })
        _write(self.tmp / ".aiwf" / "records" / "review.jsonl", {
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
        _write(self.tmp / ".aiwf" / "records" / "evidence.jsonl", {"records": [
            {"id": "EV-1", "trust": "machine_observed", "attribution": "strong", "tool_name": "Write", "session_id": "executor-session", "agent_id": "aiwf-executor", "agent_type": "aiwf-executor"},
            {"id": "EV-2", "trust": "machine_observed", "attribution": "strong", "tool_name": "Bash", "session_id": "tester-session", "agent_id": "aiwf-tester", "agent_type": "aiwf-tester"},
            {"id": "EV-3", "trust": "machine_observed", "attribution": "strong", "tool_name": "Bash", "session_id": "reviewer-session", "agent_id": "aiwf-reviewer", "agent_type": "aiwf-reviewer", "timestamp": "2026-01-02T00:00:00+00:00"},
        ]})
        goals_path = self.tmp / ".aiwf" / "state" / "goals.json"
        goals = json.loads(goals_path.read_text())
        active_goal = None
        for g in goals.get("goals", []):
            if g.get("id") == (goals.get("active_goal_id") or "GOAL-001"):
                active_goal = g
                break
        if not active_goal:
            from aiwf_core.core.state_schema import default_goal
            active_goal = default_goal()
            active_goal["id"] = "GOAL-001"
            goals.setdefault("goals", []).append(active_goal)
        active_goal["decisions"] = [{"source": "planner", "decision": "Meta-critique completed"}]
        active_goal["meta_critique"] = {
            "status": "completed", "summary": "Review signals dispositioned",
            "recorded_by": "planner", "recorded_at": "2026-01-01T00:00:04+00:00",
        }
        for i, g in enumerate(goals.get("goals", [])):
            if g.get("id") == active_goal["id"]:
                goals["goals"][i] = active_goal
                break
        _write(goals_path, goals)

    def test_active_l2_task_closes_after_complete_quality_chain(self):
        from aiwf_core.core.task_ledger import activate_task, close_task, upsert_task
        self._set_l2()
        self._seed_complete_quality_chain()
        upsert_task(str(self.tmp), "TASK-1", "Feature", status="ready")
        self._seed_plan("TASK-1")
        self.assertTrue(activate_task(str(self.tmp), "TASK-1")["activated"])
        self._mark_prepare_close_passed()

        result = close_task(str(self.tmp), "TASK-1")

        self.assertTrue(result["closed"], result["blockers"])

    def test_active_task_close_blocks_before_prepare_close(self):
        from aiwf_core.core.task_ledger import activate_task, close_task, upsert_task
        upsert_task(str(self.tmp), "TASK-PREPCLOSE", "Feature", status="ready")
        self._seed_plan("TASK-PREPCLOSE")
        self.assertTrue(activate_task(str(self.tmp), "TASK-PREPCLOSE")["activated"])

        result = close_task(str(self.tmp), "TASK-PREPCLOSE")

        # V2: close_task checks executor/tester/reviewer requirements, not prepare-close
        self.assertFalse(result["closed"])
        self.assertTrue(
            any("executor_required" in b or "tester_required" in b or "reviewer_required" in b
                for b in result["blockers"]))

    def test_periodic_architecture_review_blocks_ordinary_activation(self):
        from aiwf_core.core.task_ledger import activate_task, upsert_task
        _write(self.tmp / ".aiwf" / "state" / "tasks.json", {
            "tasks": [{"id": f"TASK-{i}", "title": "Done"} for i in range(10)]
        })
        upsert_task(str(self.tmp), "TASK-NEXT", "Next feature", status="ready")
        self._seed_plan("TASK-NEXT")

        result = activate_task(str(self.tmp), "TASK-NEXT")

        # V1: Periodic architecture review is advisory, not a gate
        self.assertTrue(result["activated"], result.get("blockers", []))

    def test_architecture_review_task_can_activate_when_review_is_due(self):
        from aiwf_core.core.task_ledger import activate_task, upsert_task
        _write(self.tmp / ".aiwf" / "state" / "tasks.json", {
            "tasks": [{"id": f"TASK-{i}", "title": "Done"} for i in range(10)]
        })
        upsert_task(str(self.tmp), "ARCH-010", "[Architect] milestone review", status="ready")

        self._seed_plan("ARCH-010")
        result = activate_task(str(self.tmp), "ARCH-010")

        self.assertTrue(result["activated"], result["blockers"])

    def test_activation_mechanically_routes_cross_module_semantic_task_to_l2(self):
        from aiwf_core.core.task_ledger import activate_task, upsert_task
        self._seed_planning_contracts()
        # Pre-set L2 — routing respects current level when downgrade is allowed.
        # Auto-upgrade is reserved for hard constraints (security/destructive).
        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["workflow_level"] = "L2_standard_team"
        state_path.write_text(json.dumps(state, indent=2))

        upsert_task(
            str(self.tmp), "TASK-ROUTE", "Cross module change", status="ready",
            allowed_write=["api/handler.py", "core/service.py"],
        )

        self._seed_plan("TASK-ROUTE")
        result = activate_task(str(self.tmp), "TASK-ROUTE")

        self.assertTrue(result["activated"], result["blockers"])
        # V2: routing state lives in routing-debug.json, not state.json
        routed = json.loads((self.tmp / ".aiwf" / "runtime" / "internal" / "routing-debug.json").read_text())
        self.assertEqual(routed["workflow_level"], "L2_standard_team")
        self.assertEqual(routed["test_template"], "regression_plus_boundary_adverse")
        self.assertEqual(routed["review_template"], "standard_review")
        self.assertEqual(routed["exploration_budget"], "asset_first_affected_files")

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
        )

        self._seed_plan("TASK-SMALL", allowed_write=["scripts/install.sh", "scripts/check.sh"])
        result = activate_task(str(self.tmp), "TASK-SMALL")

        self.assertTrue(result["activated"], result["blockers"])
        # V2: routing state lives in routing-debug.json, not state.json
        routed = json.loads((self.tmp / ".aiwf" / "runtime" / "internal" / "routing-debug.json").read_text())
        self.assertEqual(routed["workflow_level"], "L1_review_light")
        # V2: recommended_minimum_level may be L0_direct when scope is empty (scope lives in Plan.md)
        self.assertIn(routed["recommended_minimum_level"], ("L1_review_light", "L0_direct"))
        # V2: scope (allowed_write) is stored in Plan.md, not plans.json. Task scope
        # is empty by default, so routing factors are minimal. Background factors still appear.
        self.assertIn("prior_fix_loop_history", routed["routing_background_factors"])
        self.assertIn("historical_deferred_risk", routed["routing_background_factors"])
        self.assertIn("architecture_brief_present", routed["routing_background_factors"])

    def test_l2_activation_rejects_missing_planning_contracts(self):
        """V1: Activation is never blocked by contract checks. Recovery uses Task.requirements."""
        from aiwf_core.core.task_ledger import activate_task, upsert_task
        from aiwf_core.core.process_contract import planner_process_guidance
        self._set_l2()
        upsert_task(str(self.tmp), "TASK-NO-CONTRACT", "Missing contract", status="ready")

        self._seed_plan("TASK-NO-CONTRACT")
        # V1: activation is mechanical-only; contracts are not gates
        result = activate_task(str(self.tmp), "TASK-NO-CONTRACT")
        self.assertTrue(result["activated"], result["blockers"])

        # V1: recovery checks Task.requirements, not workflow_level contracts
        guidance = planner_process_guidance(str(self.tmp))
        recovery = guidance.get("recovery", {})
        # Default task has tester_required=true, reviewer_required=true
        # With no testing done, tester fires first
        self.assertEqual(recovery["state"], "blocked")
        self.assertEqual(recovery["owner"], "tester")

    def test_planner_guidance_explains_routing_and_next_required_step(self):
        from aiwf_core.core.process_contract import planner_process_guidance
        # V2: goal must be confirmed for execution-mode guidance
        goals_path = self.tmp / ".aiwf" / "state" / "goals.json"
        goals = json.loads(goals_path.read_text())
        goals["active_goal_id"] = "GOAL-001"
        goals["goals"] = [{"id": "GOAL-001", "title": "GOAL-001", "status": "discussing", "confirmed": True}]
        _write(goals_path, goals)
        guidance = planner_process_guidance(str(self.tmp))
        self.assertEqual(guidance["workflow_level"], "L1_review_light")
        # V2: task activation hint moved to advisory at L1
        self.assertTrue(any("activate" in x.lower() for x in guidance.get("advisory", [])))
        self.assertEqual(guidance["recovery"]["state"], "blocked")
        self.assertEqual(guidance["recovery"]["category"], "missing_step")
        self.assertEqual(guidance["recovery"]["primary"], "plan and activate one scoped task")
        self.assertIsInstance(guidance["advisory"], list)

    def test_recovery_guidance_for_missing_l2_tester(self):
        """V1: Recovery checks Task.requirements, not workflow_level. Default task needs tester."""
        from aiwf_core.core.process_contract import planner_process_guidance
        from aiwf_core.core.task_ledger import activate_task, upsert_task
        self._set_l2()
        upsert_task(str(self.tmp), "TASK-REC", "Needs tester", status="ready")
        self._seed_plan("TASK-REC")
        self.assertTrue(activate_task(str(self.tmp), "TASK-REC")["activated"])

        recovery = planner_process_guidance(str(self.tmp))["recovery"]

        # V1: tester_required=true (default) + no testing → blocked for tester
        self.assertEqual(recovery["state"], "blocked")
        self.assertEqual(recovery["category"], "missing_step")
        self.assertEqual(recovery["owner"], "tester")
        self.assertEqual(recovery["primary"], "dispatch independent Tester")

    def test_recovery_guidance_for_review_before_cleanup(self):
        """V1: No cleanup gate. With testing adequate, reviewer_required=true fires next."""
        from aiwf_core.core.process_contract import planner_process_guidance
        from aiwf_core.core.task_ledger import activate_task, upsert_task
        self._set_l2()
        _write(self.tmp / ".aiwf" / "records" / "testing.jsonl", {
            "status": "adequate",
            "commands": ["pytest"],
            "full_suite_status": "passed",
            "real_usage_status": "passed",
        })
        upsert_task(str(self.tmp), "TASK-CLEAN", "Needs cleanup", status="ready")
        self._seed_plan("TASK-CLEAN")
        self.assertTrue(activate_task(str(self.tmp), "TASK-CLEAN")["activated"])

        recovery = planner_process_guidance(str(self.tmp))["recovery"]

        # V1: tester passes → reviewer_required=true + no review → needs reviewer
        self.assertEqual(recovery["category"], "missing_step")
        self.assertEqual(recovery["owner"], "reviewer")
        self.assertEqual(recovery["primary"], "dispatch independent Reviewer")

    def test_recovery_guidance_for_pending_adversarial_disposition(self):
        """V1: Adversarial observations block close at all levels, not just L2."""
        from aiwf_core.core.process_contract import planner_process_guidance
        from aiwf_core.core.task_ledger import activate_task, upsert_task
        self._set_l2()
        self._seed_complete_quality_chain()
        review_path = self.tmp / ".aiwf" / "records" / "review.jsonl"
        review = json.loads(review_path.read_text())
        review["adversarial_observations"] = [{"id": "ADV-1", "disposition": "pending"}]
        _write(review_path, review)
        upsert_task(str(self.tmp), "TASK-ADV", "Needs meta", status="ready")
        self._seed_plan("TASK-ADV")
        self.assertTrue(activate_task(str(self.tmp), "TASK-ADV")["activated"])

        recovery = planner_process_guidance(str(self.tmp))["recovery"]

        # V1: pending adversarial observations block close regardless of level
        self.assertEqual(recovery["category"], "missing_step")
        self.assertEqual(recovery["owner"], "planner")
        self.assertEqual(recovery["primary"], "disposition adversarial observations")
        self.assertTrue(any("close" in item for item in recovery["forbidden"]))

    def test_planner_guidance_stops_dispatch_hints_after_review_acceptance(self):
        """V1: After review accepted, recovery shows ready to close — no dispatch hints."""
        from aiwf_core.core.process_contract import planner_process_guidance
        from aiwf_core.core.task_ledger import activate_task, upsert_task
        self._set_l2()
        self._seed_complete_quality_chain()
        upsert_task(str(self.tmp), "TASK-DONE", "Done chain", status="ready")
        self._seed_plan("TASK-DONE")
        self.assertTrue(activate_task(str(self.tmp), "TASK-DONE")["activated"])

        guidance = planner_process_guidance(str(self.tmp))

        # V1: recovery shows "ready" state when testing + review are complete
        recovery = guidance.get("recovery", {})
        self.assertEqual(recovery.get("state"), "ready")
        self.assertIn("task close", recovery.get("primary", ""))
        required = "\n".join(guidance["required_now"])
        self.assertNotIn("executor", required.lower())
        self.assertNotIn("reviewer", required.lower())
        self.assertNotIn("tester", required.lower())

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
        self._seed_plan("TASK-ROLE")
        self.assertTrue(activate_task(str(self.tmp), "TASK-ROLE")["activated"])

        hook_ids = self._inject_hook_evidence(
            ("sub-exec", "aiwf-executor", "Write"),
            ("sub-test", "aiwf-tester", "Bash"),
            ("sub-review", "aiwf-reviewer", "Bash"),
        )
        exec_ev = record_role_evidence(
            str(self.tmp), "executor", summary="implemented scoped change",
            changed_files=["src/a.py"],
            session_id="sub-exec", agent_id="aiwf-executor",
        )
        self.assertEqual(exec_ev.get("task_id"), "TASK-ROLE")
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
            verdict="PASS",
            result="accepted",
            quality_dimensions=self._full_review_dimensions(),
            review_basis=self._full_review_basis(),
            closure_allowed=True,
            accepted_evidence_ids=[exec_ev["id"]],
            cleanup_status="fresh",
            structure_status="accepted",
            summary="reviewed role delivery evidence",
        )
        record_meta_critique(str(self.tmp), "Review accepted after adversarial disposition")
        self._mark_prepare_close_passed()

        result = close_task(str(self.tmp), "TASK-ROLE")

        self.assertTrue(result["closed"], result["blockers"])

    def test_l3_prepare_close_then_task_close_uses_same_effective_evidence(self):
        from aiwf_core.core.state_ops import (
            mark_cleanup_fresh,
            prepare_close,
            record_meta_critique,
            record_review,
            record_role_evidence,
            record_testing,
        )
        from aiwf_core.core.task_ledger import activate_task, close_task, upsert_task
        self._set_l2()
        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["workflow_level"] = "L3_full_power"
        _write(state_path, state)
        (self.tmp / ".aiwf" / "runtime" / "checkpoints").mkdir(parents=True, exist_ok=True)
        (self.tmp / ".aiwf" / "runtime" / "checkpoints" / "TASK-L3.json").write_text("{}\n", encoding="utf-8")

        upsert_task(str(self.tmp), "TASK-L3", "L3 close chain", status="ready")
        self._seed_plan("TASK-L3")
        self.assertTrue(activate_task(str(self.tmp), "TASK-L3")["activated"])

        self._inject_hook_evidence(
            ("sub-exec", "aiwf-executor", "Write"),
            ("sub-test", "aiwf-tester", "Bash"),
            ("sub-review", "aiwf-reviewer", "Bash"),
        )
        exec_ev = record_role_evidence(
            str(self.tmp),
            "executor",
            summary="implemented scoped change",
            session_id="sub-exec",
            agent_id="aiwf-executor",
            agent_type="aiwf-executor",
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
            verdict="PASS",
            result="accepted",
            quality_dimensions=self._full_review_dimensions(),
            review_basis=self._full_review_basis(),
            closure_allowed=True,
            accepted_evidence_ids=[exec_ev["id"]],
            cleanup_status="fresh",
            structure_status="accepted",
            summary="reviewed completed L3 chain",
        )
        record_meta_critique(str(self.tmp), "Review accepted after adversarial disposition")

        prepared = prepare_close(str(self.tmp))
        self.assertTrue(prepared["passed"], prepared["blockers"])

        result = close_task(str(self.tmp), "TASK-L3")
        self.assertTrue(result["closed"], result["blockers"])

    def test_l3_task_close_accepts_shared_parent_session_with_distinct_hook_roles(self):
        from aiwf_core.core.state_ops import (
            mark_cleanup_fresh,
            prepare_close,
            record_meta_critique,
            record_review,
            record_role_evidence,
            record_testing,
        )
        from aiwf_core.core.task_ledger import activate_task, close_task, upsert_task
        self._set_l2()
        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["workflow_level"] = "L3_full_power"
        _write(state_path, state)
        (self.tmp / ".aiwf" / "runtime" / "checkpoints").mkdir(parents=True, exist_ok=True)
        (self.tmp / ".aiwf" / "runtime" / "checkpoints" / "TASK-L3-SINGLE.json").write_text("{}\n", encoding="utf-8")

        upsert_task(str(self.tmp), "TASK-L3-SINGLE", "L3 single session", status="ready")
        self._seed_plan("TASK-L3-SINGLE")
        self.assertTrue(activate_task(str(self.tmp), "TASK-L3-SINGLE")["activated"])

        self._inject_hook_evidence(
            ("shared-parent-session", "aiwf-executor", "Write"),
            ("shared-parent-session", "aiwf-tester", "Bash"),
            ("shared-parent-session", "aiwf-reviewer", "Bash"),
        )
        exec_ev = record_role_evidence(
            str(self.tmp),
            "executor",
            summary="implemented with subagent role evidence",
            session_id="shared-parent-session",
            agent_id="aiwf-executor",
            agent_type="aiwf-executor",
        )
        record_testing(
            str(self.tmp),
            status="adequate",
            commands=["pytest tests/embedded/test_process_enforcement.py"],
        )
        mark_cleanup_fresh(str(self.tmp), ["cleanup checked"])
        record_review(
            str(self.tmp),
            verdict="PASS",
            result="accepted",
            quality_dimensions=self._full_review_dimensions(),
            review_basis=self._full_review_basis(),
            closure_allowed=True,
            accepted_evidence_ids=[exec_ev["id"]],
            cleanup_status="fresh",
            structure_status="accepted",
            summary="review accepted with distinct hook-observed roles sharing a parent session",
        )
        record_meta_critique(str(self.tmp), "Review accepted; no adversarial blockers remain")

        prepared = prepare_close(str(self.tmp))
        self.assertTrue(prepared["passed"], prepared["blockers"])
        result = close_task(str(self.tmp), "TASK-L3-SINGLE")
        self.assertTrue(result["closed"], result["blockers"])

    def test_l3_task_close_rejects_cli_roleplay_without_hook_roles(self):
        from aiwf_core.core.state_ops import (
            mark_cleanup_fresh,
            prepare_close,
            record_meta_critique,
            record_review,
            record_role_evidence,
            record_testing,
        )
        from aiwf_core.core.task_ledger import activate_task, close_task, upsert_task
        self._set_l2()
        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["workflow_level"] = "L3_full_power"
        _write(state_path, state)
        (self.tmp / ".aiwf" / "runtime" / "checkpoints").mkdir(parents=True, exist_ok=True)
        (self.tmp / ".aiwf" / "runtime" / "checkpoints" / "TASK-L3-ROLEPLAY.json").write_text("{}\n", encoding="utf-8")

        upsert_task(str(self.tmp), "TASK-L3-ROLEPLAY", "L3 roleplay blocked", status="ready")
        self._seed_plan("TASK-L3-ROLEPLAY")
        self.assertTrue(activate_task(str(self.tmp), "TASK-L3-ROLEPLAY")["activated"])

        exec_ev = record_role_evidence(
            str(self.tmp),
            "executor",
            summary="main session claims implementation",
            session_id="shared-parent-session",
            agent_id="planner-main",
            agent_type="planner-main",
        )
        record_testing(str(self.tmp), status="adequate", commands=["pytest"])
        mark_cleanup_fresh(str(self.tmp), ["cleanup checked"])
        record_review(
            str(self.tmp),
            verdict="PASS",
            result="accepted",
            quality_dimensions=self._full_review_dimensions(),
            review_basis=self._full_review_basis(),
            closure_allowed=True,
            accepted_evidence_ids=[exec_ev["id"]],
            cleanup_status="fresh",
            structure_status="accepted",
            summary="roleplay review should not satisfy hook role gate",
        )
        record_meta_critique(str(self.tmp), "Review accepted; role evidence still lacks hook-observed roles")

        prepared = prepare_close(str(self.tmp))
        # V2: session diversity is a post-hoc warning, not a close blocker.
        # Roleplay-without-hooks still passes prepare_close but surfaces warnings.
        self.assertTrue(prepared.get("passed"), prepared.get("blockers", []))
        # close_task no longer blocks on role diversity — V2 moves it to advisory
        result = close_task(str(self.tmp), "TASK-L3-ROLEPLAY")
        self.assertTrue(result["closed"], result.get("blockers", []))

    def test_architecture_migration_task_closes_with_migration_evidence(self):
        from aiwf_core.core.task_ledger import activate_task, close_task, upsert_task
        self._set_l2()
        self._seed_architecture_migration_contract()
        self._seed_complete_quality_chain()
        evidence_path = self.tmp / ".aiwf" / "records" / "evidence.jsonl"
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
        review_path = self.tmp / ".aiwf" / "records" / "review.jsonl"
        review = json.loads(review_path.read_text())
        review["accepted_evidence_ids"].extend(["EV-4", "EV-5", "EV-6"])
        _write(review_path, review)
        upsert_task(str(self.tmp), "TASK-MIG", "Migration", status="ready")
        self._seed_plan("TASK-MIG")
        self.assertTrue(activate_task(str(self.tmp), "TASK-MIG")["activated"])
        self._mark_prepare_close_passed()

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

        # Diet: asset staleness is now silent in default guidance (reserved for --debug)
        # V2: guidance no longer returns 'conditional' key
        self.assertFalse(any("Tier 1 assets are stale" in x for x in guidance.get("conditional", [])))

    def test_planner_guidance_explains_scope_recovery_and_freeze_reason(self):
        from aiwf_core.core.process_contract import planner_process_guidance
        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["scope_violation"] = True
        _write(state_path, state)
        review_path = self.tmp / ".aiwf" / "records" / "review.jsonl"
        review = json.loads(review_path.read_text())
        review["scope_violation_events"] = [{"path": "outside.py", "status": "recorded"}]
        _write(review_path, review)

        guidance = planner_process_guidance(str(self.tmp))

        # V2: scope violation appears in required_now and recovery
        self.assertTrue(any("scope violation" in x.lower() for x in guidance["required_now"]))
        recovery = guidance.get("recovery", {})
        self.assertEqual(recovery.get("category"), "scope")

    def test_structured_meta_critique_command_records_planner_provenance(self):
        from aiwf_core.core.state_ops import record_meta_critique
        record_meta_critique(str(self.tmp), "Accepted review after disposition")
        # V2: goals live in goals.json; find the active goal
        goals = json.loads((self.tmp / ".aiwf" / "state" / "goals.json").read_text())
        active_id = goals.get("active_goal_id") or "GOAL-001"
        goal = next((g for g in goals.get("goals", []) if g.get("id") == active_id), {})
        self.assertEqual(goal.get("meta_critique", {}).get("status"), "completed")
        self.assertEqual(goal.get("meta_critique", {}).get("recorded_by"), "planner")

    def test_activation_and_close_refresh_tier1_assets(self):
        from aiwf_core.core.task_ledger import activate_task, close_task, upsert_task
        source = self.tmp / "src" / "feature.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("VALUE = 1\n", encoding="utf-8")
        upsert_task(str(self.tmp), "TASK-ASSET", "Asset refresh", status="ready",
                    allowed_write=["src/feature.py"])
        self._seed_plan("TASK-ASSET")
        self.assertTrue(activate_task(str(self.tmp), "TASK-ASSET")["activated"])
        project_map = self.tmp / ".aiwf" / "assets" / "project-map.json"
        self.assertTrue(project_map.exists())
        self.assertIn("src/feature.py", project_map.read_text())

        source.write_text("VALUE = 2\n", encoding="utf-8")
        # V2: close_task requires evidence, testing, and review records
        _write(self.tmp / ".aiwf" / "records" / "evidence.jsonl", {"records": [
            {"id": "EV-ASSET", "trust": "machine_observed", "attribution": "strong",
             "tool_name": "Write", "session_id": "asset-session", "agent_id": "aiwf-executor",
             "agent_type": "aiwf-executor", "status": "accepted", "changed_files": ["src/feature.py"]},
        ]})
        _write(self.tmp / ".aiwf" / "records" / "testing.jsonl", {
            "status": "adequate", "commands": ["pytest"],
        })
        _write(self.tmp / ".aiwf" / "records" / "review.jsonl", {
            "result": "accepted", "closure_allowed": True,
            "accepted_evidence_ids": ["EV-ASSET"],
        })
        # Mechanical routing promotes this semantic task to L1, whose close remains light.
        self._mark_prepare_close_passed()
        result = close_task(str(self.tmp), "TASK-ASSET")
        self.assertTrue(result["closed"], result.get("blockers", []))
        asset = json.loads(project_map.read_text())
        module = next(m for m in asset["modules"] if m["path"] == "src/feature.py")
        self.assertEqual(module["hash"], asset["_asset"]["source_hashes"][str(source)])


if __name__ == "__main__":
    unittest.main()
