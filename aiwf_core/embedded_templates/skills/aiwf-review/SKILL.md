---
name: aiwf-review
description: Use only when `aiwf status --prompt` lists `aiwf-review` under Required skills.
---

# AIWF Review

## Role

Dispatch independent review for the active Task.md. Do not implement, test,
plan, close, or make the review judgment in the main session.

## Dispatch

1. Read the active Task.md and `aiwf task proof`.
2. When `reviewer_required` is true, dispatch `aiwf-reviewer` with:
   - the active Task.md path;
   - implementation and testing diff refs, changed files, and testing truth;
   - unresolved external findings or fresh facts not yet recorded;
   - a request to inspect the original contract and code reality, record its
     judgment, and return a specific `REVIEW_REPORT` for Planner.
3. Do not paste the complete Task Packet or prescribe review conclusions.
   Reviewer needs the original contract and independent judgment space.
4. Let Reviewer record review. Do not record it again.

`needs_fix` and `rejected` open an Executor fix-loop. `RETURN_TO_PLANNER` opens
a Planner fix-loop. Run `aiwf status --prompt` and follow its route; do not
proceed to close.

If `reviewer_required` is false, follow `inline-execution.md` and still produce
a task-specific plain-language review report.

## Required Handoff

The report must tell Planner what Executor changed, what Tester proved, what
Reviewer personally checked, why the Task can or cannot proceed, and what
remains. Generic approval is not a valid handoff.

When the implementation changes installation, configuration, migration,
deployment, or public behavior, check the affected surface in reality. Do not
require unrelated documentation or generated assets.

## Boundaries

- Do not close the task.
- Stop after review is recorded and `REVIEW_REPORT` is returned.
