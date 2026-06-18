"""Stage 4: Change Admission Workflow contract tests."""
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


class _Base(unittest.TestCase):
    __unittest_skip__ = True  # V1: change admission removed
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aiwf_s4_"))
        from aiwf_core.core.state_schema import MVP_STATE_FILES
        for rel, factory in MVP_STATE_FILES.items():
            path = self.tmp / ".aiwf" / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(factory(), indent=2) + "\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, *args):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        return subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", *args],
            cwd=str(self.tmp), env=env, capture_output=True, text=True, timeout=TIMEOUT,
        )


# ═══════════════════════════════════════════════════════════════════════════
# 4.1: Admission judgment logic (keyword heuristic, downgraded)
# ═══════════════════════════════════════════════════════════════════════════

class TestAdmissionLogic(_Base):
    @unittest.skip("V1: feature removed")
    def test_admit_attach_plan_for_local_improvement(self):
        from aiwf_core.core.state.admission_ops import admit_change
        from aiwf_core.core.state.goal_tree_ops import init_root

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        result = admit_change(str(self.tmp), "fix typo in README")
        self.assertEqual(result["admission"], "attach_plan")
        self.assertEqual(result["plan_kind"], "implementation")

    @unittest.skip("V1: feature removed")
    def test_admit_has_heuristic_note(self):
        from aiwf_core.core.state.admission_ops import admit_change
        from aiwf_core.core.state.goal_tree_ops import init_root

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        result = admit_change(str(self.tmp), "fix typo")
        notes = result.get("notes", []) or []
        self.assertTrue(any("Heuristic" in n for n in notes))

    @unittest.skip("V1: feature removed")
    def test_explicit_target_goal_does_not_claim_default_fallback(self):
        from aiwf_core.core.state.admission_ops import admit_change
        from aiwf_core.core.state.goal_tree_ops import init_root

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        result = admit_change(
            str(self.tmp),
            "fix typo in README",
            target_goal_hint="GOAL-EXPLICIT",
        )

        self.assertEqual(result["target_goal_id"], "GOAL-EXPLICIT")
        self.assertFalse(any("target defaults to GOAL-001" in n for n in result["notes"]))
        self.assertEqual(result["confidence"], "medium")

    @unittest.skip("V1: feature removed")
    def test_admit_graft_goal_for_skeleton_change(self):
        from aiwf_core.core.state.admission_ops import admit_change
        from aiwf_core.core.state.goal_tree_ops import init_root

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        result = admit_change(str(self.tmp), "new capability: Impact Cone analysis")
        self.assertEqual(result["admission"], "graft_goal")
        self.assertEqual(result["plan_kind"], "structural")

    @unittest.skip("V1: feature removed")
    def test_admit_temporary_root_for_ownership_unclear(self):
        from aiwf_core.core.state.admission_ops import admit_change
        from aiwf_core.core.state.goal_tree_ops import init_root

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        result = admit_change(str(self.tmp), "experiment with multi-agent orchestration")
        self.assertEqual(result["admission"], "temporary_root")

    @unittest.skip("V1: feature removed")
    def test_admit_returns_plan_kind_verification(self):
        from aiwf_core.core.state.admission_ops import admit_change
        from aiwf_core.core.state.goal_tree_ops import init_root

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        result = admit_change(str(self.tmp), "test the admission judgment")
        self.assertEqual(result["admission"], "attach_plan")
        self.assertEqual(result["plan_kind"], "verification")

    @unittest.skip("V1: feature removed")
    def test_admit_returns_plan_kind_migration(self):
        from aiwf_core.core.state.admission_ops import admit_change
        from aiwf_core.core.state.goal_tree_ops import init_root

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        result = admit_change(str(self.tmp), "migrate old schema to new format")
        self.assertEqual(result["admission"], "attach_plan")
        self.assertEqual(result["plan_kind"], "migration")

    @unittest.skip("V1: feature removed")
    def test_admit_finds_best_matching_goal(self):
        from aiwf_core.core.state.admission_ops import admit_change
        from aiwf_core.core.state.goal_tree_ops import init_root

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        init_root(str(self.tmp), "GOAL-002", root_type="main", title="Goal Tree Registry")
        result = admit_change(str(self.tmp), "fix cycle detection in goal tree")
        self.assertEqual(result["admission"], "attach_plan")
        self.assertEqual(result["target_goal_id"], "GOAL-002")

    @unittest.skip("V1: feature removed")
    def test_admit_with_empty_goals_adds_note(self):
        from aiwf_core.core.state.admission_ops import admit_change

        result = admit_change(str(self.tmp), "fix typo in README")
        notes = result.get("notes", []) or []
        self.assertTrue(any("goals.json is empty" in n for n in notes))

    @unittest.skip("V1: feature removed")
    def test_admit_has_next_commands_internally(self):
        from aiwf_core.core.state.admission_ops import admit_change
        from aiwf_core.core.state.goal_tree_ops import init_root

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        result = admit_change(str(self.tmp), "fix typo in README")
        self.assertIn("next_commands", result)
        # next_commands still computed internally (for --debug), but not in default human output

    @unittest.skip("V1: feature removed")
    def test_admit_empty_summary(self):
        from aiwf_core.core.state.admission_ops import admit_change

        result = admit_change(str(self.tmp), "")
        self.assertEqual(result["admission"], "unknown")

    @unittest.skip("V1: feature removed")
    def test_admit_skeleton_signal_wins_over_local(self):
        from aiwf_core.core.state.admission_ops import admit_change
        from aiwf_core.core.state.goal_tree_ops import init_root

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        result = admit_change(str(self.tmp), "new capability to fix performance issues")
        self.assertEqual(result["admission"], "graft_goal")

    # ── Chinese keywords ──
    @unittest.skip("V1: feature removed")
    def test_admit_chinese_skeleton_change(self):
        from aiwf_core.core.state.admission_ops import admit_change
        from aiwf_core.core.state.goal_tree_ops import init_root

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        result = admit_change(str(self.tmp), "把 Goal Tree 的接口嫁接机制做实")
        self.assertEqual(result["admission"], "graft_goal")

    @unittest.skip("V1: feature removed")
    def test_admit_chinese_new_capability(self):
        from aiwf_core.core.state.admission_ops import admit_change
        from aiwf_core.core.state.goal_tree_ops import init_root

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        result = admit_change(str(self.tmp), "新增能力：Impact Cone 分析模块")
        self.assertEqual(result["admission"], "graft_goal")

    @unittest.skip("V1: feature removed")
    def test_admit_chinese_exploration(self):
        from aiwf_core.core.state.admission_ops import admit_change
        from aiwf_core.core.state.goal_tree_ops import init_root

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        result = admit_change(str(self.tmp), "探索多 agent 协作的可行性")
        self.assertEqual(result["admission"], "temporary_root")

    @unittest.skip("V1: feature removed")
    def test_admit_chinese_fix(self):
        from aiwf_core.core.state.admission_ops import admit_change
        from aiwf_core.core.state.goal_tree_ops import init_root

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        result = admit_change(str(self.tmp), "修复 README 里的拼写错误")
        self.assertEqual(result["admission"], "attach_plan")

    @unittest.skip("V1: feature removed")
    def test_admit_chinese_test(self):
        from aiwf_core.core.state.admission_ops import admit_change
        from aiwf_core.core.state.goal_tree_ops import init_root

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        result = admit_change(str(self.tmp), "给 admission 模块补测试覆盖")
        self.assertEqual(result["admission"], "attach_plan")
        self.assertEqual(result["plan_kind"], "verification")

    @unittest.skip("V1: feature removed")
    def test_admit_chinese_migration(self):
        from aiwf_core.core.state.admission_ops import admit_change
        from aiwf_core.core.state.goal_tree_ops import init_root

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        result = admit_change(str(self.tmp), "迁移旧 task plan 到新 Plan registry")
        self.assertEqual(result["admission"], "attach_plan")
        self.assertEqual(result["plan_kind"], "migration")


