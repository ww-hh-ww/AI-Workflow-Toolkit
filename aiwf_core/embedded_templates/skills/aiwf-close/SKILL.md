---
name: aiwf-close
description: Use only when `aiwf status --prompt` lists `aiwf-close` under Required skills.
---

# AIWF Close

FOLLOW EVERY STEP. CHECK OFF EACH ONE AS YOU GO. SKIP NOTHING.

## Role

Close the current active task through the machine gate. Do not implement, test, review, or force-close.

## First action

```bash
aiwf status --prompt
```

Confirm the current phase and active task.

## Self-check (before closing)

Read the active Task.md frontmatter. Check whether each requirement was fulfilled:

1. `executor_required: true/false` → check `.aiwf/records/evidence.json`
   for an executor record with this task_id.
2. `tester_required: true/false` → check `.aiwf/records/testing.json`
   for a testing record.
3. `reviewer_required: true/false` → check `.aiwf/records/review.json`
   for a review record with result=accepted.

State out loud: "Contract: executor=Y/N, tester=Y/N, reviewer=Y/N.
Fulfilled: executor=✓/✗, tester=✓/✗, reviewer=✓/✗."

If any required role has no record, STOP. Do not proceed to close.
Go back and dispatch that role.

## Command

```bash
aiwf task close
```

The machine gate re-checks everything above. If self-check passed but
close fails, the gate output tells you what's missing.

## Forbidden

- Do not pass a task ID.
- Do not rewrite the close output as if it were your own decision.
- Do not run `aiwf task force-close`; it is human-only.
- Do not continue editing files after close.

VERIFY: DID YOU FOLLOW EVERY STEP? IF YOU SKIPPED ANY, GO BACK.

## Stop condition

After close output, return control to Planner.
