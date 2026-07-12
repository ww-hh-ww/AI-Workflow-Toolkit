---
name: aiwf-implement
description: Use only when `aiwf status --prompt` lists `aiwf-implement` under Required skills.
---

# AIWF Implement

## Role

Dispatch implementation for the active Task.md. Do not plan, test
independently, review, close, or edit the active Task.md.

The Task.md already contains the Fixed Contract, Known Context, and Open
Judgment. Give Executor the document and fresh facts; do not recopy the whole
contract or turn it into step-by-step coding instructions.

## Dispatch

1. Read the active Task.md and current status. For a fix loop, also read
   `aiwf task proof` and the current finding.
2. If this is the first implementation and `executor_required` is true,
   dispatch `aiwf-executor` with:
   - the active Task.md path;
   - the current objective or fix-loop finding;
   - any verified fact not yet present in Task.md or the implementation record;
   - a request to read the contract, inspect code reality, implement, verify,
     record implementation, and return `RETURN_TO_PLANNER` rather than guess.
3. Do not paste Fixed Contract or Known Context into the prompt unless the
   agent cannot access Task.md. Duplicated packets become stale and crowd out
   code exploration.
4. Let the subagent record its own implementation. Do not record it again.

If Executor returns `RETURN_TO_PLANNER`, stop normal progress and surface the
verified conflict. The hook opens a Planner fix-loop. Run `aiwf status --prompt`
and load `aiwf-planner`; do not dispatch Tester.

## Follow-Up Repairs

After the Task has an Executor implementation record, choose the cheapest honest route:

- Dispatch Executor again for changes to main paths, interfaces, state, data
  conversion, concurrency, permissions, safety, deployment, or unclear design.
- Use inline repair only for a tiny, well-understood correction.
- If `executor_required` is false, follow `inline-execution.md`.

The hook enforces the first Executor. Planner remains responsible for deciding
whether later inline repair is actually simpler and safe.

## Boundaries

- Do not change Task.md, Done When, acceptance criteria, or Forbidden Write.
- Stop after the implementation is recorded.
