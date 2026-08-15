import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


class TestTaskCloseSyncContract(unittest.TestCase):
    def test_suspended_task_syncs_after_fresh_critiques_when_reactivated(self):
        from aiwf_core.commands.task_commands import _cmd_task_activate
        from aiwf_core.core.index_ops import write_narrative_doc
        from aiwf_core.core.task_ledger import record_task_activation_critique

        base = Path(tempfile.mkdtemp(prefix="awreactivate_sync_"))
        for rel in (".aiwf/state", ".aiwf/tasks"):
            (base / rel).mkdir(parents=True, exist_ok=True)
        write_narrative_doc(base / ".aiwf/tasks/TASK-001.md", {
            "id": "TASK-001",
            "type": "task",
            "title": "Resume changed contract",
            "contract_status": "suspended",
            "goal_id": "GOAL-001",
            "plan_id": "PLAN-001",
            "executor_required": False,
            "tester_required": False,
            "reviewer_required": True,
            "rollback_required": False,
            "tester_write": [],
            "dependencies": [],
        }, "# TASK-001\n")
        tasks_path = base / ".aiwf/state/tasks.json"
        tasks_path.write_text(json.dumps({
            "schema_version": 1,
            "tasks": [{
                "id": "TASK-001",
                "title": "Resume changed contract",
                "status": "suspended",
                "phase": "suspended",
                "suspended_phase": "implementing",
                "activation_critique_count": 0,
                "goal_id": "GOAL-001",
                "plan_id": "PLAN-001",
                "doc_path": ".aiwf/tasks/TASK-001.md",
                "requirements": {
                    "executor_required": True,
                    "tester_required": True,
                    "reviewer_required": True,
                    "rollback_required": False,
                    "tester_write": [],
                },
                "dependencies": [],
            }],
        }), encoding="utf-8")

        record_task_activation_critique(str(base), "TASK-001")
        record_task_activation_critique(str(base), "TASK-001")
        before = json.loads(tasks_path.read_text(encoding="utf-8"))["tasks"][0]
        self.assertEqual(before["activation_critique_count"], 2)
        self.assertTrue(before["requirements"]["executor_required"])

        def inspect_activation(base_dir, task_id, accept_head_change=False):
            task = json.loads(tasks_path.read_text(encoding="utf-8"))["tasks"][0]
            self.assertEqual(task_id, "TASK-001")
            self.assertFalse(task["requirements"]["executor_required"])
            self.assertFalse(task["requirements"]["tester_required"])
            self.assertTrue(task["requirements"]["reviewer_required"])
            self.assertEqual(task["activation_critique_count"], 2)
            return {"activated": True, "blockers": []}

        previous = Path.cwd()
        try:
            os.chdir(base)
            with patch(
                "aiwf_core.core.task_ledger.activate_task",
                side_effect=inspect_activation,
            ):
                with redirect_stdout(StringIO()):
                    _cmd_task_activate(SimpleNamespace(
                        task_id="TASK-001", accept_head_change=False,
                    ))
        finally:
            os.chdir(previous)

    def test_sync_reports_active_contract_changes_without_overwriting_runtime(self):
        from aiwf_core.core.index_ops import sync_index, write_narrative_doc

        base = Path(tempfile.mkdtemp(prefix="awactive_sync_"))
        for rel in (".aiwf/state", ".aiwf/tasks"):
            (base / rel).mkdir(parents=True, exist_ok=True)
        task_doc = base / ".aiwf/tasks/TASK-001.md"
        write_narrative_doc(task_doc, {
            "id": "TASK-001",
            "type": "task",
            "title": "Frozen task",
            "contract_status": "ready",
            "goal_id": "GOAL-001",
            "plan_id": "PLAN-001",
            "kind": "implementation",
            "executor_required": False,
            "tester_required": False,
            "reviewer_required": False,
            "rollback_required": False,
            "tester_write": [],
            "dependencies": [],
        }, "# TASK-001\n")
        tasks_path = base / ".aiwf/state/tasks.json"
        tasks_path.write_text(json.dumps({
            "schema_version": 1,
            "tasks": [{
                "id": "TASK-001",
                "title": "Frozen task",
                "status": "active",
                "goal_id": "GOAL-001",
                "plan_id": "PLAN-001",
                "kind": "implementation",
                "doc_path": ".aiwf/tasks/TASK-001.md",
                "requirements": {
                    "executor_required": True,
                    "tester_required": True,
                    "reviewer_required": True,
                    "rollback_required": False,
                    "tester_write": [],
                },
                "dependencies": [],
            }],
        }), encoding="utf-8")

        result = sync_index(str(base))

        self.assertTrue(any(
            "active Task contract is frozen" in error
            and "executor_required" in error
            for error in result["errors"]
        ))
        task = json.loads(tasks_path.read_text(encoding="utf-8"))["tasks"][0]
        self.assertTrue(task["requirements"]["executor_required"])
        self.assertTrue(task["requirements"]["tester_required"])
        self.assertTrue(task["requirements"]["reviewer_required"])

    def test_close_updates_task_md_contract_status_before_sync(self):
        from aiwf_core.core.index_ops import parse_md, sync_index, write_narrative_doc
        from aiwf_core.core.task_ledger import close_task

        base = Path(tempfile.mkdtemp(prefix="awclose_"))
        for rel in (".aiwf/state", ".aiwf/records", ".aiwf/tasks"):
            (base / rel).mkdir(parents=True, exist_ok=True)
        task_doc = base / ".aiwf/tasks/TASK-001.md"
        write_narrative_doc(task_doc, {
            "id": "TASK-001",
            "type": "task",
            "title": "Close sync contract",
            "contract_status": "ready",
            "goal_id": "GOAL-001",
            "plan_id": "PLAN-001",
            "executor_required": False,
            "tester_required": False,
            "reviewer_required": False,
            "rollback_required": False,
            "dependencies": [],
        }, """# TASK-001

## Fixed Contract

### Structural Home

GOAL-001 / PLAN-001.

### Objective

Close the completed task.

### Contract Responsibility

Own and record the completed result.

### Proof Standard

- [Built] The result is present.
""")
        (base / ".aiwf/state/state.json").write_text(json.dumps({
            "phase": "reviewing",
            "active_task_id": "TASK-001",
            "active_plan_id": "PLAN-001",
        }), encoding="utf-8")
        (base / ".aiwf/state/fix-loop.json").write_text(
            json.dumps({"status": "none"}),
            encoding="utf-8",
        )
        (base / ".aiwf/state/tasks.json").write_text(json.dumps({
            "schema_version": 1,
            "tasks": [{
                "id": "TASK-001",
                "title": "Close sync contract",
                "status": "active",
                "goal_id": "GOAL-001",
                "plan_id": "PLAN-001",
                "doc_path": ".aiwf/tasks/TASK-001.md",
                "requirements": {
                    "executor_required": False,
                    "tester_required": False,
                    "reviewer_required": False,
                },
            }],
        }), encoding="utf-8")
        (base / "README.md").write_text("test\n", encoding="utf-8")

        result = close_task(str(base), "TASK-001")
        self.assertTrue(result["closed"], result["blockers"])
        fm, _ = parse_md(task_doc)
        self.assertEqual(fm["contract_status"], "closed")

        sync = sync_index(str(base))
        self.assertEqual(sync["errors"], [])
        tasks = json.loads((base / ".aiwf/state/tasks.json").read_text(encoding="utf-8"))
        self.assertEqual(tasks["tasks"][0]["status"], "closed")

    def test_close_repairs_already_closed_task_frontmatter(self):
        from aiwf_core.core.index_ops import parse_md, write_narrative_doc
        from aiwf_core.core.task_ledger import close_task

        base = Path(tempfile.mkdtemp(prefix="awclose_"))
        for rel in (".aiwf/state", ".aiwf/tasks"):
            (base / rel).mkdir(parents=True, exist_ok=True)
        task_doc = base / ".aiwf/tasks/TASK-002.md"
        write_narrative_doc(task_doc, {
            "id": "TASK-002",
            "type": "task",
            "title": "Already closed",
            "contract_status": "ready",
            "goal_id": "GOAL-001",
            "plan_id": "PLAN-001",
        }, "# TASK-002\n")
        (base / ".aiwf/state/tasks.json").write_text(json.dumps({
            "schema_version": 1,
            "tasks": [{
                "id": "TASK-002",
                "status": "closed",
                "doc_path": ".aiwf/tasks/TASK-002.md",
            }],
        }), encoding="utf-8")

        result = close_task(str(base), "TASK-002")

        self.assertTrue(result["closed"], result["blockers"])
        fm, _ = parse_md(task_doc)
        self.assertEqual(fm["contract_status"], "closed")

    def test_close_retry_repairs_parent_plan_rollup(self):
        from aiwf_core.core.task_ledger import close_task

        base = Path(tempfile.mkdtemp(prefix="awclose_"))
        (base / ".aiwf/state").mkdir(parents=True)
        (base / ".aiwf/state/tasks.json").write_text(json.dumps({
            "schema_version": 1,
            "tasks": [{
                "id": "TASK-REPAIR",
                "status": "closed",
                "plan_id": "PLAN-REPAIR",
                "closure": {"git_commit": "abc123"},
            }],
        }), encoding="utf-8")
        (base / ".aiwf/state/plans.json").write_text(json.dumps({
            "schema_version": 1,
            "plans": [{
                "id": "PLAN-REPAIR",
                "plan_id": "PLAN-REPAIR",
                "status": "open",
                "task_ids": ["TASK-REPAIR"],
                "task_status": {"TASK-REPAIR": "active"},
                "closed_task_ids": [],
                "remaining_task_ids": ["TASK-REPAIR"],
            }],
        }), encoding="utf-8")

        result = close_task(str(base), "TASK-REPAIR")

        self.assertTrue(result["closed"], result["blockers"])
        self.assertTrue(result["plan_progress"]["reconciled"])
        plan = json.loads(
            (base / ".aiwf/state/plans.json").read_text(encoding="utf-8")
        )["plans"][0]
        self.assertEqual(plan["task_status"]["TASK-REPAIR"], "closed")
        self.assertEqual(plan["closed_task_ids"], ["TASK-REPAIR"])
        self.assertEqual(plan["remaining_task_ids"], [])

    def test_force_close_updates_task_md_contract_status(self):
        from aiwf_core.core.index_ops import parse_md, sync_index, write_narrative_doc
        from aiwf_core.core.agent_runtime import running_dispatches, start_dispatch
        from aiwf_core.core.task_ledger import force_close_task
        from aiwf_core.core.task_records import default_task_record, load_task_record

        base = Path(tempfile.mkdtemp(prefix="awclose_"))
        for rel in (".aiwf/state", ".aiwf/records", ".aiwf/tasks"):
            (base / rel).mkdir(parents=True, exist_ok=True)
        task_doc = base / ".aiwf/tasks/TASK-003.md"
        write_narrative_doc(task_doc, {
            "id": "TASK-003",
            "type": "task",
            "title": "Force close sync",
            "contract_status": "ready",
            "goal_id": "GOAL-001",
            "plan_id": "PLAN-001",
        }, "# TASK-003\n")
        (base / ".aiwf/state/state.json").write_text(json.dumps({
            "phase": "testing",
            "active_task_id": "TASK-003",
        }), encoding="utf-8")
        (base / ".aiwf/state/fix-loop.json").write_text(
            json.dumps({"status": "open"}),
            encoding="utf-8",
        )
        (base / ".aiwf/state/tasks.json").write_text(json.dumps({
            "schema_version": 1,
            "tasks": [{
                "id": "TASK-003",
                "status": "active",
                "doc_path": ".aiwf/tasks/TASK-003.md",
                "requirements": {"tester_required": True},
            }],
        }), encoding="utf-8")
        record = default_task_record("TASK-003")
        record["fix_loop"].update({
            "status": "open",
            "route": "tester",
            "attempt_count": 2,
            "escalation_required": True,
            "escalation_reason": "retry limit reached",
            "rollback_recommended": True,
        })
        record_path = base / ".aiwf/records/tasks/TASK-003.json"
        record_path.parent.mkdir(parents=True, exist_ok=True)
        record_path.write_text(json.dumps(record), encoding="utf-8")
        self.assertFalse(start_dispatch(
            base, "TASK-003", "aiwf-tester", "session-1", "PLAN-001", str(base),
        ))

        result = force_close_task(str(base), reason="human override")

        self.assertTrue(result["closed"], result["blockers"])
        self.assertEqual(result["task"]["closure"]["mode"], "human_force")
        self.assertEqual(result["task"]["closure"]["reason"], "human override")
        self.assertNotIn("accepted_by_human", result["task"]["closure"])
        self.assertNotIn("gate_passed", result["task"]["closure"])
        fix_loop = load_task_record(base, "TASK-003")["fix_loop"]
        self.assertEqual(fix_loop["status"], "open")
        self.assertFalse(fix_loop["escalation_required"])
        self.assertFalse(fix_loop["rollback_recommended"])
        self.assertEqual(fix_loop["route_history"][-1]["source"], "human")
        self.assertEqual(running_dispatches(base, task_id="TASK-003"), [])
        fm, _ = parse_md(task_doc)
        self.assertEqual(fm["contract_status"], "closed")
        sync_index(str(base))
        tasks = json.loads((base / ".aiwf/state/tasks.json").read_text(encoding="utf-8"))
        self.assertEqual(tasks["tasks"][0]["status"], "closed")

        from aiwf_core.aiwf_ui import _build_status_bar, load_all
        self.assertNotIn("Fix待决定", _build_status_bar(load_all(base)))

    def test_interrupt_suspends_without_closing_and_survives_sync(self):
        from aiwf_core.core.index_ops import parse_md, sync_index, write_narrative_doc
        from aiwf_core.core.task_ledger import interrupt_task

        base = Path(tempfile.mkdtemp(prefix="awclose_"))
        for rel in (".aiwf/state", ".aiwf/records", ".aiwf/tasks"):
            (base / rel).mkdir(parents=True, exist_ok=True)
        task_doc = base / ".aiwf/tasks/TASK-004.md"
        write_narrative_doc(task_doc, {
            "id": "TASK-004",
            "type": "task",
            "title": "Interrupt sync",
            "contract_status": "ready",
            "goal_id": "GOAL-001",
            "plan_id": "PLAN-001",
        }, "# TASK-004\n")
        (base / ".aiwf/state/state.json").write_text(json.dumps({
            "phase": "executing",
            "active_task_id": "TASK-004",
        }), encoding="utf-8")
        (base / ".aiwf/state/fix-loop.json").write_text(
            json.dumps({"status": "none"}),
            encoding="utf-8",
        )
        (base / ".aiwf/state/tasks.json").write_text(json.dumps({
            "schema_version": 1,
            "tasks": [{
                "id": "TASK-004",
                "status": "active",
                "doc_path": ".aiwf/tasks/TASK-004.md",
                "requirements": {"executor_required": True},
            }],
        }), encoding="utf-8")
        dispatch = base / ".aiwf/runtime/internal/agent-dispatch.jsonl"
        dispatch.parent.mkdir(parents=True, exist_ok=True)
        dispatch.write_text(json.dumps({
            "timestamp": "2026-07-19T10:00:00+00:00",
            "subagent_type": "aiwf-executor",
            "task_id": "TASK-004",
            "session_id": "test",
            "status": "started",
        }) + "\n", encoding="utf-8")

        result = interrupt_task(str(base), reason="stop and replan")

        self.assertTrue(result["interrupted"], result["blockers"])
        self.assertEqual(result["task"]["status"], "suspended")
        self.assertNotIn("closure", result["task"])
        self.assertEqual(result["task"]["interruption"]["reason"], "stop and replan")
        self.assertNotIn("mode", result["task"]["interruption"])
        self.assertNotIn("interrupted_at", result["task"])
        fm, _ = parse_md(task_doc)
        self.assertEqual(fm["contract_status"], "suspended")
        sync_index(str(base))
        tasks = json.loads((base / ".aiwf/state/tasks.json").read_text(encoding="utf-8"))
        self.assertEqual(tasks["tasks"][0]["status"], "suspended")
        dispatch_entries = [
            json.loads(line) for line in dispatch.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(dispatch_entries[-1]["status"], "cancelled")
        self.assertEqual(dispatch_entries[-1]["completion_source"], "task_interrupt")

    def test_cancel_updates_task_md_contract_status_and_survives_sync(self):
        from aiwf_core.core.index_ops import parse_md, sync_index, write_narrative_doc

        base = Path(tempfile.mkdtemp(prefix="awclose_"))
        for rel in (".aiwf/state", ".aiwf/tasks"):
            (base / rel).mkdir(parents=True, exist_ok=True)
        task_doc = base / ".aiwf/tasks/TASK-005.md"
        write_narrative_doc(task_doc, {
            "id": "TASK-005",
            "type": "task",
            "title": "Cancel sync",
            "contract_status": "ready",
            "goal_id": "GOAL-001",
            "plan_id": "PLAN-001",
        }, "# TASK-005\n")
        (base / ".aiwf/state/tasks.json").write_text(json.dumps({
            "schema_version": 1,
            "tasks": [{
                "id": "TASK-005",
                "status": "ready",
                "doc_path": ".aiwf/tasks/TASK-005.md",
            }],
        }), encoding="utf-8")
        env = dict(os.environ)
        env["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent.parent)
        env["PYTHONPYCACHEPREFIX"] = "/private/tmp/aiwf-pycache"
        result = subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", "task", "cancel", "TASK-005"],
            cwd=base,
            env=env,
            text=True,
            capture_output=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        fm, _ = parse_md(task_doc)
        self.assertEqual(fm["contract_status"], "cancelled")
        sync_index(str(base))
        tasks = json.loads((base / ".aiwf/state/tasks.json").read_text(encoding="utf-8"))
        self.assertEqual(tasks["tasks"][0]["status"], "cancelled")

    def test_human_can_restore_cancelled_task_to_ready_or_closed(self):
        from aiwf_core.core.index_ops import parse_md, write_narrative_doc
        from aiwf_core.core.task_ledger import restore_cancelled_task

        base = Path(tempfile.mkdtemp(prefix="awrestore_"))
        for rel in (".aiwf/state", ".aiwf/tasks"):
            (base / rel).mkdir(parents=True, exist_ok=True)
        tasks = []
        for task_id in ("TASK-READY", "TASK-CLOSED"):
            task_doc = base / f".aiwf/tasks/{task_id}.md"
            write_narrative_doc(task_doc, {
                "id": task_id,
                "type": "task",
                "title": task_id,
                "contract_status": "cancelled",
                "goal_id": "GOAL-001",
                "plan_id": "PLAN-001",
            }, f"# {task_id}\n")
            tasks.append({
                "id": task_id,
                "status": "cancelled",
                "phase": "planning",
                "doc_path": f".aiwf/tasks/{task_id}.md",
                "plan_id": "PLAN-001",
                "cancel_reason": "old decision",
                "activation_critique_count": 2,
            })
        (base / ".aiwf/state/tasks.json").write_text(json.dumps({
            "schema_version": 1, "tasks": tasks,
        }), encoding="utf-8")
        (base / ".aiwf/state/plans.json").write_text(json.dumps({
            "schema_version": 1,
            "plans": [{
                "id": "PLAN-001",
                "plan_id": "PLAN-001",
                "status": "open",
                "task_ids": ["TASK-READY", "TASK-CLOSED"],
                "task_status": {"TASK-READY": "cancelled", "TASK-CLOSED": "cancelled"},
                "closed_task_ids": [],
                "remaining_task_ids": [],
            }],
        }), encoding="utf-8")

        ready = restore_cancelled_task(
            str(base), "TASK-READY", status="ready", reason="resume the original scope"
        )
        self.assertTrue(ready["restored"], ready["blockers"])
        self.assertEqual(ready["task"]["status"], "ready")
        self.assertEqual(ready["task"]["activation_critique_count"], 0)
        self.assertEqual(ready["task"]["restoration"]["from"], "cancelled")
        fm, _ = parse_md(base / ".aiwf/tasks/TASK-READY.md")
        self.assertEqual(fm["contract_status"], "ready")

        closed = restore_cancelled_task(
            str(base), "TASK-CLOSED", status="closed", reason="work was already delivered"
        )
        self.assertTrue(closed["restored"], closed["blockers"])
        self.assertEqual(closed["task"]["status"], "closed")
        self.assertEqual(closed["task"]["closure"]["mode"], "human_restore")
        fm, _ = parse_md(base / ".aiwf/tasks/TASK-CLOSED.md")
        self.assertEqual(fm["contract_status"], "closed")
        plan = json.loads((base / ".aiwf/state/plans.json").read_text(encoding="utf-8"))["plans"][0]
        self.assertEqual(plan["task_status"]["TASK-READY"], "ready")
        self.assertEqual(plan["task_status"]["TASK-CLOSED"], "closed")
        self.assertEqual(plan["remaining_task_ids"], ["TASK-READY"])

    def test_command_policy_blocks_human_only_recovery_commands_for_agents(self):
        policy_path = (
            Path(__file__).resolve().parent.parent.parent
            / "aiwf_core/embedded_templates/config/command-policy.json"
        )
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        denied = {entry["command"]: entry for entry in policy["deny"]}

        self.assertTrue(denied["aiwf task force-close"]["human_only"])
        self.assertTrue(denied["aiwf task interrupt"]["human_only"])
        self.assertTrue(denied["aiwf task restore"]["human_only"])
        self.assertTrue(denied["aiwf fixloop continue"]["human_only"])

    def test_public_task_help_hides_internal_suspend(self):
        env = dict(os.environ)
        env["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent.parent)
        env["PYTHONPYCACHEPREFIX"] = "/private/tmp/aiwf-pycache"
        result = subprocess.run(
            [sys.executable, "-m", "aiwf_core.cli", "task", "--help"],
            env=env,
            text=True,
            capture_output=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("interrupt", result.stdout)
        self.assertIn("force-close", result.stdout)
        self.assertIn("restore", result.stdout)
        self.assertNotIn("suspend", result.stdout)


if __name__ == "__main__":
    unittest.main()
