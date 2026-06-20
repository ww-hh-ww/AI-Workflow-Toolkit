---
name: aiwf-test
description: Use only when `aiwf status --prompt` lists `aiwf-test` under Required skills.
---

## Workflow

1. `aiwf status --prompt`
2. Read `.aiwf/records/evidence.json` — executor's changed files and summary.
3. If `tester_required`:
   `Agent({subagent_type: "aiwf-tester", prompt: "Active Task.md: .aiwf/tasks/<TASK-ID>.md\nExecutor changed: [...files]\nExecutor summary: <summary>"})`
4. If not — read `inline-execution.md`, test inline.
5. `aiwf record testing --status passed|failed|adequate ...`
