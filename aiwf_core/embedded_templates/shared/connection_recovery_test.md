## Connection Recovery

If interrupted before completing validation, return `PAUSED_FOR_PLANNER` with: commands run, checked files, partial results, testing record already written if any, remaining validation, and whether it is safe to re-dispatch tester.

Do not downgrade required validation because of interruption.
