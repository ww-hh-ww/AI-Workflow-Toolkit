---
name: aiwf-review-verify
description: Evidence integrity, solution quality, acceptance criteria — verify what was delivered
---

**Simplicity check:** Flag speculative abstraction, unnecessary configurability, broad refactors, or changes that solve a narrower problem with a larger system. If a simpler implementation would satisfy the same acceptance criteria, the current one is over-engineered.

# AIWF Review — Verify

## Evidence Integrity Check — Catch "Declared but Not Done"

The Tester may claim tests passed, but claims are not proof. Verify:

- **Traceability**: Can each test claim be traced to an actual execution trace — a CI log, a git-recorded command with output, a timestamped run? Prose is not evidence.
- **Surface coverage**: Were all relevant test surfaces exercised (unit, integration, end-to-end, user-facing entrypoints), or only the easiest ones?
- **Command-output alignment**: Do the recorded test commands match the actual commands that produced the pass/fail results?
- **Hearsay vs machine evidence**: Is the evidence chain built on actual tool executions, or on manually written summaries? The latter is hearsay.

## Acceptance Criteria Check — Catch "Delivered Something Else"

Read `acceptance_criteria` from `.aiwf/state/goal.json`. For each criterion, determine: does the evidence show this was met, or not?

- If a criterion says "RSS fetches real signals from live sources" and the delivered code is a placeholder that reads a static JSON file, the criterion is **not met** — regardless of whether the code runs without errors.
- If a criterion cannot be verified from the evidence alone, flag it as `acceptance_criterion_unverified`.
- If the acceptance_criteria list is empty or only contains vague statements like "works correctly", record a `contract_gap`. A task without concrete acceptance criteria cannot be meaningfully reviewed.

This check is about fidelity to the goal, not correctness of the code. A perfectly working placeholder is still a failure if the goal asked for real integration.

## Solution Quality Check — Catch "Symptom Fix, Not Root Cause"

- **Root cause vs symptom**: Did the fix address the underlying cause, or just the visible error? A null-check suppresses a crash; understanding why null reached that point prevents the crash and all its cousins.
- **Complexity budget**: Did the solution add new flags, new abstractions, new configuration options, or new special cases? Each addition is a permanent tax on every future reader.
- **Constraint weakening**: Did the change weaken an existing constraint, contract, or invariant to accommodate the fix? Verify the weakening was intentional and justified.
- **Boundary respect**: Did the fix cross module, layer, or component boundaries that should have been respected?

## Adversarial Observations (standard_review and full_review)

Read scope: entire project. Find contract gaps, cross-module inconsistencies, blind spots. Record as observations — NOT blockers. Planner must disposition.

Kinds: `contract_gap`, `pattern_fragility`, `hotspot_warning`, `missing_surface`, `cross_module`, `mechanism_gap`.

Example:
```json
{"id":"ADV-001", "severity":"warn", "kind":"contract_gap",
 "message":"Brief defined API endpoint but didn't specify auth requirements",
 "suggestion":"Add auth_permission surface to evaluation contract",
 "disposition":"pending"}
```
