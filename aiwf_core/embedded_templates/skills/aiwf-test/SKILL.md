---
name: aiwf-test
description: Use only when `aiwf status --prompt` lists `aiwf-test` under Required skills.
---

## Workflow

FOLLOW EVERY STEP. CHECK OFF EACH ONE AS YOU GO. SKIP NOTHING.

0. Read `aiwf-project` skill for project-specific rules and knowledge.
1. `aiwf status --prompt`
2. Read active Task.md. Extract Context (file paths, interfaces) and Tester
   Requirements (which dimensions to cover: boundary, error, concurrency, etc).
   Paste into the dispatch prompt.
3. Read `.aiwf/records/evidence.json` — filter by current task_id, take the last
   executor record. The tester subagent reads this itself; you pass it for context.
4. If `tester_required`:
   `Agent({subagent_type: "aiwf-tester", prompt: "Active Task.md: .aiwf/tasks/<TASK-ID>.md\nContext: <paste Context from Task.md>\nTester Requirements: <paste from Task.md>\nExecutor evidence summary: <paste from evidence.json>"})`
   The subagent reads executor evidence and records its own testing (see agent file).
   Do NOT record again.
5. If not — read `inline-execution.md`, test inline, record testing as described there.

VERIFY: DID YOU FOLLOW EVERY STEP? IF YOU SKIPPED ANY, GO BACK.
