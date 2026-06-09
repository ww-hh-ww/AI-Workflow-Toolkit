---
name: aiwf-close
description: Verify gates and finalize closure — displays auto-generated summary, does not write its own
---

# AIWF Close

You handle workflow closure. Your job is to run `prepare-close`, display its output, and stop. Do not write your own summary.

## Before Closing

Sync all project assets so the close summary reflects the latest state:

```bash
aiwf state rebuild-current-state
aiwf quality digest
aiwf export-report
```

## To Close

1. Run `aiwf state prepare-close`.
2. **Display the output as-is.** The command produces a governance summary, a file change list, and warnings — all auto-generated from machine state. Do not summarize, paraphrase, or rewrite it. The user needs to see the machine output, not your interpretation of it.
3. If the output says `passed=False`, report the blockers and route to fix. Do not proceed.
4. If the output says `passed=True`, closure is complete. The Stop hook will revalidate.

## Governance Report (machine) vs Engineering Report (Planner)

The `prepare_close` output is the **governance report** — machine-generated from `.aiwf` state. It tells the user whether the process was followed and surfaces quality signals (strong/weak evidence, testing depth, review depth, asset freshness). Display it as-is.

The **engineering report** is the Planner's responsibility — a brief explanation of what changed and why, written for someone who knows the project. Not a file list (that's in Changes). Not a process summary (that's in Governance). A human-readable explanation of: what problem was solved, what approach was taken, and what follow-up work is expected.

## What You Do NOT Do

- Do NOT rewrite or paraphrase the governance report. Display it.
- Do NOT use the governance report as the engineering report. They are different things.
- Do NOT declare closure done from conversation context. Only `prepare_close` output is authoritative.
