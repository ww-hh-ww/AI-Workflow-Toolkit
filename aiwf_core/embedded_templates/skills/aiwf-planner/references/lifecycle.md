# Ordinary Task Lifecycle

## Normal path

```text
planner creates task
planner activates task
implement records evidence
test records testing
review records review
close closes active task
planner resumes
```

## Commands

```bash
aiwf task create TASK-001 --plan PLAN-001 --title "<title>"
aiwf task activate TASK-001
aiwf record evidence --role executor --summary "<summary>"
aiwf record testing --status passed --command "<command> ::: passed" --summary "<summary>"
aiwf record review --result accepted --summary "<summary>"
aiwf task close
```

## Runtime rules

- `task close` closes the current active task only.
- `task suspend` suspends the current active task only.
- `task force-close` is human-only.
- `task close` does not automatically close the parent Plan.
- Active Task.md must remain unchanged after activation.

## Failure path

If implementation, testing, or review finds blockers:

1. Record the actual result honestly.
2. Let Planner decide whether to revise, open a fix-loop, create another Task, or ask the human.
3. Do not force-close unless the human explicitly does it.
