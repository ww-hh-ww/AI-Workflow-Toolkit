---
name: aiwf-review
description: Use only when `aiwf status --prompt` lists `aiwf-review` under Required skills.
---

## Workflow

FOLLOW EVERY STEP. CHECK OFF EACH ONE AS YOU GO. SKIP NOTHING.

0. Read `aiwf-project` skill for project-specific rules and knowledge.
1. `aiwf status --prompt`
2. Read active Task.md. Extract Context, Done When, and Reviewer Requirements.
   Paste into the dispatch prompt.
3. Read `.aiwf/records/evidence.json` and `.aiwf/records/testing.json` —
   filter by current task_id. The reviewer subagent reads these itself;
   you pass summaries for context.
4. If `reviewer_required`:
   `Agent({subagent_type: "aiwf-reviewer", prompt: "Active Task.md: .aiwf/tasks/<TASK-ID>.md\nContext: <paste Context from Task.md>\nReviewer Requirements: <paste from Task.md>\nExecutor evidence: <paste summary from evidence.json>\nTesting result: <paste from testing.json>"})`
   The subagent reads evidence/testing and records its own review (see agent file).
   Do NOT record again.
5. If not — read `inline-execution.md`, review inline, record review as described there.

VERIFY: DID YOU FOLLOW EVERY STEP? IF YOU SKIPPED ANY, GO BACK.
