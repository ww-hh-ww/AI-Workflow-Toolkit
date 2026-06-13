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
        (self.tmp / ".aiwf" / "artifacts" / "reports" / "当前状态.md").unlink(missing_ok=True)

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

    def test_plan_create_writes_human_artifact_and_activate_sets_active_plan_id(self):
        # Create does NOT auto-activate — activation is explicit
        self._run_ok("plan", "create", "--plan-id", "PLAN-001", "--task-id", "TASK-001",
                     "--context-id", "CTX-001", "--title", "Build route")

        plan = self.tmp / ".aiwf" / "artifacts" / "plans" / "PLAN-001.md"
        self.assertTrue(plan.exists())
        text = plan.read_text()
        self.assertIn("AI working plan", text)
        self.assertIn("TASK-001", text)
        # Before activation: active_plan_id should be empty
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        self.assertEqual(state.get("active_plan_id", ""), "")
        # Activate: planner-executor explicitly chooses which plan
        self._run_ok("plan", "activate", "PLAN-001")
        state = json.loads((self.tmp / ".aiwf" / "state" / "state.json").read_text())
        self.assertEqual(state["active_plan_id"], "PLAN-001")
        plans = json.loads((self.tmp / ".aiwf" / "state" / "plans.json").read_text())
        self.assertTrue(any(p.get("plan_id") == "PLAN-001" for p in plans["plans"]))

    def test_execution_plan_without_active_task_routes_to_plan_only_drift(self):
        from aiwf_core.core.process_contract import planner_process_guidance

        self._run_ok("plan", "create", "--plan-id", "PLAN-001", "--task-id", "TASK-001",
                     "--context-id", "CTX-001", "--title", "Build route")
        # Activate the plan explicitly — plan_only_drift requires active_plan_id
        self._run_ok("plan", "activate", "PLAN-001")

        guidance = planner_process_guidance(str(self.tmp))

        self.assertEqual(guidance["recovery"]["state"], "blocked")
        self.assertEqual(guidance["recovery"]["category"], "plan_only_drift")
        self.assertEqual(guidance["recovery"]["owner"], "planner")
        self.assertIn("PLAN-001", guidance["recovery"]["primary"])
        self.assertTrue(any("Plan-only drift" in item for item in guidance["required_now"]))
        self.assertTrue(any("rewriting the plan" in item for item in guidance["recovery"]["forbidden"]))

    def test_non_execution_plan_remains_open_discussion_not_plan_only_drift(self):
        from aiwf_core.core.process_contract import planner_process_guidance

        self._run_ok("plan", "create", "--plan-id", "PLAN-001", "--task-id", "TASK-001",
                     "--context-id", "CTX-001", "--title", "Build route")
        self._run_ok("plan", "activate", "PLAN-001")
        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["request_mode"] = "discussion"
        state_path.write_text(json.dumps(state, indent=2) + "\n")

        guidance = planner_process_guidance(str(self.tmp))

        self.assertEqual(guidance["recovery"]["state"], "open")
        self.assertEqual(guidance["recovery"]["category"], "discussion")
        self.assertFalse(any("Plan-only drift" in item for item in guidance["required_now"]))

    def test_plan_update_treats_backslash_content_as_literal_text(self):
        self._run_ok("plan", "create", "--task-id", "TASK-001", "--context-id", "CTX-001", "--title", "Build route")
        content = r"Preserve regex capture text: \1 and \g<name> are literal notes."

        self._run_ok("plan", "update", "--task-id", "TASK-001", "--section", "scope", "--content", content)

        plan = (self.tmp / ".aiwf" / "artifacts" / "plans" / "PLAN-TASK-001.md").read_text()
        self.assertIn(content, plan)

    def test_plan_checklist_cannot_replace_mechanical_close_gates(self):
        from aiwf_core.core.task_ledger import activate_task, active_task_completion_blockers, upsert_task
        from aiwf_core.core.task_plan import create_task_plan, update_task_plan_section

        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["workflow_level"] = "L2_standard_team"
        state_path.write_text(json.dumps(state, indent=2))
        goal = json.loads((self.tmp / ".aiwf" / "state" / "goal.json").read_text())
        brief = goal["quality_brief"]
        brief["evaluation_contract"].update({
            "user_visible_outcome": "Feature works",
            "acceptance_criteria": ["checked in plan"],
            "test_obligations": ["run tests"],
            "review_obligations": ["review contract"],
        })
        brief["architecture_brief"]["target_structure"] = "Preserve public CLI shape"
        brief["non_goals"] = ["test"]
        (self.tmp / ".aiwf" / "state" / "goal.json").write_text(json.dumps(goal, indent=2))

        create_task_plan(str(self.tmp), "TASK-001", context_id="CTX-001", title="Plan says done", work_intent="feature")
        update_task_plan_section(str(self.tmp), "TASK-001", "impact",
            "- docs: no — test-only task\n- project_map: no — test\n- environment: no — test\n- capabilities: no — test\n- quality_summary: no — test\n")
        update_task_plan_section(str(self.tmp), "TASK-001", "testing", "- [x] All tests passed\n- [x] Reviewed\n")
        upsert_task(str(self.tmp), "TASK-001", "L2 work", status="ready", allowed_write=["src/a.py"],
                    plan_id="PLAN-TASK-001", goal_id="GOAL-001")
        self.assertTrue(activate_task(str(self.tmp), "TASK-001")["activated"])

        blockers = active_task_completion_blockers(str(self.tmp))
        self.assertTrue(any("independent testing" in b for b in blockers))
        self.assertTrue(any("independent review" in b for b in blockers))


    # ── Impact validation tests ──

    def test_default_plan_impact_placeholders_do_not_validate(self):
        """Default template Impact with 'unknown — fill' must be rejected."""
        from aiwf_core.core.task_plan import create_task_plan, validate_plan_impact

        create_task_plan(str(self.tmp), "TASK-001", context_id="CTX-001", title="Test")
        issues = validate_plan_impact(str(self.tmp), "TASK-001")
        self.assertTrue(len(issues) > 0, f"Default plan Impact should have issues, got: {issues}")
        self.assertTrue(any("unfilled" in i for i in issues),
                        f"Should detect unfilled placeholders, got: {issues}")

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
        self.assertEqual("planned", updated["phase"])
        self.assertEqual("PLAN-NEW", updated["active_plan_id"])
        self.assertIsNone(updated["active_task_id"])
        self.assertFalse(updated["closure_allowed"])
        self.assertFalse(updated["close_attempt"])
        self.assertEqual("", updated["close_prepared_task_id"])

    def test_unknown_docs_or_project_map_blocks_activation(self):
        """Impact with unknown docs or project_map must block activation."""
        from aiwf_core.core.task_ledger import activation_blockers, upsert_task
        from aiwf_core.core.state.plan_ops import upsert_plan

        state_path = self.tmp / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text())
        state["workflow_level"] = "L1_review_light"
        state["request_mode"] = "execution"
        state_path.write_text(json.dumps(state, indent=2))

        # Write a plan with unknown docs — should not pass validation
        plan_dir = self.tmp / ".aiwf" / "artifacts" / "plans"
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
        upsert_plan(str(self.tmp), "PLAN-TASK-001", goal_id="GOAL-001", task_ids=["TASK-001"], plan_kind="implementation", work_intent="feature")

        upsert_task(str(self.tmp), "TASK-001", "Test", status="ready", allowed_write=["test.py"],
                    plan_id="PLAN-TASK-001", goal_id="GOAL-001")
        blockers = activation_blockers(str(self.tmp), "TASK-001")
        self.assertTrue(any("Impact" in b for b in blockers),
                        f"Unknown docs should block activation, got: {blockers}")

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

        plan_dir = self.tmp / ".aiwf" / "artifacts" / "plans"
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
        upsert_plan(str(self.tmp), "PLAN-TASK-001", goal_id="GOAL-001", task_ids=["TASK-001"], plan_kind="implementation", work_intent="feature")

        upsert_task(str(self.tmp), "TASK-001", "Test", status="ready", allowed_write=["test.py"],
                    plan_id="PLAN-TASK-001", goal_id="GOAL-001")
        blockers = activation_blockers(str(self.tmp), "TASK-001")
        self.assertEqual([], blockers, f"Valid Impact should have no blockers, got: {blockers}")


if __name__ == "__main__":
    unittest.main()
