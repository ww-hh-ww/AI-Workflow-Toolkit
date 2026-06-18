## Connection Recovery

If a subagent returns `PAUSED_FOR_PLANNER`, treat it as an interrupted run, not as success or failure.

The resume package should include: completed steps, changed or checked files, commands run, records written, remaining work, and whether it is safe to re-dispatch the same role.

Re-dispatch only the smallest safe next action. Open a fix-loop only when the package reports a real implementation, testing, review, or environment blocker.
