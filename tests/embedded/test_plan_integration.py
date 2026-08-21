import json
import io
import shutil
import subprocess
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


def _write_valid_task_contract(base: Path, task_id: str) -> None:
    path = base / ".aiwf/tasks" / f"{task_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""# {task_id}

## Fixed Contract

### Structural Home

PLAN-001 integration.

### Objective

Integrate the tested result.

### Contract Responsibility

Own and prove the integrated result.

### Proof Standard

- [Built] The integrated result exists in the reviewed snapshot.
""",
        encoding="utf-8",
    )


class TestPlanIntegration(unittest.TestCase):
    def setUp(self):
        self.control = Path(tempfile.mkdtemp(prefix="aiwf_plan_integration_"))
        self.worktree = self.control.parent / f"{self.control.name}_plan"
        subprocess.run(["git", "init", "-b", "main"], cwd=self.control, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.control, check=True)
        subprocess.run(["git", "config", "user.name", "AIWF Test"], cwd=self.control, check=True)
        (self.control / "app.txt").write_text("base\n", encoding="utf-8")
        subprocess.run(["git", "add", "app.txt"], cwd=self.control, check=True)
        subprocess.run(["git", "commit", "-m", "base"], cwd=self.control, check=True, capture_output=True)
        subprocess.run(
            ["git", "worktree", "add", "-b", "aiwf/plan-001", str(self.worktree), "main"],
            cwd=self.control, check=True, capture_output=True,
        )
        (self.worktree / "feature.txt").write_text("feature\n", encoding="utf-8")
        subprocess.run(["git", "add", "feature.txt"], cwd=self.worktree, check=True)
        subprocess.run(["git", "commit", "-m", "TASK-001: feature"], cwd=self.worktree,
                       check=True, capture_output=True)
        self.plan_head = self._git(self.worktree, "rev-parse", "HEAD")

        state = self.control / ".aiwf/state"
        state.mkdir(parents=True)
        (state / "plans.json").write_text(json.dumps({
            "schema_version": 1,
            "plans": [{
                "id": "PLAN-001",
                "plan_id": "PLAN-001",
                "title": "Feature plan",
                "status": "open",
                "dependencies": [],
                "task_ids": ["TASK-001"],
                "task_status": {"TASK-001": "closed"},
                "git_worktree_path": str(self.worktree),
                "git_branch": "aiwf/plan-001",
                "git_base_branch": "main",
                "git_base_ref": self._git(self.control, "rev-parse", "main"),
                "git_head_ref": self.plan_head,
            }],
        }, indent=2) + "\n", encoding="utf-8")
        plan_doc = self.control / ".aiwf/plans/PLAN-001.md"
        plan_doc.parent.mkdir(parents=True, exist_ok=True)
        plan_doc.write_text(
            "---\nid: PLAN-001\ntype: plan\nstatus: open\n---\n\n"
            "# Feature plan\n\n"
            "## Closure Calibration\n\n"
            "Feature integrated from Plan.md.\n",
            encoding="utf-8",
        )
        subprocess.run(
            ["git", "add", ".aiwf/plans/PLAN-001.md"],
            cwd=self.control, check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "add Plan narrative"],
            cwd=self.control, check=True, capture_output=True,
        )

    def tearDown(self):
        subprocess.run(["git", "worktree", "remove", "--force", str(self.worktree)],
                       cwd=self.control, capture_output=True)
        shutil.rmtree(self.worktree, ignore_errors=True)
        shutil.rmtree(self.control, ignore_errors=True)

    @staticmethod
    def _git(cwd: Path, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=cwd, check=True,
                              capture_output=True, text=True).stdout.strip()

    @patch("aiwf_core.core.plan_integration.prepare_plan_integration")
    def test_conflict_output_gives_one_unambiguous_route(self, prepare):
        prepare.return_value = {
            "conflict": True,
            "integration_task_id": "",
            "conflicts": ["package.json", "manifest.json"],
            "critique_reset_task_ids": [],
            "governance_checkpoint": {},
        }
        from aiwf_core.commands.plan_commands import _cmd_plan_integrate

        output = io.StringIO()
        with redirect_stdout(output):
            _cmd_plan_integrate(Namespace(
                plan_id="PLAN-001", status="", accept_head_change=False,
            ))

        text = output.getvalue()
        self.assertIn("stage 1/2: conflict found", text)
        self.assertIn("choose the lightest honest path", text)
        self.assertIn("normal Git", text)
        self.assertIn("no Task or role dispatch is needed", text)
        self.assertIn("create or continue one kind=integration Task", text)
        self.assertNotIn("--resolve-nonlogic", text)

    @patch("aiwf_core.core.plan_integration.prepare_plan_integration")
    def test_prepare_output_says_it_has_not_merged(self, prepare):
        prepare.return_value = {
            "prepared": True,
            "conflict": False,
            "base_ref": "a" * 40,
            "candidate_ref": "b" * 40,
            "candidate_worktree": str(self.worktree),
            "governance_checkpoint": {},
        }
        from aiwf_core.commands.plan_commands import _cmd_plan_integrate

        output = io.StringIO()
        with redirect_stdout(output):
            _cmd_plan_integrate(Namespace(
                plan_id="PLAN-001", status="", accept_head_change=False,
            ))

        text = output.getvalue()
        self.assertIn("stage 1/2 prepared", text)
        self.assertIn("Nothing has been merged", text)
        self.assertIn("Stage 2/2, verify + merge + close", text)

    def test_prepare_keeps_plan_worktree_free_of_shared_governance(self):
        from aiwf_core.core.plan_integration import prepare_plan_integration

        stale = self.worktree / ".aiwf/records/stale.json"
        stale.parent.mkdir(parents=True, exist_ok=True)
        stale.write_text("{}\n", encoding="utf-8")
        subprocess.run(
            ["git", "add", ".aiwf/records/stale.json"],
            cwd=self.worktree, check=True,
        )

        prepared = prepare_plan_integration(str(self.control), "PLAN-001")

        self.assertTrue(prepared["prepared"])
        self.assertFalse((self.worktree / ".aiwf").exists())
        self.assertEqual(
            self._git(self.worktree, "status", "--short", "--", ".aiwf"),
            "",
        )
        flags = self._git(self.worktree, "ls-files", "-v", "--", ".aiwf")
        self.assertTrue(flags)
        self.assertTrue(all(line.startswith("S ") for line in flags.splitlines()))
        self.assertNotIn("stale.json", flags)

    @patch("aiwf_core.core.plan_integration.prepare_plan_integration")
    def test_audit_output_is_actionable_without_a_repair_workflow(self, prepare):
        prepare.return_value = {
            "prepared": False,
            "conflict": False,
            "audit_required": True,
            "audit": {
                "base": {
                    "changes": [".DS_Store"], "ignored": ["build/"],
                    "empty_directories": [], "git_operation": "",
                },
                "plan": {
                    "changes": [], "ignored": [],
                    "empty_directories": ["fixtures/empty"], "git_operation": "",
                },
            },
            "governance_checkpoint": {},
        }
        from aiwf_core.commands.plan_commands import _cmd_plan_integrate

        output = io.StringIO()
        with redirect_stdout(output):
            _cmd_plan_integrate(Namespace(
                plan_id="PLAN-001", status="", accept_head_change=False,
            ))

        text = output.getvalue()
        self.assertIn("No candidate was prepared", text)
        self.assertIn("Base changes: .DS_Store", text)
        self.assertIn("Plan empty directories: fixtures/empty", text)
        self.assertIn("normal editing and Git", text)
        self.assertIn("rerun this same command", text)
        self.assertNotIn("create a Task", text)

    def test_planner_resolves_small_conflict_with_native_git_and_reruns_integrate(self):
        from aiwf_core.core.plan_integration import (
            finish_plan_integration,
            prepare_plan_integration,
        )
        from aiwf_core.core.plan_integration_git import git_operation
        from aiwf_core.core.plan_integration_context import (
            integration_conflict_for_worktree,
        )
        from aiwf_core.core.state.plan_ops import load_plans, save_plans

        (self.worktree / ".gitignore").write_text("plan-cache/\n", encoding="utf-8")
        subprocess.run(["git", "add", ".gitignore"], cwd=self.worktree, check=True)
        subprocess.run(
            ["git", "commit", "-m", "TASK-002: plan ignore"],
            cwd=self.worktree, check=True, capture_output=True,
        )
        plans = load_plans(str(self.control))
        plan = plans["plans"][0]
        plan["git_head_ref"] = self._git(self.worktree, "rev-parse", "HEAD")
        plan["task_ids"].append("TASK-002")
        plan["task_status"]["TASK-002"] = "closed"
        save_plans(str(self.control), plans)

        (self.control / ".gitignore").write_text(".DS_Store\n", encoding="utf-8")
        subprocess.run(["git", "add", ".gitignore"], cwd=self.control, check=True)
        subprocess.run(
            ["git", "commit", "-m", "main local ignore"],
            cwd=self.control, check=True, capture_output=True,
        )

        conflict = prepare_plan_integration(str(self.control), "PLAN-001")
        self.assertTrue(conflict["conflict"])
        self.assertIn(".gitignore", conflict["conflicts"])

        context = integration_conflict_for_worktree(self.worktree)
        self.assertEqual(context["conflicts"], [".gitignore"])
        from aiwf_core.core.event_model import NormalizedEvent
        from aiwf_core.core.agent_worktree import route_agent_tool
        from aiwf_core.hooks.common.scope_checker import check_bash, check_file_write

        routed = route_agent_tool(NormalizedEvent(
            engine="claude", event_type="pre_tool_use", cwd=str(self.control),
            tool_name="Edit", tool_input={"file_path": ".gitignore"},
            agent_type="planner-main",
        ))
        self.assertEqual(routed.assignment.worktree, self.worktree.resolve())
        self.assertEqual(
            routed.tool_input["file_path"], str((self.worktree / ".gitignore").resolve()),
        )
        allowed_write = check_file_write(NormalizedEvent(
            engine="claude", event_type="pre_tool_use", cwd=str(self.worktree),
            tool_name="Edit", tool_input={"file_path": ".gitignore"},
            agent_type="planner-main",
        ))
        related_write = check_file_write(NormalizedEvent(
            engine="claude", event_type="pre_tool_use", cwd=str(self.worktree),
            tool_name="Edit", tool_input={"file_path": "app.txt"},
            agent_type="planner-main",
        ))
        native_git = check_bash(NormalizedEvent(
            engine="claude", event_type="pre_tool_use", cwd=str(self.worktree),
            tool_name="Bash", tool_input={"command": "git add .gitignore"},
            agent_type="planner-main",
        ))
        self.assertTrue(allowed_write.allowed)
        self.assertTrue(related_write.allowed)
        self.assertEqual(native_git["decision"], "allow")

        subprocess.run(
            ["git", "rebase", conflict["base_ref"]],
            cwd=self.worktree, check=False, capture_output=True,
        )
        self.assertEqual(git_operation(self.worktree), "rebase")
        (self.worktree / ".gitignore").write_text(
            ".DS_Store\nplan-cache/\n", encoding="utf-8",
        )
        subprocess.run(["git", "add", ".gitignore"], cwd=self.worktree, check=True)
        subprocess.run(
            ["git", "-c", "core.editor=true", "rebase", "--continue"],
            cwd=self.worktree, check=True, capture_output=True,
        )
        while git_operation(self.worktree) == "rebase":
            subprocess.run(
                ["git", "-c", "core.editor=true", "rebase", "--continue"],
                cwd=self.worktree, check=True, capture_output=True,
            )
        prepared = prepare_plan_integration(str(self.control), "PLAN-001")
        self.assertTrue(prepared["prepared"])
        self.assertEqual(git_operation(self.worktree), "")

        result = finish_plan_integration(
            str(self.control), "PLAN-001", status="passed",
            commands=["grep -q plan-cache .gitignore"],
            verification_results=[{
                "command": "grep -q plan-cache .gitignore",
                "expected": "exit 0", "observed": "exit 0", "matched": True,
            }],
            summary="",
        )
        self.assertTrue(result["closed"])
        closure = result["plan"]["closure"]
        self.assertEqual(closure["merged_to_branch"], "main")
        self.assertEqual(closure["resolved_conflicts"], [".gitignore"])
        self.assertNotIn("delivery_stage", closure)
        repeated = finish_plan_integration(
            str(self.control), "PLAN-001", status="passed",
            commands=["grep -q plan-cache .gitignore"],
            verification_results=[{
                "command": "grep -q plan-cache .gitignore",
                "expected": "exit 0", "observed": "exit 0", "matched": True,
            }],
            summary="",
        )
        self.assertTrue(repeated["closed"])

    def test_created_plan_worktree_inherits_develop_as_integration_branch(self):
        from aiwf_core.core.plan_worktrees import create_plan_worktree

        subprocess.run(["git", "switch", "-c", "develop"], cwd=self.control,
                       check=True, capture_output=True)
        target = self.control.parent / f"{self.control.name}_develop_plan"
        plan = {"plan_id": "PLAN-DEVELOP", "git_base_branch": "", "git_base_ref": ""}
        try:
            binding = create_plan_worktree(str(self.control), plan, target)
            self.assertEqual(binding["base_branch"], "develop")
            self.assertEqual(plan["git_base_branch"], "develop")
        finally:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(target)],
                cwd=self.control, capture_output=True,
            )
            shutil.rmtree(target, ignore_errors=True)

    def test_existing_develop_does_not_override_user_selected_main_base(self):
        from aiwf_core.core.plan_worktrees import create_plan_worktree

        subprocess.run(["git", "branch", "develop"], cwd=self.control,
                       check=True, capture_output=True)
        target = self.control.parent / f"{self.control.name}_main_plan"
        plan = {"plan_id": "PLAN-MAIN", "git_base_branch": "", "git_base_ref": ""}
        try:
            binding = create_plan_worktree(str(self.control), plan, target)
            self.assertEqual(binding["base_branch"], "main")
            self.assertEqual(plan["git_base_branch"], "main")
        finally:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(target)],
                cwd=self.control, capture_output=True,
            )
            shutil.rmtree(target, ignore_errors=True)

    def test_prepare_prove_merge_and_close_uses_exact_candidate(self):
        from aiwf_core.core.git_snapshots import ref_tree
        from aiwf_core.core.git_workflow import plan_integration_state
        from aiwf_core.core.plan_integration import finish_plan_integration, prepare_plan_integration
        from aiwf_core.core.state.plan_ops import load_plans

        (self.control / "base.txt").write_text("new base\n", encoding="utf-8")
        subprocess.run(["git", "add", "base.txt"], cwd=self.control, check=True)
        subprocess.run(["git", "commit", "-m", "advance main"], cwd=self.control,
                       check=True, capture_output=True)

        prepared = prepare_plan_integration(str(self.control), "PLAN-001")
        self.assertTrue(prepared["prepared"], prepared)
        self.assertNotEqual(prepared["candidate_ref"], self.plan_head)
        plan = load_plans(str(self.control))["plans"][0]
        self.assertEqual(plan_integration_state(str(self.control), plan), "integration_ready")

        result = finish_plan_integration(
            str(self.control), "PLAN-001", status="passed",
            commands=["test -f feature.txt"],
            verification_results=[{
                "command": "test -f feature.txt", "expected": "exit 0",
                "observed": "exit 0", "matched": True,
            }],
            summary="feature and current base work together",
        )
        self.assertTrue(result["merged"])
        self.assertTrue(result["closed"])
        plan = load_plans(str(self.control))["plans"][0]
        merge_commit = plan["integration"]["merge_commit"]
        self.assertEqual(plan["status"], "closed")
        self.assertEqual(plan["closure"]["merged_commit"], merge_commit)
        self.assertEqual(plan["closure"]["summary"], "Feature integrated from Plan.md.")
        self.assertEqual(
            self._git(self.control, "merge-base", "--is-ancestor", merge_commit, "main"),
            "",
        )
        self.assertEqual(ref_tree(str(self.control), merge_commit),
                         plan["integration"]["candidate_tree"])
        self.assertEqual(plan_integration_state(str(self.control), plan), "closed")
        checkpoint = result["governance_checkpoint"]
        self.assertTrue(checkpoint["committed"])
        self.assertNotEqual(checkpoint["commit"], merge_commit)

    def test_explicitly_accepted_gaps_merge_close_and_remain_machine_readable(self):
        from aiwf_core.core.plan_integration import (
            finish_plan_integration,
            prepare_plan_integration,
        )
        from aiwf_core.core.state.plan_ops import load_plans

        prepare_plan_integration(str(self.control), "PLAN-001")
        result = finish_plan_integration(
            str(self.control),
            "PLAN-001",
            status="accepted_with_gaps",
            commands=["node scripts/score.js"],
            verification_results=[{
                "command": "node scripts/score.js",
                "expected": "at least 17/18 cases pass",
                "observed": "12/18 cases pass",
                "matched": False,
            }],
            summary="",
            known_gaps=[
                "Only 12/18 cases pass; six layouts still need a follow-up Plan.",
            ],
            acceptance_reason=(
                "The user accepts the disclosed coverage limit for this staged merge."
            ),
        )

        self.assertTrue(result["merged"])
        self.assertTrue(result["closed"])
        plan = load_plans(str(self.control))["plans"][0]
        self.assertEqual(plan["status"], "closed")
        self.assertEqual(
            plan["integration"]["verification_status"],
            "accepted_with_gaps",
        )
        self.assertEqual(plan["integration"]["status"], "merged")
        self.assertEqual(
            plan["integration"]["known_gaps"],
            ["Only 12/18 cases pass; six layouts still need a follow-up Plan."],
        )
        self.assertEqual(plan["closure"]["mode"], "accepted_with_gaps")
        self.assertTrue(plan["closure"]["accepted"])
        self.assertEqual(
            plan["closure"]["acceptance_reason"],
            "The user accepts the disclosed coverage limit for this staged merge.",
        )
        self.assertTrue((self.control / "feature.txt").exists())

        from aiwf_core.commands.plan_commands import _cmd_plan_list, _cmd_plan_show

        output = io.StringIO()
        with patch("pathlib.Path.cwd", return_value=self.control), redirect_stdout(output):
            _cmd_plan_show(Namespace(
                plan_id_pos="PLAN-001", plan_id="", task_id="",
            ))
        shown = output.getvalue()
        self.assertIn("Verification disposition: accepted_with_gaps", shown)
        self.assertIn(
            "Accepted gap: Only 12/18 cases pass; six layouts still need a follow-up Plan.",
            shown,
        )
        self.assertIn(
            "Acceptance reason: The user accepts the disclosed coverage limit",
            shown,
        )
        output = io.StringIO()
        with patch("pathlib.Path.cwd", return_value=self.control), redirect_stdout(output):
            _cmd_plan_list(Namespace())
        self.assertIn("closed: accepted gaps", output.getvalue())

    def test_accepted_gaps_requires_disclosure_reason_and_observed_proof(self):
        from aiwf_core.core.plan_integration import (
            finish_plan_integration,
            prepare_plan_integration,
        )

        prepare_plan_integration(str(self.control), "PLAN-001")
        proof = [{
            "command": "node scripts/score.js",
            "expected": "17/18",
            "observed": "12/18",
            "matched": False,
        }]
        with self.assertRaisesRegex(ValueError, "--known-gap"):
            finish_plan_integration(
                str(self.control), "PLAN-001",
                status="accepted_with_gaps",
                commands=["node scripts/score.js"],
                verification_results=proof,
                summary="",
                acceptance_reason="The user accepts it.",
            )
        with self.assertRaisesRegex(ValueError, "--acceptance-reason"):
            finish_plan_integration(
                str(self.control), "PLAN-001",
                status="accepted_with_gaps",
                commands=["node scripts/score.js"],
                verification_results=proof,
                summary="",
                known_gaps=["Only 12/18 cases pass."],
            )
        with self.assertRaisesRegex(ValueError, "observed verification result"):
            finish_plan_integration(
                str(self.control), "PLAN-001",
                status="accepted_with_gaps",
                commands=["node scripts/score.js"],
                verification_results=[],
                summary="",
                known_gaps=["Only 12/18 cases pass."],
                acceptance_reason="The user accepts it.",
            )

    def test_accepted_gaps_recovery_keeps_the_original_disposition(self):
        from aiwf_core.core.plan_integration import (
            finish_plan_integration,
            prepare_plan_integration,
        )
        from aiwf_core.core.state.plan_ops import load_plans

        prepare_plan_integration(str(self.control), "PLAN-001")
        arguments = {
            "status": "accepted_with_gaps",
            "commands": ["node scripts/score.js"],
            "verification_results": [{
                "command": "node scripts/score.js",
                "expected": "17/18",
                "observed": "12/18",
                "matched": False,
            }],
            "summary": "",
            "known_gaps": ["Only 12/18 cases pass."],
            "acceptance_reason": "The user accepts this staged result.",
        }
        with patch(
            "aiwf_core.core.plan_integration_closure.write_plan_closure_doc",
            side_effect=OSError("simulated closure interruption"),
        ):
            with self.assertRaisesRegex(
                ValueError, "--status accepted_with_gaps",
            ):
                finish_plan_integration(
                    str(self.control), "PLAN-001", **arguments,
                )

        interrupted = load_plans(str(self.control))["plans"][0]
        self.assertEqual(interrupted["status"], "open")
        self.assertEqual(interrupted["integration"]["status"], "merged")
        self.assertEqual(
            interrupted["integration"]["verification_status"],
            "accepted_with_gaps",
        )

        recovered = finish_plan_integration(
            str(self.control), "PLAN-001", **arguments,
        )
        self.assertTrue(recovered["closed"])
        self.assertEqual(
            recovered["plan"]["closure"]["mode"],
            "accepted_with_gaps",
        )

    def test_base_change_invalidates_prepared_candidate(self):
        from aiwf_core.core.git_workflow import plan_integration_state
        from aiwf_core.core.plan_integration import finish_plan_integration, prepare_plan_integration
        from aiwf_core.core.state.plan_ops import load_plans

        prepare_plan_integration(str(self.control), "PLAN-001")
        (self.control / "later.txt").write_text("later\n", encoding="utf-8")
        subprocess.run(["git", "add", "later.txt"], cwd=self.control, check=True)
        subprocess.run(["git", "commit", "-m", "move base"], cwd=self.control,
                       check=True, capture_output=True)
        plan = load_plans(str(self.control))["plans"][0]
        self.assertEqual(plan_integration_state(str(self.control), plan), "base_changed")
        with self.assertRaisesRegex(ValueError, "base branch changed"):
            finish_plan_integration(
                str(self.control), "PLAN-001", status="passed",
                commands=["true"],
                verification_results=[{
                    "command": "true", "expected": "exit 0", "observed": "exit 0",
                    "matched": True,
                }],
                summary="stale proof",
            )

    def test_rerun_finishes_closure_without_repeating_the_merge(self):
        from aiwf_core.core.git_workflow import plan_integration_state
        from aiwf_core.core.plan_integration import finish_plan_integration, prepare_plan_integration
        from aiwf_core.core.state.plan_ops import load_plans

        prepare_plan_integration(str(self.control), "PLAN-001")
        proof = [{
            "command": "test -f feature.txt",
            "expected": "exit 0",
            "observed": "exit 0",
            "matched": True,
        }]
        with patch(
            "aiwf_core.core.plan_integration_closure.write_plan_closure_doc",
            side_effect=OSError("simulated closure interruption"),
        ):
            with self.assertRaisesRegex(ValueError, "governance closure is incomplete"):
                finish_plan_integration(
                    str(self.control), "PLAN-001", status="passed",
                    commands=["test -f feature.txt"],
                    verification_results=proof,
                    summary="feature integrated",
                )

        merge_commit = self._git(self.control, "rev-parse", "HEAD")
        interrupted = load_plans(str(self.control))["plans"][0]
        self.assertEqual(interrupted["status"], "open")
        self.assertEqual(interrupted["integration"]["merge_commit"], merge_commit)
        self.assertEqual(
            plan_integration_state(str(self.control), interrupted),
            "closure_recovery",
        )

        recovered = finish_plan_integration(
            str(self.control), "PLAN-001", status="passed",
            commands=["test -f feature.txt"],
            verification_results=proof,
            summary="feature integrated",
        )
        self.assertTrue(recovered["closed"])
        self.assertEqual(recovered["integration"]["merge_commit"], merge_commit)
        self.assertEqual(load_plans(str(self.control))["plans"][0]["status"], "closed")
        self.assertEqual(
            self._git(self.control, "merge-base", "--is-ancestor", merge_commit, "main"),
            "",
        )

    def test_state_derives_recovery_if_process_stops_after_exact_merge(self):
        from aiwf_core.core.git_workflow import plan_integration_state
        from aiwf_core.core.plan_integration import finish_plan_integration, prepare_plan_integration
        from aiwf_core.core.state.plan_ops import load_plans

        prepared = prepare_plan_integration(str(self.control), "PLAN-001")
        subprocess.run(
            [
                "git", "merge", "--no-ff", prepared["candidate_ref"],
                "-m", "Merge PLAN-001: interrupted integration",
            ],
            cwd=self.control, check=True, capture_output=True,
        )
        merge_commit = self._git(self.control, "rev-parse", "HEAD")
        interrupted = load_plans(str(self.control))["plans"][0]
        self.assertEqual(
            plan_integration_state(str(self.control), interrupted),
            "closure_recovery",
        )

        result = finish_plan_integration(
            str(self.control), "PLAN-001", status="passed",
            commands=["test -f feature.txt"],
            verification_results=[{
                "command": "test -f feature.txt",
                "expected": "exit 0",
                "observed": "exit 0",
                "matched": True,
            }],
            summary="feature integrated after interruption",
        )
        self.assertTrue(result["closed"])
        self.assertEqual(result["integration"]["merge_commit"], merge_commit)

    def test_rerun_after_full_close_is_idempotent(self):
        from aiwf_core.core.plan_integration import finish_plan_integration, prepare_plan_integration

        prepare_plan_integration(str(self.control), "PLAN-001")
        arguments = {
            "status": "passed",
            "commands": ["test -f feature.txt"],
            "verification_results": [{
                "command": "test -f feature.txt",
                "expected": "exit 0",
                "observed": "exit 0",
                "matched": True,
            }],
            "summary": "feature integrated",
        }
        first = finish_plan_integration(
            str(self.control), "PLAN-001", **arguments,
        )
        head_after_first = self._git(self.control, "rev-parse", "HEAD")
        second = finish_plan_integration(
            str(self.control), "PLAN-001", **arguments,
        )

        self.assertEqual(
            second["integration"]["merge_commit"],
            first["integration"]["merge_commit"],
        )
        self.assertEqual(self._git(self.control, "rev-parse", "HEAD"), head_after_first)
        self.assertFalse(second["governance_checkpoint"]["committed"])

    def test_passing_integration_closes_plan_markdown(self):
        from aiwf_core.core.index_ops import parse_md
        from aiwf_core.core.plan_integration import finish_plan_integration, prepare_plan_integration
        from aiwf_core.core.state.plan_ops import load_plans

        prepare_plan_integration(str(self.control), "PLAN-001")
        doc = self.control / ".aiwf/plans/PLAN-001.md"
        doc.write_text(
            "---\nid: PLAN-001\nstatus: open\n---\n\n"
            "# Feature plan\n\n"
            "## Closure Calibration\n\n"
            "Feature integrated from the verified candidate.\n\n"
            "- Remaining: follow-up belongs to a new Plan.\n",
            encoding="utf-8",
        )
        finish_plan_integration(
            str(self.control), "PLAN-001", status="passed",
            commands=["test -f feature.txt"],
            verification_results=[{
                "command": "test -f feature.txt",
                "expected": "exit 0",
                "observed": "exit 0",
                "matched": True,
            }],
            summary="this command-line text must not replace Plan.md",
        )
        frontmatter, body = parse_md(doc)
        self.assertEqual(frontmatter["status"], "closed")
        self.assertEqual(
            frontmatter["closure_summary"],
            "Feature integrated from the verified candidate.",
        )
        self.assertIn("Remaining: follow-up belongs to a new Plan.", body)
        plan = load_plans(str(self.control))["plans"][0]
        self.assertEqual(
            plan["closure"]["summary"],
            "Feature integrated from the verified candidate.",
        )

    def test_passing_integration_requires_plan_closure_calibration(self):
        from aiwf_core.core.plan_integration import finish_plan_integration, prepare_plan_integration

        prepare_plan_integration(str(self.control), "PLAN-001")
        doc = self.control / ".aiwf/plans/PLAN-001.md"
        doc.write_text(
            "---\nid: PLAN-001\nstatus: open\n---\n\n# Feature plan\n",
            encoding="utf-8",
        )
        head_before = self._git(self.control, "rev-parse", "HEAD")
        with self.assertRaisesRegex(ValueError, "Closure Calibration"):
            finish_plan_integration(
                str(self.control), "PLAN-001", status="passed",
                commands=["test -f feature.txt"],
                verification_results=[{
                    "command": "test -f feature.txt",
                    "expected": "exit 0",
                    "observed": "exit 0",
                    "matched": True,
                }],
                summary="command-line text cannot replace Plan.md",
            )
        self.assertEqual(self._git(self.control, "rev-parse", "HEAD"), head_before)

    def test_failed_integration_uses_failure_summary_without_calibration(self):
        from aiwf_core.core.plan_integration import finish_plan_integration, prepare_plan_integration

        prepare_plan_integration(str(self.control), "PLAN-001")
        doc = self.control / ".aiwf/plans/PLAN-001.md"
        doc.write_text(
            "---\nid: PLAN-001\nstatus: open\n---\n\n# Feature plan\n",
            encoding="utf-8",
        )
        result = finish_plan_integration(
            str(self.control), "PLAN-001", status="failed",
            commands=["test -f missing.txt"],
            verification_results=[{
                "command": "test -f missing.txt",
                "expected": "exit 0",
                "observed": "exit 1",
                "matched": False,
            }],
            summary="candidate is missing the required file",
        )
        self.assertFalse(result["merged"])
        self.assertEqual(
            result["integration"]["summary"],
            "candidate is missing the required file",
        )

    def test_merge_preserves_dirty_control_governance_and_ignores_plan_copy(self):
        from aiwf_core.core.plan_integration import (
            finish_plan_integration,
            prepare_plan_integration,
        )
        from aiwf_core.core.state.plan_ops import load_plans, save_plans

        plan_state = self.worktree / ".aiwf/state/milestones.json"
        plan_state.parent.mkdir(parents=True, exist_ok=True)
        plan_state.write_text('{"updated_at":"stale-plan"}\n', encoding="utf-8")
        subprocess.run(["git", "add", ".aiwf/state/milestones.json"], cwd=self.worktree,
                       check=True)
        subprocess.run(["git", "commit", "-m", "historical plan state"], cwd=self.worktree,
                       check=True, capture_output=True)
        data = load_plans(str(self.control))
        data["plans"][0]["git_head_ref"] = self._git(self.worktree, "rev-parse", "HEAD")
        save_plans(str(self.control), data)

        prepared = prepare_plan_integration(str(self.control), "PLAN-001")
        self.assertNotEqual(
            prepared["candidate_ref"],
            self._git(self.worktree, "rev-parse", "HEAD"),
        )
        candidate_state = subprocess.run(
            ["git", "cat-file", "-e",
             f"{prepared['candidate_ref']}:.aiwf/state/milestones.json"],
            cwd=self.control, capture_output=True,
        )
        self.assertNotEqual(candidate_state.returncode, 0)
        control_state = self.control / ".aiwf/state/milestones.json"
        control_state.write_text('{"updated_at":"current-control"}\n', encoding="utf-8")

        result = finish_plan_integration(
            str(self.control), "PLAN-001", status="passed",
            commands=["test -f feature.txt"],
            verification_results=[{
                "command": "test -f feature.txt",
                "expected": "exit 0",
                "observed": "exit 0",
                "matched": True,
            }],
            summary="project result integrates without replacing governance state",
        )

        self.assertTrue(result["merged"])
        self.assertEqual(
            control_state.read_text(encoding="utf-8"),
            '{"updated_at":"current-control"}\n',
        )
        committed = subprocess.run(
            [
                "git", "cat-file", "-e",
                f"{result['integration']['merge_commit']}:.aiwf/state/milestones.json",
            ],
            cwd=self.control, capture_output=True,
        )
        self.assertNotEqual(committed.returncode, 0)
        self.assertEqual(
            self._git(self.control, "show", "HEAD:.aiwf/state/milestones.json"),
            '{"updated_at":"current-control"}',
        )

    def test_merge_preserves_tracked_control_governance_change(self):
        from aiwf_core.core.plan_integration import (
            finish_plan_integration,
            prepare_plan_integration,
        )
        from aiwf_core.core.state.plan_ops import load_plans, save_plans

        control_state = self.control / ".aiwf/state/milestones.json"
        control_state.write_text('{"updated_at":"committed"}\n', encoding="utf-8")
        subprocess.run(["git", "add", ".aiwf/state/milestones.json"], cwd=self.control,
                       check=True)
        subprocess.run(["git", "commit", "-m", "governance checkpoint"], cwd=self.control,
                       check=True, capture_output=True)

        data = load_plans(str(self.control))
        data["plans"][0]["git_base_ref"] = self._git(self.control, "rev-parse", "HEAD")
        save_plans(str(self.control), data)
        prepare_plan_integration(str(self.control), "PLAN-001")
        control_state.write_text('{"updated_at":"runtime-change"}\n', encoding="utf-8")

        result = finish_plan_integration(
            str(self.control), "PLAN-001", status="passed",
            commands=["test -f feature.txt"],
            verification_results=[{
                "command": "test -f feature.txt",
                "expected": "exit 0",
                "observed": "exit 0",
                "matched": True,
            }],
            summary="tracked governance remains outside the project merge",
        )

        self.assertTrue(result["merged"])
        self.assertEqual(
            control_state.read_text(encoding="utf-8"),
            '{"updated_at":"runtime-change"}\n',
        )
        merged_governance = self._git(
            self.control,
            "show",
            f"{result['integration']['merge_commit']}:.aiwf/state/milestones.json",
        )
        self.assertEqual(merged_governance, '{"updated_at":"committed"}')
        self.assertEqual(
            self._git(self.control, "show", "HEAD:.aiwf/state/milestones.json"),
            '{"updated_at":"runtime-change"}',
        )

    def test_governance_only_merge_conflict_uses_control_state(self):
        from aiwf_core.core.plan_integration import prepare_plan_integration
        from aiwf_core.core.state.plan_ops import load_plans, save_plans

        plan_state = self.worktree / ".aiwf/state/milestones.json"
        plan_state.parent.mkdir(parents=True, exist_ok=True)
        plan_state.write_text('{"owner":"plan"}\n', encoding="utf-8")
        subprocess.run(
            ["git", "add", ".aiwf/state/milestones.json"],
            cwd=self.worktree, check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "plan governance copy"],
            cwd=self.worktree, check=True, capture_output=True,
        )
        data = load_plans(str(self.control))
        data["plans"][0]["git_head_ref"] = self._git(
            self.worktree, "rev-parse", "HEAD",
        )
        save_plans(str(self.control), data)

        control_state = self.control / ".aiwf/state/milestones.json"
        control_state.parent.mkdir(parents=True, exist_ok=True)
        control_state.write_text('{"owner":"control"}\n', encoding="utf-8")
        subprocess.run(
            ["git", "add", ".aiwf/state/milestones.json"],
            cwd=self.control, check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "control governance state"],
            cwd=self.control, check=True, capture_output=True,
        )

        prepared = prepare_plan_integration(str(self.control), "PLAN-001")

        self.assertTrue(prepared["prepared"], prepared)
        self.assertFalse(prepared["conflict"])
        self.assertEqual(
            self._git(
                self.control, "show",
                f"{prepared['candidate_ref']}:.aiwf/state/milestones.json",
            ),
            '{"owner":"control"}',
        )

    def test_already_merged_plan_can_adopt_and_verify_current_base(self):
        from aiwf_core.core.git_workflow import plan_integration_state
        from aiwf_core.core.plan_integration import finish_plan_integration, prepare_plan_integration
        from aiwf_core.core.state.plan_ops import load_plans

        subprocess.run(
            ["git", "merge", "--no-ff", "aiwf/plan-001", "-m", "manual merge"],
            cwd=self.control, check=True, capture_output=True,
        )
        merged_head = self._git(self.control, "rev-parse", "HEAD")
        plan = load_plans(str(self.control))["plans"][0]
        self.assertEqual(plan_integration_state(str(self.control), plan), "merged_unverified")

        prepared = prepare_plan_integration(str(self.control), "PLAN-001")
        self.assertTrue(prepared["already_merged"])
        self.assertTrue(prepared["governance_checkpoint"]["committed"])
        self.assertNotEqual(prepared["candidate_ref"], merged_head)
        self.assertTrue(
            self._git(
                self.control, "merge-base", "--is-ancestor",
                merged_head, prepared["candidate_ref"],
            ) == ""
        )
        self.assertEqual(Path(prepared["candidate_worktree"]).resolve(), self.control.resolve())
        plan = load_plans(str(self.control))["plans"][0]
        self.assertEqual(plan_integration_state(str(self.control), plan), "integration_ready")

        result = finish_plan_integration(
            str(self.control), "PLAN-001", status="passed",
            commands=["test -f feature.txt"],
            verification_results=[{
                "command": "test -f feature.txt", "expected": "exit 0",
                "observed": "exit 0", "matched": True,
            }],
            summary="adopted merged result verified",
        )
        self.assertEqual(result["integration"]["merge_commit"], prepared["candidate_ref"])
        plan = load_plans(str(self.control))["plans"][0]
        self.assertEqual(plan_integration_state(str(self.control), plan), "closed")

    def test_conflict_preflight_does_not_dirty_either_worktree(self):
        from aiwf_core.core.plan_integration import prepare_plan_integration
        from aiwf_core.core.state.plan_ops import load_plans, save_plans
        from aiwf_core.core.task_ledger import activate_task, load_ledger, upsert_task

        # Replace the feature commit with an overlapping change and update the governed head.
        (self.worktree / "app.txt").write_text("plan\n", encoding="utf-8")
        subprocess.run(["git", "add", "app.txt"], cwd=self.worktree, check=True)
        subprocess.run(["git", "commit", "-m", "TASK-002: overlap"], cwd=self.worktree,
                       check=True, capture_output=True)
        data = load_plans(str(self.control))
        data["plans"][0]["git_head_ref"] = self._git(self.worktree, "rev-parse", "HEAD")
        data["plans"][0]["task_status"]["TASK-002"] = "closed"
        save_plans(str(self.control), data)
        (self.control / "app.txt").write_text("main\n", encoding="utf-8")
        subprocess.run(["git", "add", "app.txt"], cwd=self.control, check=True)
        subprocess.run(["git", "commit", "-m", "main overlap"], cwd=self.control,
                       check=True, capture_output=True)

        base_before = self._git(self.control, "rev-parse", "HEAD")
        plan_before = self._git(self.worktree, "rev-parse", "HEAD")
        result = prepare_plan_integration(str(self.control), "PLAN-001")
        self.assertTrue(result["conflict"])
        self.assertTrue(result["governance_checkpoint"]["committed"])
        checkpoint_head = self._git(self.control, "rev-parse", "HEAD")
        self.assertNotEqual(checkpoint_head, base_before)
        self.assertEqual(
            self._git(self.control, "diff", "--name-only", f"{base_before}..{checkpoint_head}"),
            ".aiwf/state/plans.json",
        )
        self.assertEqual(self._git(self.worktree, "rev-parse", "HEAD"), plan_before)
        self.assertEqual(subprocess.run(
            ["git", "rev-parse", "-q", "--verify", "MERGE_HEAD"], cwd=self.control,
            capture_output=True,
        ).returncode, 1)
        self.assertEqual(subprocess.run(
            ["git", "rev-parse", "-q", "--verify", "MERGE_HEAD"], cwd=self.worktree,
            capture_output=True,
        ).returncode, 1)
        plan = load_plans(str(self.control))["plans"][0]
        self.assertEqual(plan["integration"]["status"], "conflict")

        upsert_task(
            str(self.control), "TASK-INTEGRATE", status="ready",
            plan_id="PLAN-001", kind="integration",
        )
        _write_valid_task_contract(self.control, "TASK-INTEGRATE")
        plan = load_plans(str(self.control))["plans"][0]
        self.assertEqual(plan["integration"]["status"], "conflict")
        activated = activate_task(str(self.control), "TASK-INTEGRATE")
        self.assertTrue(activated["activated"], activated["blockers"])
        task = next(
            item for item in load_ledger(str(self.control))["tasks"]
            if item["id"] == "TASK-INTEGRATE"
        )
        self.assertEqual(task["integration_base_ref"], result["base_ref"])
        self.assertEqual(task["integration_plan_ref"], result["plan_ref"])

    def test_pending_integration_task_can_refresh_governance_only_head_change(self):
        from aiwf_core.core.plan_integration import prepare_plan_integration
        from aiwf_core.core.state.plan_ops import load_plans, save_plans
        from aiwf_core.core.task_ledger import (
            load_ledger,
            record_task_activation_critique,
            upsert_task,
        )

        (self.worktree / "app.txt").write_text("plan\n", encoding="utf-8")
        subprocess.run(["git", "add", "app.txt"], cwd=self.worktree, check=True)
        subprocess.run(
            ["git", "commit", "-m", "TASK-002: overlap"],
            cwd=self.worktree, check=True, capture_output=True,
        )
        data = load_plans(str(self.control))
        data["plans"][0]["git_head_ref"] = self._git(
            self.worktree, "rev-parse", "HEAD",
        )
        data["plans"][0]["task_status"]["TASK-002"] = "closed"
        save_plans(str(self.control), data)
        (self.control / "app.txt").write_text("main\n", encoding="utf-8")
        subprocess.run(["git", "add", "app.txt"], cwd=self.control, check=True)
        subprocess.run(
            ["git", "commit", "-m", "main overlap"],
            cwd=self.control, check=True, capture_output=True,
        )
        first = prepare_plan_integration(str(self.control), "PLAN-001")
        self.assertTrue(first["conflict"])

        upsert_task(
            str(self.control), "TASK-INTEGRATE", status="ready",
            plan_id="PLAN-001", kind="integration",
        )
        _write_valid_task_contract(self.control, "TASK-INTEGRATE")
        record_task_activation_critique(str(self.control), "TASK-INTEGRATE")
        record_task_activation_critique(str(self.control), "TASK-INTEGRATE")

        note = self.worktree / ".aiwf/notes/preflight.md"
        note.parent.mkdir(parents=True, exist_ok=True)
        note.write_text("updated contract context\n", encoding="utf-8")
        subprocess.run(
            ["git", "add", ".aiwf/notes/preflight.md"],
            cwd=self.worktree, check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "update integration governance"],
            cwd=self.worktree, check=True, capture_output=True,
        )
        new_head = self._git(self.worktree, "rev-parse", "HEAD")

        refreshed = prepare_plan_integration(str(self.control), "PLAN-001")

        self.assertTrue(refreshed["conflict"])
        self.assertTrue(refreshed["head_refreshed"])
        self.assertEqual(refreshed["plan_ref"], new_head)
        self.assertEqual(refreshed["integration_task_id"], "TASK-INTEGRATE")
        self.assertEqual(
            refreshed["critique_reset_task_ids"], ["TASK-INTEGRATE"],
        )
        task = next(
            item for item in load_ledger(str(self.control))["tasks"]
            if item["id"] == "TASK-INTEGRATE"
        )
        self.assertEqual(task["activation_critique_count"], 0)
        plan = load_plans(str(self.control))["plans"][0]
        self.assertEqual(plan["git_head_ref"], new_head)
        self.assertEqual(plan["integration"]["plan_ref"], new_head)

    def test_pending_integration_task_head_change_is_inspected_without_ref_override(self):
        from aiwf_core.core.plan_integration import prepare_plan_integration
        from aiwf_core.core.state.plan_ops import load_plans, save_plans
        from aiwf_core.core.task_ledger import upsert_task

        (self.worktree / "app.txt").write_text("plan\n", encoding="utf-8")
        subprocess.run(["git", "add", "app.txt"], cwd=self.worktree, check=True)
        subprocess.run(
            ["git", "commit", "-m", "TASK-002: overlap"],
            cwd=self.worktree, check=True, capture_output=True,
        )
        data = load_plans(str(self.control))
        data["plans"][0]["git_head_ref"] = self._git(
            self.worktree, "rev-parse", "HEAD",
        )
        data["plans"][0]["task_status"]["TASK-002"] = "closed"
        save_plans(str(self.control), data)
        (self.control / "app.txt").write_text("main\n", encoding="utf-8")
        subprocess.run(["git", "add", "app.txt"], cwd=self.control, check=True)
        subprocess.run(
            ["git", "commit", "-m", "main overlap"],
            cwd=self.control, check=True, capture_output=True,
        )
        first = prepare_plan_integration(str(self.control), "PLAN-001")
        self.assertTrue(first["conflict"])
        upsert_task(
            str(self.control), "TASK-INTEGRATE", status="ready",
            plan_id="PLAN-001", kind="integration",
        )
        _write_valid_task_contract(self.control, "TASK-INTEGRATE")

        (self.worktree / "external.txt").write_text("external\n", encoding="utf-8")
        subprocess.run(["git", "add", "external.txt"], cwd=self.worktree, check=True)
        subprocess.run(
            ["git", "commit", "-m", "external project change"],
            cwd=self.worktree, check=True, capture_output=True,
        )

        accepted = prepare_plan_integration(str(self.control), "PLAN-001")
        self.assertTrue(accepted["conflict"])
        self.assertTrue(accepted["head_refreshed"])

    def test_suspended_integration_task_can_refresh_stale_preflight(self):
        from aiwf_core.core.plan_integration import prepare_plan_integration
        from aiwf_core.core.state.plan_ops import load_plans, save_plans
        from aiwf_core.core.task_ledger import (
            load_ledger,
            record_task_activation_critique,
            upsert_task,
        )

        (self.worktree / "app.txt").write_text("plan\n", encoding="utf-8")
        subprocess.run(["git", "add", "app.txt"], cwd=self.worktree, check=True)
        subprocess.run(
            ["git", "commit", "-m", "TASK-002: overlap"],
            cwd=self.worktree, check=True, capture_output=True,
        )
        data = load_plans(str(self.control))
        data["plans"][0]["git_head_ref"] = self._git(
            self.worktree, "rev-parse", "HEAD",
        )
        data["plans"][0]["task_status"]["TASK-002"] = "closed"
        save_plans(str(self.control), data)
        (self.control / "app.txt").write_text("main\n", encoding="utf-8")
        subprocess.run(["git", "add", "app.txt"], cwd=self.control, check=True)
        subprocess.run(
            ["git", "commit", "-m", "main overlap"],
            cwd=self.control, check=True, capture_output=True,
        )
        first = prepare_plan_integration(str(self.control), "PLAN-001")
        self.assertTrue(first["conflict"])

        upsert_task(
            str(self.control), "TASK-INTEGRATE", status="suspended",
            plan_id="PLAN-001", kind="integration",
        )
        _write_valid_task_contract(self.control, "TASK-INTEGRATE")
        record_task_activation_critique(str(self.control), "TASK-INTEGRATE")
        record_task_activation_critique(str(self.control), "TASK-INTEGRATE")

        (self.worktree / "fix.txt").write_text("resolved\n", encoding="utf-8")
        subprocess.run(["git", "add", "fix.txt"], cwd=self.worktree, check=True)
        subprocess.run(
            ["git", "commit", "-m", "TASK-INTEGRATE: partial resolution"],
            cwd=self.worktree, check=True, capture_output=True,
        )
        new_head = self._git(self.worktree, "rev-parse", "HEAD")

        refreshed = prepare_plan_integration(str(self.control), "PLAN-001")

        self.assertEqual(refreshed["integration_task_id"], "TASK-INTEGRATE")
        self.assertTrue(refreshed["head_refreshed"])
        self.assertEqual(refreshed["plan_ref"], new_head)
        task = next(
            item for item in load_ledger(str(self.control))["tasks"]
            if item["id"] == "TASK-INTEGRATE"
        )
        self.assertEqual(task["activation_critique_count"], 0)

    def test_dirty_base_enters_soft_audit_before_candidate(self):
        from aiwf_core.core.event_model import NormalizedEvent
        from aiwf_core.core.plan_integration import prepare_plan_integration
        from aiwf_core.hooks.common.scope_checker import check_file_write

        (self.control / "local.txt").write_text("uncommitted\n", encoding="utf-8")
        audited = prepare_plan_integration(str(self.control), "PLAN-001")
        self.assertTrue(audited["audit_required"])
        self.assertFalse(audited["prepared"])
        self.assertIn("local.txt", audited["audit"]["base"]["changes"])
        allowed = check_file_write(NormalizedEvent(
            engine="claude", event_type="pre_tool_use", cwd=str(self.control),
            tool_name="Edit", tool_input={"file_path": str(self.control / "local.txt")},
            agent_type="planner-main",
        ))
        self.assertTrue(allowed.allowed)

        (self.control / "local.txt").unlink()
        prepared = prepare_plan_integration(str(self.control), "PLAN-001")
        self.assertTrue(prepared["prepared"])

    def test_ds_store_before_prepare_is_repairable_without_a_task(self):
        from aiwf_core.core.event_model import NormalizedEvent
        from aiwf_core.core.plan_integration import prepare_plan_integration
        from aiwf_core.hooks.common.scope_checker import check_file_write

        residue = self.worktree / ".DS_Store"
        residue.write_text("local residue\n", encoding="utf-8")
        allowed = check_file_write(NormalizedEvent(
            engine="claude", event_type="pre_tool_use", cwd=str(self.worktree),
            tool_name="Edit", tool_input={"file_path": ".DS_Store"},
            agent_type="planner-main",
        ))
        self.assertTrue(allowed.allowed)

        audited = prepare_plan_integration(str(self.control), "PLAN-001")
        self.assertTrue(audited["audit_required"])
        self.assertIn(".DS_Store", audited["audit"]["plan"]["untracked"])

        residue.unlink()
        prepared = prepare_plan_integration(str(self.control), "PLAN-001")
        self.assertTrue(prepared["prepared"])

    def test_ignored_assets_and_empty_directories_are_visible_but_soft(self):
        from aiwf_core.core.plan_integration import prepare_plan_integration
        from aiwf_core.core.state.plan_ops import load_plans, save_plans

        (self.worktree / ".gitignore").write_text("local-cache/\n", encoding="utf-8")
        subprocess.run(["git", "add", ".gitignore"], cwd=self.worktree, check=True)
        subprocess.run(
            ["git", "commit", "-m", "TASK-002: define local cache"],
            cwd=self.worktree, check=True, capture_output=True,
        )
        plans = load_plans(str(self.control))
        plans["plans"][0]["git_head_ref"] = self._git(self.worktree, "rev-parse", "HEAD")
        plans["plans"][0]["task_status"]["TASK-002"] = "closed"
        save_plans(str(self.control), plans)
        (self.worktree / "local-cache").mkdir()
        (self.worktree / "local-cache/artifact.bin").write_bytes(b"ignored")
        (self.worktree / "skeleton/empty").mkdir(parents=True)

        prepared = prepare_plan_integration(str(self.control), "PLAN-001")

        self.assertTrue(prepared["prepared"])
        self.assertIn("local-cache/", prepared["audit"]["plan"]["ignored"])
        self.assertIn("skeleton/empty", prepared["audit"]["plan"]["empty_directories"])

    def test_plan_proof_pairs_results_by_order_not_repeated_command_text(self):
        from aiwf_core.core.plan_integration import (
            finish_plan_integration,
            prepare_plan_integration,
        )

        prepare_plan_integration(str(self.control), "PLAN-001")
        result = finish_plan_integration(
            str(self.control), "PLAN-001", status="passed",
            commands=['printf "%s\\n" "feature ready"'],
            verification_results=[{
                "command": "printf '%s\\n' 'feature ready'",
                "expected": "feature ready",
                "observed": "feature ready",
                "matched": True,
            }],
            summary="",
        )

        self.assertTrue(result["closed"])
        self.assertEqual(
            result["integration"]["verification_results"][0]["command"],
            'printf "%s\\n" "feature ready"',
        )

    def test_integration_task_close_creates_the_reviewed_merge_commit(self):
        from aiwf_core.core.plan_integration import prepare_plan_integration
        from aiwf_core.core.state.context_ops import record_implementation
        from aiwf_core.core.state.plan_ops import load_plans, save_plans
        from aiwf_core.core.state.review_ops import record_review
        from aiwf_core.core.state.testing_ops import record_testing
        from aiwf_core.core.task_ledger import close_task

        (self.worktree / "app.txt").write_text("plan\n", encoding="utf-8")
        subprocess.run(["git", "add", "app.txt"], cwd=self.worktree, check=True)
        subprocess.run(["git", "commit", "-m", "TASK-002: overlap"], cwd=self.worktree,
                       check=True, capture_output=True)
        plan_ref = self._git(self.worktree, "rev-parse", "HEAD")
        data = load_plans(str(self.control))
        data["plans"][0]["git_head_ref"] = plan_ref
        data["plans"][0]["task_status"]["TASK-002"] = "closed"
        save_plans(str(self.control), data)
        (self.control / "app.txt").write_text("main\n", encoding="utf-8")
        subprocess.run(["git", "add", "app.txt"], cwd=self.control, check=True)
        subprocess.run(["git", "commit", "-m", "main overlap"], cwd=self.control,
                       check=True, capture_output=True)
        conflict = prepare_plan_integration(str(self.control), "PLAN-001")
        base_ref = conflict["base_ref"]

        tasks_path = self.control / ".aiwf/state/tasks.json"
        tasks_path.write_text(json.dumps({
            "schema_version": 1,
            "tasks": [{
                "id": "TASK-INTEGRATE",
                "title": "Resolve Plan integration",
                "status": "active",
                "phase": "implementing",
                "kind": "integration",
                "plan_id": "PLAN-001",
                "worktree_path": str(self.worktree),
                "git_branch": "aiwf/plan-001",
                "git_origin_ref": plan_ref,
                "integration_plan_ref": plan_ref,
                "integration_base_ref": base_ref,
                "requirements": {
                    "executor_required": True,
                    "tester_required": True,
                    "reviewer_required": True,
                },
            }],
        }, indent=2) + "\n", encoding="utf-8")
        _write_valid_task_contract(self.control, "TASK-INTEGRATE")
        data = load_plans(str(self.control))
        data["plans"][0]["task_ids"].append("TASK-INTEGRATE")
        data["plans"][0]["task_status"]["TASK-INTEGRATE"] = "active"
        save_plans(str(self.control), data)

        merge = subprocess.run(["git", "merge", "--no-commit", base_ref], cwd=self.worktree,
                               capture_output=True, text=True)
        self.assertNotEqual(merge.returncode, 0)
        (self.worktree / "app.txt").write_text("main + plan\n", encoding="utf-8")
        implementation = record_implementation(
            str(self.worktree), "resolved both behaviors", command="cat app.txt",
            task_id="TASK-INTEGRATE",
        )
        testing = record_testing(
            str(self.worktree), status="passed", commands=["grep -q 'main + plan' app.txt"],
            coverage_summary="combined behavior present",
            verification_results=[{
                "command": "grep -q 'main + plan' app.txt", "expected": "exit 0",
                "observed": "exit 0", "matched": True,
            }], task_id="TASK-INTEGRATE",
        )
        review = record_review(
            str(self.worktree), result="accepted", closure_allowed=True,
            summary="reviewed combined behavior", task_id="TASK-INTEGRATE",
        )
        self.assertEqual(review["reviewed_ref"], testing["tested_ref"])
        self.assertNotEqual(implementation["implementation_ref"], plan_ref)

        result = close_task(str(self.worktree), "TASK-INTEGRATE")
        self.assertTrue(result["closed"], result["blockers"])
        commit = result["task"]["closure"]["git_commit"]
        parents = self._git(self.worktree, "show", "-s", "--format=%P", commit).split()
        self.assertEqual(parents, [plan_ref, base_ref])
        self.assertEqual((self.worktree / "app.txt").read_text(), "main + plan\n")
        plan = load_plans(str(self.control))["plans"][0]
        self.assertEqual(plan["git_head_ref"], commit)
        self.assertNotIn("integration", plan)


if __name__ == "__main__":
    unittest.main()