# ═══════════════════════════════════════════════════════════════════════════
# 4.2: CLI — heuristic fallback
# ═══════════════════════════════════════════════════════════════════════════

class TestChangeAdmitCLI(_Base):
    @unittest.skip("V1: feature removed")
    def test_cli_admit_shows_heuristic_warning(self):
        from aiwf_core.core.state.goal_tree_ops import init_root

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        r = self._run("change", "admit", "--summary", "fix typo in README")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Heuristic recommendation only", r.stdout)

    @unittest.skip("V1: feature removed")
    def test_cli_admit_shows_recommendation(self):
        from aiwf_core.core.state.goal_tree_ops import init_root

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        r = self._run("change", "admit", "--summary", "fix typo in README")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("attach_plan", r.stdout)

    @unittest.skip("V1: feature removed")
    def test_cli_admit_hides_commands_by_default(self):
        from aiwf_core.core.state.goal_tree_ops import init_root

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        r = self._run("change", "admit", "--summary", "fix typo in README")
        self.assertEqual(r.returncode, 0, r.stderr)
        # Shell commands must NOT appear in default output
        self.assertNotIn("aiwf plan create", r.stdout)
        self.assertNotIn("aiwf goal-tree", r.stdout)

    @unittest.skip("V1: feature removed")
    def test_cli_admit_debug_shows_commands(self):
        from aiwf_core.core.state.goal_tree_ops import init_root

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        r = self._run("change", "admit", "--summary", "fix typo in README", "--debug")
        self.assertEqual(r.returncode, 0, r.stderr)
        # In debug mode, commands are visible
        self.assertIn("plan create", r.stdout)

    @unittest.skip("V1: feature removed")
    def test_cli_admit_requires_summary(self):
        r = self._run("change", "admit")
        self.assertNotEqual(r.returncode, 0)

    @unittest.skip("V1: feature removed")
    def test_cli_admit_with_debug_shows_signals(self):
        from aiwf_core.core.state.goal_tree_ops import init_root

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        r = self._run("change", "admit", "--summary", "fix typo", "--debug")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Signals detected", r.stdout)

    @unittest.skip("V1: feature removed")
    def test_cli_change_help(self):
        r = self._run("change")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Semantic Admission Protocol", r.stdout)
        self.assertIn("Heuristic fallback", r.stdout)


# ═══════════════════════════════════════════════════════════════════════════
# 4.4: Orphan-patch review detection
# ═══════════════════════════════════════════════════════════════════════════

class TestOrphanPatchDetection(_Base):
    @unittest.skip("V1: feature removed")
    def test_task_without_plan_is_orphan(self):
        from aiwf_core.core.state.review_ops import check_orphan_patches
        from aiwf_core.core.task_ledger import upsert_task

        upsert_task(str(self.tmp), "TASK-ORPHAN", "Orphan task", status="ready",
                    goal_id="GOAL-001")
        result = check_orphan_patches(str(self.tmp))
        orphan_count = sum(
            1 for w in result.get("warnings", [])
            if "no plan_id" in w and "TASK-ORPHAN" in w
        )
        self.assertTrue(orphan_count > 0 or result.get("orphan_patches_found"))

    @unittest.skip("V1: feature removed")
    def test_plan_without_target_goal_is_orphan(self):
        from aiwf_core.core.state.plan_ops import upsert_plan
        from aiwf_core.core.state.review_ops import check_orphan_patches

        upsert_plan(str(self.tmp), "PLAN-ORPHAN", goal_id="GOAL-001")
        result = check_orphan_patches(str(self.tmp))
        orphan_count = sum(
            1 for w in result.get("warnings", [])
            if "no valid target_goal_id" in w and "PLAN-ORPHAN" in w
        )
        self.assertTrue(orphan_count > 0 or result.get("orphan_patches_found"))

    @unittest.skip("V1: feature removed")
    def test_goal_without_graft_interface_is_orphan(self):
        from aiwf_core.core.state.goal_tree_ops import add_child_goal, init_root
        from aiwf_core.core.state.review_ops import check_orphan_patches

        init_root(str(self.tmp), "GOAL-001", root_type="main")
        add_child_goal(str(self.tmp), "GOAL-001", "GOAL-CHILD-NO-GRAFT")
        result = check_orphan_patches(str(self.tmp))
        orphan_count = sum(
            1 for w in result.get("warnings", [])
            if "no graft_interface" in w and "GOAL-CHILD-NO-GRAFT" in w
        )
        self.assertTrue(orphan_count > 0 or result.get("orphan_patches_found"))

    @unittest.skip("V1: feature removed")
    def test_goal_with_graft_history_is_not_orphan(self):
        from aiwf_core.core.state.goal_tree_ops import graft_branch, init_root
        from aiwf_core.core.state.review_ops import check_orphan_patches

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        init_root(str(self.tmp), "GOAL-X", root_type="temporary", title="Trial")
        graft_branch(str(self.tmp), "GOAL-X", "GOAL-001",
                     reason="Normal graft",
                     interface_consumed="test interface",
                     capability_provided="test capability")

        result = check_orphan_patches(str(self.tmp))
        orphan_goal_x = any(
            "GOAL-X" in w and "no graft_interface" in w
            for w in result.get("warnings", [])
        )
        self.assertFalse(orphan_goal_x)

    @unittest.skip("V1: feature removed")
    def test_cross_relation_without_reason_is_orphan(self):
        from aiwf_core.core.state.goal_tree_ops import add_child_goal, add_relation, init_root
        from aiwf_core.core.state.review_ops import check_orphan_patches

        init_root(str(self.tmp), "GOAL-ROOT-1", root_type="main")
        init_root(str(self.tmp), "GOAL-ROOT-2", root_type="main")
        add_child_goal(str(self.tmp), "GOAL-ROOT-1", "GOAL-A")
        add_child_goal(str(self.tmp), "GOAL-ROOT-2", "GOAL-B")
        add_relation(str(self.tmp), "GOAL-A", "GOAL-B", "depends_on",
                     allow_cross=True, reason="")

        result = check_orphan_patches(str(self.tmp))
        orphan_count = sum(
            1 for w in result.get("warnings", [])
            if "cross-parent" in w and "no reason" in w
        )
        self.assertTrue(orphan_count > 0 or result.get("orphan_patches_found"))

    @unittest.skip("V1: feature removed")
    def test_normal_workspace_no_orphans(self):
        from aiwf_core.core.state.goal_tree_ops import init_root
        from aiwf_core.core.state.plan_ops import upsert_plan
        from aiwf_core.core.state.review_ops import check_orphan_patches
        from aiwf_core.core.task_ledger import upsert_task

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        upsert_plan(str(self.tmp), "PLAN-001", goal_id="GOAL-001",
                    target_goal_id="GOAL-001")
        upsert_task(str(self.tmp), "TASK-001", "Proper task", status="ready",
                    plan_id="PLAN-001", goal_id="GOAL-001")

        result = check_orphan_patches(str(self.tmp))
        self.assertFalse(result.get("orphan_patches_found"))

    @unittest.skip("V1: feature removed")
    def test_orphan_severity_l1_is_warning(self):
        from aiwf_core.core.state.goal_tree_ops import init_root
        from aiwf_core.core.state.plan_ops import upsert_plan
        from aiwf_core.core.state.review_ops import check_orphan_patches

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        upsert_plan(str(self.tmp), "PLAN-001", goal_id="GOAL-001")
        result = check_orphan_patches(str(self.tmp))
        self.assertEqual(result.get("severity"), "warning")

    @unittest.skip("V1: feature removed")
    def test_orphan_severity_v1_always_warning(self):
        """V1: workflow_level does not control orphan severity — always 'warning'."""
        from aiwf_core.core.state.goal_tree_ops import init_root
        from aiwf_core.core.state.plan_ops import upsert_plan
        from aiwf_core.core.state.review_ops import check_orphan_patches

        state_path = Path(self.tmp) / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["workflow_level"] = "L2_standard_team"
        state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        upsert_plan(str(self.tmp), "PLAN-001", goal_id="GOAL-001")
        result = check_orphan_patches(str(self.tmp))
        # V1: always 'warning' — severity is not derived from workflow_level
        self.assertEqual(result.get("severity"), "warning")


