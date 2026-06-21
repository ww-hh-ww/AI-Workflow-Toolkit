---
name: aiwf-close
description: Use only when `aiwf status --prompt` lists `aiwf-close` under Required skills.
---

# AIWF Close

FOLLOW EVERY STEP. CHECK OFF EACH ONE AS YOU GO. SKIP NOTHING.

## Role

Close the current active task through the machine gate. Do not implement, test, review, or force-close.

## First action

Read `aiwf-project` skill for project-specific rules and knowledge.

```bash
aiwf status --prompt
```

Confirm the current phase and active task.

## Command

```bash
aiwf task close
```

The command checks: dispatch log (were required subagents actually spawned?)
and the standard evidence/testing/review/fix-loop gates. If it fails, it
tells you exactly which role was never dispatched and which skill to load.

## Forbidden

- Do not pass a task ID.
- Do not rewrite the close output as if it were your own decision.
- Do not run `aiwf task force-close`; it is human-only.
- Do not continue editing files after close.

VERIFY: DID YOU FOLLOW EVERY STEP? IF YOU SKIPPED ANY, GO BACK.
VERIFY: Re-read aiwf-project. Any project rule you missed?

## Stop condition

After close output, return control to Planner.
