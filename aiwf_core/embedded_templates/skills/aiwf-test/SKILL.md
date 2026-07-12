---
name: aiwf-test
description: Use only when `aiwf status --prompt` lists `aiwf-test` under Required skills.
---

# AIWF Test

## Role

Dispatch independent testing for the active Task.md. Do not implement, review,
plan, close, or edit implementation code.

## Dispatch

1. Read the active Task.md and `aiwf task proof`.
2. When `tester_required` is true, dispatch `aiwf-tester` with:
   - the active Task.md path;
   - the implementation handoff and changed-file summary;
   - any fresh verified finding not yet recorded;
   - a request to build its own failure model, run every Verification Command,
     add relevant adversarial probes, record testing, and return rather than
     guess when the claim is not testable.
3. Do not paste the Task Packet into the prompt. Tester must read the original
   contract and retain room for independent judgment.
4. Let Tester record testing. Do not record it again.

Failed testing opens an Executor fix-loop. `EXTERNAL_FINDING` and
`RETURN_TO_PLANNER` open a Planner fix-loop. In either case, run
`aiwf status --prompt` and follow its route; do not dispatch Reviewer.

If `tester_required` is false, follow `inline-execution.md` and preserve the
same expected/observed/matched truth in the testing record.

## Boundaries

- Do not soften failed commands into `adequate`.
- Stop after testing is recorded.
