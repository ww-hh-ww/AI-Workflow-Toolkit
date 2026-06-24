---
name: aiwf-review
description: Use only when `aiwf status --prompt` lists `aiwf-review` under Required skills.
---

## Workflow

FOLLOW EVERY STEP. CHECK OFF EACH ONE AS YOU GO. SKIP NOTHING.

0. Read `aiwf-project` skill for project-specific rules and knowledge.
1. `aiwf status --prompt`
2. Read active Task.md. Extract the Task Packet:
   - Fixed Contract: Structural Home, Objective, Scope, Forbidden Write,
     Proof Standard, Verification Commands.
   - Known Context: Known Surfaces, Interfaces/Invariants, Integration Evidence,
     Resolved/Deferred Unknowns.
   - Open Judgment: Reviewer Judgment.
   Paste these sections into the dispatch prompt.
3. Run `aiwf record evidence-view`. Do NOT read raw
   `.aiwf/records/evidence.json` unless the view command is unavailable.
   Pass the compact view summary for context.
4. If `reviewer_required`:
   `Agent({subagent_type: "aiwf-reviewer", prompt: "Active Task.md: .aiwf/tasks/<TASK-ID>.md\nFixed Contract: <paste Fixed Contract>\nKnown Context: <paste Known Context>\nOpen Judgment: <paste Reviewer Judgment>\nEvidence view: <paste compact evidence-view summary>"})`
   The subagent reads evidence/testing and records its own review (see agent file).
   Do NOT record again.
5. If not — read `inline-execution.md`, review inline, record review as described there.

VERIFY: DID YOU FOLLOW EVERY STEP? IF YOU SKIPPED ANY, GO BACK.
VERIFY: Re-read aiwf-project. Any project rule you missed?
