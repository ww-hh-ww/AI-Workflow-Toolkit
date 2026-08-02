"""Init-first user flow contract.

Users initialize AIWF once, then converse naturally. Planner and lifecycle
skills remain planner-directed capabilities, not a manual user checklist.
"""
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch


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

    def test_status_recovers_an_interrupted_plan_closure(self):
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
                        "_integration_state": "closure_recovery",
                    },
                    {
                        "plan_id": "PLAN-004",
                        "git_base_branch": "main",
                        "_integration_state": "closure_recovery",
                    },
                ],
                [],
            )
        prompt = output.getvalue()
        self.assertIn("handle each open Plan at its current closeout point", prompt)
        self.assertIn("project merge completed but governance closure was interrupted", prompt)
        self.assertIn("rerun the same aiwf plan integrate PLAN-001 --status passed", prompt)
        self.assertIn("It will not merge the candidate again", prompt)
        self.assertNotIn("merge in the planned order", prompt)
        self.assertNotIn("combined result", prompt)
        self.assertNotIn("Before starting another Plan", prompt)

        output = StringIO()
        with redirect_stdout(output):
            _print_prompt(
                Path("/tmp/control"),
                Path("/tmp/control"),
                [],
                None,
                [{
                    "plan_id": "PLAN-GAPS",
                    "git_base_branch": "main",
                    "integration": {
                        "verification_status": "accepted_with_gaps",
                    },
                    "_integration_state": "closure_recovery",
                }],
                [],
            )
        gap_prompt = output.getvalue()
        self.assertIn(
            "aiwf plan integrate PLAN-GAPS --status accepted_with_gaps",
            gap_prompt,
        )
        self.assertIn("same proof and gap arguments", gap_prompt)

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
        self.assertNotIn("/aiwf-architect", prompt)

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

    def test_status_makes_passing_integration_merge_explicit(self):
        from aiwf_core.commands.flow import _print_prompt

        output = StringIO()
        with redirect_stdout(output):
            _print_prompt(
                Path("/tmp/control"), Path("/tmp/control"), [], None,
                [{
                    "plan_id": "PLAN-001",
                    "git_worktree_path": "/tmp/plan-001",
                    "_integration_state": "integration_ready",
                    "integration": {
                        "candidate_worktree": "/tmp/plan-001",
                    },
                }],
                [],
            )
        prompt = output.getvalue()
        self.assertIn("ask whether the user wants /aiwf-architect", prompt)
        self.assertIn("on this exact candidate", prompt)
        self.assertIn("one or several Plans whose results are present", prompt)
        self.assertIn("If a finding changes the candidate", prompt)
        self.assertIn("resolve environment, generated, or non-semantic work directly", prompt)
        self.assertIn("use a Task only for semantic project work", prompt)
        self.assertIn("after the user declines or decides the findings", prompt)
        self.assertIn("write Plan.md '## Closure Calibration'", prompt)
        self.assertIn("immediately merges the passing candidate", prompt)
        self.assertIn("do not call it passed", prompt)
        self.assertIn("--status accepted_with_gaps", prompt)
        self.assertIn("--known-gap", prompt)
        self.assertIn("--acceptance-reason", prompt)
        self.assertIn("aiwf plan hold PLAN-001", prompt)

    def test_status_marks_dirty_candidate_stale_without_forcing_a_task(self):
        from aiwf_core.commands.flow import _print_prompt

        output = StringIO()
        with patch(
            "aiwf_core.core.git_workflow.changed_project_files",
            return_value=["generated/manifest.json"],
        ), redirect_stdout(output):
            _print_prompt(
                Path("/tmp/control"), Path("/tmp/control"), [], None,
                [{
                    "plan_id": "PLAN-001",
                    "_integration_state": "integration_ready",
                    "integration": {"candidate_worktree": str(PROJECT_ROOT)},
                }],
                [],
            )
        prompt = output.getvalue()
        self.assertIn("candidate worktree changed after preparation", prompt)
        self.assertIn("the old candidate is stale", prompt)
        self.assertIn("resolve local, generated, or non-semantic integration work directly", prompt)
        self.assertIn("use a Task only for semantic project work", prompt)
        self.assertIn("rerun the same plan integrate command", prompt)


if __name__ == "__main__":
    unittest.main()
