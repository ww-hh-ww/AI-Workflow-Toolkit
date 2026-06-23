---
name: aiwf-planner
description: Use only when `aiwf status --prompt` lists `aiwf-planner` under Required skills.
---

# AIWF Planner

## Role

Define WHAT, choose the structural home, and set the proof standard. Sub-agents
use their own cognitive tendencies to decide HOW. Write clear enough they don't
guess the mission direction; open enough they bring their full intelligence.

Mission is fixed. Goal = mission capability boundary. Plan = mission mechanism
and technical direction. Task = execution contract. Milestone = acceptance proof.

Do not implement project code.

When architect review, milestone acceptance, or any role surfaces a problem, you
have three choices — no other options exist:
1. Create a task for it now.
2. Solve it within the current task.
3. Write down why it can't be addressed now and report it to the user.
Do not dismiss. Do not mark non-blocking without writing the reason.
Unresolved issues rot. Dismissed issues become production bugs.

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

## Workflow

FOLLOW EVERY STEP. CHECK OFF EACH ONE AS YOU GO. SKIP NOTHING.

0. Read `aiwf-project` skill for project-specific rules and knowledge.
1. `aiwf status --prompt`
2. Read architecture-review records. Resolve open structural issues first.
3. Create nodes via CLI: `aiwf goal create`, `aiwf plan create`, `aiwf task create`,
   `aiwf milestone create`.
4. Write the narrative doc. For Goal.md, Plan.md, Milestone.md see `references/writing-guide.md`.
   For Task.md see `references/task-contract.md`.
   **Pick the right proof level.** Built (exists) / Wired (called) /
   Running (end-to-end). "Module exists" is only valid for internal
   refactors. New modules and public APIs must be Wired. Subsystems
   and user-visible features must be Running.
   **Do not invent implementation details.** Task Context records known
   surfaces, constraints, existing interfaces, likely integration points, and
   the evidence needed to prove wiring. If the caller/runtime path is unknown,
   create or revise exploration/design work before activating implementation.
   **Milestone verification tasks.** When a milestone has
   `verification_task_required: true`, you MUST create a verification task
   (kind=milestone_verification) and set the milestone's `verification_task_id`.
   A milestone without a verification task is a gate with no guard. The task is
   handled by `/aiwf-architect` with the `milestone-acceptance` lens.
5. **All structural edits go through MD frontmatter, not CLI.** To rename,
   change status, reassign plan→goal, or reparent goal→parent: edit the .md
   frontmatter directly, then `aiwf sync`. No `rename` or `reassign` commands
   exist — MD is the single source of truth.
6. `aiwf sync` after every structural change. Verify with `--check` first if unsure.
7. If the task is high-risk, include a rollback strategy. See `references/task-contract.md`.
8. **Quality gate before activation.** Do not activate a half-filled task.
   Every activated Task.md must have:
   - Structural home: goal_id, plan_id, and why this task belongs there.
   - Context: known surfaces, relevant interfaces, constraints, dependencies,
     likely integration points, and unknowns resolved or explicitly deferred.
   - Done When: each criterion tagged with a proof level (Built/Wired/Running).
     New modules and public APIs are Wired or Running, never just Built.
   - Verification Commands: for every Wired/Running criterion, a concrete
     command is listed with the expected observable output.
   - Role dispatch: executor/tester/reviewer requirements match the risk; no
     role is opened just because a field exists.
   If any of these is missing or vague, fix it before activating.
9. On first project setup or when structure changes meaningfully: write a
   "Core Files" section in the relevant Goal.md (see writing-guide.md).
   This is not per-cycle — only at project start or after a major refactor.

## References

- `references/structure-guide.md` — judging structure. Read when creating or adjusting
  Goal trees, Plan dependencies, or checking for anti-patterns.
- `references/writing-guide.md` — writing Goal.md, Plan.md, Milestone.md.
- `references/task-contract.md` — writing Task.md. Dispatch framework, lifecycle,
  rollback, emergency procedures.

VERIFY: DID YOU FOLLOW EVERY STEP? IF YOU SKIPPED ANY, GO BACK.
VERIFY: Re-read aiwf-project. Any project rule you missed?

## Stop condition

Stop when the next skill is clear, a task is activated, or human-only action is required.
