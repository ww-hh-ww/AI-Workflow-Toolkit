import tempfile
import unittest
from pathlib import Path

from aiwf_core.commands.task_reading import read_task_story
from aiwf_core.core.task_proof import read_task_proof_contract


class TestTaskReading(unittest.TestCase):
    def test_readable_story_preserves_exact_proof_without_duplicated_state(self):
        with tempfile.TemporaryDirectory(prefix="aiwf_reading_") as directory:
            root = Path(directory)
            path = root / ".aiwf/tasks/TASK-001.md"
            path.parent.mkdir(parents=True)
            content = """# TASK-001
## Fixed Contract
### Structural Home
Existing editor.
### Objective
登录失效后不丢失编辑内容。
### Contract Responsibility
保留草稿；不修改登录流程。
### Proof Standard
Done When:
- [Running] 显示重新登录提示，草稿保持不变（V-003）。

Verification Commands:
| ID | Command | Expected Observable Output |
| --- | --- | --- |
| V-003 | python3 check_expired.py | 提示登录，草稿保持不变 |
### Dispatch Decisions
Review when construction is complete.
## Open Judgment
提示放在哪个位置最清楚？
## Closure Calibration
已完成失效保存路径，草稿保持不变。
"""
            path.write_text(content)
            task = {"id": "TASK-001", "doc_path": ".aiwf/tasks/TASK-001.md"}
            story = read_task_story(root, task)
            self.assertEqual(story["Intent"], "登录失效后不丢失编辑内容。")
            self.assertIn("V-003", story["Done when"])
            self.assertNotIn("python3", story["Done when"])
            self.assertEqual(story["Open questions"], "提示放在哪个位置最清楚？")
            proof = read_task_proof_contract(str(root), task)
            self.assertEqual(proof.verification_commands[0].command, "python3 check_expired.py")
            self.assertEqual(path.read_text(), content)


if __name__ == "__main__":
    unittest.main()
