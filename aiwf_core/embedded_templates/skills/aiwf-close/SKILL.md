---
name: aiwf-close
description: Use only when `aiwf status --prompt` lists `aiwf-close` under Required skills.
---

# AIWF Close

## Role

Close the current active task through the machine gate. You do not implement,
test, review, plan, interrupt, or force-close.

## Workflow

1. Run:

   ```bash
   aiwf status --prompt
   ```

2. Confirm the current phase and active task.
3. If Planner has not yet recorded what actually happened in Task.md, stop and
   ask Planner to use the implementation, testing, review, and relevant user
   decisions to run:

   ```bash
   aiwf task calibrate --summary "<what actually completed; notable difference from the original Task.md; follow-up if any>"
   ```

   This writes only `## Closure Calibration`. It does not change the active
   contract.
4. Run:

   ```bash
   aiwf task close
   ```

The command decides. It checks dispatch logs, snapshot freshness, testing,
review, and fix-loop gates, then creates the Task commit. If it fails, report
the exact blockers and the next required skill.

## Forbidden

- Do not pass a task ID.
- Do not rewrite close output as your own decision.
- Do not run `aiwf task interrupt`; it is human-only.
- Do not run `aiwf task force-close`; it is human-only.
- Do not continue editing files after close.

VERIFY: Did you let the command decide?

## Stop Condition

After close output, return control to Planner.
