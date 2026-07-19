---
name: aiwf-test
description: Use only when `aiwf status --prompt` lists `aiwf-test` under Required skills.
---

# AIWF Test

## Role

Route testing for the selected Task.md. Do not implement, review, plan, close,
or edit implementation code.

## Dispatch

Start the first Tester only after Executor has returned and recorded
implementation. Do not run Tester beside Executor or another Tester in the same
worktree.

Do not run `aiwf task test`; that command does not exist. Testing is completed
by Tester and recorded with `aiwf record testing`.

1. Run `aiwf task proof <TASK-ID>`. For first validation, read the entire
   Task.md. For follow-up verification, read the earlier finding, repaired
   implementation and diff, required verification, and affected Task clauses.
2. For the first validation, when `tester_required` is true, dispatch
   `aiwf-tester` with the Task ID and current `USER_DELTA`, if one exists. AIWF
   adds the current contract path and assigned worktree without removing your
   prompt.
3. `USER_DELTA` may contain only an explicit user clarification missing from
   Task.md. It must not change execution, boundaries, or acceptance. A material
   change requires human interrupt and write-back to the relevant MD; do not
   test a stale implementation.
4. Do not paste the Task Packet into the prompt. Tester must read the original
   contract and retain room for independent judgment.
5. Let Tester record testing. Do not record it again.

The Agent prompt must name exactly one active Task ID. AIWF adds the current
contract path and worktree, then routes project tools there. Do not use `EnterWorktree`
or copy Task changes between worktrees. Other Plans may test in parallel; roles
for this Task remain sequential.

Failed testing opens an implementation repair loop. `EXTERNAL_FINDING` and
`RETURN_TO_PLANNER` open a Planner fix-loop. In either case, run
`aiwf status --prompt` and follow its route; do not dispatch Reviewer.

When testing verifies a recorded repair, the testing record resolves that
fix-loop automatically. Run `aiwf status --prompt`; it will route to Reviewer or
show any verification still missing.

## Follow-Up Verification

After an independent Tester has worked once, choose the cheapest honest way to
verify a repair:

- Retest inline when the repair is tiny and local, the failed behavior has an
  exact reproducer, and the expected observable result is clear.
- Dispatch Tester again when the repair affects a main path, interface, state,
  data, concurrency, permissions, safety, deployment, or the test method; also
  dispatch when the earlier failure exposed a bypass or false pass.

Either route must run the required regression checks and record a fresh testing
snapshot. Inline follow-up is not permission to reuse the old result.

Do not paste or reread the whole Task for follow-up verification unless the
repair changed a wider contract path or the test method itself.

If `tester_required` is false, do not dispatch Tester. Read
`inline-execution.md`, follow its Test section in this session, and record each
command's expected result, actual result, and whether they matched.

## Boundaries

- Do not soften failed commands into `adequate`.
- Stop after testing is recorded.
