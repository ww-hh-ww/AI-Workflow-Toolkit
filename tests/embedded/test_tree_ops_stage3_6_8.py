"""Stages 3.6-3.8: Graft, Prune, Relations, Impact Cone contract tests."""
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
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aiwf_s368_"))
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

    def _run_ok(self, *args):
        r = self._run(*args)
        self.assertEqual(r.returncode, 0, f"{args}\nstdout={r.stdout}\nstderr={r.stderr}")
        return r


# ═══════════════════════════════════════════════════════════════════════════
# Stage 3.6: Graft & Prune
# ═══════════════════════════════════════════════════════════════════════════

class TestGraftPrune(_Base):
    def test_graft_moves_temporary_into_main_tree(self):
        from aiwf_core.core.state.goal_tree_ops import get_goal, graft_branch, init_root

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Main")
        init_root(str(self.tmp), "TMP-001", root_type="temporary", title="Trial")

        result = graft_branch(str(self.tmp), "TMP-001", "GOAL-001", reason="Ready to adopt")
        self.assertTrue(result["grafted"])

        source = get_goal(str(self.tmp), "TMP-001")
        self.assertIsNone(source["root_type"])  # no longer a root
        self.assertEqual(source["parent_goal_id"], "GOAL-001")
        self.assertEqual(source["visibility"], "default")  # now visible

        target = get_goal(str(self.tmp), "GOAL-001")
        self.assertIn("TMP-001", target["child_goal_ids"])

    def test_graft_rejects_self_target(self):
        from aiwf_core.core.state.goal_tree_ops import graft_branch, init_root

        init_root(str(self.tmp), "GOAL-001", root_type="main")
        with self.assertRaises(ValueError):
            graft_branch(str(self.tmp), "GOAL-001", "GOAL-001")

    def test_graft_rejects_nonexistent(self):
        from aiwf_core.core.state.goal_tree_ops import graft_branch, init_root

        init_root(str(self.tmp), "GOAL-001", root_type="main")
        with self.assertRaises(ValueError):
            graft_branch(str(self.tmp), "NONEXISTENT", "GOAL-001")

    def test_graft_records_history(self):
        from aiwf_core.core.state.goal_tree_ops import get_goal, graft_branch, init_root

        init_root(str(self.tmp), "GOAL-001", root_type="main")
        init_root(str(self.tmp), "TMP-001", root_type="temporary")
        graft_branch(str(self.tmp), "TMP-001", "GOAL-001", reason="Test graft")

        source = get_goal(str(self.tmp), "TMP-001")
        history = source.get("graft_history", [])
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["reason"], "Test graft")
        self.assertEqual(history[0]["previous_root_type"], "temporary")

    def test_prune_archives_not_deletes(self):
        from aiwf_core.core.state.goal_tree_ops import get_goal, init_root, prune_branch

        init_root(str(self.tmp), "TMP-001", root_type="temporary", title="Trial")
        result = prune_branch(str(self.tmp), "TMP-001", reason="No longer needed")
        self.assertTrue(result["pruned"])

        # Still exists — archived, not deleted
        branch = get_goal(str(self.tmp), "TMP-001")
        self.assertEqual(branch["status"], "archived")
        self.assertEqual(branch["visibility"], "archived_only")
        self.assertEqual(branch["prune_reason"], "No longer needed")

    def test_prune_cannot_touch_active_main_root(self):
        from aiwf_core.core.state.goal_tree_ops import init_root, prune_branch

        init_root(str(self.tmp), "GOAL-001", root_type="main")
        with self.assertRaises(ValueError):
            prune_branch(str(self.tmp), "GOAL-001")

    def test_prune_removes_from_parent(self):
        from aiwf_core.core.state.goal_tree_ops import add_child_goal, get_goal, init_root, prune_branch

        init_root(str(self.tmp), "GOAL-001", root_type="main")
        add_child_goal(str(self.tmp), "GOAL-001", "GOAL-001-A")
        prune_branch(str(self.tmp), "GOAL-001-A", reason="Obsolete")

        parent = get_goal(str(self.tmp), "GOAL-001")
        self.assertNotIn("GOAL-001-A", parent["child_goal_ids"])

    def test_cli_graft_and_prune(self):
        self._run_ok("goal-tree", "init-root", "GOAL-001", "--type", "main")
        self._run_ok("goal-tree", "init-root", "TMP-001", "--type", "temporary")

        r = self._run_ok("goal-tree", "graft", "TMP-001", "--target", "GOAL-001", "--reason", "adopt")
        self.assertIn("Grafted", r.stdout)

        r = self._run_ok("goal-tree", "prune", "TMP-001", "--reason", "done")
        self.assertIn("Pruned", r.stdout)

    # ── Stage 3.9: graft through interface ──

    def test_graft_interface_fields_recorded(self):
        from aiwf_core.core.state.goal_tree_ops import get_goal, graft_branch, init_root

        init_root(str(self.tmp), "GOAL-ROOT", root_type="main")
        init_root(str(self.tmp), "TMP-001", root_type="temporary")
        result = graft_branch(
            str(self.tmp), "TMP-001", "GOAL-ROOT",
            reason="Trial validated",
            interface_consumed="Goal Tree registry api",
            capability_provided="Temporary Root trial growth",
            relation_to_parent="extends",
            affected_plan_ids=["PLAN-ROOT-STRUCTURE"],
            whether_parent_meaning_changes=False,
        )
        self.assertTrue(result["grafted"])
        self.assertEqual(result["affected_plan_ids"], ["PLAN-ROOT-STRUCTURE"])

        gr = result["graft_record"]
        self.assertEqual(gr["interface_consumed"], "Goal Tree registry api")
        self.assertEqual(gr["capability_provided"], "Temporary Root trial growth")
        self.assertEqual(gr["relation_to_parent"], "extends")
        self.assertEqual(gr["affected_plan_ids"], ["PLAN-ROOT-STRUCTURE"])
        self.assertFalse(gr["whether_parent_meaning_changes"])

        # Source carries graft_interface trace
        source = get_goal(str(self.tmp), "TMP-001")
        gi = source.get("graft_interface", {})
        self.assertEqual(gi.get("consumed"), "Goal Tree registry api")
        self.assertEqual(gi.get("provided"), "Temporary Root trial growth")

    def test_graft_interface_parent_meaning_changes(self):
        from aiwf_core.core.state.goal_tree_ops import get_goal, graft_branch, init_root

        init_root(str(self.tmp), "GOAL-ROOT", root_type="main")
        init_root(str(self.tmp), "TMP-001", root_type="temporary")
        graft_branch(str(self.tmp), "TMP-001", "GOAL-ROOT",
                     reason="Significant shift",
                     whether_parent_meaning_changes=True)

        source = get_goal(str(self.tmp), "TMP-001")
        gi = source.get("graft_interface", {})
        self.assertTrue(gi.get("parent_meaning_changes"))

        history = source.get("graft_history", [])
        self.assertTrue(history[0]["whether_parent_meaning_changes"])

    def test_cli_graft_with_interface_flags(self):
        self._run_ok("goal-tree", "init-root", "GOAL-ROOT", "--type", "main")
        self._run_ok("goal-tree", "init-root", "TMP-001", "--type", "temporary")

        r = self._run_ok("goal-tree", "graft", "TMP-001",
                         "--target", "GOAL-ROOT",
                         "--interface", "recursive Goal Tree registry",
                         "--provides", "Temporary Root trial growth",
                         "--relation-to-parent", "extends",
                         "--affected-plan", "PLAN-ROOT-STRUCTURE",
                         "--reason", "test interface graft")
        self.assertIn("Grafted", r.stdout)
        self.assertIn("Interface consumed: recursive Goal Tree registry", r.stdout)
        self.assertIn("Capability provided: Temporary Root trial growth", r.stdout)
        self.assertIn("Relation to parent: extends", r.stdout)


