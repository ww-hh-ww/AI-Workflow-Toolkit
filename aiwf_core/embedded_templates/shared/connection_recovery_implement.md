## Connection Recovery

- Continue the assigned implementation normally; do not reduce scope just to produce an early response.
- If the platform interrupts, the connection appears unstable, or you must stop before completion for non-task reasons, return `PAUSED_FOR_PLANNER`.
- `PAUSED_FOR_PLANNER` must include: completed steps, changed files, commands run, last successful evidence, next proposed action, and whether it is safe to re-dispatch the same subagent.
- Do not spawn or request another subagent from inside this subagent; return the resume package to Planner-main.
