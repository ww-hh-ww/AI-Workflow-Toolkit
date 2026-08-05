---
name: aiwf-test
description: Use only when `aiwf status --prompt` lists `aiwf-test` under Required skills.
---

# AIWF Test

## Role

Route testing for the selected Task.md. Do not implement, review, plan, close,
or edit implementation code.

## Dispatch

Start the first Tester when the current implementation evidence is available.
Wait for Executor to return when `executor_required=true`; when it is false,
test the current implementation snapshot named by proof. Do not run Tester
beside Executor or another Tester in the same worktree.

Do not run `aiwf task test`; that command does not exist. Testing is completed
by Tester and recorded with `aiwf record testing`.

1. Run `aiwf task proof <TASK-ID>`. For first validation, read the entire
   Task.md. For follow-up verification, read the earlier finding, repaired
   implementation and diff, required verification, and affected Task clauses.
   If proof and `aiwf status --prompt` disagree about the next role, stop and
   rerun status; do not continue from memory.
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

Tester should record the complete validation pass once. If a required result is
missing, run and record only that result. AIWF preserves earlier valid results
only while the implementation and tested worktree are unchanged.

The Agent prompt must name exactly one active Task ID. AIWF adds the current
contract path and worktree, then routes project tools there. Do not use `EnterWorktree`
or copy Task changes between worktrees. Other Plans may test in parallel; roles
for this Task remain sequential.

Failed testing opens an implementation repair loop. `EXTERNAL_FINDING` and
`RETURN_TO_PLANNER` open a Planner fix-loop. In either case, run
`aiwf status --prompt` and follow its route; do not dispatch Reviewer.

For an integration Task, a finding is invalid if it only says the Plan has not
yet been merged into main. Do not dispatch Executor for that. On the unchanged
implementation snapshot, verify the recorded base merge and combined behavior,
record the narrow testing correction inline, then resolve the fix-loop. A
missing or wrong `MERGE_HEAD` is a real implementation failure.

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
snapshot after the repaired implementation is recorded. Inline follow-up is
not permission to reuse results from the earlier implementation.

When `aiwf status --prompt` names a previous Tester ID, resume that Agent only
if it is available in the current session or the resumed original session.
Read the fix-loop and proof gaps, then write a concise verification brief that
names the missing or mismatched proof, its source, and which results remain
valid on the unchanged snapshot. Send the Task ID and this brief with
`SendMessage` once. If resume is unavailable or fails, dispatch a new Tester
with the same brief. Keep `USER_DELTA` separate; it is only an explicit user
clarification, not a label for verification evidence.

Do not paste or reread the whole Task for follow-up verification unless the
repair changed a wider contract path or the test method itself.

If `tester_required` is false, do not dispatch Tester. Read
`inline-execution.md`, follow its Test section in this session, and record each
command's expected result, actual result, and whether they matched.

The testing role must judge each actual observable against the contract.
Record by the stable Verification Command ID from Task.md, never by command
text. A changed Task.md contract starts a fresh proof snapshot; do not rely on
or merge results from the old contract. Use `matched` only when the evidence supports success; use `mismatched`
for a verified contract failure and `blocked` for a real environment limit with
a reason. If the contract itself is unclear, return to Planner. Do not rewrite
Task.md merely to make a record pass.

The Task command is the proof target. If the command actually run differs
because the project or environment requires a concrete path or wrapper, keep
the Task contract unchanged and record the real command with
`--executed-command` (or `executed_command` in a proof file). Do not add it
when the recorded command is the one that ran. Reviewer checks whether the
actual command still proves the same claim.

If `aiwf record testing` rejects a result, do not rewrite Task.md, change the
verification ID or command just to make the record pass, or soften the verdict.
Keep the actual evidence, inspect the exact error, and return
`RETURN_TO_PLANNER:` when it is a contract, snapshot, or tool problem rather
than a simple retry with the same ID and evidence.

Ask the user before weakening expected behavior, accepting an environment limit
as adequate for a main path, widening scope, bypassing a gate, or skipping a
required independent Tester.

## Boundaries

- Do not soften failed commands into `adequate`.
- Stop after testing is recorded.
