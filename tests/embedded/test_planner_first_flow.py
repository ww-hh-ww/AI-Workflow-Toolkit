"""Init-first user flow contract.

Users initialize AIWF once, then converse naturally. Planner and lifecycle
skills remain planner-directed capabilities, not a manual user checklist.
"""
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class TestPlannerFirstFlow(unittest.TestCase):
    def test_installed_claude_template_declares_planner_directed_capabilities(self):
        text = (PROJECT_ROOT / "aiwf_core" / "embedded_templates" / "CLAUDE.md").read_text()
        self.assertIn("planner", text.lower())
        self.assertIn("aiwf", text.lower())

    def test_planner_discusses_before_creating_nodes(self):
        text = (
            PROJECT_ROOT
            / "aiwf_core"
            / "embedded_templates"
            / "skills"
            / "aiwf-planner"
            / "SKILL.md"
        ).read_text()
        self.assertIn("Discussion is the default", text)
        self.assertIn("Write governance only after the user clearly asks", text)


if __name__ == "__main__":
    unittest.main()
