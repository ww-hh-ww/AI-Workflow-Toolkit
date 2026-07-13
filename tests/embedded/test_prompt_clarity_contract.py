import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATES = ROOT / "aiwf_core" / "embedded_templates"


def read(relative):
    return (TEMPLATES / relative).read_text(encoding="utf-8")


class TestPromptClarityContract(unittest.TestCase):
    def test_planner_keeps_the_full_loop_without_repeating_every_guide(self):
        planner = read("skills/aiwf-planner/SKILL.md")
        self.assertLess(len(planner.split()), 1400)
        for required in [
            "Discussion is the default",
            "Read the relevant code",
            "aiwf-explorer",
            "references/goal-writing.md",
            "references/plan-writing.md",
            "references/task-contract.md",
            "references/milestone-writing.md",
            "two real critique passes",
            "Run `aiwf status --prompt` before acting",
            "Closure Calibration",
            "Add, correct, or delete",
            "#### After a Task",
            "#### Close Out a Plan",
            "Compare the actual result",
            "Do not modify a closed Plan",
        ]:
            self.assertIn(required, planner)

    def test_planner_and_guides_preserve_design_and_consistency_judgment(self):
        combined = "\n".join([
            read("skills/aiwf-planner/SKILL.md"),
            read("skills/aiwf-planner/references/plan-writing.md"),
            read("skills/aiwf-planner/references/task-contract.md"),
        ])
        for required in [
            "source-backed basis",
            "credible alternatives",
            "Consistency Contract",
            "shared truth",
            "consumer",
            "old path",
            "Built",
            "Wired",
            "Running",
            "expected observable",
            "independent roles",
        ]:
            self.assertIn(required, combined)

    def test_planning_separates_capabilities_from_code_architecture(self):
        planner = read("skills/aiwf-planner/SKILL.md")
        goal = read("skills/aiwf-planner/references/goal-writing.md")
        plan = read("skills/aiwf-planner/references/plan-writing.md")
        critique = read("skills/aiwf-planner/references/activation-critique.md")
        executor = read("agents/aiwf-executor.md")
        reviewer = read("agents/aiwf-reviewer.md")

        plan_text = " ".join(plan.split())
        critique_text = " ".join(critique.split())
        executor_text = " ".join(executor.split())
        reviewer_text = " ".join(reviewer.split())

        self.assertIn("Goal tree describes capabilities, not code modules", planner)
        self.assertIn("short, low-risk", planner)
        self.assertIn("conditions that can change the architecture", goal)
        for required in [
            "Do not mirror the Goal tree in code",
            "data and state each part owns",
            "dependency direction",
            "failure ownership",
            "real condition, expected response or threshold",
        ]:
            self.assertIn(required, plan_text)
        self.assertIn("module boundaries follow ownership", critique_text)
        self.assertIn("Do not create modules that mirror Goal or Task names", executor_text)
        self.assertIn("likely-to-change decisions have clear boundaries", reviewer_text)

    def test_md_guides_require_decisions_without_required_forms(self):
        guides = "\n".join([
            read("skills/aiwf-planner/references/goal-writing.md"),
            read("skills/aiwf-planner/references/plan-writing.md"),
            read("skills/aiwf-planner/references/task-contract.md"),
            read("skills/aiwf-planner/references/milestone-writing.md"),
        ])
        self.assertNotIn("Required Form", guides)
        self.assertNotIn("None — reason:", guides)
        self.assertIn("Omit empty optional sections", guides)
        for required in [
            "Mission Capability",
            "Target Mechanism",
            "Contract Responsibility",
            "Pass Standard",
            "Real Verification",
        ]:
            self.assertIn(required, guides)

    def test_generated_docs_are_small_starting_contracts_not_blank_forms(self):
        source = (ROOT / "aiwf_core" / "core" / "index_ops.py").read_text(encoding="utf-8")
        for required in [
            "## Mission Capability",
            "## Target Mechanism",
            "## Fixed Contract",
            "## Known Context",
            "## Open Judgment",
            "## Pass Standard",
            "## Real Verification",
        ]:
            self.assertIn(required, source)
        self.assertNotIn("None — reason:", source)
        self.assertNotIn("### Consistency Contract", source)

    def test_architect_common_prompt_routes_only_selected_lenses(self):
        skill = read("skills/aiwf-architect/SKILL.md")
        agent = read("agents/aiwf-architect.md")
        self.assertLess(len(agent.split()), 700)
        self.assertIn("Read only the references selected for this run", agent)
        self.assertIn("Do not carry other lenses into a split review", agent)
        self.assertIn("unique directory", skill)
        self.assertIn("Do not turn findings into Tasks", skill)

    def test_architect_references_preserve_all_review_capabilities(self):
        combined = "\n".join([
            read("skills/aiwf-architect/references/design-review.md"),
            read("skills/aiwf-architect/references/code-review.md"),
            read("skills/aiwf-architect/references/structure-review.md"),
            read("skills/aiwf-architect/references/milestone-acceptance.md"),
        ])
        normalized = " ".join(combined.split())
        for required in [
            "Mission Fit",
            "Mission Leverage",
            "Capability Gaps",
            "WebSearch",
            "zero-caller",
            "old path",
            "Goal tree",
            "Goal, Plan, Task, Milestone",
            "Pass Standard",
            "aiwf milestone integration-test",
            "aiwf milestone arch-review",
            "explicit human approval",
        ]:
            self.assertIn(required, normalized)

    def test_executor_tester_reviewer_keep_independent_judgment_and_handoff(self):
        executor = read("agents/aiwf-executor.md")
        tester = read("agents/aiwf-tester.md")
        reviewer = read("agents/aiwf-reviewer.md")
        reviewer_text = " ".join(reviewer.split())
        for required in [
            "follow the real main path",
            "Trace before editing",
            "RETURN_TO_PLANNER:",
            "aiwf record implementation",
        ]:
            self.assertIn(required, executor)
        for required in [
            "Build a failure model",
            "false pass",
            "EXTERNAL_FINDING:",
            "expected observable, actual result",
        ]:
            self.assertIn(required, tester)
        for required in [
            "complete story holds",
            "Trace callers and consumers",
            "REVIEW_REPORT",
            "what Executor actually changed",
            "what Tester ran and proved",
            "assumptions used by remaining Tasks",
        ]:
            self.assertIn(required, reviewer_text)

    def test_role_skills_dispatch_without_recopying_the_task_packet(self):
        implement = read("skills/aiwf-implement/SKILL.md")
        testing = read("skills/aiwf-test/SKILL.md")
        review = read("skills/aiwf-review/SKILL.md")
        self.assertIn("do not recopy the whole contract", " ".join(implement.split()))
        self.assertIn("Do not paste the Task Packet", testing)
        self.assertIn("Do not paste the complete Task Packet", review)
        self.assertIn("The report must tell Planner what Executor changed", review)

    def test_critic_is_manual_and_does_not_join_the_workflow(self):
        skill = read("skills/aiwf-critic/SKILL.md")
        agent = read("agents/aiwf-critic.md")
        self.assertIn("Critic is manual", skill)
        self.assertIn("does not join the normal workflow", skill)
        self.assertIn("Do not manufacture objections", agent)
        self.assertIn("project reality", agent)


if __name__ == "__main__":
    unittest.main()
