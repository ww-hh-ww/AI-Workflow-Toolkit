---
name: aiwf-implement
description: Use only when `aiwf status --prompt` lists `aiwf-implement` under Required skills.
---

# AIWF Implement

## Role

Implement the active Task.md contract. Do not test, review, or close.

## First action

```bash
aiwf status --prompt
```

Read the active Task.md from Required read.

## Required read

- Active `.aiwf/tasks/<TASK-ID>.md`
- `.aiwf/state/tasks.json` for requirements
- Source files required by Task.md

## Workflow

1. Confirm the active Task.md and requirements.
2. If `executor_required` is true, dispatch `aiwf-executor` with the active Task.md path and boundaries.
3. If `executor_required` is false, implement inline but still obey Task.md.
4. Keep writes within Allowed Write.
5. Do not modify active Task.md.
6. Record evidence after implementation.
7. Stop and return control to Test/Planner.

## Required record

```bash
aiwf record evidence --role executor --summary "<what changed>" --command "<command or action>"
```

## Forbidden

- Do not edit active Task.md.
- Do not hand-edit `.aiwf/state/` or `.aiwf/records/`.
- Do not close, suspend, or force-close the task.
- Do not expand scope silently.
- Do not run human-only milestone commands.

## Stop condition

Evidence recorded, implementation handoff complete.
