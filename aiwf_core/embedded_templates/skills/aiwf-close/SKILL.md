---
name: aiwf-close
description: Use only when `aiwf status --prompt` lists `aiwf-close` under Required skills.
---

# AIWF Close

## Role

Close the current active task through the machine gate. Do not implement, test, review, or force-close.

## First action

```bash
aiwf status --prompt
```

Confirm the current phase and active task.

## Command

```bash
aiwf task close
```

No TASK-ID is used. The command closes only the active task.

## Machine gate checks

The close command verifies:

1. Active Task.md hash is unchanged after activation.
2. Required executor evidence exists.
3. Required testing is adequate, passed, or otherwise accepted by the gate.
4. Required review is accepted.
5. No unresolved fix-loop blocks closure.

## Forbidden

- Do not pass a task ID.
- Do not rewrite the close output as if it were your own decision.
- Do not run `aiwf task force-close`; it is human-only.
- Do not continue editing files after close.

## Stop condition

After close output, return control to Planner.
