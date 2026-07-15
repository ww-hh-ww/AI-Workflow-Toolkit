import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATES = ROOT / "aiwf_core" / "embedded_templates"


def read(relative):
    return (TEMPLATES / relative).read_text(encoding="utf-8")


class TestPromptClarityContract(unittest.TestCase):
    def test_planner_keeps_the_full_loop_without_repeating_every_guide(self):
        planner = read("skills/aiwf-planner/SKILL.md")
        lifecycle = read("skills/aiwf-planner/references/lifecycle.md")
        self.assertLess(len(planner.split()), 1200)
        for required in [
            "Discussion is the default",
            "Read the relevant code",
            "aiwf-explorer",
            "references/structure-guide.md",
            "references/writing-guide.md",
            "references/goal-writing.md",
            "references/plan-writing.md",
            "references/task-contract.md",
            "references/milestone-writing.md",
            "references/activation-critique.md",
            "references/lifecycle.md",
            "two real critique passes",
            "Run `aiwf status --prompt` when Planner starts work",
            "Closure Calibration",
            "Add, correct, or delete",
        ]:
            self.assertIn(required, planner)
        for required in [
            "## After A Task",
            "## Close Out A Plan",
            "Compare the actual result",
            "Do not modify a closed Plan",
            "shared files",
            "shared mechanism",
            "implementable, testable, and reviewable",
            "combined proof",
        ]:
            self.assertIn(required, lifecycle)

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

    def test_task_planning_reads_parent_direction_before_writing(self):
        task = " ".join(
            read("skills/aiwf-planner/references/task-contract.md").split()
        )
        for required in [
            "read its owning Goal, parent Plan",
            "completed Task Calibration",
            "capability boundary",
            "technical direction",
            "correct the planning first",
        ]:
            self.assertIn(required, task)

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
            "--adversarial-observations",
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
        self.assertIn("one project-writing Executor at a time", implement)
        self.assertIn("one Tester to own the final tested snapshot", testing)
        self.assertIn("Do not run it in parallel with Executor or Tester", review)

    def test_dispatch_uses_task_baseline_and_only_explicit_user_delta(self):
        planner = read("skills/aiwf-planner/SKILL.md")
        lifecycle = read("skills/aiwf-planner/references/lifecycle.md")
        role_skills = [
            read("skills/aiwf-implement/SKILL.md"),
            read("skills/aiwf-test/SKILL.md"),
            read("skills/aiwf-review/SKILL.md"),
        ]
        agents = [
            read("agents/aiwf-executor.md"),
            read("agents/aiwf-tester.md"),
            read("agents/aiwf-reviewer.md"),
        ]

        lifecycle_words = " ".join(lifecycle.split())
        self.assertIn("references/lifecycle.md", planner)
        self.assertIn("Executor, Tester, and Reviewer", lifecycle_words)
        self.assertIn("Explorer, Architect, and Critic use their own prompts", lifecycle_words)
        self.assertIn("Task.md is the baseline", lifecycle_words)
        self.assertIn("Add `USER_DELTA` only", lifecycle_words)
        self.assertIn("Pass it faithfully", lifecycle_words)
        self.assertIn("Do not add a Planner fallback", lifecycle_words)
        for source in role_skills:
            self.assertIn("USER_DELTA", source)
            self.assertIn("Planner-created fallbacks", source)
            self.assertNotIn("verified fact not yet", source)
            self.assertNotIn("fresh facts not yet", source)
        for source in agents:
            self.assertIn("Other dispatch wording does", source)
            self.assertIn("not change the contract", source)

        executor = agents[0]
        self.assertIn("requires a named skill or tool", executor)
        self.assertIn("do not imitate its output", executor)

    def test_workflow_agents_reuse_the_bound_plan_worktree(self):
        lifecycle = read("skills/aiwf-planner/references/lifecycle.md")
        planner = read("skills/aiwf-planner/SKILL.md")
        self.assertIn("aiwf plan bind-worktree <PLAN-ID> --create", planner)
        self.assertIn("Every Plan worktree is a peer", lifecycle)
        self.assertIn("The command is idempotent", lifecycle)
        self.assertIn("Set its `cwd` to that worktree", lifecycle)
        self.assertIn("Task roles share the Plan worktree", lifecycle)
        for path in (
            "agents/aiwf-executor.md",
            "agents/aiwf-tester.md",
            "agents/aiwf-reviewer.md",
        ):
            agent = read(path)
            self.assertIn("Verify that the current Git worktree is the assigned path", agent)
            self.assertIn("Do not call `EnterWorktree` from this", agent)
            self.assertNotIn("Call `EnterWorktree", agent)
        for path in ("agents/aiwf-executor.md", "agents/aiwf-tester.md"):
            agent = read(path)
            self.assertIn("Never copy or sync Task changes", agent)

    def test_activation_checks_only_explicit_capability_dependencies(self):
        critique = read("skills/aiwf-planner/references/activation-critique.md")
        structure = read("skills/aiwf-planner/references/structure-guide.md")
        critique_words = " ".join(critique.split())

        self.assertIn("explicitly requires a named Skill, MCP, or tool", critique_words)
        self.assertIn("assigned role can use it", critique_words)
        self.assertIn("Do not try to predict every possible runtime failure", critique_words)
        self.assertIn("Executor must return", critique_words)
        self.assertNotIn("Task Activation Readiness", structure)
        self.assertIn(
            "aiwf record disposition",
            read("skills/aiwf-planner/references/lifecycle.md"),
        )

    def test_testing_skill_uses_the_real_public_commands(self):
        testing = read("skills/aiwf-test/SKILL.md")
        self.assertIn("Do not run `aiwf task test`", testing)
        self.assertIn("`aiwf record testing`", testing)

    def test_optional_agents_keep_the_full_inline_record_chain(self):
        implement = read("skills/aiwf-implement/SKILL.md")
        test = read("skills/aiwf-test/SKILL.md")
        review = read("skills/aiwf-review/SKILL.md")
        inline = read("shared/inline-execution.md")

        self.assertIn("`executor_required` is false, do not dispatch Executor", implement)
        self.assertIn("`tester_required` is false, do not dispatch Tester", test)
        self.assertIn("`reviewer_required` is false, do not dispatch Reviewer", review)
        for command in (
            "record implementation --task-id <TASK-ID>",
            "record testing --task-id <TASK-ID>",
            "record review --task-id <TASK-ID>",
        ):
            self.assertIn(command, inline)

    def test_critic_is_manual_and_does_not_join_the_workflow(self):
        skill = read("skills/aiwf-critic/SKILL.md")
        agent = read("agents/aiwf-critic.md")
        self.assertIn("Critic is manual", skill)
        self.assertIn("does not join the normal workflow", skill)
        self.assertIn("Do not manufacture objections", agent)
        self.assertIn("project reality", agent)


if __name__ == "__main__":
    unittest.main()
