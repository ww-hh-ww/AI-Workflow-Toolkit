# Risk and Git Rollback Policy

AIWF does not create its own snapshot rollback system. Rollback is handled by Git and human decision.

## No automatic rollback work

- Do not require rollback planning for every Task.
- Do not automatically commit.
- Do not automatically reset.
- Do not invent AIWF rollback commands.

## High-risk tasks

A Task needs a rollback strategy when it changes one of these surfaces:

- State schema or record format
- Directory layout
- Install output
- Command parser or public command surface
- Batch rename or broad generated file changes
- Broad removal of old mechanisms
- Cross-cutting workflow behavior

## Required Task.md wording

```text
Rollback Strategy required: yes
Method: Git
Before work:
- inspect git status
- inspect git diff
- make sure unrelated work is not mixed into the task
Rollback:
- use git restore for selected files
- use git reset only by human decision
```

## Milestone boundary

After successful milestone close, tell the human:

```bash
git status
git add -A
git commit -m "milestone(MS-001): <title>"
```

The model must not run the commit automatically.
