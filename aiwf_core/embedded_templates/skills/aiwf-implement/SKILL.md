---
name: aiwf-implement
description: Use only when `aiwf status --prompt` lists `aiwf-implement` under Required skills.
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
   - Open Judgment: Executor Judgment.
   Paste these sections into the dispatch prompt so the subagent starts from
   the map without losing implementation judgment.
3. Run `aiwf record evidence-view` only when fix-loop context is needed. Do
   NOT read raw `.aiwf/records/evidence.json` unless the view command is
   unavailable.
4. If `executor_required`:
   `Agent({subagent_type: "aiwf-executor", prompt: "Active Task.md: .aiwf/tasks/<TASK-ID>.md\nFixed Contract: <paste Fixed Contract>\nKnown Context: <paste Known Context>\nOpen Judgment: <paste Executor Judgment>\n[if fix-loop: Last attempt changed: <files>\nTester found: <failure details>]"})`
   The subagent reads prior evidence and records its own (see agent file).
   Do NOT record again.
5. If not — read `inline-execution.md`, implement inline, record evidence
   as described there.

VERIFY: DID YOU FOLLOW EVERY STEP? IF YOU SKIPPED ANY, GO BACK.
VERIFY: Re-read aiwf-project. Any project rule you missed?
