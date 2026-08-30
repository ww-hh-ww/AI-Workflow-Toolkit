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
- Do not move work Executor can resolve while implementing into an Experiment.
- If such an unknown blocks implementation, return it to Planner as a concrete,
  falsifiable question. Do not open or answer it by contaminating the Task
  worktree with a spike.
- Executor does not choose or dispatch its successor. It returns facts relevant
  to Task.md Dispatch Decisions; the stable main session evaluates those facts
  after construction evidence is recorded.
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

After the record succeeds, return the Executor report. In the stable main
session, run `aiwf status --prompt`, read Task.md Dispatch Decisions and
`aiwf task proof <TASK-ID>`, then choose the declared next path. This may be
Experimenter followed by Review, or Review directly. Load and dispatch the
selected role yourself; never ask Executor to make that routing decision.

The recorded `implementation_ref` is a hidden candidate snapshot, not the Plan
branch HEAD. In Task proof, trust `snapshot_binding.candidate_tree_status`:
`matched` is ready for Experiment or Review even when HEAD differs and the
worktree remains dirty relative to that HEAD. Do not move the branch to the
snapshot; Task close creates the formal commit.
