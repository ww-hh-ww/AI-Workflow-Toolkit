---
name: aiwf-implement
description: Use only when `aiwf status --prompt` lists `aiwf-implement` under Required skills.
---

## Workflow

1. `aiwf status --prompt`
2. Read active Task.md. Extract the Context section — file paths, registration
   points, core signatures, dependencies. These go directly into the dispatch
   prompt so the subagent doesn't re-discover them.
3. Read `.aiwf/records/evidence.json` — filter by current task_id, take the last
   executor record. Read `.aiwf/records/testing.json` — filter by task_id.
4. If `executor_required`:
   `Agent({subagent_type: "aiwf-executor", prompt: "Active Task.md: .aiwf/tasks/<TASK-ID>.md\nContext: <paste Context section from Task.md>\nChanged last cycle: [...files]\nLast evidence: <summary>\n[if fix: Test failed: <what failed>]"})`
   The subagent records its own evidence (see agent file). Do NOT record again.
5. If not — read `inline-execution.md`, implement inline, record evidence as described there.
