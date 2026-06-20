---
name: aiwf-test
description: Use only when `aiwf status --prompt` lists `aiwf-test` under Required skills.
---

## Workflow

1. `aiwf status --prompt`
2. If `tester_required` — `Agent({subagent_type: "aiwf-tester", prompt: "Active Task.md: .aiwf/tasks/<TASK-ID>.md"})`
3. If not — read `inline-execution.md`, test inline.
4. `aiwf record testing --status passed|failed|adequate ...`
