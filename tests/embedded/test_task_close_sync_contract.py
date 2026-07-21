import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class TestTaskCloseSyncContract(unittest.TestCase):
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
        }, "# TASK-001\n")
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

    def test_command_policy_blocks_human_only_recovery_commands_for_agents(self):
        policy_path = (
            Path(__file__).resolve().parent.parent.parent
            / "aiwf_core/embedded_templates/config/command-policy.json"
        )
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        denied = {entry["command"]: entry for entry in policy["deny"]}

        self.assertTrue(denied["aiwf task force-close"]["human_only"])
        self.assertTrue(denied["aiwf task interrupt"]["human_only"])
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
        self.assertNotIn("suspend", result.stdout)


if __name__ == "__main__":
    unittest.main()
