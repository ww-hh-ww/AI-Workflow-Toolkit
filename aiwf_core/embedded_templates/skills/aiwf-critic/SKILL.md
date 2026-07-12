---
name: aiwf-critic
description: Manual independent challenge of a project, node, decision, result, or named claim. Dispatches an independent skeptic and returns its findings to the user.
---

# AIWF Critic

## Role

This skill dispatches an independent Critic. The main session chooses the slice
with the user and presents the report. It does not perform or soften the
critique.

Critic is manual. It does not join the normal workflow or block work.

## Workflow

1. Ask what the user wants challenged. Use the request directly when it is
   already clear.

   The slice may be the full project, Mission, one Goal, Plan, Task, Milestone,
   technical decision, implementation result, or named claim.

2. Use critique only by default. Include better options when the user asks how
   to improve the selected subject.

3. Dispatch the project-local `aiwf-critic` subagent. Pass the user's request
   verbatim, the selected slice, and the answer mode. Do not summarize the claim
   for Critic or give it a preferred conclusion.

   `Agent({subagent_type: "aiwf-critic", prompt: "User request: <verbatim request>\nCritique slice: <selected slice>\nAnswer mode: <critique only | critique plus better options>\nRead the relevant project and AIWF material yourself. Follow /aiwf-critic. Return CRITIC_REPORT."})`

4. Present the report as Critic findings. Keep clear what it inspected, what it
   inferred, and what remains unknown. Do not defend the project or turn the
   findings into tasks.

## Boundaries

- Do not run Critic automatically.
- Do not open a fix-loop or change workflow state.
- Do not modify project or governance files.
- Stop after presenting the findings.
