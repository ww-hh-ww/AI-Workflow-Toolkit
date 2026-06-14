"""Node Contract documentation locks for Rooted Functional Tree Stage 3.0."""
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class TestNodeContractDocs(unittest.TestCase):
    def setUp(self):
        self.node = (PROJECT_ROOT / "docs" / "NODE_CONTRACT.md").read_text(encoding="utf-8")
        self.axioms = (PROJECT_ROOT / "docs" / "AIWF_DESIGN_AXIOMS.md").read_text(encoding="utf-8")
        self.migration = (PROJECT_ROOT / "docs" / "TREE_FOUNDATION_MIGRATION.md").read_text(encoding="utf-8")

    # ── existence ──

    def test_all_three_design_docs_exist(self):
        self.assertTrue((PROJECT_ROOT / "docs" / "NODE_CONTRACT.md").exists())
        self.assertTrue((PROJECT_ROOT / "docs" / "AIWF_DESIGN_AXIOMS.md").exists())
        self.assertTrue((PROJECT_ROOT / "docs" / "TREE_FOUNDATION_MIGRATION.md").exists())

    # ── rooted functional tree model ──

    def test_rooted_functional_tree_model(self):
        self.assertIn("Rooted Functional Tree with Procedural Scaffolds", self.node)
        self.assertIn("recursive Goal tree", self.node)
        self.assertIn("single tree chain", self.node)

    def test_not_fixed_five_layer_chain(self):
        self.assertNotIn("five AIWF semantic layers", self.node)
        self.assertNotIn("Mission → Goal → Milestone → Plan → Task", self.node)

    # ── plan as scaffold ──

    def test_plan_is_procedural_scaffold(self):
        self.assertIn("plan_kind", self.node)
        self.assertIn("structural", self.node)
        self.assertIn("implementation", self.node)
        self.assertIn("procedural scaffold", self.axioms)
        self.assertIn("A Plan is not the skeleton", self.axioms)

    def test_plan_kinds_in_contract(self):
        self.assertIn("`structural`", self.node)
        self.assertIn("`implementation`", self.node)
        self.assertIn("target_goal_id", self.node)
        self.assertIn("active_phase", self.node)
        self.assertIn("`framing`", self.node)
        self.assertIn("`integration`", self.node)
        self.assertIn("`seal`", self.node)

    def test_plan_phase_loading_in_contract(self):
        self.assertIn("phase-loadable procedural scaffold", self.node)
        self.assertIn("phase-loadable procedural scaffold", self.axioms)
        self.assertIn("Plan Phase Loading", self.axioms)

    def test_prompt_discipline_phase_loading(self):
        self.assertIn("Default prompts must not include the full high-level Plan", self.node)

    # ── milestone as structural convergence ──

    def test_milestone_is_convergence_not_layer(self):
        self.assertIn("structural convergence node", self.node)
        self.assertIn("covered_goal_ids", self.node)
        self.assertIn("convergence_meaning", self.node)

    def test_milestone_is_not_time_checkpoint_or_fixed_layer(self):
        self.assertIn("time checkpoint", self.node.lower())
        self.assertIn("NOT a fixed layer", self.node)

    def test_milestone_has_legacy_and_new_fields(self):
        self.assertIn("scope_type", self.node)
        self.assertIn("scope_refs", self.node)
        self.assertIn("stability_claim", self.node)
        self.assertIn("downstream_dependency", self.node)
        # Legacy fields preserved
        self.assertIn("goal_id", self.node)
        self.assertIn("stage_synthesis", self.node)

    # ── sibling relations replace graph links ──

    def test_sibling_relations_not_graph_links(self):
        self.assertIn("Sibling relation", self.node)
        self.assertIn("depends_on", self.node)
        self.assertIn("blocks", self.node)
        self.assertIn("conflicts_with", self.node)
        self.assertIn("invalidates", self.node)
        self.assertIn("supports", self.node)

    def test_relations_are_advisory_only(self):
        self.assertIn("`depends_on` in relations is advisory", self.node)
        self.assertIn("Goal relations never block Plan or Task activation", self.node)
        self.assertIn("`plan.dependencies[]` blocks activation", self.node)
        self.assertIn("`task.dependencies[]` independently controls", self.node)

    def test_no_graph_engine(self):
        self.assertIn("No graph engine", self.node)

    # ── impact cone replaces weights ──

    def test_impact_cone_replaces_weights(self):
        self.assertIn("Impact Cone", self.node)
        self.assertIn("replaces abstract weight", self.node)
        self.assertNotIn("attention", self.node.split("## 2. Unified Node Schema")[1].split("##")[0].lower())

    # ── temporary roots / graft / prune ──

    def test_temporary_roots_present(self):
        self.assertIn("Temporary Root", self.node)
        self.assertIn("graft", self.node.lower())
        self.assertIn("prune", self.node.lower())
        self.assertIn("Temporary Roots", self.axioms)

    # ── registry authority ──

    def test_plan_registry_authority(self):
        self.assertIn("plans.json` is the sole machine authority", self.node)
        self.assertIn("Do NOT auto-migrate legacy", self.node)

    def test_legacy_goal_id_mapping(self):
        self.assertIn("GOAL-001", self.node)
        self.assertIn("legacy node id `GOAL-001`", self.node)

    def test_legacy_markdown_blocks_activation(self):
        self.assertIn("remediation message", self.node)

    # ── mission is project-level singleton node ──

    def test_mission_is_project_level_singleton(self):
        self.assertIn("project-level singleton", self.node.lower())
        self.assertIn("hidden_from_prompt", self.node)

    def test_mission_not_a_regular_goal_child(self):
        self.assertIn("NOT a regular Goal Tree child", self.node)

    # ── evidence rollup ──

    def test_evidence_must_roll_upward(self):
        self.assertIn("Evidence must roll upward", self.axioms)
        self.assertIn("Task must never directly complete a Goal", self.node)

    # ── anti-goals ──

    def test_anti_goals_present(self):
        for phrase in [
            "No graph engine",
            "No abstract weights",
            "No multi-agent parallel scheduling",
            "No context pack auto-generation",
            "No UI",
            "No fixed five-layer chain",
            "No forced milestone for L0/L1",
            "No Task→Goal direct completion",
            "No Mission or full Milestone expansion in `status --prompt`",
        ]:
            self.assertIn(phrase, self.node, f"missing anti-goal: {phrase}")

    def test_axioms_anti_goals_present(self):
        for phrase in [
            "Turn Goal Tree into a heavyweight project management tree",
            "Require a perfect tree before execution",
            "Force exploratory work into the main root too early",
            "Treat Plan as the main skeleton",
            "Treat child order as dependency",
            "Add abstract weights when structural impact is enough",
            "Build a graph engine before sibling relations prove insufficient",
            "Let status --prompt expand with full tree details",
            "Let unowned patches enter stable structure",
            "Let Task completion directly imply Goal completion",
            "Let a Plan silently redefine its Goal",
            "Let Milestone become a mechanical checklist",
        ]:
            self.assertIn(phrase, self.axioms, f"missing anti-goal: {phrase}")

    # ── migration doc gates ──

    def test_migration_doc_stage_dependencies(self):
        self.assertIn("Stage 3.0", self.migration)
        self.assertIn("Stage 3.1", self.migration)
        self.assertIn("Goal Tree Registry", self.migration)
        self.assertIn("goals.json", self.migration)

    def test_migration_implementation_status(self):
        self.assertIn("Stage 3.0–3.9 complete", self.migration)
        self.assertIn("Stage 4.0–4.6", self.migration)

    # ── status display boundaries ──

    def test_status_prompt_budget(self):
        self.assertIn("~200-800 characters", self.node)

    def test_mission_never_in_prompt(self):
        self.assertIn("Does NOT appear in `status --prompt`", self.node)

    # ── change admission rule ──

    def test_change_admission_rule_present(self):
        self.assertIn("Change Admission Rule", self.node)
        self.assertIn("Change Admission Rule", self.axioms)
        self.assertIn("Plan Attachment", self.node)
        self.assertIn("Goal Graft", self.node)
        self.assertIn("Temporary Root", self.node)

    def test_change_admission_no_orphans(self):
        self.assertIn("No orphan patch", self.node)
        self.assertIn("No silent Goal mutation", self.node)
        self.assertIn("No Plan that secretly redefines its Goal", self.node)
        self.assertIn("No new Goal without an interface", self.node)

    def test_change_admission_two_paths(self):
        self.assertIn("Function skeleton unchanged", self.node)
        self.assertIn("Function skeleton changed", self.node)
        self.assertIn("Ownership unclear", self.node)

    def test_patch_policy_is_consequence(self):
        self.assertIn("Do not reject patches", self.axioms)
        self.assertIn("Reject orphan patches", self.axioms)

    # ── bidirectional planning ──

    def test_bidirectional_planning(self):
        self.assertIn("Top-down decomposition", self.axioms)
        self.assertIn("Bottom-up realization", self.axioms)
        self.assertIn("bidirectional", self.axioms.lower())

    # ── Stage 4.7.2: five core nodes ──

    def test_five_core_node_types_in_contract(self):
        for node_type in ["Mission", "Goal", "Milestone", "Plan", "Task"]:
            self.assertIn(node_type, self.node,
                          f"Core node type '{node_type}' should be in node contract")

    def test_mission_listed_in_type_enum(self):
        self.assertIn("`mission`", self.node)

    def test_evidence_not_a_core_node(self):
        self.assertIn("Evidence is lightweight", self.axioms)
        self.assertIn("not a core", self.node.lower())
        self.assertIn("governance node", self.node.lower())

    def test_evidence_is_not_a_node_type(self):
        self.assertIn("NOT a node type", self.node)

    # ── Stage 4.7.2: truth source contract ──

    def test_truth_source_contract_present(self):
        self.assertIn("Truth Source Contract", self.node)
        self.assertIn("object truth", self.node.lower())
        self.assertIn("relationship truth", self.node.lower())

    def test_no_tree_json_source_of_truth(self):
        self.assertIn("Do NOT introduce a single `tree.json`", self.node)
        self.assertIn("Do NOT duplicate", self.node)

    def test_registries_own_objects_tree_owns_relationships(self):
        self.assertIn("goals.json", self.node)
        self.assertIn("plans.json", self.node)

    def test_axioms_has_five_node_statement(self):
        self.assertIn("Mission / Goal / Milestone / Plan / Task", self.axioms)

    def test_axioms_evidence_is_lightweight(self):
        self.assertIn("lightweight proof material", self.axioms.lower())
        self.assertIn("not a core governance node", self.axioms.lower())

    def test_axioms_milestone_is_convergence_not_seal(self):
        self.assertIn("structural convergence node", self.axioms.lower())
        self.assertIn("optional structural convergence", self.axioms)


if __name__ == "__main__":
    unittest.main()
