import json
import shutil
import subprocess
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


class TestControlRootConsistency(unittest.TestCase):
    def setUp(self):
        self.control = Path(tempfile.mkdtemp(prefix="aiwf_control_root_"))
        self.worktree = self.control.parent / f"{self.control.name}_plan"
        subprocess.run(
            ["git", "init", "-b", "main"], cwd=self.control,
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=self.control, check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "AIWF Test"],
            cwd=self.control, check=True,
        )
        state = self.control / ".aiwf/state"
        state.mkdir(parents=True)
        (state / "tasks.json").write_text(
            '{"schema_version":1,"tasks":[]}\n', encoding="utf-8",
        )
        (self.control / "README.md").write_text("test\n", encoding="utf-8")
        subprocess.run(
            ["git", "add", "README.md"], cwd=self.control,
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "base"], cwd=self.control,
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "worktree", "add", "-b", "aiwf/plan-001",
             str(self.worktree), "main"],
            cwd=self.control, check=True, capture_output=True,
        )

    def tearDown(self):
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(self.worktree)],
            cwd=self.control, capture_output=True,
        )
        shutil.rmtree(self.worktree, ignore_errors=True)
        shutil.rmtree(self.control, ignore_errors=True)

    def test_narrative_created_from_plan_worktree_uses_control_root(self):
        from aiwf_core.core.index_ops import create_narrative_for_entity

        relative = create_narrative_for_entity(
            str(self.worktree), "TASK-WT", "task", title="Worktree task",
        )

        self.assertEqual(relative, ".aiwf/tasks/TASK-WT.md")
        self.assertTrue((self.control / relative).exists())
        self.assertFalse((self.worktree / relative).exists())

    def test_repeated_create_preserves_existing_narrative(self):
        from aiwf_core.core.index_ops import create_narrative_for_entity

        relative = create_narrative_for_entity(
            str(self.control), "TASK-KEEP", "task", title="Original",
        )
        path = self.control / relative
        path.write_text(
            path.read_text(encoding="utf-8") + "\nUNIQUE-PLANNER-CONTENT\n",
            encoding="utf-8",
        )

        create_narrative_for_entity(
            str(self.worktree), "TASK-KEEP", "task", title="Replacement",
        )

        self.assertIn("UNIQUE-PLANNER-CONTENT", path.read_text(encoding="utf-8"))

    def test_create_repairs_incomplete_frontmatter_without_losing_body(self):
        from aiwf_core.core.index_ops import (
            create_narrative_for_entity,
            parse_md,
        )

        path = self.control / ".aiwf/tasks/TASK-DRAFT.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "---\nid: TASK-DRAFT\n---\n\n# Hand-written draft\n\nKeep this.\n",
            encoding="utf-8",
        )

        create_narrative_for_entity(
            str(self.worktree), "TASK-DRAFT", "task",
            title="Draft", goal_id="GOAL-001", plan_id="PLAN-001",
        )

        frontmatter, body = parse_md(path)
        self.assertEqual(frontmatter["type"], "task")
        self.assertEqual(frontmatter["goal_id"], "GOAL-001")
        self.assertEqual(frontmatter["plan_id"], "PLAN-001")
        self.assertIn("Keep this.", body)

    def test_goal_and_milestone_state_use_control_root(self):
        from aiwf_core.core.state.goal_tree_ops import init_root
        from aiwf_core.core.state.milestone_ops import upsert_milestone

        init_root(str(self.worktree), "GOAL-WT", title="Goal")
        upsert_milestone(
            str(self.worktree), "MS-WT", goal_id="GOAL-WT", title="Milestone",
        )

        goals = json.loads(
            (self.control / ".aiwf/state/goals.json").read_text(encoding="utf-8")
        )
        milestones = json.loads(
            (self.control / ".aiwf/state/milestones.json").read_text(encoding="utf-8")
        )
        self.assertIn("GOAL-WT", {goal["id"] for goal in goals["goals"]})
        self.assertIn(
            "MS-WT", {item["milestone_id"] for item in milestones["milestones"]}
        )
        self.assertFalse((self.worktree / ".aiwf/state/goals.json").exists())
        self.assertFalse((self.worktree / ".aiwf/state/milestones.json").exists())

    def test_concurrent_task_creates_do_not_overwrite_each_other(self):
        from aiwf_core.core.task_ledger import load_ledger, upsert_task

        task_ids = [f"TASK-{index:03d}" for index in range(20)]
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(
                lambda task_id: upsert_task(
                    str(self.control), task_id, title=task_id, status="ready",
                ),
                task_ids,
            ))

        tasks = load_ledger(str(self.control))["tasks"]
        self.assertEqual({task["id"] for task in tasks}, set(task_ids))
        parsed = json.loads(
            (self.control / ".aiwf/state/tasks.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(parsed["tasks"]), len(task_ids))

    def test_activation_critique_route_names_each_pass(self):
        from aiwf_core.core.task_ledger import (
            record_task_activation_critique,
            task_activation_critique_blockers,
            upsert_task,
        )

        upsert_task(str(self.control), "TASK-CRIT", status="ready")
        first = " ".join(
            task_activation_critique_blockers(str(self.control), "TASK-CRIT")
        )
        self.assertIn("Pass 1", first)
        self.assertIn("complete, consistent", first)

        record_task_activation_critique(str(self.control), "TASK-CRIT")
        second = " ".join(
            task_activation_critique_blockers(str(self.control), "TASK-CRIT")
        )
        self.assertIn("Pass 2", second)
        self.assertIn("actual code and proof paths", second)


if __name__ == "__main__":
    unittest.main()