# ═══════════════════════════════════════════════════════════════════════════
# 4.2 Semantic Admission Validator
# ═══════════════════════════════════════════════════════════════════════════

class TestAdmissionValidator(_Base):
    @unittest.skip("V1: feature removed")
    def test_validate_valid_attach_plan(self):
        from aiwf_core.core.state.admission_ops import validate_admission_decision
        from aiwf_core.core.state.goal_tree_ops import init_root

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        decision = {
            "admission_type": "attach_plan",
            "target_goal_id": "GOAL-001",
            "plan_kind": "implementation",
            "reason": "Fix typo",
            "confidence": "high",
            "needs_human_confirmation": False,
        }
        result = validate_admission_decision(str(self.tmp), decision)
        self.assertTrue(result["valid"])

    @unittest.skip("V1: feature removed")
    def test_validate_attach_plan_rejects_missing_target_goal(self):
        from aiwf_core.core.state.admission_ops import validate_admission_decision
        decision = {"admission_type": "attach_plan", "plan_kind": "implementation", "reason": "test"}
        result = validate_admission_decision(str(self.tmp), decision)
        self.assertFalse(result["valid"])

    @unittest.skip("V1: feature removed")
    def test_validate_graft_goal_rejects_missing_interface(self):
        from aiwf_core.core.state.admission_ops import validate_admission_decision
        from aiwf_core.core.state.goal_tree_ops import init_root

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        decision = {
            "admission_type": "graft_goal",
            "target_parent_goal_id": "GOAL-001",
            "plan_kind": "structural",
            "reason": "new capability",
        }
        result = validate_admission_decision(str(self.tmp), decision)
        self.assertFalse(result["valid"])
        self.assertTrue(any("interface_consumed" in i for i in result["issues"]))

    @unittest.skip("V1: feature removed")
    def test_validate_valid_temporary_root(self):
        from aiwf_core.core.state.admission_ops import validate_admission_decision
        decision = {
            "admission_type": "temporary_root",
            "reason": "Ownership unclear",
            "confidence": "medium",
        }
        result = validate_admission_decision(str(self.tmp), decision)
        self.assertTrue(result["valid"])

    @unittest.skip("V1: feature removed")
    def test_validate_low_confidence_warns(self):
        from aiwf_core.core.state.admission_ops import validate_admission_decision
        decision = {
            "admission_type": "temporary_root",
            "reason": "unsure",
            "confidence": "low",
            "needs_human_confirmation": False,
        }
        result = validate_admission_decision(str(self.tmp), decision)
        self.assertTrue(result["valid"])
        self.assertTrue(len(result["warnings"]) > 0)

    @unittest.skip("V1: feature removed")
    def test_validate_rejects_invalid_admission_type(self):
        from aiwf_core.core.state.admission_ops import validate_admission_decision
        result = validate_admission_decision(str(self.tmp), {"admission_type": "garbage"})
        self.assertFalse(result["valid"])

    @unittest.skip("V1: feature removed")
    def test_cli_validate_decision_valid(self):
        from aiwf_core.core.state.goal_tree_ops import init_root

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        d = {"admission_type": "attach_plan", "target_goal_id": "GOAL-001",
             "plan_kind": "implementation", "reason": "test"}
        f = Path(self.tmp) / "admission.json"
        f.write_text(json.dumps(d), encoding="utf-8")
        r = self._run("change", "validate-decision", "--file", str(f))
        self.assertEqual(r.returncode, 0, r.stderr)

    @unittest.skip("V1: feature removed")
    def test_cli_validate_decision_invalid(self):
        from aiwf_core.core.state.goal_tree_ops import init_root

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        d = {"admission_type": "graft_goal", "target_parent_goal_id": "GOAL-001"}
        f = Path(self.tmp) / "bad.json"
        f.write_text(json.dumps(d), encoding="utf-8")
        r = self._run("change", "validate-decision", "--file", str(f))
        self.assertNotEqual(r.returncode, 0)


# ═══════════════════════════════════════════════════════════════════════════
# Stage 4.3: Admission-to-Action Plan — human + operation plan, no shell cmds
# ═══════════════════════════════════════════════════════════════════════════

