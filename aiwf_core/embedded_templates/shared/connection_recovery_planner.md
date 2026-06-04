## Subagent Connection Recovery

If a subagent returns `PAUSED_FOR_PLANNER`, treat it as an interrupted/resumable run, not a failed implementation, test, or review.

- Read the resume package: completed steps, changed/checked files, commands run, last successful evidence, next proposed action, and safe-to-re-dispatch note.
- Re-dispatch the same role with the smallest safe next action when the package is coherent.
- If the likely cause is connection/platform instability, avoid broad replanning and do not open a fix-loop merely because the subagent stopped.
- Open a fix-loop only when the subagent reports a real implementation/testing/review blocker.
- For Tester/Reviewer pauses, preserve the original depth obligations; do not downgrade `test_template`, `review_template`, surface obligations, or system integration obligations because of an interruption.
