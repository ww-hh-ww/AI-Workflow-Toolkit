---
name: aiwf-planner-contracts
description: Architecture Brief, Evaluation Contract, Quality Policy — freeze before execution
---

# AIWF Planner — Contracts

Freeze these before any L1+ implementation. L0: minimal. L1/L2: standard. L3: complete.

## Architecture Brief (L1+ required, L2+ must include structural fields)

Defines structural boundaries. Example:
```
aiwf state record-quality-brief \
  --target-structure "Add divide as peer calculator operation" \
  --allowed-file src/calc.js --protected-file src/shared/validation.js \
  --architecture-invariant "Existing add/subtract/multiply APIs unchanged" \
  --forbidden-restructure "Do not redesign shared numeric validation" \
  --integration-point "calculator public export path"
```

For architecture migration tasks, add:
```
--migration-source-of-truth "README.md + scripts/new-mainline.sh define the only supported flow" \
--legacy-path "scripts/old-mainline.sh" \
--legacy-term "old_handoff" \
--default-entrypoint "scripts/new-mainline.sh" \
--validator "scripts/validate.sh"
```

## Evaluation Contract (L1+ required)

Turns user intent into acceptance criteria. Tester/Reviewer use this to verify.
Record via `aiwf state record-quality-brief`:
- acceptance_criteria, test_focus, review_focus, non_goals, escalation_triggers
- Select 1-3 surface_types (`aiwf quality surfaces`) for test/review direction

## Quality Policy

Valid task_types: code_label_or_text_change, small_function, bug_fix, api_endpoint, refactor, numeric_semantics, security_sensitive, documentation, embedded_or_hardware.
```
aiwf state record-quality-policy --task-type <T> --workflow-level <L> --risk-flag <F> --reason "..."
```

## System Integration Obligations (L2+)

When task touches local change + whole-system boundary:
- L0: Usually not needed. L1: 1 obligation if touching public API. L2/L3: MUST write.
- Name the affected system path: router -> handler -> service, UI action -> API -> state update, CLI command -> state mutation, import/export chain.
- Record: `--system-integration-obligation "..."`