class TestPrepareActionPlan(_Base):
    @unittest.skip("V1: feature removed")
    def test_attach_plan_produces_human_action_plan(self):
        from aiwf_core.core.state.admission_ops import prepare_action_plan
        from aiwf_core.core.state.goal_tree_ops import init_root

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Change Admission")
        decision = {
            "admission_type": "attach_plan",
            "target_goal_id": "GOAL-001",
            "plan_kind": "structural",
            "active_phase": "framing",
            "reason": "Replace keyword heuristic",
        }
        result = prepare_action_plan(str(self.tmp), decision)
        self.assertTrue(result["valid"])
        human = result["human_action_plan"]
        self.assertEqual(human["entry_type"], "attach_plan")
        self.assertEqual(human["target_goal_id"], "GOAL-001")
        self.assertEqual(human["plan_kind"], "structural")
        self.assertIn("risks", human)
        self.assertIn("requires_confirmation", human)

    @unittest.skip("V1: feature removed")
    def test_attach_plan_produces_operation_plan(self):
        from aiwf_core.core.state.admission_ops import prepare_action_plan
        from aiwf_core.core.state.goal_tree_ops import init_root

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        decision = {
            "admission_type": "attach_plan",
            "target_goal_id": "GOAL-001",
            "plan_kind": "implementation",
            "reason": "test",
        }
        result = prepare_action_plan(str(self.tmp), decision)
        ops = result["operation_plan"]["operations"]
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0]["op"], "create_plan")
        self.assertEqual(ops[0]["target_goal_id"], "GOAL-001")
        self.assertFalse(result["operation_plan"]["mutates_state"])

    @unittest.skip("V1: feature removed")
    def test_graft_goal_produces_human_action_plan_with_interface(self):
        from aiwf_core.core.state.admission_ops import prepare_action_plan
        from aiwf_core.core.state.goal_tree_ops import init_root

        init_root(str(self.tmp), "GOAL-ROOT", root_type="main", title="Rooted Tree")
        decision = {
            "admission_type": "graft_goal",
            "target_parent_goal_id": "GOAL-ROOT",
            "new_goal_title": "Impact Cone",
            "interface_consumed": "Goal Tree relation",
            "capability_provided": "Structural analysis",
            "relation_to_parent": "extends",
            "reason": "Adds impact analysis",
        }
        result = prepare_action_plan(str(self.tmp), decision)
        human = result["human_action_plan"]
        self.assertEqual(human["entry_type"], "graft_goal")
        self.assertEqual(human["interface_consumed"], "Goal Tree relation")
        self.assertEqual(human["capability_provided"], "Structural analysis")

    @unittest.skip("V1: feature removed")
    def test_graft_goal_operation_plan_uses_structured_ops_not_commands(self):
        from aiwf_core.core.state.admission_ops import prepare_action_plan
        from aiwf_core.core.state.goal_tree_ops import init_root

        init_root(str(self.tmp), "GOAL-ROOT", root_type="main", title="Root")
        decision = {
            "admission_type": "graft_goal",
            "target_parent_goal_id": "GOAL-ROOT",
            "new_goal_title": "Impact Cone",
            "interface_consumed": "test interface",
            "capability_provided": "test capability",
            "relation_to_parent": "extends",
            "reason": "test",
        }
        result = prepare_action_plan(str(self.tmp), decision)
        ops = result["operation_plan"]["operations"]
        for op in ops:
            self.assertIn("op", op)
            self.assertNotIn("aiwf", op.get("op", ""))
        self.assertGreaterEqual(len(ops), 3)

    @unittest.skip("V1: feature removed")
    def test_graft_with_existing_temp_root_skips_create(self):
        from aiwf_core.core.state.admission_ops import prepare_action_plan
        from aiwf_core.core.state.goal_tree_ops import init_root

        init_root(str(self.tmp), "GOAL-ROOT", root_type="main", title="Root")
        decision = {
            "admission_type": "graft_goal",
            "target_parent_goal_id": "GOAL-ROOT",
            "existing_temporary_root_id": "TMP-001",
            "new_goal_title": "Impact Cone",
            "interface_consumed": "test",
            "capability_provided": "test",
            "relation_to_parent": "extends",
            "reason": "test",
        }
        result = prepare_action_plan(str(self.tmp), decision)
        ops = result["operation_plan"]["operations"]
        self.assertTrue(
            any(o["op"] == "graft_goal" and
                o.get("source_goal_id") == "TMP-001" for o in ops)
        )

    @unittest.skip("V1: feature removed")
    def test_temporary_root_produces_exploration_action_plan(self):
        from aiwf_core.core.state.admission_ops import prepare_action_plan

        decision = {
            "admission_type": "temporary_root",
            "new_goal_title": "Explore context pack",
            "reason": "Ownership unclear",
        }
        result = prepare_action_plan(str(self.tmp), decision)
        human = result["human_action_plan"]
        self.assertEqual(human["entry_type"], "temporary_root")
        self.assertTrue(any("Temporary" in r for r in human["risks"]))
        ops = result["operation_plan"]["operations"]
        self.assertEqual(ops[0]["op"], "create_temporary_root")

    @unittest.skip("V1: feature removed")
    def test_invalid_decision_produces_no_plan(self):
        from aiwf_core.core.state.admission_ops import prepare_action_plan

        result = prepare_action_plan(str(self.tmp), {"admission_type": "attach_plan"})
        self.assertFalse(result["valid"])
        self.assertIsNone(result["human_action_plan"])
        self.assertIsNone(result["operation_plan"])

    @unittest.skip("V1: feature removed")
    def test_low_confidence_marks_requires_confirmation(self):
        from aiwf_core.core.state.admission_ops import prepare_action_plan

        decision = {
            "admission_type": "temporary_root",
            "reason": "unsure",
            "confidence": "low",
        }
        result = prepare_action_plan(str(self.tmp), decision)
        self.assertTrue(result["human_action_plan"]["requires_confirmation"])
        self.assertTrue(result["operation_plan"]["execution_requires_confirmation"])

    @unittest.skip("V1: feature removed")
    def test_no_shell_commands_in_output(self):
        from aiwf_core.core.state.admission_ops import prepare_action_plan
        from aiwf_core.core.state.goal_tree_ops import init_root

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        decision = {
            "admission_type": "attach_plan",
            "target_goal_id": "GOAL-001",
            "plan_kind": "structural",
            "reason": "test",
        }
        result = prepare_action_plan(str(self.tmp), decision)
        encoded = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("aiwf plan create", encoded)
        self.assertNotIn("aiwf goal-tree", encoded)

    @unittest.skip("V1: feature removed")
    def test_does_not_mutate_state(self):
        from aiwf_core.core.state.admission_ops import prepare_action_plan
        from aiwf_core.core.state.goal_tree_ops import init_root, load_goal_tree

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        before = json.dumps(load_goal_tree(str(self.tmp), auto_create=False))

        decision = {
            "admission_type": "attach_plan",
            "target_goal_id": "GOAL-001",
            "plan_kind": "implementation",
            "reason": "test",
        }
        prepare_action_plan(str(self.tmp), decision)

        after = json.dumps(load_goal_tree(str(self.tmp), auto_create=False))
        self.assertEqual(before, after, "prepare_action_plan must not mutate goals.json")

    # ── CLI ──

    @unittest.skip("V1: feature removed")
    def test_cli_change_prepare_human_readable(self):
        from aiwf_core.core.state.goal_tree_ops import init_root

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Change Admission")
        d = {
            "admission_type": "attach_plan",
            "target_goal_id": "GOAL-001",
            "plan_kind": "structural",
            "active_phase": "framing",
            "reason": "Replace keyword heuristic",
        }
        f = Path(self.tmp) / "admission.json"
        f.write_text(json.dumps(d), encoding="utf-8")

        r = self._run("change", "prepare", "--file", str(f))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Change Action Plan", r.stdout)
        self.assertIn("Why:", r.stdout)
        self.assertIn("Risk:", r.stdout)
        self.assertNotIn("aiwf plan create", r.stdout)

    @unittest.skip("V1: feature removed")
    def test_cli_change_prepare_json(self):
        from aiwf_core.core.state.goal_tree_ops import init_root

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        d = {
            "admission_type": "attach_plan",
            "target_goal_id": "GOAL-001",
            "plan_kind": "implementation",
            "reason": "test",
        }
        f = Path(self.tmp) / "admission.json"
        f.write_text(json.dumps(d), encoding="utf-8")

        r = self._run("change", "prepare", "--file", str(f), "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        parsed = json.loads(r.stdout)
        self.assertTrue(parsed["valid"])
        self.assertIn("human_action_plan", parsed)
        self.assertIn("operation_plan", parsed)
        # JSON output must also be free of shell commands
        encoded = json.dumps(parsed, ensure_ascii=False)
        self.assertNotIn("aiwf plan create", encoded)

    @unittest.skip("V1: feature removed")
    def test_cli_change_prepare_invalid_exits_1(self):
        d = {"admission_type": "attach_plan"}
        f = Path(self.tmp) / "bad.json"
        f.write_text(json.dumps(d), encoding="utf-8")
        r = self._run("change", "prepare", "--file", str(f))
        self.assertNotEqual(r.returncode, 0)

    @unittest.skip("V1: feature removed")
    def test_cli_change_help_stage4_3(self):
        r = self._run("change")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("prepare", r.stdout)
        self.assertIn("Action Plan", r.stdout)


# ═══════════════════════════════════════════════════════════════════════════
# Stage 4.4: Admission-aware Review
# ═══════════════════════════════════════════════════════════════════════════

class TestAdmissionReview(_Base):
    @unittest.skip("V1: feature removed")
    def test_plan_with_valid_trace_passes(self):
        from aiwf_core.core.state.goal_tree_ops import init_root
        from aiwf_core.core.state.plan_ops import load_plans, save_plans, upsert_plan
        from aiwf_core.core.state.review_ops import admission_review

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        upsert_plan(str(self.tmp), "PLAN-001", goal_id="GOAL-001", target_goal_id="GOAL-001")
        plans = load_plans(str(self.tmp))
        for p in plans["plans"]:
            if p["plan_id"] == "PLAN-001":
                p["admission_trace"] = {
                    "decision_id": "ADM-001", "admission_type": "attach_plan",
                    "validated": True, "prepared_action_id": "ACT-001",
                }
                p["target_goal_id"] = "GOAL-001"
        save_plans(str(self.tmp), plans)

        result = admission_review(str(self.tmp))
        self.assertEqual(result["total_issues"], 0)

    @unittest.skip("V1: feature removed")
    def test_plan_admitted_attach_plan_without_target_goal_flagged(self):
        from aiwf_core.core.state.goal_tree_ops import init_root
        from aiwf_core.core.state.plan_ops import load_plans, save_plans, upsert_plan
        from aiwf_core.core.state.review_ops import admission_review

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        upsert_plan(str(self.tmp), "PLAN-001", goal_id="GOAL-001")
        plans = load_plans(str(self.tmp))
        for p in plans["plans"]:
            if p["plan_id"] == "PLAN-001":
                p["admission_trace"] = {"admission_type": "attach_plan", "validated": True}
                p["target_goal_id"] = ""
        save_plans(str(self.tmp), plans)

        result = admission_review(str(self.tmp))
        self.assertTrue(result["admission_trace_issues"]["found"])
        self.assertTrue(any("target_goal_id" in w for w in result.get("warnings", [])))

    @unittest.skip("V1: feature removed")
    def test_goal_admitted_graft_without_interface_flagged(self):
        from aiwf_core.core.state.goal_tree_ops import add_child_goal, init_root, load_goal_tree, save_goal_tree
        from aiwf_core.core.state.review_ops import admission_review

        init_root(str(self.tmp), "GOAL-001", root_type="main")
        add_child_goal(str(self.tmp), "GOAL-001", "GOAL-CHILD")
        tree = load_goal_tree(str(self.tmp))
        for g in tree["goals"]:
            if g["id"] == "GOAL-CHILD":
                g["admission_trace"] = {"admission_type": "graft_goal", "validated": True}
        save_goal_tree(str(self.tmp), tree)

        result = admission_review(str(self.tmp))
        self.assertTrue(result["admission_trace_issues"]["found"])
        self.assertTrue(any("graft_interface" in w for w in result.get("warnings", [])))

    @unittest.skip("V1: feature removed")
    def test_admission_trace_validated_false_flagged(self):
        from aiwf_core.core.state.goal_tree_ops import init_root, load_goal_tree, save_goal_tree
        from aiwf_core.core.state.review_ops import admission_review

        init_root(str(self.tmp), "GOAL-001", root_type="main")
        tree = load_goal_tree(str(self.tmp))
        for g in tree["goals"]:
            if g["id"] == "GOAL-001":
                g["admission_trace"] = {"admission_type": "attach_plan", "validated": False}
        save_goal_tree(str(self.tmp), tree)

        result = admission_review(str(self.tmp))
        self.assertTrue(result["admission_trace_issues"]["found"])

    @unittest.skip("V1: feature removed")
    def test_structure_plan_with_implementation_admission_flagged(self):
        from aiwf_core.core.state.goal_tree_ops import init_root
        from aiwf_core.core.state.plan_ops import load_plans, save_plans, upsert_plan
        from aiwf_core.core.state.review_ops import admission_review

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        # Admitted as graft_goal but plan_kind is implementation, not structural
        upsert_plan(str(self.tmp), "PLAN-001", goal_id="GOAL-001",
                    target_goal_id="GOAL-001", plan_kind="implementation")
        plans = load_plans(str(self.tmp))
        for p in plans["plans"]:
            if p["plan_id"] == "PLAN-001":
                p["admission_trace"] = {"admission_type": "graft_goal", "validated": True}
        save_plans(str(self.tmp), plans)

        result = admission_review(str(self.tmp))
        self.assertTrue(result["operation_alignment"]["found"])

    @unittest.skip("V1: feature removed")
    def test_admission_review_severity_v1_always_warning(self):
        """V1: workflow_level does not control admission review severity — always 'warning'."""
        from aiwf_core.core.state.goal_tree_ops import init_root
        from aiwf_core.core.state.plan_ops import load_plans, save_plans, upsert_plan
        from aiwf_core.core.state.review_ops import admission_review

        state_path = Path(self.tmp) / ".aiwf" / "state" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["workflow_level"] = "L2_standard_team"
        state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

        init_root(str(self.tmp), "GOAL-001", root_type="main")
        upsert_plan(str(self.tmp), "PLAN-001", goal_id="GOAL-001")
        plans = load_plans(str(self.tmp))
        for p in plans["plans"]:
            if p["plan_id"] == "PLAN-001":
                p["admission_trace"] = {"admission_type": "attach_plan", "validated": True}
                p["target_goal_id"] = ""
        save_plans(str(self.tmp), plans)

        result = admission_review(str(self.tmp))
        # V1: always 'warning' — severity is not derived from workflow_level
        self.assertEqual(result["severity"], "warning")

    @unittest.skip("V1: feature removed")
    def test_admission_review_includes_summary_fields(self):
        from aiwf_core.core.state.goal_tree_ops import init_root
        from aiwf_core.core.state.review_ops import admission_review

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        result = admission_review(str(self.tmp))
        self.assertIn("summary", result)
        self.assertIn("orphan_patches", result)
        self.assertIn("admission_trace_issues", result)
        self.assertIn("operation_alignment", result)
        self.assertIn("next_review_focus", result)

    @unittest.skip("V1: feature removed")
    def test_no_admission_traces_still_reviewable(self):
        """Workspace without any admission_trace should not crash."""
        from aiwf_core.core.state.goal_tree_ops import init_root
        from aiwf_core.core.state.review_ops import admission_review

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        result = admission_review(str(self.tmp))
        self.assertFalse(result["has_admission_trace"])
        self.assertEqual(result["total_issues"], 0)

    @unittest.skip("V1: feature removed")
    def test_admission_trace_preserved_on_goal_upsert(self):
        """upsert_goal should not erase an existing admission_trace."""
        from aiwf_core.core.state.goal_tree_ops import get_goal, init_root, load_goal_tree, save_goal_tree, upsert_goal

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        tree = load_goal_tree(str(self.tmp))
        for g in tree["goals"]:
            if g["id"] == "GOAL-001":
                g["admission_trace"] = {"admission_type": "attach_plan", "validated": True}
        save_goal_tree(str(self.tmp), tree)

        upsert_goal(str(self.tmp), "GOAL-001", title="Updated Title")
        g = get_goal(str(self.tmp), "GOAL-001")
        self.assertIsNotNone(g.get("admission_trace"))
        self.assertEqual(g["admission_trace"]["admission_type"], "attach_plan")

    @unittest.skip("V1: feature removed")
    def test_admission_trace_preserved_on_plan_upsert(self):
        """upsert_plan should not erase an existing admission_trace."""
        from aiwf_core.core.state.plan_ops import get_plan, load_plans, save_plans, upsert_plan

        upsert_plan(str(self.tmp), "PLAN-001", goal_id="GOAL-001")
        plans = load_plans(str(self.tmp))
        for p in plans["plans"]:
            if p["plan_id"] == "PLAN-001":
                p["admission_trace"] = {"admission_type": "attach_plan", "validated": True}
        save_plans(str(self.tmp), plans)

        upsert_plan(str(self.tmp), "PLAN-001", title="Updated Plan")
        p = get_plan(str(self.tmp), "PLAN-001")
        self.assertIsNotNone(p.get("admission_trace"))
        self.assertEqual(p["admission_trace"]["admission_type"], "attach_plan")


# ═══════════════════════════════════════════════════════════════════════════
# Stage 4.4b: Action Granularity — patch, task, plan
# ═══════════════════════════════════════════════════════════════════════════

class TestActionGranularity(_Base):
    @unittest.skip("V1: feature removed")
    def test_patch_granularity_does_not_create_plan(self):
        from aiwf_core.core.state.admission_ops import prepare_action_plan
        from aiwf_core.core.state.goal_tree_ops import init_root
        from aiwf_core.core.state.plan_ops import upsert_plan

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        upsert_plan(str(self.tmp), "PLAN-001", goal_id="GOAL-001", target_goal_id="GOAL-001")

        decision = {
            "admission_type": "attach_plan",
            "target_goal_id": "GOAL-001",
            "target_plan_id": "PLAN-001",
            "action_granularity": "patch",
            "reason": "fix wording",
        }
        result = prepare_action_plan(str(self.tmp), decision)
        self.assertTrue(result["valid"])
        human = result["human_action_plan"]
        self.assertEqual(human["action_granularity"], "patch")
        self.assertEqual(human["target_plan_id"], "PLAN-001")
        # Operation should be record_patch, not create_plan
        ops = result["operation_plan"]["operations"]
        self.assertEqual(ops[0]["op"], "record_patch")

    @unittest.skip("V1: feature removed")
    def test_task_granularity_creates_task_not_plan(self):
        from aiwf_core.core.state.admission_ops import prepare_action_plan
        from aiwf_core.core.state.goal_tree_ops import init_root
        from aiwf_core.core.state.plan_ops import upsert_plan

        init_root(str(self.tmp), "GOAL-001", root_type="main")
        upsert_plan(str(self.tmp), "PLAN-001", goal_id="GOAL-001", target_goal_id="GOAL-001")

        decision = {
            "admission_type": "attach_plan",
            "target_goal_id": "GOAL-001",
            "target_plan_id": "PLAN-001",
            "action_granularity": "task",
            "reason": "fix assertion",
        }
        result = prepare_action_plan(str(self.tmp), decision)
        ops = result["operation_plan"]["operations"]
        self.assertEqual(ops[0]["op"], "create_task")

    @unittest.skip("V1: feature removed")
    def test_plan_granularity_creates_plan(self):
        from aiwf_core.core.state.admission_ops import prepare_action_plan
        from aiwf_core.core.state.goal_tree_ops import init_root

        init_root(str(self.tmp), "GOAL-001", root_type="main")
        decision = {
            "admission_type": "attach_plan",
            "target_goal_id": "GOAL-001",
            "plan_kind": "implementation",
            "action_granularity": "plan",
            "reason": "implement feature",
        }
        result = prepare_action_plan(str(self.tmp), decision)
        ops = result["operation_plan"]["operations"]
        self.assertEqual(ops[0]["op"], "create_plan")

    @unittest.skip("V1: feature removed")
    def test_default_granularity_is_plan(self):
        from aiwf_core.core.state.admission_ops import prepare_action_plan
        from aiwf_core.core.state.goal_tree_ops import init_root

        init_root(str(self.tmp), "GOAL-001", root_type="main")
        # No action_granularity field → defaults to "plan"
        decision = {
            "admission_type": "attach_plan",
            "target_goal_id": "GOAL-001",
            "plan_kind": "implementation",
            "reason": "test",
        }
        result = prepare_action_plan(str(self.tmp), decision)
        human = result["human_action_plan"]
        self.assertEqual(human["action_granularity"], "plan")

    @unittest.skip("V1: feature removed")
    def test_patch_human_action_plan_shows_existing_plan(self):
        from aiwf_core.core.state.admission_ops import prepare_action_plan
        from aiwf_core.core.state.goal_tree_ops import init_root
        from aiwf_core.core.state.plan_ops import upsert_plan

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        upsert_plan(str(self.tmp), "PLAN-001", goal_id="GOAL-001", target_goal_id="GOAL-001")

        decision = {
            "admission_type": "attach_plan",
            "target_goal_id": "GOAL-001",
            "target_plan_id": "PLAN-001",
            "action_granularity": "patch",
            "reason": "fix wording",
        }
        result = prepare_action_plan(str(self.tmp), decision)
        human = result["human_action_plan"]
        self.assertIn("granularity_label", human)
        self.assertIn("Lightweight", human["granularity_label"])
        # Should mention existing plan
        self.assertIn("PLAN-001", human.get("next_review_focus", ""))

    @unittest.skip("V1: feature removed")
    def test_cli_prepare_patch_shows_granularity(self):
        from aiwf_core.core.state.goal_tree_ops import init_root
        from aiwf_core.core.state.plan_ops import upsert_plan

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        upsert_plan(str(self.tmp), "PLAN-001", goal_id="GOAL-001", target_goal_id="GOAL-001")

        d = {
            "admission_type": "attach_plan",
            "target_goal_id": "GOAL-001",
            "target_plan_id": "PLAN-001",
            "action_granularity": "patch",
            "reason": "fix wording",
        }
        f = Path(self.tmp) / "admission.json"
        f.write_text(json.dumps(d), encoding="utf-8")

        r = self._run("change", "prepare", "--file", str(f))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("patch", r.stdout.lower())
        self.assertIn("PLAN-001", r.stdout)
        self.assertNotIn("aiwf plan create", r.stdout)


# ═══════════════════════════════════════════════════════════════════════════
# Stage 4.5: Day-1 Foundation Tree
# ═══════════════════════════════════════════════════════════════════════════

class TestFoundationTree(_Base):
    def _valid_foundation(self):
        return {
            "project_title": "Test Project",
            "root_goal": {"id": "GOAL-ROOT", "title": "Kernel", "intent": "Governance"},
            "first_level_goals": [
                {"id": "G1", "title": "Structure", "intent": "Skeleton", "relation_to_root": "decomposes"},
                {"id": "G2", "title": "Admission", "intent": "Entry", "relation_to_root": "extends"},
                {"id": "G3", "title": "Quality", "intent": "Gates", "relation_to_root": "extends"},
            ],
            "structural_plan": {
                "plan_id": "PLAN-S", "target_goal_id": "GOAL-ROOT",
                "plan_kind": "structural", "active_phase": "framing",
                "purpose": "Define interfaces",
                "interfaces": [
                    {"owner": "Goal Tree", "description": "Skeleton"},
                ],
            },
            "active_path": {"sequence": ["GOAL-ROOT", "G1", "PLAN-S"], "reason": "Structure first"},
            "evidence_rollup_policy": {"task_to_plan": "closed tasks update plan", "plan_to_goal": "complete plans roll to goal"},
        }

    @unittest.skip("V1: feature removed")
    def test_valid_foundation_passes(self):
        from aiwf_core.core.state.foundation_ops import validate_foundation_tree

        result = validate_foundation_tree(self._valid_foundation())
        self.assertTrue(result["valid"], f"Issues: {result['issues']}")

    @unittest.skip("V1: feature removed")
    def test_missing_root_fails(self):
        from aiwf_core.core.state.foundation_ops import validate_foundation_tree

        result = validate_foundation_tree({})
        self.assertFalse(result["valid"])
        self.assertTrue(any("root_goal" in i for i in result["issues"]))

    @unittest.skip("V1: feature removed")
    def test_too_many_first_level_goals_warns(self):
        from aiwf_core.core.state.foundation_ops import validate_foundation_tree

        f = self._valid_foundation()
        f["first_level_goals"] = [
            {"id": f"G{i}", "title": f"G{i}", "intent": "x", "relation_to_root": "extends"}
            for i in range(1, 10)
        ]
        result = validate_foundation_tree(f)
        self.assertTrue(result["valid"])  # not a hard error
        self.assertTrue(any("max recommended" in w for w in result.get("warnings", [])))

    @unittest.skip("V1: feature removed")
    def test_missing_structural_plan_fails(self):
        from aiwf_core.core.state.foundation_ops import validate_foundation_tree

        f = self._valid_foundation()
        del f["structural_plan"]
        result = validate_foundation_tree(f)
        self.assertFalse(result["valid"])

    @unittest.skip("V1: feature removed")
    def test_active_path_reference_unknown_fails(self):
        from aiwf_core.core.state.foundation_ops import validate_foundation_tree

        f = self._valid_foundation()
        f["active_path"] = {"sequence": ["GOAL-ROOT", "NONEXISTENT"], "reason": "test"}
        result = validate_foundation_tree(f)
        self.assertFalse(result["valid"])

    @unittest.skip("V1: feature removed")
    def test_missing_evidence_rollup_fails(self):
        from aiwf_core.core.state.foundation_ops import validate_foundation_tree

        f = self._valid_foundation()
        del f["evidence_rollup_policy"]
        result = validate_foundation_tree(f)
        self.assertFalse(result["valid"])

    @unittest.skip("V1: feature removed")
    def test_no_interface_warns_or_fails(self):
        from aiwf_core.core.state.foundation_ops import validate_foundation_tree

        f = self._valid_foundation()
        f["structural_plan"]["interfaces"] = []
        result = validate_foundation_tree(f)
        self.assertFalse(result["valid"])
        self.assertTrue(any("interface" in i for i in result["issues"]))

    @unittest.skip("V1: feature removed")
    def test_valid_with_temporary_roots_and_milestone(self):
        from aiwf_core.core.state.foundation_ops import validate_foundation_tree

        f = self._valid_foundation()
        f["temporary_roots"] = [
            {"title": "Context Pack", "reason": "Unclear scope",
             "resolution_criterion": "When tree stabilizes"}
        ]
        f["initial_milestone"] = {
            "title": "Foundation accepted",
            "acceptance_criteria": ["Tree validated", "Active path ready"]
        }
        result = validate_foundation_tree(f)
        self.assertTrue(result["valid"], f"Issues: {result['issues']}")

    @unittest.skip("V1: feature removed")
    def test_nested_goal_with_hierarchy_triad_passes(self):
        from aiwf_core.core.state.foundation_ops import validate_foundation_tree

        f = self._valid_foundation()
        f["first_level_goals"][0]["child_goals"] = [
            {
                "id": "G1-QUERY",
                "title": "Query Strategy",
                "intent": "Build structured queries",
                "hierarchy_rationale": {
                    "composition": "Search execution is incomplete without query construction",
                    "primary_ownership": "Query construction primarily belongs to search execution",
                    "independent_outcome": False,
                },
            }
        ]
        f["active_path"]["sequence"].insert(2, "G1-QUERY")
        result = validate_foundation_tree(f)
        self.assertTrue(result["valid"], f"Issues: {result['issues']}")
        self.assertEqual(result["summary"]["nested_goal_count"], 1)

    @unittest.skip("V1: feature removed")
    def test_cli_displays_nested_goal_and_hierarchy_rationale(self):
        f = self._valid_foundation()
        f["first_level_goals"][0]["child_goals"] = [
            {
                "id": "G1-QUERY",
                "title": "Query Strategy",
                "intent": "Build structured queries",
                "hierarchy_rationale": {
                    "composition": "Search is incomplete without query construction",
                    "primary_ownership": "Query construction belongs to search",
                    "independent_outcome": False,
                },
            }
        ]
        f_path = Path(self.tmp) / "nested-foundation.json"
        f_path.write_text(json.dumps(f), encoding="utf-8")
        result = self._run("goal-tree", "validate-foundation", "--file", str(f_path))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("G1-QUERY: Query Strategy", result.stdout)
        self.assertIn("composition: Search is incomplete", result.stdout)
        self.assertIn("primary ownership: Query construction belongs", result.stdout)

    @unittest.skip("V1: feature removed")
    def test_nested_goal_without_hierarchy_triad_fails(self):
        from aiwf_core.core.state.foundation_ops import validate_foundation_tree

        f = self._valid_foundation()
        f["first_level_goals"][0]["child_goals"] = [
            {"id": "G1-QUERY", "title": "Query Strategy", "intent": "Build queries"}
        ]
        result = validate_foundation_tree(f)
        self.assertFalse(result["valid"])
        self.assertTrue(any("hierarchy_rationale is required" in i for i in result["issues"]))

    @unittest.skip("V1: feature removed")
    def test_independent_child_is_rejected_as_parent_child(self):
        from aiwf_core.core.state.foundation_ops import validate_foundation_tree

        f = self._valid_foundation()
        f["first_level_goals"][0]["child_goals"] = [
            {
                "id": "G1-SHARED",
                "title": "Shared Evidence Grading",
                "intent": "Serve several capability domains",
                "hierarchy_rationale": {
                    "composition": "Useful to this parent",
                    "primary_ownership": "Shared across multiple parents",
                    "independent_outcome": True,
                },
            }
        ]
        result = validate_foundation_tree(f)
        self.assertFalse(result["valid"])
        self.assertTrue(any("use sibling Goal + relation" in i for i in result["issues"]))

    @unittest.skip("V1: feature removed")
    def test_no_shell_commands_in_output(self):
        from aiwf_core.core.state.foundation_ops import validate_foundation_tree

        result = validate_foundation_tree(self._valid_foundation())
        encoded = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("aiwf plan create", encoded)
        self.assertNotIn("aiwf goal-tree", encoded)

    # ── CLI ──

    @unittest.skip("V1: feature removed")
    def test_cli_validate_foundation_valid(self):
        f_path = Path(self.tmp) / "foundation.json"
        f_path.write_text(json.dumps(self._valid_foundation()), encoding="utf-8")

        r = self._run("goal-tree", "validate-foundation", "--file", str(f_path))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Foundation Tree Proposal", r.stdout)
        self.assertIn("GOAL-ROOT", r.stdout)
        self.assertNotIn("aiwf plan create", r.stdout)

    @unittest.skip("V1: feature removed")
    def test_cli_validate_foundation_invalid(self):
        f_path = Path(self.tmp) / "bad.json"
        f_path.write_text(json.dumps({}), encoding="utf-8")

        r = self._run("goal-tree", "validate-foundation", "--file", str(f_path))
        self.assertNotEqual(r.returncode, 0)

    @unittest.skip("V1: feature removed")
    def test_cli_validate_foundation_json(self):
        f_path = Path(self.tmp) / "foundation.json"
        f_path.write_text(json.dumps(self._valid_foundation()), encoding="utf-8")

        r = self._run("goal-tree", "validate-foundation", "--file", str(f_path), "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        parsed = json.loads(r.stdout)
        self.assertTrue(parsed["valid"])
        self.assertIn("summary", parsed)

    # ── Strengthened validation ──

    @unittest.skip("V1: feature removed")
    def test_structural_plan_target_goal_undeclared_fails(self):
        from aiwf_core.core.state.foundation_ops import validate_foundation_tree

        f = self._valid_foundation()
        f["structural_plan"]["target_goal_id"] = "UNDECLARED"
        result = validate_foundation_tree(f)
        self.assertFalse(result["valid"])
        self.assertTrue(any("target_goal_id" in i for i in result["issues"]))

    @unittest.skip("V1: feature removed")
    def test_one_first_level_goal_warns(self):
        from aiwf_core.core.state.foundation_ops import validate_foundation_tree

        f = self._valid_foundation()
        f["first_level_goals"] = [
            {"id": "G1", "title": "Only", "intent": "Solo", "relation_to_root": "decomposes"}
        ]
        result = validate_foundation_tree(f)
        self.assertTrue(result["valid"])  # 1 is allowed
        self.assertTrue(any("only 1" in w for w in result.get("warnings", [])))

    @unittest.skip("V1: feature removed")
    def test_interface_consumer_undeclared_warns(self):
        from aiwf_core.core.state.foundation_ops import validate_foundation_tree

        f = self._valid_foundation()
        f["structural_plan"]["interfaces"] = [
            {"owner": "Goal Tree", "description": "Skeleton", "consumers": ["UNKNOWN"]}
        ]
        result = validate_foundation_tree(f)
        self.assertTrue(result["valid"])
        self.assertTrue(any("consumers" in w for w in result.get("warnings", [])))

    @unittest.skip("V1: feature removed")
    def test_milestone_covers_undeclared_warns(self):
        from aiwf_core.core.state.foundation_ops import validate_foundation_tree

        f = self._valid_foundation()
        f["initial_milestone"] = {
            "title": "MS-001",
            "covers": ["UNKNOWN"],
            "acceptance_criteria": ["Done"]
        }
        result = validate_foundation_tree(f)
        self.assertTrue(result["valid"])
        self.assertTrue(any("covers" in w for w in result.get("warnings", [])))

    @unittest.skip("V1: feature removed")
    def test_operation_plan_has_version(self):
        from aiwf_core.core.state.admission_ops import prepare_action_plan
        from aiwf_core.core.state.goal_tree_ops import init_root

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Root")
        decision = {
            "admission_type": "attach_plan",
            "target_goal_id": "GOAL-001",
            "plan_kind": "implementation",
            "reason": "test",
        }
        result = prepare_action_plan(str(self.tmp), decision)
        ops = result["operation_plan"]
        self.assertEqual(ops.get("operation_plan_version"), 1)


if __name__ == "__main__":
    unittest.main()