# ═══════════════════════════════════════════════════════════════════════════
# Stage 3.7: Sibling Relations
# ═══════════════════════════════════════════════════════════════════════════

class TestSiblingRelations(_Base):
    def test_add_relation(self):
        from aiwf_core.core.state.goal_tree_ops import add_relation, get_relations, init_root

        init_root(str(self.tmp), "GOAL-A", root_type="main")
        init_root(str(self.tmp), "GOAL-B", root_type="main")

        result = add_relation(str(self.tmp), "GOAL-A", "GOAL-B", "depends_on", reason="A needs B")
        self.assertTrue(result["added"])

        rels = get_relations(str(self.tmp), "GOAL-A")
        self.assertEqual(len(rels), 1)
        self.assertEqual(rels[0]["type"], "depends_on")

    def test_add_relation_rejects_invalid_type(self):
        from aiwf_core.core.state.goal_tree_ops import add_relation, init_root

        init_root(str(self.tmp), "GOAL-A", root_type="main")
        init_root(str(self.tmp), "GOAL-B", root_type="main")
        with self.assertRaises(ValueError):
            add_relation(str(self.tmp), "GOAL-A", "GOAL-B", "garbage")

    def test_add_relation_rejects_self(self):
        from aiwf_core.core.state.goal_tree_ops import add_relation, init_root

        init_root(str(self.tmp), "GOAL-A", root_type="main")
        with self.assertRaises(ValueError):
            add_relation(str(self.tmp), "GOAL-A", "GOAL-A")

    def test_remove_relation(self):
        from aiwf_core.core.state.goal_tree_ops import add_relation, get_relations, init_root, remove_relation

        init_root(str(self.tmp), "GOAL-A", root_type="main")
        init_root(str(self.tmp), "GOAL-B", root_type="main")
        add_relation(str(self.tmp), "GOAL-A", "GOAL-B", "depends_on")

        result = remove_relation(str(self.tmp), "GOAL-A", "GOAL-B")
        self.assertTrue(result["removed"])
        self.assertEqual(len(get_relations(str(self.tmp), "GOAL-A")), 0)

    def test_relation_does_not_block_activation(self):
        from aiwf_core.core.state.goal_tree_ops import add_relation, init_root
        from aiwf_core.core.state.plan_ops import upsert_plan
        from aiwf_core.core.task_ledger import activate_task, upsert_task

        init_root(str(self.tmp), "GOAL-001", root_type="main")
        init_root(str(self.tmp), "GOAL-002", root_type="main")
        upsert_plan(str(self.tmp), "PLAN-001", goal_id="GOAL-001")

        # Add a depends_on relation — must NOT affect activation
        add_relation(str(self.tmp), "GOAL-001", "GOAL-002", "depends_on")

        upsert_task(str(self.tmp), "TASK-001", "Test", status="ready", plan_id="PLAN-001", goal_id="GOAL-001")
        result = activate_task(str(self.tmp), "TASK-001")
        # Activation may fail for other reasons (no plan markdown, etc.) but NOT due to relations
        blockers_text = " ".join(result.get("blockers", []) or [])
        self.assertNotIn("relation", blockers_text.lower())

    def test_cli_relation_add_remove_show(self):
        self._run_ok("goal-tree", "init-root", "GOAL-A", "--type", "main")
        self._run_ok("goal-tree", "init-root", "GOAL-B", "--type", "main")

        r = self._run_ok("relation", "add", "GOAL-A", "GOAL-B", "depends_on", "--reason", "ordering")
        self.assertIn("depends_on", r.stdout)

        r = self._run_ok("relation", "show", "GOAL-A")
        self.assertIn("GOAL-B", r.stdout)

        r = self._run_ok("relation", "remove", "GOAL-A", "GOAL-B")
        self.assertIn("removed", r.stdout)

    # ── Stage 3.9: relation same-parent enforcement ──

    def test_relation_requires_same_parent(self):
        """Sibling relations default to same-parent; different-parent goals must use --cross."""
        from aiwf_core.core.state.goal_tree_ops import add_child_goal, add_relation, init_root

        # GOAL-ROOT → GOAL-A, GOAL-ROOT → GOAL-B  (same parent)
        init_root(str(self.tmp), "GOAL-ROOT", root_type="main")
        add_child_goal(str(self.tmp), "GOAL-ROOT", "GOAL-A")
        add_child_goal(str(self.tmp), "GOAL-ROOT", "GOAL-B")

        # Same parent — should succeed
        result = add_relation(str(self.tmp), "GOAL-A", "GOAL-B", "depends_on")
        self.assertTrue(result["added"])

    def test_relation_rejects_different_parents(self):
        from aiwf_core.core.state.goal_tree_ops import add_child_goal, add_relation, init_root

        init_root(str(self.tmp), "GOAL-ROOT-1", root_type="main")
        init_root(str(self.tmp), "GOAL-ROOT-2", root_type="main")
        add_child_goal(str(self.tmp), "GOAL-ROOT-1", "GOAL-A")
        add_child_goal(str(self.tmp), "GOAL-ROOT-2", "GOAL-B")

        # Different parents — should fail by default
        with self.assertRaises(ValueError):
            add_relation(str(self.tmp), "GOAL-A", "GOAL-B", "depends_on")

    def test_relation_cross_parent_allowed(self):
        from aiwf_core.core.state.goal_tree_ops import add_child_goal, add_relation, init_root

        init_root(str(self.tmp), "GOAL-ROOT-1", root_type="main")
        init_root(str(self.tmp), "GOAL-ROOT-2", root_type="main")
        add_child_goal(str(self.tmp), "GOAL-ROOT-1", "GOAL-A")
        add_child_goal(str(self.tmp), "GOAL-ROOT-2", "GOAL-B")

        # allow_cross=True — should succeed
        result = add_relation(str(self.tmp), "GOAL-A", "GOAL-B", "depends_on",
                              allow_cross=True)
        self.assertTrue(result["added"])
        self.assertTrue(result["relation"]["cross_parent"])

    def test_cli_relation_add_cross(self):
        self._run_ok("goal-tree", "init-root", "GOAL-ROOT-1", "--type", "main")
        self._run_ok("goal-tree", "init-root", "GOAL-ROOT-2", "--type", "main")
        self._run_ok("goal-tree", "add", "GOAL-A", "--parent", "GOAL-ROOT-1")
        self._run_ok("goal-tree", "add", "GOAL-B", "--parent", "GOAL-ROOT-2")

        # Without --cross should fail
        r = self._run("relation", "add", "GOAL-A", "GOAL-B", "depends_on")
        self.assertNotEqual(r.returncode, 0)

        # With --cross should succeed
        r = self._run_ok("relation", "add", "GOAL-A", "GOAL-B", "depends_on", "--cross")
        self.assertIn("cross-parent", r.stdout)


