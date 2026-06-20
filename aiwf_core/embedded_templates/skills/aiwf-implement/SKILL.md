---
name: aiwf-implement
description: Use only when `aiwf status --prompt` lists `aiwf-implement` under Required skills.
---

## Workflow

1. `aiwf status --prompt`
2. If `executor_required` — `Agent({subagent_type: "aiwf-executor", prompt: "Active Task.md: .aiwf/tasks/<TASK-ID>.md"})`
3. If not — read `inline-execution.md`, implement inline.
4. `aiwf record evidence --role executor --summary "<what changed>" --command "<command>"`
