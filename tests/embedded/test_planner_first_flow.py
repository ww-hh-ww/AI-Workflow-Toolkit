"""Planner-first user flow contract.

Users should normally interface with /aiwf-planner. Implement/test/review/close
remain available as planner-directed capabilities, not a manual user checklist.
"""
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class TestPlannerFirstFlow(unittest.TestCase):
    def test_readme_declares_planner_as_main_interface(self):
        text = (PROJECT_ROOT / "README.md").read_text()
        self.assertIn("用户主要只需要和 Planner 对接", text)
        self.assertIn("planner-directed capabilities", text)

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
        self.assertIn("project architect", text.lower())


if __name__ == "__main__":
    unittest.main()
