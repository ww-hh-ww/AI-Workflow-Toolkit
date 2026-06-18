---
name: aiwf-review
description: Use only when `aiwf status --prompt` lists `aiwf-review` under Required skills.
---

# AIWF Review

## Role

Review the active Task.md result. Do not implement, test, plan, or close.

## First action

```bash
aiwf status --prompt
```

Read the active Task.md from Required read.

## Required read

- Active `.aiwf/tasks/<TASK-ID>.md`
- `.aiwf/records/evidence.json`
- `.aiwf/records/testing.json`
- Changed files and relevant surrounding code

## Workflow

1. Read Task.md contract.
2. Read evidence and testing records.
3. If `reviewer_required` is true, dispatch `aiwf-reviewer`.
4. If reviewing inline, check contract compliance first, then quality.
5. Record review result.
6. Stop and return control to Close/Planner.

## Review layers

1. Scope and forbidden-path compliance.
2. Done When and acceptance compliance.
3. Evidence and testing adequacy.
4. Code quality and structural risk.

See references when deeper review is needed:

- `references/trace-checklist.md`
- `references/verify-checklist.md`
- `references/review-output.md`

## Required record

```bash
aiwf record review --result accepted --summary "<why accepted>"
```

```bash
aiwf record review --result needs_fix --summary "<summary>" --blocker "<specific blocker>"
```

```bash
aiwf record review --result rejected --summary "<summary>" --blocker "<fundamental issue>"
```

## Rules

- `accepted` is the only review result that satisfies the normal close gate.
- `needs_fix` means the task should not close yet.
- Do not modify files.
- Do not hand-edit `.aiwf/records/`.
- Do not close the task.
