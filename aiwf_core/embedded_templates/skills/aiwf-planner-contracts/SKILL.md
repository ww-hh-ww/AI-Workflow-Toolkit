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

**Inheritance is a starting point, not the final answer.** After inheriting defaults, build the actual set this task needs — not just resize the parent's boundaries.

**What stays, what goes, what's new?**
Some inherited paths you keep. Some you drop because this task doesn't touch them. Some you add because this task introduces new files or reaches into modules the parent never listed. The result is a task-specific set, not a scaled version of the parent.

If dropping inherited paths: no explanation needed — the parent's scope was just broader than this task.
If adding new paths: record the reason. Is this a new module? A cross-cutting change? A one-time migration pass? The next Planner needs to know why this task's scope is different from the parent's default.

**What should this task explicitly NOT touch?**
- Files that other Plans under the same Goal are actively working on
- Interfaces that this Plan consumes but does not own
- Legacy paths that look in-scope but are migration-protected

Declare these as `--forbidden-write` and `--escalation-trigger`. If the Executor hits them, stop — don't expand.

**What new boundaries does this task create?**
If this Plan introduces a new interface, module, or data format, declare it. Later Plans will inherit it. A boundary not declared today is a scope violation for someone else tomorrow.

**What could a future task need to know about this one's decisions?**
Record in the Plan's Decision section. The carry-forward at task close will surface it.

**Override rule:** Planner's explicit CLI arguments always win over inherited defaults.
If you pass `--test-focus "custom"`, it replaces the inherited test_focus entirely.

**Before freezing contracts, step back and ask:**
- What did I explicitly exclude that the parent includes? Why?
- What new constraint did I add that the parent didn't have? Why?
- If another Planner picks up this task in 3 months, what would they wish I had written down?

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

## Scope & Guidance

Plan scope is set directly on the Plan (no separate context entity). Set `allowed_write` and guidance fields on the Plan itself:
```
aiwf plan create PLAN-001 --goal-id GOAL-001 \
  --allowed-write 'src/calc.js' --allowed-write 'test/calc.test.js' \
  --purpose 'Implement divide operation within existing calculator surface'
```
Guidance fields (`test_focus`, `review_focus`, `non_goals`, `escalation_triggers`) are Plan fields — set them on the Plan, not a separate context. Tasks inherit from the Plan on activation.

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
