# LOAD THE PHASE SKILL. LOAD THE PHASE SKILL. LOAD THE PHASE SKILL.
# FOLLOW THE SKILL EXACTLY. FOLLOW THE SKILL EXACTLY. FOLLOW THE SKILL EXACTLY.

Every step in a skill is mandatory. Skip a step = task broken. The close gate checks.

Run `aiwf status --prompt` first, then load `/aiwf-project`, then every
`Required skills:` entry. Follow every numbered step. No exceptions.
`/aiwf-architect` too, including its `milestone-acceptance` lens when milestone
verification is required.

## Phase → skill

| Phase | Load |
|-------|------|
| planning | `/aiwf-planner` |
| executing | `/aiwf-implement` |
| testing | `/aiwf-test` |
| reviewing | `/aiwf-review` |
| closing | `/aiwf-close` |
| blocked | resolve blockers first |
| closed | `/aiwf-planner` (next cycle)

Write gates, evidence rules, dispatch rules, and close gates are enforced
mechanically or documented in the skill/agent files. Read them there.

## Non-negotiable

- Load every Required skill. Follow every step. No skipping.
- FORBIDDEN: routing downgrades unless user explicitly orders.
- FORBIDDEN: `aiwf task force-close` — human emergency override only.
