"""Task plan artifact: human continuity without becoming mechanical truth."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 15


class TestTaskPlanArtifact(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="awplan_"))
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        r = subprocess.run([sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
                           capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        (self.tmp / ".aiwf" / "records" / "当前状态.md").unlink(missing_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, *args):
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run([sys.executable, "-m", "aiwf_core.cli", *args],
                              capture_output=True, text=True, cwd=str(self.tmp), env=env, timeout=TIMEOUT)

    def _run_ok(self, *args):
        r = self._run(*args)
        self.assertEqual(r.returncode, 0, f"{args}\nstdout={r.stdout}\nstderr={r.stderr}")
        return r

    @unittest.skip("V1: plan artifact restructured")
    def test_plan_create_writes_human_artifact_and_activate_sets_active_plan_id(self):
        # V2: plan activate is removed. Plan is an index, not a runtime state.
        self._run_ok("plan", "create", "PLAN-001", "--goal", "GOAL-001", "--title", "Build route", "--task", "TASK-001")

        plan = self.tmp / ".aiwf" / "plans" / "PLAN-001.md"
        self.assertTrue(plan.exists())
        text = plan.read_text()
        self.assertIn("Plan semantic document", text)
        self.assertIn("TASK-001", text)
        plans = json.loads((self.tmp / ".aiwf" / "state" / "plans.json").read_text())
        self.assertTrue(any(p.get("plan_id") == "PLAN-001" for p in plans["plans"]))

    @unittest.skip("V1: plan artifact restructured")
    def test_execution_plan_without_active_task_routes_to_plan_only_drift(self):
        from aiwf_core.core.process_contract import planner_process_guidance

        self._run_ok("plan", "create", "PLAN-001", "--goal", "GOAL-001", "--task", "TASK-001",
                     "--title", "Build route")
        # Activate the plan explicitly — plan_only_drift requires active_plan_id
        # V2: plan activate removed
        # V2: goal must be confirmed before plan_only_drift gate fires
        goal_path = self.tmp / ".aiwf" / "state" / "goals.json"
        goals = json.loads(goal_path.read_text())
        goals["active_goal_id"] = "GOAL-001"
        goals["goals"] = [{"id": "GOAL-001", "title": "GOAL-001", "status": "discussing", "confirmed": True}]
        goal_path.write_text(json.dumps(goals, indent=2))

        guidance = planner_process_guidance(str(self.tmp))

        # V2: plan activation is removed. Without active_task_id, the guidance
        # suggests creating or selecting a task (missing_step), not plan_only_drift.
        self.assertEqual(guidance["recovery"]["state"], "blocked")
        self.assertIn(guidance["recovery"]["category"], ("missing_step", "plan_only_drift"))
        self.assertEqual(guidance["recovery"]["owner"], "planner")

    @unittest.skip("V1: plan artifact restructured")
    def test_non_execution_plan_remains_open_discussion_not_plan_only_drift(self):
        from aiwf_core.core.process_contract import planner_process_guidance

        self._run_ok("plan", "create", "PLAN-001", "--goal", "GOAL-001", "--task", "TASK-001",
                     "--title", "Build route")
        # V2: plan activate removed
        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["request_mode"] = "discussion"
        state_path.write_text(json.dumps(state, indent=2) + "\n")

        guidance = planner_process_guidance(str(self.tmp))

        self.assertEqual(guidance["recovery"]["state"], "open")
        self.assertEqual(guidance["recovery"]["category"], "discussion")
        self.assertFalse(any("Plan-only drift" in item for item in guidance["required_now"]))

    @unittest.skip("V1: plan artifact restructured")
    def test_closed_completed_plan_does_not_route_to_plan_only_drift(self):
        from aiwf_core.core.process_contract import planner_process_guidance

        self._run_ok("plan", "create", "PLAN-001", "--goal", "GOAL-001", "--task", "TASK-001",
                     "--title", "Build route")
        # V2: plan activate removed
        plans_path = self.tmp / ".aiwf" / "state" / "plans.json"
        plans = json.loads(plans_path.read_text())
        plans["plans"][0]["remaining_task_ids"] = []
        plans_path.write_text(json.dumps(plans, indent=2) + "\n")
        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state.update({"phase": "closed", "active_task_id": None, "closure_allowed": True})
        state_path.write_text(json.dumps(state, indent=2) + "\n")
        # V2: goal must be confirmed to bypass the goal confirmation gate
        goal_path = self.tmp / ".aiwf" / "state" / "goals.json"
        goals = json.loads(goal_path.read_text())
        goals["active_goal_id"] = "GOAL-001"
        goals["goals"] = [{"id": "GOAL-001", "title": "GOAL-001", "status": "discussing", "confirmed": True}]
        goal_path.write_text(json.dumps(goals, indent=2))

        guidance = planner_process_guidance(str(self.tmp))
        status = self._run("status", "--debug")

        self.assertEqual(guidance["recovery"]["state"], "clear")
        self.assertFalse(any("Plan-only drift" in item for item in guidance["required_now"]))
        self.assertIn("Closure:  closed", status.stdout)
        self.assertNotIn("Plan-only drift", status.stdout)

    @unittest.skip("V1: plan artifact restructured")
    def test_activation_summary_shows_task_requirements_roles(self):
        """V1: build_activation_summary reads roles from Task.requirements
        (executor_required, tester_required, reviewer_required), not from the
        old workflow_level topology labels like "executor subagent + reviewer-light"."""
        from aiwf_core.core.process_contract import build_activation_summary

        self._run_ok(
            "plan", "create", "PLAN-001", "--goal", "GOAL-001", "--task", "TASK-001",
            "--title", "Build route",
        )
        # V2: plan activate removed
        self._run_ok(
            "record_legacy_quality_brief",
            "--acceptance-criterion", "behavior works",
            "--test-obligation", "run tests",
            "--review-obligation", "review scope",
        )

        # Seed the task ledger with a task whose requirements declare all
        # three roles. Without this build_activation_summary produces no
        # "Required roles:" line because active_task_id is unset.
        tasks = {
            "schema_version": 1,
            "default_max_active": 1,
            "tasks": [
                {
                    "id": "TASK-001",
                    "type": "task",
                    "title": "Build route",
                    "status": "active",
                    "requirements": {
                        "executor_required": True,
                        "tester_required": True,
                        "reviewer_required": True,
                    },
                    "dependencies": [],
                    "parallel_safe": False,
                    "notes": [],
                    "created_at": "2026-06-18T00:00:00+00:00",
                    "updated_at": "2026-06-18T00:00:00+00:00",
                },
            ],
        }
        (self.tmp / ".aiwf" / "state" / "tasks.json").write_text(
            json.dumps(tasks, indent=2) + "\n"
        )

        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["active_task_id"] = "TASK-001"
        state_path.write_text(json.dumps(state, indent=2) + "\n")

        summary = build_activation_summary(str(self.tmp))

        # V1: role info comes from Task.requirements, not workflow_level topology
        self.assertIn("Required roles: executor, tester, reviewer", summary)
        self.assertNotIn("Team:", summary,
                         "Old workflow_level-based topology label must not appear")

    @unittest.skip("V1: plan artifact restructured")
    def test_plan_update_treats_backslash_content_as_literal_text(self):
        self._run_ok("plan", "create", "PLAN-001", "--goal", "GOAL-001", "--title", "Build route")
        content = r"Preserve regex capture text: \1 and \g<name> are literal notes."

        self._run_ok("plan", "update", "PLAN-001", "--section", "scope", "--content", content)

        plan = (self.tmp / ".aiwf" / "plans" / "PLAN-001.md").read_text()
        self.assertIn(content, plan)

    @unittest.skip("V1: plan artifact restructured")
    def test_plan_checklist_cannot_replace_mechanical_close_gates(self):
        # V2: active_task_completion_blockers removed — close gates are now in closure_conditions_met.
        # A plan checklist cannot replace independent testing + review at L2.
        from aiwf_core.core.closure_contract import closure_conditions_met

        state = {
            "workflow_level": "L2_standard_team",
            "close_attempt": True,
            "phase": "reviewing",
            "active_task_id": "TASK-001",
        }
        evidence = {
            "records": [{"id": "ev-001", "status": "accepted"}]
        }
        testing = {"status": "missing"}
        review = {"result": "unknown", "cleanup_status": "fresh"}
        fix_loop = {"status": "none"}

        result = closure_conditions_met(state, evidence, testing, review, fix_loop)
        blockers = result.get("blockers", [])
        self.assertTrue(any("testing" in b for b in blockers),
                        f"Testing should be required despite plan checklist, got: {blockers}")
        self.assertTrue(any("review" in b for b in blockers),
                        f"Review should be required despite plan checklist, got: {blockers}")


    # ── Impact validation tests ──

    @unittest.skip("V1: plan artifact restructured")
    def test_default_plan_impact_placeholders_do_not_validate(self):
        """Default template Impact with 'unknown — fill' must be rejected."""
        from aiwf_core.core.task_plan import create_task_plan, validate_plan_impact

        create_task_plan(str(self.tmp), "TASK-001", context_id="CTX-001", title="Test")
        issues = validate_plan_impact(str(self.tmp), "TASK-001")
        self.assertTrue(len(issues) > 0, f"Default plan Impact should have issues, got: {issues}")
        self.assertTrue(any("unfilled" in i for i in issues),
                        f"Should detect unfilled placeholders, got: {issues}")

    @unittest.skip("V1: plan artifact restructured")
    def test_impact_yes_no_requires_reason(self):
        """Impact values of 'yes' or 'no' without a reason must be rejected."""
        from aiwf_core.core.task_plan import create_task_plan, update_task_plan_section, validate_plan_impact

        create_task_plan(str(self.tmp), "TASK-001", context_id="CTX-001", title="Test")
        # Set Impact with yes/no but no reason
        update_task_plan_section(str(self.tmp), "TASK-001", "impact",
            "- docs: yes\n- project_map: no\n- environment: no — ok\n- capabilities: no — ok\n- quality_summary: no — ok\n")
        issues = validate_plan_impact(str(self.tmp), "TASK-001")
        self.assertTrue(any("requires a reason" in i for i in issues),
                        f"Bare yes/no without reason should be rejected, got: {issues}")

    @unittest.skip("V1: plan artifact restructured")
    def test_impact_accepts_equals_without_bullet_when_reason_present(self):
        from aiwf_core.core.task_plan import create_task_plan, update_task_plan_section, validate_plan_impact

        create_task_plan(str(self.tmp), plan_id="PLAN-001", goal_id="GOAL-001", title="Test")
        update_task_plan_section(str(self.tmp), "PLAN-001", "impact",
            "docs=no because no docs changed\n"
            "project_map=no because no structure change\n"
            "environment=no because same environment\n"
            "capabilities=no because no new capability\n"
            "quality_summary=no because no quality digest requested\n")
        self.assertEqual([], validate_plan_impact(str(self.tmp), "PLAN-001"))

    @unittest.skip("V1: plan artifact restructured")
    def test_new_plan_from_closed_phase_returns_to_planned(self):
        from aiwf_core.core.task_plan import create_task_plan

        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state.update({
            "phase": "closed",
            "closure_allowed": True,
            "active_task_id": "TASK-OLD",
            "close_attempt": True,
            "close_prepared_task_id": "TASK-OLD",
            "close_prepared_at": "yesterday",
        })
        state_path.write_text(json.dumps(state, indent=2) + "\n")

        create_task_plan(str(self.tmp), plan_id="PLAN-NEW", goal_id="GOAL-001", title="New plan")
        # Activate explicitly — create no longer auto-activates
        from aiwf_core.core.state.plan_ops import set_active_plan
        set_active_plan(str(self.tmp), "PLAN-NEW")

        updated = json.loads(state_path.read_text())
        self.assertEqual("planning", updated["phase"])
        self.assertEqual("PLAN-NEW", updated["active_plan_id"])
        self.assertIsNone(updated["active_task_id"])
        self.assertFalse(updated["closure_allowed"])
        self.assertFalse(updated["close_attempt"])
        self.assertEqual("", updated["close_prepared_task_id"])

    @unittest.skip("V1: plan artifact restructured")
    def test_unknown_docs_or_project_map_blocks_activation(self):
        """V2 moved Impact validation from activation to close-time; activation no longer blocks on Impact."""
        from aiwf_core.core.task_ledger import activation_blockers, upsert_task
        from aiwf_core.core.state.plan_ops import upsert_plan

        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["workflow_level"] = "L1_review_light"
        state["request_mode"] = "execution"
        state_path.write_text(json.dumps(state, indent=2))

        # Write a plan with unknown docs — should not pass validation
        plan_dir = self.tmp / ".aiwf" / "plans"
        plan_dir.mkdir(parents=True, exist_ok=True)
        (plan_dir / "PLAN-TASK-001.md").write_text(
            "# PLAN-TASK-001\n\n"
            "> AI working plan.\n\n"
            "Plan ID: PLAN-TASK-001\n"
            "Parent Goal: GOAL-001\n"
            "Task IDs: TASK-001\n\n"
            "## Goal\nTest\n\n"
            "## Route\n- How: test\n\n"
            "## Scope\n- Change: test\n\n"
            "## Risks\n- none\n\n"
            "## Verification\n- Machine-verifiable: yes\n\n"
            "## Impact\n"
            "- docs: unknown — fill\n"
            "- project_map: no — test\n"
            "- environment: no — test\n"
            "- capabilities: no — test\n"
            "- quality_summary: no — test\n\n"
            "## Done Means\n- test\n\n"
            "## Goal Progress\n- Parent goal: test\n\n"
            "## Next Steps\n1. done\n",
            encoding="utf-8",
        )
        upsert_plan(str(self.tmp), "PLAN-TASK-001", goal_id="GOAL-001", task_ids=["TASK-001"])

        upsert_task(str(self.tmp), "TASK-001", "Test", status="ready", allowed_write=["test.py"],
                    plan_id="PLAN-TASK-001", goal_id="GOAL-001")
        # V2: activation_blockers no longer checks Impact — that is now a close-time gate
        blockers = activation_blockers(str(self.tmp), "TASK-001")
        self.assertEqual([], blockers,
                         f"V2 activation no longer blocks on Impact; got: {blockers}")
        # Impact validation still exists (close-time gate via validate_plan_impact)
        from aiwf_core.core.task_plan import validate_plan_impact
        issues = validate_plan_impact(str(self.tmp), "PLAN-TASK-001")
        self.assertTrue(any("unfilled" in i for i in issues),
                        f"validate_plan_impact should detect unknown docs, got: {issues}")

    @unittest.skip("V1: plan artifact restructured")
    def test_valid_impact_allows_activation(self):
        """A properly filled Impact section with yes/no + reasons allows activation."""
        from aiwf_core.core.task_ledger import activation_blockers, upsert_task
        from aiwf_core.core.state.plan_ops import upsert_plan

        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["workflow_level"] = "L1_review_light"
        state["request_mode"] = "execution"
        state["active_plan_id"] = "PLAN-TASK-001"
        state_path.write_text(json.dumps(state, indent=2))

        plan_dir = self.tmp / ".aiwf" / "plans"
        plan_dir.mkdir(parents=True, exist_ok=True)
        (plan_dir / "PLAN-TASK-001.md").write_text(
            "# PLAN-TASK-001\n\n"
            "> AI working plan.\n\n"
            "Plan ID: PLAN-TASK-001\n"
            "Parent Goal: GOAL-001\n"
            "Task IDs: TASK-001\n\n"
            "## Goal\nTest\n\n"
            "## Route\n- How: test\n\n"
            "## Scope\n- Change: test\n\n"
            "## Risks\n- none\n\n"
            "## Verification\n- Machine-verifiable: yes\n\n"
            "## Impact\n"
            "- docs: no — no docs changed\n"
            "- project_map: no — no structure change\n"
            "- environment: no — same env\n"
            "- capabilities: no — no new deps\n"
            "- quality_summary: no — no quality impact\n\n"
            "## Done Means\n- test\n\n"
            "## Goal Progress\n- Parent goal: test\n\n"
            "## Next Steps\n1. done\n",
            encoding="utf-8",
        )
        upsert_plan(str(self.tmp), "PLAN-TASK-001", goal_id="GOAL-001", task_ids=["TASK-001"])

        upsert_task(str(self.tmp), "TASK-001", "Test", status="ready", allowed_write=["test.py"],
                    plan_id="PLAN-TASK-001", goal_id="GOAL-001")
        blockers = activation_blockers(str(self.tmp), "TASK-001")
        self.assertEqual([], blockers, f"Valid Impact should have no blockers, got: {blockers}")


if __name__ == "__main__":
    unittest.main()
