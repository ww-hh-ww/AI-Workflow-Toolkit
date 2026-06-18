## Connection Recovery

If interrupted before completing implementation, return `PAUSED_FOR_PLANNER` with: completed steps, changed files, commands run, evidence already recorded, remaining implementation work, and whether it is safe to re-dispatch executor.

Do not reduce scope or claim completion just to end early.
