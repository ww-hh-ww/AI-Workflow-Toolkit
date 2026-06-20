---
name: aiwf-implement
description: Use only when `aiwf status --prompt` lists `aiwf-implement` under Required skills.
---

## Workflow

1. `aiwf status --prompt`
2. Read `.aiwf/records/evidence.json` — filter by current task_id, take the last
   executor record. Read `.aiwf/records/testing.json` — filter by task_id.
   Include only this task's data in the prompt.
3. If `executor_required`:
   `Agent({subagent_type: "aiwf-executor", prompt: "Active Task.md: .aiwf/tasks/<TASK-ID>.md\nChanged last cycle: [...files]\nLast evidence: <summary>\n[if fix: Test failed: <what failed>]"})`
4. If not — read `inline-execution.md`, implement inline.
5. `aiwf record evidence --role executor --summary "<what changed>" --command "<command>"`
