## Connection Recovery

If interrupted before completing architecture review, return `PAUSED_FOR_PLANNER` with: surfaces read, checks completed, partial risks, remaining architecture checks, and whether it is safe to re-dispatch architect.

Do not record `intact` unless the architecture review actually completed.
