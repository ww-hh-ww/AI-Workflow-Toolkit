"""Claude agent wrappers must not weaken shared AIWF workflow contracts."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _install(cwd, target):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    result = subprocess.run(
        [sys.executable, "-m", "aiwf_core.cli", "install", target, "--force"],
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
        timeout=20,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr or result.stdout)


class TestAgentWrapperAlignment(unittest.TestCase):
    """Thin Claude agents must reinforce, not narrow, shared Skill contracts."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="aw_agent_align_"))
        _install(cls.tmp, "claude")
        _install(cls.tmp, "reasonix")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _claude_agent(self, name):
        return (self.tmp / ".claude" / "agents" / f"{name}.md").read_text()

    def _claude_skill(self, name):
        return (self.tmp / ".claude" / "skills" / name / "SKILL.md").read_text()

    def _reasonix_skill(self, name):
        return (self.tmp / ".reasonix" / "skills" / name / "SKILL.md").read_text()

    def test_executor_agent_mentions_architecture_contract_not_only_allowed_write(self):
        content = self._claude_agent("aiwf-executor")
        for required in [
            "architecture_brief",
            "protected_files",
            "forbidden_restructures",
            "aiwf arch-change request",
            "Do not hand-edit",
        ]:
            self.assertIn(required, content)

    def test_reviewer_agent_mentions_cleanup_depth_and_evidence_disposition(self):
        content = self._claude_agent("aiwf-reviewer")
        for required in [
            "cleanup_verified_at",
            "review_template",
            "unit tests alone are not enough",
            "accepted-evidence-id",
            "rejected-evidence-id",
            "adversarial observations",
            "system integration evidence",
        ]:
            self.assertIn(required, content)

    def test_reviewer_agent_is_evidence_first_not_default_full_rerun(self):
        content = self._claude_agent("aiwf-reviewer")
        for required in [
            "Evidence-first",
            "audit testing evidence before rerunning",
            "spot-checks",
            "missing, stale, contradictory",
            "rerun",
        ]:
            self.assertIn(required, content)

    def test_curator_agent_is_advisory_and_bound_by_lesson_admission(self):
        content = self._claude_agent("aiwf-curator")
        self.assertIn("advisory", content.lower())
        self.assertIn("Do not directly edit", content)
        self.assertIn("LESSON-ADMISSION-POLICY", content)
        self.assertIn("applies_to", content)
        self.assertIn("expires_when", content)

    def test_tester_agent_keeps_full_and_real_usage_obligations(self):
        content = self._claude_agent("aiwf-tester")
        for required in [
            "validation layers",
            "full_regression",
            "real_usage",
            "Never silently skip",
        ]:
            self.assertIn(required, content)

    def test_reasonix_uses_shared_skills_without_duplicate_thin_agents(self):
        self.assertFalse((self.tmp / ".reasonix" / "agents" / "aiwf-executor.md").exists())
        self.assertFalse((self.tmp / ".reasonix" / "agents" / "aiwf-reviewer.md").exists())
        for skill_name, required in {
            "aiwf-implement": ["architecture_brief", "forbidden_restructures", "aiwf arch-change request"],
            "aiwf-test": ["Validation Layers", "full_regression", "real_usage"],
            "aiwf-review": [
                "cleanup_verified_at",
                "review_template",
                "accepted-evidence-id",
                "Evidence-First Testing Boundary",
                "do not default to rerunning the Tester full suite",
            ],
        }.items():
            content = self._reasonix_skill(skill_name)
            for needle in required:
                self.assertIn(needle, content)

    def test_role_skills_forbid_planner_roleplay(self):
        for skill_name, role in {
            "aiwf-implement": "executor",
            "aiwf-test": "tester",
            "aiwf-review": "reviewer",
        }.items():
            content = self._claude_skill(skill_name)
            self.assertIn("STOP", content)
            self.assertIn("DISPATCH GATE", content)
            self.assertIn("planner-main", content.lower())
            self.assertIn(role, content.lower())

            reasonix_content = self._reasonix_skill(skill_name)
            self.assertIn("STOP", reasonix_content)
            self.assertIn("planner-main", reasonix_content.lower())

    def test_claude_agents_declare_separate_subagent_role(self):
        for agent_name, role in {
            "aiwf-executor": "Executor",
            "aiwf-tester": "Tester",
            "aiwf-reviewer": "Reviewer",
        }.items():
            content = self._claude_agent(agent_name)
            self.assertIn(f"separate AIWF {role} subagent role", content)
            self.assertIn("not planner-main roleplaying", content)

    def test_claude_agents_do_not_conflict_with_shared_skills(self):
        executor_agent = self._claude_agent("aiwf-executor")
        executor_skill = self._claude_skill("aiwf-implement")
        for shared_boundary in ["architecture_brief", "forbidden_restructures", "allowed_write"]:
            self.assertIn(shared_boundary, executor_agent)
            self.assertIn(shared_boundary, executor_skill)

        reviewer_agent = self._claude_agent("aiwf-reviewer")
        reviewer_skill = self._claude_skill("aiwf-review")
        for shared_gate in [
            "cleanup_verified_at",
            "review_template",
            "accepted-evidence-id",
            "do not default to rerunning the Tester full suite",
        ]:
            self.assertIn(shared_gate, reviewer_skill)


if __name__ == "__main__":
    unittest.main()
