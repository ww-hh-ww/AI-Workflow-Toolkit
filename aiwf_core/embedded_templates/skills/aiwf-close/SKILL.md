---
name: aiwf-close
description: Use only when `aiwf status --prompt` lists `aiwf-close` under Required skills.
---

# AIWF Close

## Role

Close the selected active Task through the machine gate. You do not implement,
test, review, plan, interrupt, or force-close.

Implementation and testing snapshots live outside the branch. This is normal.
Do not commit, cherry-pick, merge, or reset them; `task close` creates the Task
commit.

## Workflow

1. Run:

   ```bash
   aiwf status --prompt
   ```

2. Confirm the Task ID, phase, assigned worktree, and `aiwf task proof <TASK-ID>`.
3. If Planner has not yet recorded what actually happened in Task.md, stop and
   ask Planner to use the implementation, testing, review, and relevant user
   decisions to run:

   ```bash
   aiwf task calibrate <TASK-ID> --summary "<what actually completed; notable difference from the original Task.md; follow-up if any>"
   ```

   This writes only `## Closure Calibration`. It does not change the active
   contract.
4. Run:

   ```bash
   aiwf task close <TASK-ID>
   ```

   If it fails, report the exact blockers and the next required skill.

## Forbidden

- Do not close a different Task from the one selected by status.
- Do not rewrite close output as your own decision.
- Do not run `aiwf task interrupt`; it is human-only.
- Do not run `aiwf task force-close`; it is human-only.
- Do not continue editing files after close.

## Stop Condition

After close output, return control to Planner.
