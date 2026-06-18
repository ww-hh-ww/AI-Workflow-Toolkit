---
name: aiwf-test
description: Use only when `aiwf status --prompt` lists `aiwf-test` under Required skills.
---

# AIWF Test

## Role

Validate the active Task.md. Do not implement, review, or close.

## First action

```bash
aiwf status --prompt
```

Read the active Task.md from Required read.

## Required read

- Active `.aiwf/tasks/<TASK-ID>.md`
- `.aiwf/records/evidence.json`
- Changed files and relevant tests

## Workflow

1. Read Tester Requirements and Done When.
2. Read executor evidence.
3. If `tester_required` is true, dispatch `aiwf-tester`.
4. If `tester_required` is false, test inline or record an adequate reason.
5. Record the actual testing result.
6. Stop and return control to Review/Planner.

## Required record

Passed:

```bash
aiwf record testing --status passed --command "<command> ::: passed" --summary "<summary>"
```

Failed:

```bash
aiwf record testing --status failed --command "<command> ::: failed" --summary "<summary>"
```

Adequate without runnable test:

```bash
aiwf record testing --status adequate --summary "<why adequate>"
```

## Rules

- Failed tests are valid evidence; record them honestly.
- Do not claim passed unless the command passed.
- Do not modify code.
- Do not hand-edit `.aiwf/records/`.
- Do not close the task.
