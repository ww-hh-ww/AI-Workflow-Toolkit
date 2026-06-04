## Connection Recovery

- Continue the required review depth normally; do not reduce review scope just to produce an early response.
- If the platform interrupts, the connection appears unstable, or you must stop before completion for non-task reasons, return `PAUSED_FOR_PLANNER`.
- `PAUSED_FOR_PLANNER` must include: completed checks, checked files, evidence reviewed, remaining review obligations, next proposed action, and whether it is safe to re-dispatch the same subagent.
- Recovery protocol must not be used to skip required obligations from `review_template`, `surface_types`, `architecture_brief`, acceptance criteria, or system integration obligations.
- Do not spawn or request another subagent from inside this subagent; return the resume package to Planner-main.
