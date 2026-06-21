---
name: aiwf-critic
description: Manual. Independent project critic — challenges assumptions, finds blind spots, tests whether the project is worth doing. Spawns an independent subagent for unbiased critique.
---

## Workflow

FOLLOW EVERY STEP. CHECK OFF EACH ONE AS YOU GO. SKIP NOTHING.

1. Ask the user: "Which scope — full project, specific goal, or specific plan?"
   If the user didn't specify, default to full project.
2. Read the relevant goals, plans, and milestones to understand what the project
   does. Summarize in the dispatch prompt: "This project aims to [X] for [Y] by [Z]."
3. Dispatch:
   `Agent({subagent_type: "aiwf-critic", prompt: "Critique this project.\n\nContext: <your summary of goals, plans, milestones>\n\nScope: <full / goal GOAL-ID / plan PLAN-ID>\n\nFollow your workflow. Present findings in four categories: what holds up, what's shaky, what's wrong, what's missing."})`
   The subagent is an independent model with no stake in the project. It reads
   the project files itself and forms its own judgments. Do not pre-digest or
   soft-pedal.
4. Present the subagent's findings to the user as-is. Do not summarize, filter,
   or defend the project against the critique.

VERIFY: Did you dispatch an independent subagent? Did you present findings unfiltered?
