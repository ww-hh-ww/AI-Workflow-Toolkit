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
   - the Task ID and absolute Task.md path;
   - the assigned worktree path, with the Agent's `cwd` set to that path;
   - a request to read implementation, testing, findings, and diff refs in
     `aiwf task proof <TASK-ID>`;
   - the current `USER_DELTA`, if one exists;
   - a request to inspect the original contract and code reality, record its
     judgment and any non-blocking observations, and return a specific
     `REVIEW_REPORT` for Planner.
3. `USER_DELTA` may contain only an explicit user requirement missing from
   Task.md. Do not add Planner-created fallbacks or reinterpret the contract.
4. Do not paste the complete Task Packet or prescribe review conclusions.
   Reviewer needs the original contract and independent judgment space.
5. Let Reviewer record review. Do not record it again.

The Agent prompt must name exactly one active Task ID and its assigned
worktree. The Agent verifies its location; do not ask it to call
`EnterWorktree`. Other Plans may be reviewed in other worktrees; roles for this
Task remain sequential.

`needs_fix` and `rejected` open an Executor fix-loop. `RETURN_TO_PLANNER` opens
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
