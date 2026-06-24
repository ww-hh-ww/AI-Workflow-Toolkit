---
name: aiwf-test
description: Use only when `aiwf status --prompt` lists `aiwf-test` under Required skills.
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
   - Open Judgment: Tester Judgment.
   Paste these sections into the dispatch prompt.
3. Run `aiwf record evidence-view`. Do NOT read raw
   `.aiwf/records/evidence.json` unless the view command is unavailable.
   Use the compact view to summarize executor evidence for context.
4. If `tester_required`:
   `Agent({subagent_type: "aiwf-tester", prompt: "Active Task.md: .aiwf/tasks/<TASK-ID>.md\nFixed Contract: <paste Fixed Contract>\nKnown Context: <paste Known Context>\nOpen Judgment: <paste Tester Judgment>\nExecutor evidence summary: <paste compact evidence-view summary>"})`
   The subagent reads executor evidence and records its own testing (see agent file).
   Do NOT record again.
5. If not — read `inline-execution.md`, test inline, record testing as described there.

VERIFY: DID YOU FOLLOW EVERY STEP? IF YOU SKIPPED ANY, GO BACK.
VERIFY: Re-read aiwf-project. Any project rule you missed?
