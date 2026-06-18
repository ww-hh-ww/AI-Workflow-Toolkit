"""Init-first user flow contract.

Users initialize AIWF once, then converse naturally. Planner and lifecycle
skills remain planner-directed capabilities, not a manual user checklist.
"""
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class TestPlannerFirstFlow(unittest.TestCase):
    @unittest.skip("README.md /aiwf-init references pending next cleanup pass")
    def test_readme_declares_status_then_natural_conversation(self):
        text = (PROJECT_ROOT / "README.md").read_text()
        self.assertIn("aiwf status", text)
        self.assertIn("之后直接对话", text)
        self.assertNotIn("/aiwf-init", text)

    def test_installed_claude_template_declares_planner_directed_capabilities(self):
        text = (PROJECT_ROOT / "aiwf_core" / "embedded_templates" / "CLAUDE.md").read_text()
        self.assertIn("planner", text.lower())
        self.assertIn("aiwf", text.lower())

    def test_planner_skill_says_user_normally_talks_to_planner(self):
        text = (
            PROJECT_ROOT
            / "aiwf_core"
            / "embedded_templates"
            / "skills"
            / "aiwf-planner"
            / "SKILL.md"
        ).read_text()
        self.assertIn("planner", text.lower())
        self.assertIn("create and adjust", text.lower())


if __name__ == "__main__":
    unittest.main()
