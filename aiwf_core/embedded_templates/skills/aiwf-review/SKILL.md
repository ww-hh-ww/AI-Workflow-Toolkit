---
name: aiwf-review
description: Use only when `aiwf status --prompt` lists `aiwf-review` under Required skills.
---

## Workflow

1. `aiwf status --prompt`
2. Read `.aiwf/records/evidence.json` and `.aiwf/records/testing.json` —
   filter by current task_id. Only this task's data.
3. If `reviewer_required`:
   `Agent({subagent_type: "aiwf-reviewer", prompt: "Active Task.md: .aiwf/tasks/<TASK-ID>.md\nExecutor changed: [...files]\nExecutor summary: <summary>\nTesting: <passed|failed|adequate> — <findings>"})`
4. If not — read `inline-execution.md`, review inline.
5. `aiwf record review --result accepted|needs_fix|rejected ...`
