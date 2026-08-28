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
        self.assertIn("Do not request an Experiment merely to postpone work", skill)

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

    def test_experimenter_records_but_does_not_dispose_or_promote(self):
        agent = read("agents/aiwf-experimenter.md")
        self.assertIn("at least one concrete `--observation`", agent)
        self.assertIn("do not make more project changes", agent)
        self.assertIn("Do not\nrun `aiwf experiment finish`", agent)
        self.assertIn("Never copy or\nsync them into the stable", agent)

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
