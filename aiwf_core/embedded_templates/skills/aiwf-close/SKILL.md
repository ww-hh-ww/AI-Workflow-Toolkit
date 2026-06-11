---
name: aiwf-close
description: Verify closure gate, then close the active ledger task — displays auto-generated summary, does not write its own
---

# AIWF Close

Run `prepare-close` while the active task is still active, display its output, then close the active ledger task only after the gate passes. Do not write your own summary.

## Before Closing

Check the active plan's Docs / Assets Impact section:
- If impact=yes, verify the required docs/assets were already handled during implementation.
- If impact=no, do not invent docs or asset work. Do not run `aiwf quality digest` or sync all assets unless the plan explicitly requires it.

## To Close

1. Run `aiwf state prepare-close`.
2. **Display the output as-is.** The command produces a governance summary, a file change list, and warnings — all auto-generated from machine state. Do not summarize, paraphrase, or rewrite it.
3. If `passed=False`, report the blockers and route to fix. Do not proceed.
4. If `passed=True`, run `aiwf task close <ACTIVE-TASK-ID>`.
5. The Stop hook will revalidate the closed workflow.

## Governance Report vs Engineering Report

The `prepare_close` output is the **governance report** — machine-generated from `.aiwf` state while the task is still active. Display it as-is.

The **engineering report** is the Planner's responsibility — a brief explanation of what changed and why. Not a file list. Not a process summary. A human-readable explanation of: what problem was solved, what approach was taken, what follow-up work is expected.

## What You Do NOT Do

- Do NOT rewrite or paraphrase the governance report. Display it.
- Do NOT use the governance report as the engineering report.
- Do NOT close the ledger task before `prepare_close` passes.
- Do NOT declare closure done from conversation. Only `prepare_close` output plus successful `aiwf task close <ACTIVE-TASK-ID>` completes the cycle.
- Do NOT run `aiwf quality digest` or sync all assets unless the active plan explicitly requires it.
