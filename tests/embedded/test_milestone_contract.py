"""Milestone acceptance stays explicit, observable, and CLI-accessible."""
import json
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from contextlib import redirect_stdout

from aiwf_core.commands.parser import build_parser
from aiwf_core.commands.milestone_commands import _cmd_milestone_create
from aiwf_core.commands.flow import (
    _milestones_at_acceptance,
    _print_prompt,
    _task_next,
)
from aiwf_core.core.state.milestone_ops import (
    close_milestone,
    get_milestone,
    load_milestones,
    record_milestone_integration,
    upsert_milestone,
)


class TestMilestoneContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aiwf-milestone-")
        self.root = Path(self.temp.name)
        state = self.root / ".aiwf/state"
        state.mkdir(parents=True)
        (state / "milestones.json").write_text(
            json.dumps({"schema_version": 1, "active_milestone_id": None, "milestones": []}),
            encoding="utf-8",
        )
        (state / "tasks.json").write_text(
            json.dumps({"tasks": [{
                "id": "TASK-VERIFY", "status": "closed",
                "kind": "milestone_verification", "milestone_id": "MS-001",
            }]}),
            encoding="utf-8",
        )
        (state / "plans.json").write_text(
            json.dumps({"plans": []}), encoding="utf-8",
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_reverse_trace_evidence_is_reachable_from_public_cli(self):
        parser = build_parser(None)
        args = parser.parse_args([
            "milestone", "integration-test", "MS-001",
            "--status", "passed",
            "--coverage-mode", "function_reverse_trace",
            "--main-path-status", "passed",
            "--source-file", "src/a.py",
            "--accounted-file", "src/generated.py",
            "--function-trace", "src/a.py::run::main::connected",
            "--failed-point", "none",
        ])

        self.assertEqual(args.source_file, ["src/a.py"])
        self.assertEqual(args.accounted_file, ["src/generated.py"])
        self.assertEqual(args.function_trace, ["src/a.py::run::main::connected"])
        self.assertEqual(args.failed_point, ["none"])
        help_text = parser._subparsers._group_actions[0].choices["milestone"] \
            ._subparsers._group_actions[0].choices["integration-test"].format_help()
        self.assertIn("default recommendation", " ".join(help_text.split()))

        upsert_milestone(str(self.root), "MS-001")
        result = record_milestone_integration(
            str(self.root), "MS-001", status="passed",
            coverage_mode="function_reverse_trace", main_path_status="passed",
            source_files=args.source_file, accounted_files=args.accounted_file,
            function_traces=[{
                "file": "src/a.py", "function": "run", "callers": ["main"],
                "status": "connected", "reason": "",
            }],
        )
        self.assertEqual(result["integration_test"]["status"], "passed")

    def test_create_surfaces_verification_choices_without_selecting_for_user(self):
        output = io.StringIO()
        with redirect_stdout(output):
            _cmd_milestone_create(SimpleNamespace(
                milestone_id="MS-CHOICE", goal_id="", title="Choice", status="open",
            ))

        text = output.getvalue()
        self.assertIn("choose verification coverage with the user", text)
        self.assertIn("Recommended default: end_to_end_flow", text)
        self.assertIn("Optional: function_reverse_trace", text)

    def test_open_milestones_coexist_and_pointer_tracks_current_focus(self):
        upsert_milestone(str(self.root), "MS-001")
        upsert_milestone(str(self.root), "MS-002")

        data = load_milestones(str(self.root))
        self.assertEqual(data["active_milestone_id"], "MS-002")
        self.assertEqual(
            {item["milestone_id"]: item["status"] for item in data["milestones"]},
            {"MS-001": "open", "MS-002": "open"},
        )

    def test_new_milestone_has_no_automatic_acceptance_policy(self):
        upsert_milestone(str(self.root), "MS-001")

        milestone = get_milestone(str(self.root), "MS-001")
        acceptance = milestone["user_acceptance"]
        self.assertNotIn("advance_policy", milestone)
        self.assertTrue(acceptance["required"])
        self.assertNotEqual(acceptance["status"], "not_required")

    def test_tag_failure_is_visible_without_claiming_a_tag(self):
        upsert_milestone(str(self.root), "MS-001")
        failed_tag = subprocess.CompletedProcess(
            ["git", "tag"], 128, stdout="", stderr="fatal: not a git repository",
        )

        with patch(
            "aiwf_core.core.state.milestone_ops.check_milestone_readiness",
            return_value=[],
        ), patch("subprocess.run", return_value=failed_tag):
            result = close_milestone(str(self.root), "MS-001")

        self.assertTrue(result["closed"])
        self.assertEqual(result["milestone"]["git_tag"], "")
        self.assertIn("Git tag was not created", result["warnings"][0])

    def test_closed_plan_routes_to_verification_task_creation_without_dispatch(self):
        upsert_milestone(str(self.root), "MS-001", plan_ids=["PLAN-001"])
        (self.root / ".aiwf/state/plans.json").write_text(json.dumps({
            "plans": [{"id": "PLAN-001", "plan_id": "PLAN-001", "status": "closed"}],
        }), encoding="utf-8")
        (self.root / ".aiwf/state/tasks.json").write_text(
            json.dumps({"tasks": []}), encoding="utf-8",
        )

        milestones = _milestones_at_acceptance(self.root)
        output = io.StringIO()
        with redirect_stdout(output):
            _print_prompt(self.root, self.root, [], None, [], [], milestones)

        prompt = output.getvalue()
        self.assertIn("verification Task missing", prompt)
        self.assertIn("Required skills: /aiwf-planner", prompt)
        self.assertIn("does not create a Task, dispatch Architect", prompt)
        self.assertIn("aiwf milestone link-task MS-001 <TASK-ID>", prompt)

    def test_open_plan_does_not_trigger_milestone_acceptance(self):
        upsert_milestone(str(self.root), "MS-001", plan_ids=["PLAN-001"])
        (self.root / ".aiwf/state/plans.json").write_text(json.dumps({
            "plans": [{"id": "PLAN-001", "plan_id": "PLAN-001", "status": "open"}],
        }), encoding="utf-8")
        (self.root / ".aiwf/state/tasks.json").write_text(
            json.dumps({"tasks": []}), encoding="utf-8",
        )

        self.assertEqual(_milestones_at_acceptance(self.root), [])

    def test_active_verification_task_routes_only_to_architect(self):
        upsert_milestone(str(self.root), "MS-001")
        task = {
            "id": "TASK-VERIFY", "status": "active",
            "kind": "milestone_verification", "milestone_id": "MS-001",
            "requirements": {
                "executor_required": False, "tester_required": False,
                "reviewer_required": False,
            },
        }

        role, action = _task_next(task, {}, self.root)

        self.assertEqual(role, "Milestone acceptance")
        self.assertIn("/aiwf-architect", action)
        self.assertNotIn("inline", action.lower())

    def test_passed_verification_waits_for_human_then_routes_close(self):
        upsert_milestone(str(self.root), "MS-001")
        path = self.root / ".aiwf/state/milestones.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        milestone = data["milestones"][0]
        milestone["integration_test"].update({
            "status": "passed", "main_path_status": "passed",
        })
        milestone["architecture_review"]["status"] = "intact"
        milestone["stage_synthesis"].update({"status": "closed", "verdict": "PASS"})
        path.write_text(json.dumps(data), encoding="utf-8")
        task = {
            "id": "TASK-VERIFY", "status": "active",
            "kind": "milestone_verification", "milestone_id": "MS-001",
            "requirements": {},
        }

        role, action = _task_next(task, {}, self.root)
        self.assertEqual(role, "Human acceptance")
        self.assertIn("explicitly approve", action)

        data = json.loads(path.read_text(encoding="utf-8"))
        data["milestones"][0]["user_acceptance"]["status"] = "confirmed"
        path.write_text(json.dumps(data), encoding="utf-8")
        role, action = _task_next(task, {}, self.root)
        self.assertEqual(role, "Planner calibration")
        self.assertIn("aiwf milestone close MS-001", action)

    def test_verification_task_cannot_close_before_milestone_acceptance(self):
        from aiwf_core.core.task_ledger import close_task

        upsert_milestone(str(self.root), "MS-001")
        (self.root / ".aiwf/state/tasks.json").write_text(json.dumps({"tasks": [{
            "id": "TASK-VERIFY", "status": "active", "phase": "reviewing",
            "kind": "milestone_verification", "milestone_id": "MS-001",
            "requirements": {
                "executor_required": False, "tester_required": False,
                "reviewer_required": False,
            },
        }]}), encoding="utf-8")

        result = close_task(str(self.root), task_id="TASK-VERIFY")

        self.assertFalse(result["closed"])
        self.assertIn("milestone stage synthesis required", " ".join(result["blockers"]))


if __name__ == "__main__":
    unittest.main()
