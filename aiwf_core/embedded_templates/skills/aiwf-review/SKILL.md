---
name: aiwf-review
description: Use only when `aiwf status --prompt` lists `aiwf-review` under Required skills.
---

# AIWF Review

## Role

Route review for the selected Task.md. Do not implement, test, plan, or close.
Make the review judgment in the main session only when `reviewer_required` is
false.

## Dispatch

Start Reviewer only after Tester has returned and recorded the tested snapshot.
Do not run it in parallel with Executor or Tester.

1. Read the Task.md and run `aiwf task proof <TASK-ID>`.
2. When `reviewer_required` is true, dispatch `aiwf-reviewer` with:
   - the Task ID;
   - the current `USER_DELTA`, if one exists.
   AIWF adds the current contract path and assigned worktree without removing
   your prompt.
3. `USER_DELTA` may contain only an explicit user clarification missing from
   Task.md. It must not change execution, boundaries, or acceptance. A material
   change requires human interrupt and write-back to the relevant MD.
4. Do not paste the complete Task Packet or prescribe review conclusions.
   Reviewer needs the original contract and independent judgment space.
5. Let Reviewer record review. Do not record it again.

The Agent prompt must name exactly one active Task ID. AIWF adds the current
contract path and worktree, then routes project tools there. Do not use `EnterWorktree`
or copy Task changes between worktrees. Other Plans may be reviewed in
parallel; roles for this Task remain sequential.

`needs_fix` and `rejected` open an implementation repair loop. `RETURN_TO_PLANNER` opens
a Planner fix-loop. Run `aiwf status --prompt` and follow its route; do not
proceed to close.

If `reviewer_required` is false, do not dispatch Reviewer. Read
`inline-execution.md`, follow its Review section in this session, and produce
the same task-specific report and record.

## Required Handoff

The report must tell Planner what Executor changed, what Tester proved, what
Reviewer personally checked, why the Task can or cannot proceed, and what
remains. Generic approval is not a valid handoff.

When the implementation changes installation, configuration, migration,
deployment, or public behavior, check the affected surface in reality. Do not
require unrelated documentation or generated assets.

## Boundaries

- Do not close the task.
- Stop after review is recorded and `REVIEW_REPORT` is returned.