# ═══════════════════════════════════════════════════════════════════════════
# Stage 3.8: Impact Cone
# ═══════════════════════════════════════════════════════════════════════════

class TestImpactCone(_Base):
    def test_impact_cone_includes_ancestors(self):
        from aiwf_core.core.state.goal_tree_ops import add_child_goal, init_root
        from aiwf_core.core.state.impact_ops import compute_impact_cone

        init_root(str(self.tmp), "GOAL-ROOT", root_type="main")
        add_child_goal(str(self.tmp), "GOAL-ROOT", "GOAL-L1")
        add_child_goal(str(self.tmp), "GOAL-L1", "GOAL-L2")

        result = compute_impact_cone(str(self.tmp), "GOAL-L2")
        self.assertTrue(result["found"])
        self.assertIn("GOAL-L1", result["ancestors"])
        self.assertIn("GOAL-ROOT", result["ancestors"])

    def test_impact_cone_includes_children(self):
        from aiwf_core.core.state.goal_tree_ops import add_child_goal, init_root
        from aiwf_core.core.state.impact_ops import compute_impact_cone

        init_root(str(self.tmp), "GOAL-ROOT", root_type="main")
        add_child_goal(str(self.tmp), "GOAL-ROOT", "GOAL-L1")

        result = compute_impact_cone(str(self.tmp), "GOAL-ROOT")
        child_ids = [c["id"] for c in result["children"]]
        self.assertIn("GOAL-L1", child_ids)

    def test_impact_cone_includes_relations(self):
        from aiwf_core.core.state.goal_tree_ops import add_relation, init_root
        from aiwf_core.core.state.impact_ops import compute_impact_cone

        init_root(str(self.tmp), "GOAL-A", root_type="main")
        init_root(str(self.tmp), "GOAL-B", root_type="main")
        add_relation(str(self.tmp), "GOAL-A", "GOAL-B", "depends_on")

        result = compute_impact_cone(str(self.tmp), "GOAL-A")
        self.assertEqual(len(result["relations"]), 1)
        self.assertEqual(result["relations"][0]["type"], "depends_on")

    def test_impact_cone_readonly(self):
        from aiwf_core.core.state.goal_tree_ops import init_root, load_goal_tree
        from aiwf_core.core.state.impact_ops import compute_impact_cone

        init_root(str(self.tmp), "GOAL-001", root_type="main")

        # Snapshot before
        before = json.dumps(load_goal_tree(str(self.tmp), auto_create=False))
        compute_impact_cone(str(self.tmp), "GOAL-001")
        # Snapshot after — must be identical
        after = json.dumps(load_goal_tree(str(self.tmp), auto_create=False))
        self.assertEqual(before, after, "impact cone must be read-only")

    def test_impact_cone_nonexistent_node(self):
        from aiwf_core.core.state.impact_ops import compute_impact_cone

        result = compute_impact_cone(str(self.tmp), "NONEXISTENT")
        self.assertFalse(result["found"])

    def test_cli_impact_cone(self):
        from aiwf_core.core.state.goal_tree_ops import add_relation, init_root

        init_root(str(self.tmp), "GOAL-001", root_type="main", title="Main Root")
        init_root(str(self.tmp), "GOAL-002", root_type="main", title="Sibling")
        add_relation(str(self.tmp), "GOAL-001", "GOAL-002", "supports", reason="shared")

        r = self._run_ok("goal-tree", "impact", "GOAL-001")
        self.assertIn("Impact Cone for GOAL-001", r.stdout)
        self.assertIn("Ancestors:", r.stdout)
        self.assertIn("GOAL-002", r.stdout)


if __name__ == "__main__":
    unittest.main()
