---
name: aiwf-review
description: Use only when `aiwf status --prompt` lists `aiwf-review` under Required skills.
---

## Workflow

1. `aiwf status --prompt`
2. Read active Task.md. Extract Context, Done When, and Reviewer Requirements.
3. Read `.aiwf/records/evidence.json` and `.aiwf/records/testing.json` —
   filter by current task_id. Only this task's data.
4. If `reviewer_required`:
   `Agent({subagent_type: "aiwf-reviewer", prompt: "Active Task.md: .aiwf/tasks/<TASK-ID>.md\nContext: <paste Context section from Task.md>\nExecutor changed: [...files]\nExecutor summary: <summary>\nTesting: <passed|failed|adequate> — <findings>"})`
   The subagent records its own review (see agent file). Do NOT record again.
5. If not — read `inline-execution.md`, review inline, record review as described there.
