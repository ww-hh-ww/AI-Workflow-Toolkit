import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2] / "aiwf_core" / "embedded_templates"


def read(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


class TestPromptClarityContract(unittest.TestCase):
    def test_three_roles_have_distinct_authority(self):
        executor = read("agents/aiwf-executor.md")
        experimenter = read("agents/aiwf-experimenter.md")
        reviewer = read("agents/aiwf-reviewer.md")

        self.assertIn("You change stable reality", executor)
        self.assertIn("every Task V-*", executor)
        self.assertIn("You learn about reality", experimenter)
        self.assertIn("disposable worktree", experimenter)
        self.assertIn("You judge stable reality", reviewer)
        self.assertIn("needs_experiment", reviewer)

    def test_experiment_is_orthogonal_not_a_phase(self):
        runtime = read("CLAUDE.md")
        task_contract = read("skills/aiwf-planner/references/task-contract.md")
        lifecycle = read("skills/aiwf-planner/references/lifecycle.md")

        self.assertIn("capabilities,\n  not a fixed three-stage pipeline", runtime)
        self.assertIn("no requirement boolean because it is orthogonal", task_contract)
        self.assertIn("before Executor, after Executor, both, or not at all", task_contract)
        self.assertIn("pre-implementation unknown", lifecycle)
        self.assertIn("post-implementation empirical unknown", lifecycle)

    def test_executor_skill_owns_construction_evidence(self):
        skill = read("skills/aiwf-implement/SKILL.md")
        self.assertIn("V-* is\nExecutor-owned construction evidence", skill)
        self.assertIn("--check V-001", skill)
        self.assertIn("--verdict matched", skill)
        self.assertIn("Do not move work Executor can resolve", skill)

    def test_main_session_owns_task_dispatch_decisions(self):
        runtime = read("CLAUDE.md")
        executor = read("agents/aiwf-executor.md")
        implement = read("skills/aiwf-implement/SKILL.md")
        task_contract = read("skills/aiwf-planner/references/task-contract.md")
        lifecycle = read("skills/aiwf-planner/references/lifecycle.md")

        self.assertIn("stable main session evaluates", runtime)
        self.assertIn("child role never chooses or starts its successor", runtime)
        self.assertIn("Do not open an Experiment", executor)
        self.assertIn("Do not turn those facts into a\nrole-dispatch instruction", executor)
        self.assertIn("never ask Executor to make that routing decision", implement)
        self.assertIn("Executor -> Experimenter -> Reviewer", task_contract)
        self.assertIn("stable main session owns dispatch", lifecycle)

    def test_experiment_skill_exposes_full_ref_lifecycle(self):
        skill = read("skills/aiwf-experiment/SKILL.md")
        for command in (
            "aiwf experiment open EXP-001",
            "aiwf experiment start EXP-001",
            "aiwf experiment record EXP-001",
            "aiwf experiment finish EXP-001",
        ):
            self.assertIn(command, skill)
        self.assertIn("immutable subject commit", skill)
        self.assertIn("does not move files into stable reality", skill)

    def test_reviewer_verdicts_separate_defect_from_unknown(self):
        skill = read("skills/aiwf-review/SKILL.md")
        self.assertIn("`needs_change`: a concrete repairable defect", skill)
        self.assertIn("`needs_experiment`: acceptance depends on one important empirical fact", skill)
        self.assertIn("Do not use `needs_experiment` for a missing V-* result", skill)
        self.assertIn("`rejected`", skill)

    def test_reviewer_explicitly_owns_complete_story_assertion(self):
        skill = read("skills/aiwf-review/SKILL.md")
        agent = read("agents/aiwf-reviewer.md")

        for text in (skill, agent):
            self.assertIn("--story-complete", text)
            self.assertIn("whole", text)
        self.assertIn("not a main-session or Planner judgment", skill)
        self.assertIn("Never add it\nmerely to pass the close gate", skill)

    def test_codex_freshness_packet_delegates_only_mechanical_read(self):
        skill = read("skills/aiwf-review/SKILL.md")
        agent = read("agents/aiwf-reviewer.md")

        for text in (skill, agent):
            self.assertIn("On Codex only", text)
            self.assertIn("exact current `implementation_ref`", text)
            self.assertIn("equal non-empty", text)
            self.assertIn("`implementation_tree`", text)
            self.assertIn("`candidate_tree`", text)
            self.assertIn("bare `unavailable`", text)
        self.assertIn("Reviewer still owns the complete-story judgment", skill)

    def test_experimenter_records_but_does_not_dispose_or_promote(self):
        agent = read("agents/aiwf-experimenter.md")
        self.assertIn("at least one concrete `--observation`", agent)
        self.assertIn("do not make more project changes", agent)
        self.assertIn("Do not\nrun `aiwf experiment finish`", agent)
        self.assertIn("Never copy or\nsync them into the stable", agent)

    def test_each_independent_role_has_its_proof_and_terminal_command(self):
        executor = read("agents/aiwf-executor.md")
        experimenter = read("agents/aiwf-experimenter.md")
        reviewer = read("agents/aiwf-reviewer.md")
        review_skill = read("skills/aiwf-review/SKILL.md")

        self.assertIn("aiwf task proof <TASK-ID>", executor)
        self.assertIn("aiwf record implementation --task-id <TASK-ID>", executor)
        self.assertIn("aiwf experiment show <EXP-ID>", experimenter)
        self.assertIn("aiwf experiment record <EXP-ID>", experimenter)
        self.assertIn("aiwf task proof <TASK-ID>", reviewer)
        self.assertIn("aiwf record review --task-id <TASK-ID>", reviewer)
        self.assertIn("After Reviewer returns", review_skill)
        self.assertIn("aiwf status --prompt", review_skill)

    def test_experiment_skill_uses_state_instead_of_reopening_review_request(self):
        skill = read("skills/aiwf-experiment/SKILL.md")
        self.assertIn("needs_experiment` already creates an `open`", skill)
        self.assertIn("Do not run `open` again", skill)
        self.assertIn("experiment disposition <EXP-ID>", skill)
        self.assertIn("Post-implementation evidence needs no extra Planner disposition", skill)

    def test_roles_use_tree_binding_not_head_equality_for_hidden_snapshots(self):
        executor = read("agents/aiwf-executor.md")
        experimenter = read("agents/aiwf-experimenter.md")
        reviewer = read("agents/aiwf-reviewer.md")
        implement_skill = read("skills/aiwf-implement/SKILL.md")
        review_skill = read("skills/aiwf-review/SKILL.md")
        experiment_skill = read("skills/aiwf-experiment/SKILL.md")

        for text in (executor, experimenter, reviewer, implement_skill, review_skill, experiment_skill):
            self.assertIn("snapshot", text)
            self.assertIn("HEAD", text)
        self.assertIn("candidate_tree_status=matched", executor)
        self.assertIn("candidate_tree_status=matched", reviewer)
        self.assertIn("candidate_tree_status=matched", experiment_skill)
        self.assertIn("never move HEAD", review_skill)

    def test_removed_role_has_no_instruction_surface(self):
        surfaces = [
            read("CLAUDE.md"),
            read("skills/aiwf-implement/SKILL.md"),
            read("skills/aiwf-experiment/SKILL.md"),
            read("skills/aiwf-review/SKILL.md"),
            read("agents/aiwf-executor.md"),
            read("agents/aiwf-experimenter.md"),
            read("agents/aiwf-reviewer.md"),
            read("skills/aiwf-planner/references/task-contract.md"),
            read("skills/aiwf-planner/references/lifecycle.md"),
        ]
        retired = ("aiwf-tester", "aiwf-test", "record testing", "tester_required", "tested_ref")
        for text in surfaces:
            for token in retired:
                self.assertNotIn(token, text)


if __name__ == "__main__":
    unittest.main()
