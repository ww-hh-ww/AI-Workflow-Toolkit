---
name: aiwf-review-output
description: Review output format, key checks, and recording rules
---

# AIWF Review — Output

## Review Output (REQUIRED — gate will block closure without this)

You MUST record review with `aiwf state record-review` before exiting. The command records reviewer role evidence so L2/L3 closure can verify the independent review happened.

Example:
```bash
aiwf state record-review \
  --result accepted \
  --closure-allowed \
  --accepted-evidence-id EV-EXEC \
  --accepted-evidence-id EV-TEST \
  --cleanup-status fresh \
  --structure-status accepted \
  --cleanup-code clean \
  --docs-checked yes \
  --root-cause fixed \
  --summary "Reviewed scope, tests, structure, and evidence"
```

For blocking review, omit `--closure-allowed` and add `--blocker "..."`.

## Key Checks

- Architecture Brief: changed files vs allowed_files, protected_files touched?, invariants preserved?, over-engineering?, boundary pollution?
- If the Architecture Brief is missing or boilerplate for a structural change, record blocker: `Architecture contract insufficient`.
- Architecture Change Requests: unresolved ACR entries in `.aiwf/state/fix-loop.json` block closure until Planner records a decision.
- Evaluation Contract: user-visible outcome satisfied?, acceptance criteria met?, test obligations adequate?, non-goals respected?
- Surface completeness: compare declared surfaces vs changed files. Missing obvious surface -> flag as needs_more_testing.
- Cleanup: stale items -> `mark-cleanup-stale`. Fresh -> `mark-cleanup-fresh`.
- Staleness: files changed after accepted review -> re-review. Implementation changed after testing -> re-test.

## Evidence-First Testing Boundary

Audit testing evidence before running commands. Default: inspect `.aiwf/quality/testing.json`, accepted evidence, command list, coverage mappings. Run small spot-checks only when evidence is ambiguous, stale, or contradictory. Request Tester rerun when full regression or system integration evidence is missing.

Only rerun broad tests yourself when there is a concrete reason: missing evidence, stale implementation, contradictory results, suspected fabricated evidence, or high-risk regression surface that Tester did not cover.
