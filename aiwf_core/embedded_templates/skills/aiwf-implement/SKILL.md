---
name: aiwf-implement
description: Use only when `aiwf status --prompt` lists `aiwf-implement` under Required skills.
---

# AIWF Implement

## Role

Route implementation for the selected Task.md. Do not plan, test independently,
review, close, or edit the active Task.md. Implement in the current session only
when `executor_required` is false or a follow-up repair qualifies below.

The Task.md is the baseline. Give Executor its path; do not recopy the whole
contract or turn the dispatch prompt into separate coding instructions.

## Dispatch

Dispatch one project-writing Executor at a time for this Task. Other Plans may
run in their own worktrees. Wait for this Executor before starting this Task's
Tester.

1. Read the Task.md and run `aiwf task proof <TASK-ID>`. Note its assigned
   worktree. For a fix loop, also read the current finding.
2. If this is the first implementation and `executor_required` is true,
   dispatch `aiwf-executor` with:
   - the Task ID and absolute Task.md path;
   - the assigned worktree path;
   - a requirement to write only there and never copy changes to another
     worktree;
   - for a fix loop, a request to read the current recorded finding;
   - `USER_DELTA: <requirement>` only for an explicit user requirement that
     Task.md does not contain;
   - a request to read the contract, inspect code reality, implement, verify,
     record implementation, and return `RETURN_TO_PLANNER` rather than guess.
3. State `USER_DELTA` faithfully. Do not add Planner-created fallbacks,
   substitute methods, acceptance changes, or interpretations. If there is no
   missing user requirement, omit it.
4. Do not paste Fixed Contract or Known Context into the prompt unless the
   agent cannot access Task.md. Duplicated packets become stale and crowd out
   code exploration.
5. Let the subagent record its own implementation. Do not record it again.

If `executor_required` is false, do not dispatch Executor. Read
`inline-execution.md`, follow its Implement section in this session, and record
the result for this Task.

The Agent prompt must name exactly one active Task ID and its assigned
worktree. AIWF routes the Agent's relative file, search, and Bash tools there
on every call. Do not use `EnterWorktree`, `isolation: worktree`, or copy Task
changes between worktrees.

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
