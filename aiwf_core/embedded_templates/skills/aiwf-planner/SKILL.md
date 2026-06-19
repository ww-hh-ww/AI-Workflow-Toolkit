---
name: aiwf-planner
description: Use only when `aiwf status --prompt` lists `aiwf-planner` under Required skills.
---

# AIWF Planner

## Role

You manage AIWF structure. You create and adjust Mission-facing work nodes: Goal, Plan, Task, and Milestone. You write Task.md contracts. You do not implement project code.

## First action

Run:

```bash
aiwf status --prompt
```

Follow the reported phase, Required skills, Required read, Forbidden actions, and Next action.

## Required read

Read only what is needed for the planning decision:

- `.aiwf/state/state.json`
- `.aiwf/state/goals.json`
- `.aiwf/state/plans.json`
- `.aiwf/state/tasks.json`
- `.aiwf/state/milestones.json`
- Relevant `.aiwf/goals/`, `.aiwf/plans/`, `.aiwf/tasks/`, `.aiwf/milestones/` Markdown docs
- User request and any files named by the user

## Allowed actions

- Create, show, list, rename, close, cancel, link, and unlink Goal/Plan/Task/Milestone nodes using public AIWF commands.
- Write or update non-active Task.md contracts before activation.
- Activate a ready task when the contract is clear.
- Record planner evidence when planning changed the workflow materially.
- Ask for human action only when command policy requires it.

## Forbidden actions

- Do not edit project source files as Planner.
- Do not edit the active Task.md.
- Do not hand-edit `.aiwf/state/` or `.aiwf/records/`.
- Do not run human-only commands.
- Do not invent commands beyond `aiwf --help`.
- Do not add automatic documentation, retro, or summary work unless the user asks or an explicit Task is created.
- Do not create a snapshot rollback system. Rollback is Git-based.

## Workflow

1. Read `aiwf status --prompt`.
2. Decide whether the next action is structural planning, task activation, milestone gating, or returning to another skill.
3. If creating or updating a Goal, Plan, Task, or Milestone, write the MD frontmatter first.
4. Run `aiwf sync` after any frontmatter change — this compiles MD into the JSON machine state that gates read.
5. If the Task is high risk, include a Git rollback strategy.
6. Activate only when Task.md is stable enough to freeze.
7. After activation, stop and hand off to the required next skill.

## Task.md minimum contract

A ready Task.md must state:

- `executor_required`, `tester_required`, `reviewer_required` — set deliberately. See `references/task-contract.md` for decision criteria.
- `rollback_required` — true for high-risk surfaces. See `references/risk-and-rollback.md`.
- `report_policy` — `silent_until_done` for routine milestone tasks, `ask` for tasks needing human attention.
- Scope
- Allowed Write
- Forbidden Write
- Executor Requirements
- Tester Requirements
- Reviewer Requirements
- Done When
- Rollback Strategy required: yes/no

Use `references/task-contract.md` for the full contract checklist.

## Commands

Examples of valid structural commands:

```bash
aiwf goal create GOAL-001 --title "<title>"
aiwf plan create PLAN-001 --goal GOAL-001 --title "<title>"
aiwf task create TASK-001 --plan PLAN-001 --title "<title>"
aiwf task activate TASK-001
aiwf milestone create MS-001 --goal GOAL-001 --title "<title>"
aiwf milestone link-plan MS-001 PLAN-001
aiwf milestone link-task MS-001 TASK-001
```

## References

- `references/task-contract.md` — Task.md contract shape.
- `references/lifecycle.md` — ordinary task lifecycle.
- `references/risk-and-rollback.md` — high-risk task rollback policy.

## Stop condition

Stop when the next skill is clear, a task is activated, or a human-only action is required.
