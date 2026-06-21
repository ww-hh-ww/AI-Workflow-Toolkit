---
name: aiwf-implement
description: Use only when `aiwf status --prompt` lists `aiwf-implement` under Required skills.
---

## Workflow

FOLLOW EVERY STEP. CHECK OFF EACH ONE AS YOU GO. SKIP NOTHING.

0. Read `aiwf-project` skill for project-specific rules and knowledge.
1. `aiwf status --prompt`
2. Read active Task.md. Extract the Context section — file paths, registration
   points, core signatures, dependencies. Paste into the dispatch prompt so the
   subagent starts there instead of re-discovering.
3. Read `.aiwf/records/evidence.json` and `.aiwf/records/testing.json` —
   filter by current task_id. Only for fix-loop context.
4. If `executor_required`:
   `Agent({subagent_type: "aiwf-executor", prompt: "Active Task.md: .aiwf/tasks/<TASK-ID>.md\nContext: <paste Context section from Task.md>\n[if fix-loop: Last attempt changed: <files>\nTester found: <failure details>]"})`
   The subagent reads prior evidence and records its own (see agent file).
   Do NOT record again.
5. If not — read `inline-execution.md`, implement inline, record evidence
   as described there.

VERIFY: DID YOU FOLLOW EVERY STEP? IF YOU SKIPPED ANY, GO BACK.
VERIFY: Re-read aiwf-project. Any project rule you missed?
