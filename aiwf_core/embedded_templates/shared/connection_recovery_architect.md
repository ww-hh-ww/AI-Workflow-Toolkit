## Connection Recovery

- Continue the required architecture review depth normally; do not reduce scope just to produce an early response.
- If the platform interrupts, the connection appears unstable, or you must stop before completion for non-task reasons, return `PAUSED_FOR_PLANNER`.
- `PAUSED_FOR_PLANNER` must include: completed checks, files/signals read, partial findings, remaining review areas, next proposed action, and whether it is safe to re-dispatch the same subagent.
- Recovery protocol must not be used to skip required architecture trend checks, task-history review, PROJECT-MAP review, or cleanup candidate analysis.
- Do not spawn or request another subagent from inside this subagent; return the resume package to Planner-main.
