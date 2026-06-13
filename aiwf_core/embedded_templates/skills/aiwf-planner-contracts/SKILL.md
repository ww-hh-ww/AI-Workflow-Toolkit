---
name: aiwf-planner-contracts
description: Architecture Brief, Evaluation Contract, Quality Policy — freeze before execution
---

# AIWF Planner — Contracts

Freeze these before any L1+ implementation. L0: minimal. L1/L2: standard. L3: complete.

## Tree-Driven Inheritance

When you create a context under an existing Plan + Goal, defaults are auto-inherited from the tree.
You only declare deltas — what's different from the parent.

**Inheritance chain:**

| Source | Inherited as | Override with |
|--------|-------------|---------------|
| Goal `surface_types` | default `test_focus` entries | `--test-focus` |
| Goal `architecture_invariants` | default `review_focus` entries | `--review-focus` |
| Goal `non_goals` | default `non_goals` | `--non-goal` |
| Goal `module_boundaries` | suggested `allowed_write` | `--allowed-write` |
| Architecture Brief `protected_files` | suggested `forbidden_write` | `--forbidden-write` |
| Architecture Brief `forbidden_restructures` | `escalation_triggers` | `--escalation-trigger` |
| Plan `interfaces` | default `interface_contract` | `--interface-contract` |
| Plan `work_intent` | derived `forbidden_changes` (informational) | — |
| Plan `constraints` | context constraints (informational) | — |
| Temporary Root | auto `non_goals: isolate from stable structure` | — |

**Validation:** if inherited `non_goals` overlap with `allowed_write`, a warning is injected into context notes.

**Override rule:** Planner's explicit CLI arguments always win over inherited defaults.
If you pass `--test-focus "custom"`, it replaces the inherited test_focus entirely.

## Architecture Brief (L1+ required, L2+ must include structural fields)

Defines structural boundaries:
```
aiwf state record-quality-brief \
  --target-structure "Add divide as peer calculator operation" \
  --allowed-file src/calc.js --protected-file src/shared/validation.js \
  --architecture-invariant "Existing add/subtract/multiply APIs unchanged" \
  --forbidden-restructure "Do not redesign shared numeric validation" \
  --integration-point "calculator public export path"
```

For architecture migration tasks, add `--migration-source-of-truth`, `--legacy-path`, `--legacy-term`, `--default-entrypoint`, `--validator`.

## Context Dispatch

Use `aiwf state start-context` to create scoped execution boundaries with `--purpose`, `--test-focus`, `--review-focus`, `--non-goal`, `--escalation-trigger`. Context fields inform role execution within `allowed_write` — they do not expand write boundaries.

## Evaluation Contract (L2+ required)

Turns user intent into acceptance criteria. Record via `aiwf state record-quality-brief`:
- `--acceptance-criterion`, `--test-focus`, `--review-focus`, `--non-goal`, `--escalation-trigger`
- Select 1-3 surface_types (`aiwf quality surfaces`) for test/review direction
- `--user-visible-outcome`, `--test-obligation`, `--review-obligation`, `--known-risk`, `--closure-question`

## Quality Policy

```
aiwf state record-quality-policy --task-type <T> --workflow-level <L> --risk-flag <F> --reason "..."
```

Valid task_types: code_label_or_text_change, small_function, bug_fix, api_endpoint, refactor, numeric_semantics, security_sensitive, documentation, embedded_or_hardware.

## Docs / Assets Impact

Declare whether this task changes docs or assets in the active plan. If impact=yes, verify after implementation. If impact=no, do not invent docs/assets work. Capabilities and raw ideas are optional — load only when the task declares it needs them.

External capabilities cannot override AIWF gates: scope, evidence, testing, review, Impact, cleanup, and prepare-close remain authoritative.

## System Integration Obligations (L2+)

When task touches local change + whole-system boundary:
- L0/L1: optional. L2/L3: MUST write.
- Name the affected system path: router -> handler -> service, UI -> API -> state, CLI -> mutation.
- Record: `--system-integration-obligation "..."`
