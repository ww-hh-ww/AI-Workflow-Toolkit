"""Init-first user flow contract.

Users initialize AIWF once, then converse naturally. Planner and lifecycle
skills remain planner-directed capabilities, not a manual user checklist.
"""
import unittest
from contextlib import redirect_stdout
from io import StringIO
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

    def test_status_does_not_ask_to_merge_an_already_merged_plan(self):
        from aiwf_core.commands.flow import _print_prompt

        output = StringIO()
        with redirect_stdout(output):
            _print_prompt(
                Path("/tmp/control"),
                Path("/tmp/control"),
                [],
                None,
                [
                    {
                        "plan_id": "PLAN-001",
                        "git_base_branch": "main",
                        "_integration_state": "merged_pending_close",
                    },
                    {
                        "plan_id": "PLAN-004",
                        "git_base_branch": "main",
                        "_integration_state": "merged_pending_close",
                    },
                ],
                [],
            )
        prompt = output.getvalue()
        self.assertIn("handle each open Plan at its current closeout point", prompt)
        self.assertIn("- PLAN-001 | verified candidate merged into main", prompt)
        self.assertIn("- PLAN-004 | verified candidate merged into main", prompt)
        self.assertIn("close this Plan now", prompt)
        self.assertNotIn("merge in the planned order", prompt)
        self.assertNotIn("combined result", prompt)
        self.assertNotIn("Before starting another Plan", prompt)

    def test_status_asks_once_before_merging_or_holding_a_plan(self):
        from aiwf_core.commands.flow import _print_prompt

        output = StringIO()
        with redirect_stdout(output):
            _print_prompt(
                Path("/tmp/control"), Path("/tmp/control"), [], None,
                [{
                    "plan_id": "PLAN-001",
                    "git_branch": "aiwf/plan-001",
                    "git_base_branch": "main",
                    "_integration_state": "awaiting_decision",
                }],
                [],
            )
        prompt = output.getvalue()
        self.assertIn("awaiting user decision", prompt)
        self.assertIn("add another Task, leave", prompt)
        self.assertIn("Do not merge before the user chooses", prompt)
        self.assertIn("aiwf plan hold PLAN-001", prompt)
        self.assertIn("ask whether the user wants /aiwf-architect", prompt)
        self.assertIn("review several Plans as one slice", prompt)

        output = StringIO()
        with redirect_stdout(output):
            _print_prompt(
                Path("/tmp/control"), Path("/tmp/control"), [], None,
                [{
                    "plan_id": "PLAN-001",
                    "integration_hold_ref": "1234567890abcdef",
                    "_integration_state": "held",
                }],
                [],
            )
        held_prompt = output.getvalue()
        self.assertIn("intentionally left open at 1234567890ab", held_prompt)
        self.assertIn("do not ask again or merge", held_prompt)
        self.assertNotIn("awaiting user decision", held_prompt)


if __name__ == "__main__":
    unittest.main()
