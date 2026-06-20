---
name: aiwf-test
description: Use only when `aiwf status --prompt` lists `aiwf-test` under Required skills.
---

## Workflow

1. `aiwf status --prompt`
2. Read active Task.md. Extract the Context section — the tester needs file paths
   and interfaces to target tests without re-exploring the codebase.
3. Read `.aiwf/records/evidence.json` — filter by current task_id, take the last
   executor record. Extract: changed files, summary (especially what tests ran and
   with what results — tester must NOT re-run the same tests).
4. If `tester_required`:
   `Agent({subagent_type: "aiwf-tester", prompt: "Active Task.md: .aiwf/tasks/<TASK-ID>.md\nContext: <paste Context section from Task.md>\nExecutor changed: [...files]\nExecutor test results: <paste executor evidence summary — what tests ran, how many passed, what dimensions covered>"})`
   The subagent records its own testing (see agent file). Do NOT record again.
5. If not — read `inline-execution.md`, test inline, record testing as described there.
