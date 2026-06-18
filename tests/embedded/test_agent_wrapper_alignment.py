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
            "Do not modify the active Task.md",
            "Do not write outside Task.md scope",
            "Do not change Done When",
            "Do not modify `.aiwf/state/` or `.aiwf/records/`",
            "Allowed",
            "Forbidden",
        ]:
            self.assertIn(required, content)

    def test_reviewer_agent_mentions_cleanup_depth_and_evidence_disposition(self):
        content = self._claude_agent("aiwf-reviewer")
        for required in [
            "--result accepted",
            "Done When",
            "Forbidden Write",
            "Do not modify `.aiwf/state/` or `.aiwf/records/`",
            "Do not modify code",
            "Contract compliance",
            "Evidence integrity",
        ]:
            self.assertIn(required, content)

    def test_reviewer_agent_is_evidence_first_not_default_full_rerun(self):
        content = self._claude_agent("aiwf-reviewer")
        for required in [
            "done when",
            "scope",
            "forbidden paths",
            "evidence",
            "testing",
            "code quality",
            "safety",
        ]:
            self.assertIn(required, content.lower())

    def test_curator_agent_retired_in_v1(self):
        """aiwf-curator is retired; reviewer handles review output now."""
        agent_path = self.tmp / ".claude" / "agents" / "aiwf-curator.md"
        self.assertFalse(agent_path.exists(), "aiwf-curator should not be installed")

    def test_tester_agent_keeps_full_and_real_usage_obligations(self):
        content = self._claude_agent("aiwf-tester")
        for required in [
            "Tester Requirements",
            "Do not modify code",
            "Do not modify `.aiwf/state/` or `.aiwf/records/`",
            "passed",
            "failed",
            "adequate",
        ]:
            self.assertIn(required, content)

    def test_reasonix_uses_shared_skills_without_duplicate_thin_agents(self):
        self.assertFalse((self.tmp / ".reasonix" / "agents" / "aiwf-executor.md").exists())
        self.assertFalse((self.tmp / ".reasonix" / "agents" / "aiwf-reviewer.md").exists())
        for skill_name, required in {
            "aiwf-implement": ["Do not expand scope", "Allowed Write", "executor_required"],
            "aiwf-test": ["Tester Requirements", "passed", "failed", "adequate"],
            "aiwf-review": [
                "reviewer_required",
                "Done When",
                "review",
                "accepted",
                "needs_fix",
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
            self.assertIn("Role", content)
            self.assertIn("Required read", content)
            self.assertIn(role, content.lower())

            reasonix_content = self._reasonix_skill(skill_name)
            self.assertIn("Role", reasonix_content)
            self.assertIn(role, reasonix_content.lower())

    def test_claude_agents_declare_separate_subagent_role(self):
        for agent_name, (role_line, exclusivity) in {
            "aiwf-executor": ("You implement the active Task.md", "You do not test, review, plan, or close"),
            "aiwf-tester": ("You validate", "You do not implement, review, plan, or close"),
            "aiwf-reviewer": ("You review", "You do not implement, test, plan, or close"),
        }.items():
            content = self._claude_agent(agent_name)
            self.assertIn(role_line, content)
            self.assertIn(exclusivity, content)

    def test_claude_agents_do_not_conflict_with_shared_skills(self):
        executor_agent = self._claude_agent("aiwf-executor")
        executor_skill = self._claude_skill("aiwf-implement")
        for shared_boundary in ["Allowed", "Forbidden", "Do not modify"]:
            self.assertIn(shared_boundary, executor_agent)
            self.assertIn(shared_boundary, executor_skill)

        reviewer_agent = self._claude_agent("aiwf-reviewer")
        reviewer_skill = self._claude_skill("aiwf-review")
        for shared_gate in [
            "Done When",
            "Forbidden",
            "review",
            "evidence",
            "testing",
        ]:
            self.assertIn(shared_gate.lower(), reviewer_skill.lower())
            self.assertIn(shared_gate.lower(), reviewer_agent.lower())


if __name__ == "__main__":
    unittest.main()
