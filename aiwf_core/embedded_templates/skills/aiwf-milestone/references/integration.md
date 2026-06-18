# Milestone Integration Gate

The integration gate checks whether the phase works as a whole, not only whether individual tasks closed.

## Required checks

- Linked Plans are coherent.
- Linked Tasks are closed or intentionally excluded.
- Milestone verification task is closed when required.
- Main path works end to end or the reverse trace proves equivalent coverage.

## Coverage modes

Use `end_to_end_flow` when a real command or scenario exercises the main path.

Use `function_reverse_trace` when direct end-to-end execution is unavailable but the code path can be traced from command entry to state/record output.

## Command

```bash
aiwf milestone integration-test MS-001 --status passed --coverage-mode end_to_end_flow --main-path-status passed --command "<command> ::: passed" --summary "<summary>"
```

If failed:

```bash
aiwf milestone integration-test MS-001 --status failed --coverage-mode end_to_end_flow --main-path-status failed --command "<command> ::: failed" --summary "<failure>"
```
