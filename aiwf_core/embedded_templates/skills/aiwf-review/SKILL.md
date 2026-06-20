---
name: aiwf-review
description: Use only when `aiwf status --prompt` lists `aiwf-review` under Required skills.
---

## Workflow

1. `aiwf status --prompt`
2. If `reviewer_required` — `Agent({subagent_type: "aiwf-reviewer", prompt: "Active Task.md: .aiwf/tasks/<TASK-ID>.md"})`
3. If not — read `../../shared/inline-execution.md`, review inline.
4. `aiwf record review --result accepted|needs_fix|rejected ...`
