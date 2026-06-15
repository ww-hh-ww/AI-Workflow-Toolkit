---
name: aiwf-review-output
description: Review output format, key checks, and recording rules
---

# AIWF Review — Output

## Review Output (REQUIRED — gate will block closure without this)

You MUST record review with `aiwf state record-review` before exiting. The command records reviewer role evidence so L2/L3 closure can verify the independent review happened.

Full V2 example for `standard_review`, `full_review`, L2/L3, or governance-sensitive tasks:
```bash
aiwf state record-review \
  --verdict PASS \
  --accepted-evidence-id EV-EXEC \
  --accepted-evidence-id EV-TEST \
  --dimension-score requirement_fit=PASS \
  --dimension-score architecture_fit=PASS \
  --dimension-score minimality=PASS \
  --dimension-score correctness=PASS \
  --dimension-score test_adequacy=PASS \
  --dimension-score maintainability=PASS \
  --dimension-score risk_debt=PASS \
  --dimension-score human_trust=PASS \
  --basis-status goal=covered \
  --basis-status plan=covered \
  --basis-status scope=covered \
  --basis-status evidence=covered \
  --basis-status testing=covered \
  --basis-status impact=covered \
  --cleanup-status fresh \
  --structure-status accepted \
  --cleanup-code clean \
  --docs-checked not_applicable \
  --root-cause fixed \
  --summary "Reviewed scope, tests, structure, and evidence"
```

For `review_lite` on L0/L1 tasks, keep the output light. A V1-compatible accepted review is allowed when the task has no scope/evidence/Impact risk:
```bash
aiwf state record-review \
  --result accepted \
  --closure-allowed \
  --accepted-evidence-id EV-EXEC \
  --cleanup-status fresh \
  --structure-status accepted \
  --cleanup-code clean \
  --docs-checked not_applicable \
  --root-cause fixed \
  --summary "Light review: goal, scope, evidence, and tests are consistent"
```

Use full V2 Quality Verdict when the route is L2/L3, the review template is `standard_review` or `full_review`, the task touches AIWF governance/closure/evidence/scope/Impact, or any risk remains.

For blocking review, use `--verdict REVISE` or `--verdict REJECT`, add `--blocker "..."`, and mark at least one review basis as `gap` with a `--basis-note`.

Record observations with
`--adversarial-observation "critical:::main_path:::authentication rejects the real entrypoint"`.
CRITICAL/HIGH findings require REVISE/REJECT. After implementation changes,
Tester must rerun validation. The follow-up review must include
`--resolution "..." --resolution-evidence-id <ID>`; review history is retained.

Use verdicts as engineering quality outcomes:
- `PASS`: all quality dimensions are PASS.
- `PASS_WITH_RISK`: no FAIL dimensions, no CRITICAL/HIGH observation, at least one RISK dimension, and every RISK has a `--dimension-note`.
- `REVISE`: implementation can likely be corrected in the fix-loop. Requires at least one `--blocker`; if dimensions are scored, at least one must be RISK or FAIL.
- `REJECT`: wrong direction, unsafe structure, or not a real solution. Requires at least one `--blocker`; if dimensions are scored, at least one must be FAIL.

## Review Basis Recording

Every V2 verdict must record all six review basis items:
- `--basis-status goal=covered|gap|not_applicable`
- `--basis-status plan=covered|gap|not_applicable`
- `--basis-status scope=covered|gap|not_applicable`
- `--basis-status evidence=covered|gap|not_applicable`
- `--basis-status testing=covered|gap|not_applicable`
- `--basis-status impact=covered|gap|not_applicable`

Use `covered` only after evaluating the actual source:
- `goal`: `.aiwf/state/goal.json`, Evaluation Contract, and current user intent.
- `plan`: active `.aiwf/artifacts/plans/<PLAN-ID>.md`, especially Goal Progress, Scope, Done Means, and Verification.
- `scope`: Plan `allowed_write` / `forbidden_write`, changed files, and scope violations.
- `evidence`: accepted and rejected evidence IDs, changed files, and trust levels.
- `testing`: `.aiwf/artifacts/quality/testing.json`, commands, coverage, untested risks, and changed-file risk.
- `impact`: active plan's Impact section against actual project/governance/support changes.

Use `gap` when that source contradicts closure or is insufficient. `gap` and `not_applicable` require a `--basis-note name_note=...`.

## Impact-Aware Docs Check

Use `--docs-checked yes` only when `Impact.docs=yes` and required docs were updated or verified.
Use `--docs-checked not_applicable` when `Impact.docs=no`.
Use `--docs-checked no` when `Impact.docs=yes` but docs were missed.

## Quality Dimension Questions

Score each dimension from evidence, not intuition:
- `requirement_fit`: does the delivered behavior actually satisfy the Goal, Evaluation Contract, and active plan Done Means?
- `architecture_fit`: does the implementation respect module boundaries, architecture_brief invariants, protected files, and integration points?
- `minimality`: is this the smallest sufficient change, without speculative abstraction, broad refactor, or unnecessary configuration?
- `correctness`: does the code handle the intended behavior and important failure paths, not just the happy path?
- `test_adequacy`: do recorded tests verify Plan.Verification, changed-file risk, acceptance criteria, and the selected routing level?
- `maintainability`: will future engineers understand and safely extend this change without hidden coupling or unclear ownership?
- `risk_debt`: are residual risks, deferred tests, hotspots, and technical debt explicit and acceptable for this task?
- `human_trust`: would a human reviewer trust the evidence chain and explanation enough to rely on this result?

## Key Checks

- Architecture Brief: changed files vs allowed_files, protected_files touched?, invariants preserved?, over-engineering?, boundary pollution?
- If the Architecture Brief is missing or boilerplate for a structural change, record blocker: `Architecture contract insufficient`.
- Architecture Change Requests: unresolved ACR entries in `.aiwf/state/fix-loop.json` block closure until Planner records a decision.
- Evaluation Contract: user-visible outcome satisfied?, acceptance criteria met?, test obligations adequate?, non-goals respected?
- Surface completeness: compare declared surfaces vs changed files. Missing obvious surface -> flag as needs_more_testing.
- Cleanup: stale items -> `mark-cleanup-stale`. Fresh -> `mark-cleanup-fresh`.
- Staleness: files changed after accepted review -> re-review. Implementation changed after testing -> re-test.
- Quality dimensions: requirement_fit, architecture_fit, minimality, correctness, test_adequacy, maintainability, risk_debt, human_trust.
- Root cause: reject symptom-only fixes unless explicitly scoped as temporary risk.

## Evidence-First Testing Boundary

Audit testing evidence before running commands. Default: inspect `.aiwf/artifacts/quality/testing.json`, accepted evidence, command list, coverage mappings. Run small spot-checks only when evidence is ambiguous, stale, or contradictory. Request Tester rerun when full regression or system integration evidence is missing.

Only rerun broad tests yourself when there is a concrete reason: missing evidence, stale implementation, contradictory results, suspected fabricated evidence, or high-risk regression surface that Tester did not cover.
