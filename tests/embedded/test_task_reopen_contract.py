import json
import subprocess
import tempfile
import unittest
from pathlib import Path


class TestTaskReopenContract(unittest.TestCase):
    def setUp(self):
        from aiwf_core.core.index_ops import write_narrative_doc
        from aiwf_core.core.task_records import default_task_record, save_task_record

        self.base = Path(tempfile.mkdtemp(prefix="aiwf_reopen_"))
        for rel in (".aiwf/state", ".aiwf/tasks", ".aiwf/plans", ".aiwf/records/tasks"):
            (self.base / rel).mkdir(parents=True, exist_ok=True)
        self._git("init", "-b", "main")
        self._git("config", "user.email", "test@example.com")
        self._git("config", "user.name", "AIWF Test")
        (self.base / "seed.txt").write_text("seed\n", encoding="utf-8")
        self._git("add", "seed.txt")
        self._git("commit", "-m", "seed")
        self.base_ref = self._git("rev-parse", "HEAD")
        self._git("checkout", "-b", "aiwf/plan-001")
        (self.base / "result.txt").write_text("accepted result\n", encoding="utf-8")
        self._git("add", "result.txt")
        self._git("commit", "-m", "close TASK-001")
        self.task_commit = self._git("rev-parse", "HEAD")

        write_narrative_doc(
            self.base / ".aiwf/tasks/TASK-001.md",
            {
                "id": "TASK-001",
                "type": "task",
                "title": "Closed result",
                "contract_status": "closed",
                "goal_id": "GOAL-001",
                "plan_id": "PLAN-001",
            },
            "# TASK-001\n\n> **CLOSED** old banner\n\n## Closure Calibration\n\nOld accepted claim.\n",
        )
        write_narrative_doc(
            self.base / ".aiwf/plans/PLAN-001.md",
            {
                "id": "PLAN-001",
                "type": "plan",
                "title": "Open Plan",
                "status": "open",
                "goal_id": "GOAL-001",
            },
            "# PLAN-001\n\n## Closure Calibration\n\nOld candidate claim.\n",
        )
        self.task = {
            "id": "TASK-001",
            "status": "closed",
            "phase": "closed",
            "doc_path": ".aiwf/tasks/TASK-001.md",
            "goal_id": "GOAL-001",
            "plan_id": "PLAN-001",
            "dependencies": [],
            "activation_critique_count": 2,
            "worktree_path": str(self.base),
            "git_branch": "aiwf/plan-001",
            "closed_at": "2026-08-22T00:00:00+00:00",
            "closure": {
                "mode": "normal",
                "accepted": True,
                "git_commit": self.task_commit,
                "implementation_ref": "impl-ref",
                "tested_ref": "tested-ref",
                "reviewed_ref": "reviewed-ref",
            },
        }
        self._write_tasks([self.task])
        self._write_plan({
            "id": "PLAN-001",
            "plan_id": "PLAN-001",
            "status": "open",
            "doc_path": ".aiwf/plans/PLAN-001.md",
            "task_ids": ["TASK-001"],
            "task_status": {"TASK-001": "closed"},
            "closed_task_ids": ["TASK-001"],
            "remaining_task_ids": [],
            "git_worktree_path": str(self.base),
            "git_branch": "aiwf/plan-001",
            "git_base_branch": "main",
            "git_base_ref": self.base_ref,
            "git_head_ref": self.task_commit,
            "integration_hold_ref": self.task_commit,
            "integration": {
                "status": "prepared",
                "candidate_ref": self.task_commit,
            },
        })
        record = default_task_record("TASK-001")
        record["implementation"]["implementation_ref"] = "impl-ref"
        record["testing"].update({"status": "passed", "tested_ref": "tested-ref"})
        record["review"].update({"result": "accepted", "reviewed_ref": "reviewed-ref"})
        save_task_record(self.base, record)

    def _git(self, *args):
        result = subprocess.run(
            ["git", *args], cwd=self.base, text=True, capture_output=True,
            encoding="utf-8", errors="surrogateescape",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def _write_tasks(self, tasks):
        (self.base / ".aiwf/state/tasks.json").write_text(
            json.dumps({"schema_version": 1, "tasks": tasks}), encoding="utf-8",
        )

    def _write_plan(self, plan):
        (self.base / ".aiwf/state/plans.json").write_text(
            json.dumps({"schema_version": 1, "plans": [plan]}), encoding="utf-8",
        )

    def test_reopen_archives_proof_and_invalidates_unmerged_plan_candidate(self):
        from aiwf_core.core.index_ops import parse_md
        from aiwf_core.core.task_ledger import reopen_closed_task
        from aiwf_core.core.task_records import load_task_record

        result = reopen_closed_task(
            str(self.base), "TASK-001", reason="runtime evidence disproved the close"
        )

        self.assertTrue(result["reopened"], result["blockers"])
        task = result["task"]
        self.assertEqual(task["status"], "ready")
        self.assertEqual(task["phase"], "planning")
        self.assertEqual(task["activation_critique_count"], 0)
        self.assertNotIn("closure", task)
        self.assertEqual(task["reopen_history"][0]["previous_closure"]["git_commit"], self.task_commit)

        record = load_task_record(self.base, "TASK-001")
        self.assertEqual(record["implementation"]["implementation_ref"], "")
        self.assertEqual(record["testing"]["status"], "missing")
        self.assertEqual(record["review"]["result"], "unknown")
        self.assertEqual(record["attempt_history"][0]["proof"]["testing"]["status"], "passed")
        from aiwf_core.core.task_proof import build_task_proof
        proof = build_task_proof(str(self.base), task)
        self.assertEqual(proof["attempt_history"][0]["closure"]["git_commit"], self.task_commit)

        plan = json.loads(
            (self.base / ".aiwf/state/plans.json").read_text(encoding="utf-8")
        )["plans"][0]
        self.assertEqual(plan["task_status"]["TASK-001"], "ready")
        self.assertEqual(plan["remaining_task_ids"], ["TASK-001"])
        self.assertNotIn("integration", plan)
        self.assertNotIn("integration_hold_ref", plan)
        self.assertEqual(plan["integration_history"][0]["status"], "invalidated_by_task_reopen")

        frontmatter, body = parse_md(self.base / ".aiwf/tasks/TASK-001.md")
        self.assertEqual(frontmatter["contract_status"], "ready")
        self.assertNotIn("## Closure Calibration", body)
        self.assertNotIn("**CLOSED**", body)
        self.assertIn("## Reopen History", body)
        self.assertNotIn(
            "## Closure Calibration",
            (self.base / ".aiwf/plans/PLAN-001.md").read_text(encoding="utf-8"),
        )

    def test_reopen_refuses_started_dependent_task(self):
        from aiwf_core.core.task_ledger import reopen_closed_task
        from aiwf_core.core.task_records import default_task_record, save_task_record

        dependent = {
            "id": "TASK-002",
            "status": "suspended",
            "phase": "suspended",
            "plan_id": "PLAN-001",
            "dependencies": ["TASK-001"],
            "worktree_path": str(self.base),
        }
        self._write_tasks([self.task, dependent])
        record = default_task_record("TASK-002")
        record["implementation"]["implementation_ref"] = "dependent-impl"
        save_task_record(self.base, record)

        result = reopen_closed_task(str(self.base), "TASK-001", reason="bad evidence")

        self.assertFalse(result["reopened"])
        self.assertTrue(any("TASK-002" in item for item in result["blockers"]))

    def test_reopen_accepts_candidate_derived_from_the_same_task_close(self):
        from aiwf_core.core.task_ledger import reopen_closed_task

        (self.base / "candidate.txt").write_text("base combination\n", encoding="utf-8")
        self._git("add", "candidate.txt")
        self._git("commit", "-m", "prepared integration candidate")
        candidate = self._git("rev-parse", "HEAD")
        plans_path = self.base / ".aiwf/state/plans.json"
        data = json.loads(plans_path.read_text(encoding="utf-8"))
        plan = data["plans"][0]
        plan["git_head_ref"] = candidate
        plan["integration"].update({
            "plan_ref": self.task_commit,
            "candidate_ref": candidate,
        })
        plans_path.write_text(json.dumps(data), encoding="utf-8")

        result = reopen_closed_task(
            str(self.base), "TASK-001", reason="candidate contains invalid task evidence"
        )

        self.assertTrue(result["reopened"], result["blockers"])
        plan = json.loads(plans_path.read_text(encoding="utf-8"))["plans"][0]
        self.assertNotIn("integration", plan)
        self.assertEqual(
            plan["integration_history"][0]["integration"]["candidate_ref"], candidate,
        )

    def test_reopen_refuses_when_newer_plan_work_exists(self):
        from aiwf_core.core.task_ledger import reopen_closed_task

        (self.base / "later.txt").write_text("later\n", encoding="utf-8")
        self._git("add", "later.txt")
        self._git("commit", "-m", "later Plan work")

        result = reopen_closed_task(str(self.base), "TASK-001", reason="bad evidence")

        self.assertFalse(result["reopened"])
        self.assertTrue(any("HEAD changed" in item for item in result["blockers"]))

    def test_reopen_refuses_merged_parent_plan(self):
        from aiwf_core.core.task_ledger import reopen_closed_task

        path = self.base / ".aiwf/state/plans.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["plans"][0]["status"] = "closed"
        data["plans"][0]["integration"] = {
            "status": "merged", "merge_commit": "merged-ref",
        }
        path.write_text(json.dumps(data), encoding="utf-8")

        result = reopen_closed_task(str(self.base), "TASK-001", reason="bad evidence")

        self.assertFalse(result["reopened"])
        self.assertTrue(any("parent Plan is closed" in item for item in result["blockers"]))

    def test_reopen_refuses_accepted_milestone_consumer(self):
        from aiwf_core.core.task_ledger import reopen_closed_task

        (self.base / ".aiwf/state/milestones.json").write_text(json.dumps({
            "schema_version": 1,
            "milestones": [{
                "id": "MS-001",
                "status": "open",
                "plan_ids": ["PLAN-001"],
                "task_ids": [],
                "user_acceptance": {"status": "confirmed"},
            }],
        }), encoding="utf-8")

        result = reopen_closed_task(str(self.base), "TASK-001", reason="bad evidence")

        self.assertFalse(result["reopened"])
        self.assertTrue(any("MS-001" in item for item in result["blockers"]))


if __name__ == "__main__":
    unittest.main()
