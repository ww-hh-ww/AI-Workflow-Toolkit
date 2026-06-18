---
name: aiwf-milestone
description: Use only when `aiwf status --prompt` lists `aiwf-milestone` under Required skills.
---

# AIWF Milestone

## Role

Run milestone acceptance gates. You do not replace human acceptance.

## First action

```bash
aiwf status --prompt
```

Read the milestone specified by status or user request.

## Required read

- `.aiwf/state/milestones.json`
- `.aiwf/state/plans.json`
- `.aiwf/state/tasks.json`
- Relevant `.aiwf/milestones/<MS-ID>.md`
- Linked Plan and Task docs
- `.aiwf/records/testing.json`
- `.aiwf/records/review.json`
- `.aiwf/records/architecture-review.json`

## Workflow

1. Confirm linked Plans and Tasks.
2. Ensure linked ordinary tasks are closed or intentionally not required.
3. Ensure milestone verification task exists and closes when required.
4. Run or verify integration test gate.
5. Run or verify architecture review gate.
6. Record milestone assessment.
7. Stop for human confirmation.
8. After human confirmation is present, close milestone.
9. Report the human Git commit suggestion printed by the close command.

## Commands

Integration gate:

```bash
aiwf milestone integration-test MS-001 --status passed --coverage-mode end_to_end_flow --main-path-status passed --command "<command> ::: passed" --summary "<summary>"
```

Architecture gate:

```bash
aiwf milestone arch-review MS-001 --status intact --notes "<summary>"
```

Assessment:

```bash
aiwf milestone assess MS-001 --verdict PASS --summary "<summary>"
```

Close after human confirmation:

```bash
aiwf milestone close MS-001
```

## Human-only command

`aiwf milestone confirm` is human-only. The model must not run it.

When confirmation is needed, stop and ask the human to run:

```bash
aiwf milestone confirm MS-001 --summary "<what was accepted>"
```

## References

- `references/integration.md`
- `references/architecture-review.md`

## Rules

- Do not auto-commit.
- Do not bypass human confirmation.
- Do not close a milestone with failed integration or unresolved architecture issues unless the assessment explicitly records risk and the human confirms.
- Do not create ordinary project changes during milestone review.
