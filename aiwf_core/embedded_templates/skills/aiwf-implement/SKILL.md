---
name: aiwf-implement
description: Route or perform Executor work when AIWF status requires implementation or construction evidence for a Task.
---

# AIWF Implement

Executor changes stable project reality. This skill routes that responsibility;
it does not move ordinary implementation work into an Experiment.

## Start

Run `aiwf task proof <TASK-ID>` and read the Task contract. Treat its objective,
boundaries, Done When clauses, and V-* rows as the stable obligation. V-* is
Executor-owned construction evidence: implementation is not complete until every
required V-* or current FIX-* ID has an honest matched, mismatched, or blocked
result.

When `executor_required=true`, dispatch `aiwf-executor` with exactly the Task ID
and any explicit user clarification that is absent from Task.md. AIWF injects the
contract and assigned worktree. Do not recopy Task.md or prescribe an
implementation. When Executor is optional, perform the same contract inline.

## Decisions

- Executor owns production code, formal tests, build/config changes, diagnosis,
  repair, and self-checks needed to make the Task true.
- Do not request an Experiment merely to postpone work Executor can resolve while
  implementing. An Experiment is appropriate only for a distinct empirical
  unknown whose disposable full-project changes or measurements should remain
  outside the stable candidate.
- If such an unknown blocks implementation, return it to Planner as a concrete,
  falsifiable question. Do not open or answer it by contaminating the Task
  worktree with a spike.
- A changed implementation invalidates the previous Review and makes
  post-implementation experiments about an older ref stale.

## Record

The Executor records the candidate once its V evidence is complete:

```text
aiwf record implementation --task-id <TASK-ID> --summary "<change>" \
  --check V-001 --observed "<actual result>" --verdict matched \
  --basis "<why the observable satisfies the row>"
```

Use `--executed-command` when the actual probe differs from the Task baseline,
or `--proof-file` for multiple results. A blocked result needs a concrete basis
and will keep the Task from review. Never invent output or rerun successful work
only to rephrase its record.

After the record succeeds, return the Executor report and run
`aiwf status --prompt` in the main session.
