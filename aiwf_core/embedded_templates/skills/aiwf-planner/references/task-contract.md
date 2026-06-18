# Task Contract Reference

Task.md is the execution contract. The active Task.md is frozen by hash at activation and must not be edited by the model during execution.

## Required sections

### Scope

State the exact work outcome. Keep it small enough for one implementation/testing/review cycle.

### Allowed Write

List files, directories, or narrow surfaces that may be modified. If a broad directory is allowed, explain why.

### Forbidden Write

List files and directories that must not be modified. Include AIWF state and records by default:

```text
.aiwf/state/
.aiwf/records/
```

### Executor Requirements

State what implementation must change. Avoid vague wording such as "clean up" unless paired with concrete acceptance.

### Tester Requirements

State expected validation. Include command expectations when known.

Allowed outcomes:

- `passed` when runnable checks pass.
- `failed` when checks fail.
- `adequate` when no runnable test exists but honest validation is still possible.

### Reviewer Requirements

State what reviewer must verify:

- Scope compliance
- Forbidden Write compliance
- Done When compliance
- Evidence/testing adequacy
- Quality or architecture risks

### Done When

Use observable completion criteria, not subjective satisfaction.

### Rollback Strategy required: yes/no

Use `yes` for high-risk tasks such as state migration, directory structure changes, batch rename, broad parser changes, install output migration, or generated surface rewrites.

When `yes`, include:

```text
Method: Git
Before work: inspect git status and git diff
Rollback: use git restore for selected files; use git reset only by human decision
```

## Bad contract signs

- Allowed Write is broader than needed.
- Done When repeats the title.
- Tester Requirements say only "run tests" without naming likely commands or validation type.
- Reviewer Requirements do not mention scope or forbidden paths.
- High-risk work has no rollback strategy.
