import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from aiwf_core.core.git_workflow import bind_plan_worktree
from aiwf_core.core.event_model import NormalizedEvent
from aiwf_core.core.state.plan_ops import (
    add_plan_dependency,
    load_plans,
    save_plans,
    upsert_plan,
)
from aiwf_core.core.task_ledger import activate_task, load_ledger, upsert_task
from aiwf_core.hooks.common.scope_checker import check_bash, check_file_write


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class TestTaskParallelContract(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aiwf_task_parallel_"))
        subprocess.run(
            ["git", "init", "-b", "main"], cwd=self.tmp,
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=self.tmp, check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "AIWF Test"],
            cwd=self.tmp, check=True,
        )
        (self.tmp / "seed.txt").write_text("seed\n", encoding="utf-8")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", "install", "claude", "--force"],
            cwd=self.tmp, env=env, check=True, capture_output=True, text=True,
        )
        subprocess.run(["git", "add", "-A"], cwd=self.tmp, check=True)
        subprocess.run(
            ["git", "commit", "-m", "seed"], cwd=self.tmp,
            check=True, capture_output=True,
        )
        self.worktree_a = self.tmp / ".claude/worktrees/plan-a"
        self.worktree_b = self.tmp / ".claude/worktrees/plan-b"
        self.worktree_a.parent.mkdir(parents=True)
        subprocess.run(
            ["git", "worktree", "add", "-b", "plan/a", str(self.worktree_a)],
            cwd=self.tmp, check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "worktree", "add", "-b", "plan/b", str(self.worktree_b)],
            cwd=self.tmp, check=True, capture_output=True,
        )

        upsert_plan(str(self.tmp), "PLAN-A")
        upsert_plan(str(self.tmp), "PLAN-B")
        plans = load_plans(str(self.tmp))
        for plan in plans["plans"]:
            plan_id = plan.get("plan_id") or plan.get("id")
            target = self.worktree_a if plan_id == "PLAN-A" else self.worktree_b
            bind_plan_worktree(str(self.tmp), plan, target)
        save_plans(str(self.tmp), plans)

        upsert_task(str(self.tmp), "TASK-A1", status="ready", plan_id="PLAN-A")
        upsert_task(str(self.tmp), "TASK-A2", status="ready", plan_id="PLAN-A")
        upsert_task(str(self.tmp), "TASK-B1", status="ready", plan_id="PLAN-B")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_different_plan_worktrees_can_activate_together(self):
        from aiwf_core.core.temporary_access import (
            enable_temporary_ai_writes,
            temporary_ai_writes_enabled,
        )

        enable_temporary_ai_writes(self.tmp)
        self.assertTrue(temporary_ai_writes_enabled(self.tmp))
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(
                lambda task_id: activate_task(str(self.tmp), task_id),
                ("TASK-A1", "TASK-B1"),
            ))

        self.assertTrue(all(result["activated"] for result in results), results)
        self.assertFalse(temporary_ai_writes_enabled(self.tmp))
        active = {
            task["id"]: task["worktree_path"]
            for task in load_ledger(str(self.tmp))["tasks"]
            if task["status"] == "active"
        }
        self.assertEqual(active, {
            "TASK-A1": str(self.worktree_a.resolve()),
            "TASK-B1": str(self.worktree_b.resolve()),
        })
        state = json.loads((self.tmp / ".aiwf/state/state.json").read_text())
        self.assertNotIn("active_task_id", state)
        self.assertTrue((self.tmp / ".aiwf/records/tasks/TASK-A1.json").exists())
        self.assertTrue((self.tmp / ".aiwf/records/tasks/TASK-B1.json").exists())

    def test_plan_worktree_create_is_idempotent_and_keeps_control_root_clean(self):
        upsert_plan(str(self.tmp), "PLAN-C")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        command = [
            sys.executable, "-m", "aiwf_core.cli",
            "plan", "bind-worktree", "PLAN-C", "--create",
        ]

        created = subprocess.run(
            command, cwd=self.tmp, env=env, capture_output=True, text=True,
        )
        reused = subprocess.run(
            command, cwd=self.tmp, env=env, capture_output=True, text=True,
        )

        self.assertEqual(created.returncode, 0, created.stderr)
        self.assertIn("Action: created", created.stdout)
        self.assertEqual(reused.returncode, 0, reused.stderr)
        self.assertIn("Action: reused", reused.stdout)
        plan = next(
            item for item in load_plans(str(self.tmp))["plans"]
            if item.get("plan_id") == "PLAN-C"
        )
        expected = self.tmp / ".claude/worktrees/plan-c"
        self.assertEqual(Path(plan["git_worktree_path"]), expected.resolve())
        self.assertEqual(plan["git_branch"], "aiwf/plan-c")
        self.assertTrue(expected.is_dir())
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=self.tmp, check=True, capture_output=True, text=True,
        ).stdout
        self.assertNotIn(".claude/worktrees", status)

    def test_opencode_session_uses_its_own_worktree_directory_when_hosts_coexist(self):
        plugin = self.tmp / ".opencode/plugins/aiwf.js"
        plugin.parent.mkdir(parents=True)
        plugin.write_text("export const AIWFPlugin = async () => ({})\n", encoding="utf-8")
        subprocess.run(["git", "add", str(plugin)], cwd=self.tmp, check=True)
        subprocess.run(
            ["git", "commit", "-m", "add opencode adapter"],
            cwd=self.tmp, check=True, capture_output=True,
        )
        upsert_plan(str(self.tmp), "PLAN-OPEN")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        env["AIWF_HOST"] = "opencode"

        created = subprocess.run(
            [
                sys.executable, "-m", "aiwf_core.cli",
                "plan", "bind-worktree", "PLAN-OPEN", "--create",
            ],
            cwd=self.tmp, env=env, capture_output=True, text=True,
        )

        self.assertEqual(created.returncode, 0, created.stderr)
        plan = next(
            item for item in load_plans(str(self.tmp))["plans"]
            if item.get("plan_id") == "PLAN-OPEN"
        )
        expected = self.tmp / ".opencode/worktrees/plan-open"
        self.assertEqual(Path(plan["git_worktree_path"]), expected.resolve())
        self.assertTrue(expected.is_dir())

    def test_public_bind_does_not_turn_control_root_into_plan_worktree(self):
        upsert_plan(str(self.tmp), "PLAN-CONTROL")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)

        result = subprocess.run(
            [
                sys.executable, "-m", "aiwf_core.cli", "plan", "bind-worktree",
                "PLAN-CONTROL", ".",
            ],
            cwd=self.tmp, env=env, capture_output=True, text=True,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("control root is for Planner", result.stderr)
        self.assertIn(
            "aiwf plan bind-worktree PLAN-CONTROL --create",
            result.stderr,
        )

    def test_unbound_plan_activation_routes_to_one_create_command(self):
        upsert_plan(str(self.tmp), "PLAN-UNBOUND")
        upsert_task(str(self.tmp), "TASK-UNBOUND", status="ready", plan_id="PLAN-UNBOUND")

        result = activate_task(str(self.tmp), "TASK-UNBOUND")

        self.assertFalse(result["activated"])
        blockers = " ".join(result["blockers"])
        self.assertIn(
            "aiwf plan bind-worktree PLAN-UNBOUND --create",
            blockers,
        )
        self.assertNotIn("protected branch", blockers)

    def test_linked_worktree_uses_control_root_memory_for_status_and_doctor(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        status = subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", "status", "--prompt"],
            cwd=self.worktree_a, env=env, capture_output=True, text=True,
        )
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn(
            f"Planner memory root: {self.tmp.resolve() / '.aiwf/memory'}",
            status.stdout,
        )
        self.assertIn("Planner memory snapshot:", status.stdout)
        self.assertIn("[Memory Review](notes/memory-layer.md)", status.stdout)

        index_path = self.tmp / ".aiwf/memory/MEMORY.md"
        original = index_path.read_text(encoding="utf-8")
        try:
            index_path.write_text(
                original + "\n- [Missing](notes/control-root-only.md) - missing\n",
                encoding="utf-8",
            )
            doctor = subprocess.run(
                [sys.executable, "-m", "aiwf_core.cli", "doctor"],
                cwd=self.worktree_a, env=env, capture_output=True, text=True,
            )
            self.assertIn("WARN memory:", doctor.stdout)
            self.assertIn("control-root-only.md", doctor.stdout)
        finally:
            index_path.write_text(original, encoding="utf-8")

    def test_status_and_ui_show_all_active_plan_worktrees(self):
        self.assertTrue(activate_task(str(self.tmp), "TASK-A1")["activated"])
        self.assertTrue(activate_task(str(self.tmp), "TASK-B1")["activated"])

        from aiwf_core.core.task_records import load_task_record, save_task_record

        record_b = load_task_record(self.tmp, "TASK-B1")
        record_b["implementation"]["implementation_ref"] = "implementation-b"
        save_task_record(self.tmp, record_b)

        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        status = subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", "status", "--prompt"],
            cwd=self.tmp, env=env, capture_output=True, text=True, check=True,
        ).stdout
        self.assertIn("TASK-A1", status)
        self.assertIn(str(self.worktree_a.resolve()), status)
        self.assertIn("TASK-B1", status)
        self.assertIn(str(self.worktree_b.resolve()), status)
        self.assertIn("next=Executor", status)
        self.assertIn("next=Tester", status)
        self.assertIn("Independent Plans may run in parallel", status)
        self.assertNotIn("Before starting another Plan", status)
        self.assertIn("Required skills: /aiwf-implement, /aiwf-test", status)

        status_from_plan_a = subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", "status", "--prompt"],
            cwd=self.worktree_a, env=env, capture_output=True, text=True, check=True,
        ).stdout
        self.assertIn("TASK-A1 [current]", status_from_plan_a)
        self.assertIn("TASK-B1", status_from_plan_a)
        self.assertIn("next=Tester", status_from_plan_a)
        self.assertIn(str(self.worktree_b.resolve()), status_from_plan_a)

        from aiwf_core.aiwf_ui import build_tree, load_all

        data = load_all(self.tmp)
        active_nodes = {
            node["id"] for node in build_tree(data)
            if node.get("kind") == "task" and node.get("active")
        }
        self.assertEqual(active_nodes, {"TASK-A1", "TASK-B1"})
        self.assertEqual(
            set(data["task_records"]), {"TASK-A1", "TASK-B1"}
        )

    def test_status_advances_ready_plan_while_another_agent_runs(self):
        from aiwf_core.core.agent_runtime import start_dispatch
        from aiwf_core.core.task_records import load_task_record, save_task_record

        self.assertTrue(activate_task(str(self.tmp), "TASK-A1")["activated"])
        self.assertTrue(activate_task(str(self.tmp), "TASK-B1")["activated"])
        record_b = load_task_record(self.tmp, "TASK-B1")
        record_b["implementation"]["implementation_ref"] = "implementation-b"
        save_task_record(self.tmp, record_b)
        self.assertFalse(start_dispatch(
            self.tmp,
            "TASK-A1",
            "aiwf-executor",
            "parallel-session",
            "PLAN-A",
            str(self.worktree_a),
        ))

        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        status = subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", "status", "--prompt"],
            cwd=self.tmp, env=env, capture_output=True, text=True, check=True,
        ).stdout

        self.assertIn("advance the ready Tasks below now", status)
        self.assertIn("Do not wait for Agents in other Plan worktrees", status)
        self.assertLess(status.index("- TASK-B1"), status.index("- TASK-A1"))
        self.assertIn("TASK-A1", status)
        self.assertIn("next=Agent running", status)
        self.assertIn("TASK-B1", status)
        self.assertIn("next=Tester", status)

    def test_two_plan_worktrees_complete_independent_task_chains(self):
        from aiwf_core.core.state.context_ops import record_implementation
        from aiwf_core.core.state.review_ops import record_review
        from aiwf_core.core.state.testing_ops import record_testing
        from aiwf_core.core.task_ledger import close_task
        from aiwf_core.core.task_records import load_task_record

        self.assertTrue(activate_task(str(self.tmp), "TASK-A1")["activated"])
        self.assertTrue(activate_task(str(self.tmp), "TASK-B1")["activated"])
        (self.worktree_a / "feature-a.txt").write_text("A\n", encoding="utf-8")
        (self.worktree_b / "feature-b.txt").write_text("B\n", encoding="utf-8")

        for task_id, worktree, filename in (
            ("TASK-A1", self.worktree_a, "feature-a.txt"),
            ("TASK-B1", self.worktree_b, "feature-b.txt"),
        ):
            record_implementation(
                str(worktree), f"implemented {filename}", task_id=task_id,
            )
            record_testing(
                str(worktree), status="passed",
                commands=[f"test -f {filename}"],
                coverage_summary=f"{filename} exists",
                verification_results=[{
                    "command": f"test -f {filename}",
                    "expected": "exit 0",
                    "observed": "exit 0",
                    "matched": True,
                }],
                task_id=task_id,
            )
            record_review(
                str(worktree), result="accepted", closure_allowed=True,
                summary=f"{filename} is isolated and verified",
                task_id=task_id,
            )
            closed = close_task(str(worktree), task_id=task_id)
            self.assertTrue(closed["closed"], closed["blockers"])

        ledger = load_ledger(str(self.tmp))
        self.assertEqual(
            {task["id"]: task["status"] for task in ledger["tasks"]
             if task["id"] in {"TASK-A1", "TASK-B1"}},
            {"TASK-A1": "closed", "TASK-B1": "closed"},
        )
        refs = {
            task_id: load_task_record(self.tmp, task_id)["review"]["reviewed_ref"]
            for task_id in ("TASK-A1", "TASK-B1")
        }
        self.assertTrue(all(refs.values()))
        self.assertNotEqual(refs["TASK-A1"], refs["TASK-B1"])

    def test_planner_can_resolve_other_plan_fix_loop_by_task_id(self):
        from aiwf_core.core.state.fixloop_ops import open_fix_loop, resolve_fix_loop

        self.assertTrue(activate_task(str(self.tmp), "TASK-A1")["activated"])
        self.assertTrue(activate_task(str(self.tmp), "TASK-B1")["activated"])
        opened = open_fix_loop(
            str(self.tmp), route="planner", reason="needs a Planner decision",
            source="executor", task_id="TASK-B1",
        )
        self.assertEqual(opened["status"], "open")

        resolved = resolve_fix_loop(
            str(self.tmp), resolution="Planner confirmed the existing contract",
            source="planner", task_id="TASK-B1",
        )

        self.assertEqual(resolved["status"], "resolved")

    def test_suspended_task_reactivates_with_its_open_fix_loop(self):
        from aiwf_core.core.state.fixloop_ops import open_fix_loop
        from aiwf_core.core.task_ledger import interrupt_task
        from aiwf_core.core.task_records import load_task_record

        self.assertTrue(activate_task(str(self.tmp), "TASK-A1")["activated"])
        open_fix_loop(
            str(self.worktree_a), route="executor", reason="repair the real defect",
            required_fixes=["fix feature-a.txt"], task_id="TASK-A1",
        )
        interrupted = interrupt_task(
            str(self.worktree_a), reason="human paused the task", task_id="TASK-A1",
        )
        self.assertTrue(interrupted["interrupted"])

        resumed = activate_task(str(self.tmp), "TASK-A1")

        self.assertTrue(resumed["activated"], resumed["blockers"])
        self.assertEqual(resumed["task"]["status"], "active")
        self.assertEqual(
            load_task_record(self.tmp, "TASK-A1")["fix_loop"]["route"], "executor",
        )

    def test_suspended_task_adopts_changed_head_only_after_explicit_flag(self):
        from aiwf_core.core.state.fixloop_ops import open_fix_loop
        from aiwf_core.core.task_ledger import interrupt_task
        from aiwf_core.core.task_records import load_task_record, save_task_record

        self.assertTrue(activate_task(str(self.tmp), "TASK-A1")["activated"])
        open_fix_loop(
            str(self.worktree_a), route="executor", reason="repair the real defect",
            required_fixes=["fix feature-a.txt"], task_id="TASK-A1",
        )
        record = load_task_record(self.tmp, "TASK-A1")
        record["review"]["adversarial_observations"] = [{
            "id": "ADV-001", "severity": "warn", "kind": "edge",
            "message": "preserve this finding", "disposition": "pending",
        }]
        save_task_record(self.tmp, record)
        self.assertTrue(interrupt_task(
            str(self.worktree_a), reason="pause", task_id="TASK-A1",
        )["interrupted"])

        (self.worktree_a / "external.txt").write_text("accepted head\n", encoding="utf-8")
        subprocess.run(["git", "add", "external.txt"], cwd=self.worktree_a, check=True)
        subprocess.run(
            ["git", "commit", "-m", "external accepted change"],
            cwd=self.worktree_a, check=True, capture_output=True,
        )
        current_head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=self.worktree_a, check=True,
            capture_output=True, text=True,
        ).stdout.strip()

        blocked = activate_task(str(self.tmp), "TASK-A1")
        self.assertFalse(blocked["activated"])
        self.assertIn("--accept-head-change", " ".join(blocked["blockers"]))

        resumed = activate_task(
            str(self.tmp), "TASK-A1", accept_head_change=True,
        )
        self.assertTrue(resumed["activated"], resumed["blockers"])
        self.assertEqual(resumed["adopted_head_ref"], current_head)
        self.assertEqual(resumed["task"]["git_origin_ref"], current_head)
        refreshed = load_task_record(self.tmp, "TASK-A1")
        self.assertFalse(refreshed["implementation"]["implementation_ref"])
        self.assertEqual(refreshed["testing"]["status"], "missing")
        self.assertEqual(refreshed["review"]["result"], "unknown")
        self.assertEqual(
            refreshed["review"]["adversarial_observations"][0]["id"], "ADV-001",
        )
        self.assertEqual(refreshed["fix_loop"]["status"], "open")

    def test_suspended_fix_loop_can_be_resolved_by_explicit_task_id(self):
        from aiwf_core.core.state.fixloop_ops import open_fix_loop, resolve_fix_loop
        from aiwf_core.core.task_ledger import interrupt_task

        self.assertTrue(activate_task(str(self.tmp), "TASK-A1")["activated"])
        open_fix_loop(
            str(self.worktree_a), route="planner", reason="decision already made",
            task_id="TASK-A1",
        )
        self.assertTrue(interrupt_task(
            str(self.worktree_a), reason="pause", task_id="TASK-A1",
        )["interrupted"])

        resolved = resolve_fix_loop(
            str(self.tmp), resolution="verified decision", source="planner",
            task_id="TASK-A1",
        )

        self.assertEqual(resolved["status"], "resolved")
        task = next(
            item for item in load_ledger(str(self.tmp))["tasks"]
            if item["id"] == "TASK-A1"
        )
        self.assertEqual(task["status"], "suspended")
        self.assertEqual(task["phase"], "suspended")
        self.assertEqual(task["suspended_phase"], "reviewing")

    def test_optional_agents_route_to_inline_work_without_skipping_records(self):
        from aiwf_core.commands.flow import _task_next
        from aiwf_core.core.task_records import default_task_record

        task = {
            "id": "TASK-INLINE",
            "requirements": {
                "executor_required": False,
                "tester_required": False,
                "reviewer_required": False,
            },
        }
        record = default_task_record("TASK-INLINE")
        self.assertEqual(_task_next(task, record)[0], "Inline implementation")
        record["implementation"]["implementation_ref"] = "impl"
        self.assertEqual(_task_next(task, record)[0], "Inline testing")
        record["testing"].update({"status": "passed", "tested_ref": "tested"})
        self.assertEqual(_task_next(task, record)[0], "Inline review")
        record["review"].update({"result": "accepted", "closure_allowed": True})
        self.assertEqual(_task_next(task, record)[0], "Close")

        record["review"]["adversarial_observations"] = [{
            "id": "ADV-001", "severity": "warn", "disposition": "pending",
        }]
        role, action = _task_next(task, record)
        self.assertEqual(role, "Planner decision")
        self.assertIn("fix an observation now", action)
        self.assertIn("before choosing deferred", action)
        self.assertIn("ask the user to agree", action)
        self.assertIn("deferred-findings.md", action)

        record["review"]["adversarial_observations"][0]["disposition"] = "deferred"
        role, action = _task_next(task, record)
        self.assertEqual(role, "Close")
        self.assertIn("confirm 1 deferred Reviewer observation", action)
        self.assertIn("deferred-findings.md", action)

    def test_one_worktree_cannot_activate_two_tasks(self):
        first = activate_task(str(self.tmp), "TASK-A1")
        self.assertTrue(first["activated"], first["blockers"])

        second = activate_task(str(self.tmp), "TASK-A2")
        self.assertFalse(second["activated"])
        self.assertIn(
            "target worktree already has active Task TASK-A1",
            second["blockers"],
        )

    def test_task_write_cannot_escape_to_primary_or_another_plan_worktree(self):
        self.assertTrue(activate_task(str(self.tmp), "TASK-A1")["activated"])

        inside = check_file_write(NormalizedEvent(
            cwd=str(self.worktree_a),
            tool_name="Write",
            tool_input={"file_path": str(self.worktree_a / "lesson.html")},
            agent_type="aiwf-executor",
        ))
        primary = check_file_write(NormalizedEvent(
            cwd=str(self.worktree_a),
            tool_name="Write",
            tool_input={"file_path": str(self.tmp / "lesson.html")},
            agent_type="aiwf-executor",
        ))
        other_plan = check_file_write(NormalizedEvent(
            cwd=str(self.worktree_a),
            tool_name="Write",
            tool_input={"file_path": str(self.worktree_b / "lesson.html")},
            agent_type="aiwf-executor",
        ))

        self.assertTrue(inside.allowed, inside.reason)
        self.assertFalse(primary.allowed)
        self.assertFalse(other_plan.allowed)
        self.assertIn("assigned to worktree", primary.reason)
        self.assertIn("different AIWF worktree", other_plan.reason)

    def test_task_bash_copy_cannot_target_primary_worktree(self):
        self.assertTrue(activate_task(str(self.tmp), "TASK-A1")["activated"])

        denied = check_bash(NormalizedEvent(
            cwd=str(self.worktree_a),
            tool_name="Bash",
            tool_input={
                "command": f"cp lesson.html '{self.tmp / 'lesson.html'}'",
            },
            agent_type="aiwf-executor",
        ))
        allowed = check_bash(NormalizedEvent(
            cwd=str(self.worktree_a),
            tool_name="Bash",
            tool_input={
                "command": f"cp '{self.tmp / 'seed.txt'}' lesson.html",
            },
            agent_type="aiwf-executor",
        ))
        denied_with_redirect = check_bash(NormalizedEvent(
            cwd=str(self.worktree_a),
            tool_name="Bash",
            tool_input={
                "command": (
                    f"cp lesson.html '{self.worktree_b / 'lesson.html'}' "
                    "> copy.log"
                ),
            },
            agent_type="aiwf-executor",
        ))

        self.assertFalse(denied["allowed"])
        self.assertIn("Shell write target", denied["reason"])
        self.assertFalse(denied_with_redirect["allowed"])
        self.assertIn(str(self.worktree_b), denied_with_redirect["reason"])
        self.assertNotEqual(allowed.get("allowed"), False, allowed)

    def test_task_may_write_outside_managed_worktrees_for_temporary_output(self):
        self.assertTrue(activate_task(str(self.tmp), "TASK-A1")["activated"])
        temporary = Path(tempfile.gettempdir()) / "aiwf-worktree-guard-output.txt"

        result = check_file_write(NormalizedEvent(
            cwd=str(self.worktree_a),
            tool_name="Write",
            tool_input={"file_path": str(temporary)},
            agent_type="aiwf-executor",
        ))

        self.assertTrue(result.allowed, result.reason)

    def test_installed_claude_hooks_enforce_worktree_ownership(self):
        self.assertTrue(activate_task(str(self.tmp), "TASK-A1")["activated"])
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)

        events = (
            (
                "aiwf_scope_check.py",
                "Write",
                {"file_path": str(self.tmp / "copied.html")},
            ),
            (
                "aiwf_bash_guard.py",
                "Bash",
                {"command": f"cp lesson.html '{self.tmp / 'copied.html'}'"},
            ),
        )
        for script, tool_name, tool_input in events:
            payload = json.dumps({
                "session_id": "worktree-guard",
                "cwd": str(self.worktree_a),
                "hook_event_name": "PreToolUse",
                "tool_name": tool_name,
                "tool_input": tool_input,
                "agent_type": "aiwf-executor",
            })
            result = subprocess.run(
                [sys.executable, str(self.tmp / "scripts" / script)],
                input=payload,
                cwd=self.worktree_a,
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            output = json.loads(result.stdout)
            hook = output["hookSpecificOutput"]
            self.assertEqual(hook["permissionDecision"], "deny")
            self.assertIn("assigned to worktree", hook["permissionDecisionReason"])

    def test_plan_dependency_blocks_parallel_activation(self):
        add_plan_dependency(str(self.tmp), "PLAN-B", "PLAN-A")

        result = activate_task(str(self.tmp), "TASK-B1")

        self.assertFalse(result["activated"])
        self.assertTrue(any("PLAN-A" in blocker for blocker in result["blockers"]))

    def test_corrupt_same_worktree_state_is_recovered(self):
        self.assertTrue(activate_task(str(self.tmp), "TASK-A1")["activated"])
        path = self.tmp / ".aiwf/state/tasks.json"
        ledger = json.loads(path.read_text())
        task = next(item for item in ledger["tasks"] if item["id"] == "TASK-A2")
        task.update({
            "status": "active",
            "phase": "implementing",
            "worktree_path": str(self.worktree_a),
        })
        path.write_text(json.dumps(ledger), encoding="utf-8")

        recovered = load_ledger(str(self.tmp))
        statuses = {task["id"]: task["status"] for task in recovered["tasks"]}
        self.assertEqual(statuses["TASK-A1"], "active")
        self.assertEqual(statuses["TASK-A2"], "suspended")


if __name__ == "__main__":
    unittest.main()
