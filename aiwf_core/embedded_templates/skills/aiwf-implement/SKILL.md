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

1. Run `aiwf task proof <TASK-ID>` and note its assigned worktree. For first
   implementation, read the entire Task.md. For a fix loop, read the current
   finding, latest records and diff, and only the affected Task clauses.
2. If this is the first implementation and `executor_required` is true,
   dispatch `aiwf-executor` with the Task ID. Add `USER_DELTA: <requirement>`
   only for an explicit user clarification that Task.md does not contain. AIWF
   adds the current control-root Task.md path and assigned worktree without
   removing your prompt.
3. `USER_DELTA` must not change execution, boundaries, or acceptance. A
   material change requires human interrupt, write-back to the relevant MD,
   sync, critique, and reactivation. Otherwise state it faithfully; do not add
   Planner-created fallbacks or interpretations.
4. Do not paste Fixed Contract or Known Context into the prompt unless the
   agent cannot access Task.md. Duplicated packets become stale and crowd out
   code exploration.
5. Let the subagent record its own implementation. Do not record it again.

If `executor_required` is false, do not dispatch Executor. Read
`inline-execution.md`, follow its Implement section in this session, and record
the result for this Task. With one active Task, AIWF routes this session's
relative project tools to its assigned worktree. Do not change
`executor_required`, enter a worktree, or request temporary writes to make an
inline write pass.
With several active Tasks, use the exact assigned worktree path shown by
`aiwf status --prompt`; AIWF will not guess between Tasks.

The Agent prompt must name exactly one active Task ID. AIWF adds the current
contract path and worktree, then routes project tools there. Do not use `EnterWorktree`,
`isolation: worktree`, or copy Task changes between worktrees.

Read `.aiwf` governance from the control root. The Plan worktree owns project
code, not a separate copy of the Task contract.

If Executor returns `RETURN_TO_PLANNER`, stop normal progress and surface the
verified conflict. The hook opens a Planner fix-loop. Run `aiwf status --prompt`
and load `aiwf-planner`; do not dispatch Tester.

## Follow-Up Repairs

After the Task has an Executor implementation record, choose the cheapest honest route:

- Dispatch Executor again for changes to main paths, interfaces, state, data
  conversion, concurrency, permissions, safety, deployment, or unclear design.
- Use inline repair only for a tiny, well-understood correction. Follow the
  Implement section of `inline-execution.md` and record the repaired
  implementation. That record hands the fix-loop to Tester.
- If `executor_required` is false, follow `inline-execution.md`.

When `aiwf status --prompt` names a previous Executor ID, resume that Agent for
a non-trivial repair only if it is available in the current session or the
resumed original session. Try `SendMessage` once. Send only the Task ID and
tell it to read `aiwf task proof`. If resume is unavailable or fails, dispatch
a new Executor with the Task ID and current finding. Do not retry the resume.

The hook enforces the first Executor. Planner remains responsible for deciding
whether later inline repair is actually simpler and safe.

When dispatching a repair Executor, still send only the Task ID and any valid
`USER_DELTA`. The Agent gets the current finding and records from `task proof`;
do not paste the original Task or rewrite the finding in the prompt.

## Boundaries

- Do not change Task.md, Done When, acceptance criteria, or Forbidden Write.
- Stop after the implementation is recorded.
