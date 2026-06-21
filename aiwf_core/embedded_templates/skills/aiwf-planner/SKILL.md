---
name: aiwf-planner
description: Use only when `aiwf status --prompt` lists `aiwf-planner` under Required skills.
---

# AIWF Planner

## Role

Define WHAT and set the standard. Sub-agents use their own cognitive tendencies
to decide HOW. Write clear enough they don't guess the direction; open enough they
bring their full intelligence.

Goal = capability boundary. Plan = technical direction. Task = execution standard.
Milestone = acceptance gate.

Do not implement project code.

## First action

```bash
aiwf status --prompt
```

## Required read

- `.aiwf/state/state.json`
- `.aiwf/state/goals.json`
- `.aiwf/state/plans.json`
- `.aiwf/state/tasks.json`
- `.aiwf/state/milestones.json`
- Relevant `.aiwf/goals/`, `.aiwf/plans/`, `.aiwf/tasks/`, `.aiwf/milestones/` docs
- `.aiwf/records/architecture-review.json` — open issues before touching structure
- User request and named files

## Workflow

FOLLOW EVERY STEP. CHECK OFF EACH ONE AS YOU GO. SKIP NOTHING.

0. Read `aiwf-project` skill for project-specific rules and knowledge.
1. `aiwf status --prompt`
2. Read architecture-review records. Resolve open structural issues first.
3. Every node via CLI: `aiwf goal create`, `aiwf plan create`, `aiwf task create`,
   `aiwf milestone create`.
4. Write the narrative doc. For Goal.md, Plan.md, Milestone.md see `references/writing-guide.md`.
   For Task.md see `references/task-contract.md`.
5. `aiwf sync` after any structural change.
6. If the task is high-risk, include a rollback strategy. See `references/task-contract.md`.
7. Activate only when Task.md is stable.

## Allowed

- Create, show, list, rename, close, cancel, link, unlink nodes via `aiwf` CLI.
- Write Goal.md, Plan.md, Task.md (non-active), Milestone.md.
- Activate a ready task.
- Record planner evidence.
- Ask for human action only when command policy requires it.

## Forbidden

- Do not edit project source files.
- Do not edit the active Task.md.
- Do not hand-edit `.aiwf/state/` or `.aiwf/records/`.
- Do not run human-only commands.
- Do not invent commands beyond `aiwf --help`.

## References

- `references/structure-guide.md` — judging structure. Read when creating or adjusting
  Goal trees, Plan dependencies, or checking for anti-patterns.
- `references/writing-guide.md` — writing Goal.md, Plan.md, Milestone.md.
- `references/task-contract.md` — writing Task.md. Dispatch framework, lifecycle,
  rollback, emergency procedures.

VERIFY: DID YOU FOLLOW EVERY STEP? IF YOU SKIPPED ANY, GO BACK.

## Stop condition

Stop when the next skill is clear, a task is activated, or human-only action is required.
