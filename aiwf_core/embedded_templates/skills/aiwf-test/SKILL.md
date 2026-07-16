---
name: aiwf-test
description: Use only when `aiwf status --prompt` lists `aiwf-test` under Required skills.
---

# AIWF Test

## Role

Route testing for the selected Task.md. Do not implement, review, plan, close,
or edit implementation code.

## Dispatch

Start Tester only after Executor has returned and recorded implementation. Use
one Tester to own the final tested snapshot; do not run it beside Executor or
another Tester in the same worktree.

Do not run `aiwf task test`; that command does not exist. Testing is completed
by Tester and recorded with `aiwf record testing`.

1. Read the Task.md and run `aiwf task proof <TASK-ID>`.
2. When `tester_required` is true, dispatch `aiwf-tester` with:
   - the Task ID and absolute Task.md path;
   - the assigned worktree path;
   - a request to read the implementation and findings in
     `aiwf task proof <TASK-ID>`;
   - the current `USER_DELTA`, if one exists;
   - a request to build its own failure model, run every Verification Command,
     add relevant adversarial probes, record testing, and return rather than
     guess when the claim is not testable.
3. `USER_DELTA` may contain only an explicit user requirement missing from
   Task.md. Do not add Planner-created fallbacks or reinterpret the contract.
   If it changes the implementation claim, return to Planner instead of testing
   a stale implementation.
4. Do not paste the Task Packet into the prompt. Tester must read the original
   contract and retain room for independent judgment.
5. Let Tester record testing. Do not record it again.

The Agent prompt must name exactly one active Task ID and its assigned
worktree. AIWF routes the Agent's relative file, search, and Bash tools there
on every call. Do not use `EnterWorktree` or copy Task changes between
worktrees. Other Plans may test in parallel; roles for this Task remain
sequential.

Failed testing opens an Executor fix-loop. `EXTERNAL_FINDING` and
`RETURN_TO_PLANNER` open a Planner fix-loop. In either case, run
`aiwf status --prompt` and follow its route; do not dispatch Reviewer.

If `tester_required` is false, do not dispatch Tester. Read
`inline-execution.md`, follow its Test section in this session, and record each
command's expected result, actual result, and whether they matched.

## Boundaries

- Do not soften failed commands into `adequate`.
- Stop after testing is recorded.
