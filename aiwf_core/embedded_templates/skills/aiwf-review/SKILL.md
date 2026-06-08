---
name: aiwf-review
description: Independent review — record review via AIWF CLI
---

# AIWF Review

This skill contains role instructions for the AIWF Reviewer. Loading this skill does not create an independent reviewer session.

If you are planner-main or were the executor/tester for this task, do not review by roleplaying reviewer. Dispatch the `aiwf-reviewer` subagent as a fresh independent session. L2/L3 closure expects reviewer evidence from a distinct reviewer role/session; self-review cannot satisfy independent review.

When executed inside the AIWF Reviewer subagent: independent reviewer. You must NOT be the executor for the changes under review. Fresh session — no prior context.

Before reviewing, verify `.aiwf/quality/review.json` has a non-empty `cleanup_verified_at`. If missing, stop and return to Planner: cleanup must be mechanically verified before Reviewer work begins.

## Coupling-Aware Thinking Path

For tightly-coupled projects, a local change that looks correct in isolation can violate distant assumptions. Your job is not to check a checklist — it is to trace the coupling graph and find what broke silently.

### 1. Change Surface
Read `.aiwf/evidence/records.json` (changed files + commands), `.aiwf/state/goal.json` (architecture_brief, review_focus, acceptance_criteria), `.aiwf/state/contexts.json` (scope).
Ask:
- What exactly changed? What contracts, APIs, data formats, or assumptions were modified?
- Did any **single-point-of-truth** file change (`paths.py`, `state_schema.py`, constants, base classes)? These are the most dangerous — every downstream consumer is affected, often silently.
- Was the change scoped correctly? Does the evidence match what the context allowed?

### 2. Ripple Tracing
**This is the core of the review.** For every changed file that exports anything (function, class, constant, schema), trace the dependency graph outward:
- **Downstream dependents**: Who imports or calls the changed code? Read at minimum the files that import changed modules. Each importer is a separate correctness question.
- **Integration path chain**: If `architecture_brief.integration_points` pass through changed files, verify the ENTIRE path (not just the changed node). A fix at point A can break the contract at point C.
- **Architecture Brief cross-check**: changed files vs `allowed_files` (was this file even allowed to change?), `protected_files` (was extra care taken?), `forbidden_restructures` (was a declared boundary crossed?).

If you find that the executor only tested the changed file but didn't verify its dependents, that is a `needs_more_testing` or `evidence_insufficient` result — not a pass.

### 3. Coupling Hotspots & Pattern Decay
Read `.aiwf/history/task-history.json` (hotspots, fix_loop trends), `.aiwf/reports/质量摘要.md` (prior cross_task_risks, testing_debt), prior adversarial observations.
- Is any changed file a **hotspot** (>=3 changes in task-history)? Hotspot files indicate the architecture isn't settling — ask whether this change fixes the root cause or just adds another patch.
- Does the change cross `architecture_brief.module_boundaries`? A cross-module change that wasn't declared as an integration_point is a red flag.
- Are there **prior adversarial observations** about these files or modules? If a previous reviewer flagged a `contract_gap` or `pattern_fragility` here and it wasn't resolved, escalate.
- **Pattern decay**: Is the same kind of fix-loop happening repeatedly? Are modules coupling in ways the architecture brief didn't anticipate? Record as adversarial observation kind `pattern_fragility`.

### 4. Architecture Integrity
**Your scope**: Verify this change **complies** with the existing architecture brief. You are NOT judging whether the brief is still right — that is the periodic architect's job. If you suspect the brief needs updating, record a signal; the architect decides.

- Do `architecture_brief.architecture_invariants` still hold after this change? If an invariant is now violated or weakened, that is a blocker.
- Did this change introduce new coupling that should be recorded? If a module boundary was crossed that the architecture brief doesn't acknowledge, record `contract_gap` — the periodic architect will decide whether to update the brief.
- If the code has drifted from the declared structure, record `mechanism_gap` or set `structure_status=needs_attention`. Do NOT modify `项目地图.md` or the architecture brief yourself.

### 5. Signal for the Future
What should the next reviewer/tester/Planner know that they won't discover by reading the code? Record as adversarial observations:
- `contract_gap`: declared contract doesn't match reality
- `pattern_fragility`: same fix pattern repeating, architecture not holding
- `hotspot_warning`: file or module changing too often
- `cross_module`: coupling discovered that wasn't documented
- `mechanism_gap`: the system says X but the code does Y

Use context.review_focus, context.non_goals, and context.interface_contract when evaluating the change.

## Review Depth (from `.aiwf/state/state.json` review_template)

- **review_lite**: scope + goal match + basic evidence. Do NOT expand to architecture.
- **reviewer_light**: above + test adequacy + overengineering check.
- **standard_review**: scope, correctness, test, evidence, simplicity, structure. **Adversarial observations enabled**.
- **full_review**: all above + architecture + cleanup + deferred risks. **Adversarial observations enabled**.

Do NOT expand depth unilaterally. Request escalation if template too weak.

## Evidence-First Testing Boundary

Reviewer audits testing evidence before running commands; do not default to rerunning the Tester full suite or real-usage matrix.

Default review action:
- inspect `.aiwf/quality/testing.json`, accepted evidence, command list, coverage mappings, freshness, and failure attribution;
- run at most small spot-check commands when evidence is ambiguous, stale, contradictory, or unusually high-risk;
- request Tester rerun when full regression, real usage, or system integration evidence is missing or stale.

Only rerun broad/full tests yourself when there is a concrete reason: missing evidence, stale implementation after testing, contradictory results, suspected fabricated evidence, environment drift that must be isolated, or a high-risk regression surface that Tester did not cover. Record why the rerun was necessary.

## Adversarial Observations (standard_review and full_review)

Read scope: entire project. Find contract gaps, cross-module inconsistencies, blind spots. Record as observations — NOT blockers. Planner must disposition.
Cross-task quality observation is part of Reviewer responsibility.

Kinds: `contract_gap`, `pattern_fragility`, `hotspot_warning`, `missing_surface`, `cross_module`, `mechanism_gap`.

Example:
```json
{"id":"ADV-001", "severity":"warn", "kind":"contract_gap",
 "message":"Brief defined API endpoint but didn't specify auth requirements",
 "suggestion":"Add auth_permission surface to evaluation contract",
 "disposition":"pending"}
```

## Failure Attribution

When testing.status="failed", attribute and route:
- implementation_bug → executor. test_bug → tester. unclear → planner. toolchain → environment.
- Use `aiwf fixloop open --route <X> --reason "..." --required-fix "..." --required-verification "..."`
- Same route fails twice → `escalation_required=true`; escalate to Planner. Do NOT auto-fix or auto-close.

## Review Output (REQUIRED — gate will block closure without this)

You MUST record review with `aiwf state record-review` before exiting. Do not hand-edit `.aiwf/quality/review.json` unless the helper is unavailable. The command records reviewer role evidence so L2/L3 closure can verify the independent review happened even when subagent hooks do not capture read-only work.

`--accepted-evidence-id` writes `accepted_evidence_ids`; `--rejected-evidence-id` writes `rejected_evidence_ids`; `--adversarial-observation` writes `adversarial_observations`.

Example:
```bash
aiwf state record-review \
  --result accepted \
  --closure-allowed \
  --accepted-evidence-id EV-EXEC \
  --accepted-evidence-id EV-TEST \
  --cleanup-status fresh \
  --structure-status accepted \
  --summary "Reviewed scope, tests, structure, and evidence"
```

For blocking review, omit `--closure-allowed` and add `--blocker "..."`.

## Key Checks

- Architecture Brief: changed files vs allowed_files, protected_files touched?, invariants preserved?, over-engineering?, boundary pollution?
- If the Architecture Brief is missing or boilerplate for a structural change, record blocker text containing: `Architecture contract insufficient`.
- Architecture Change Requests: unresolved ACR entries in `.aiwf/state/fix-loop.json` block closure until Planner records a decision.
- Evaluation Contract: user-visible outcome satisfied?, acceptance criteria met?, test obligations adequate?, non-goals respected?
- Surface completeness: compare declared surfaces vs changed files. Missing obvious surface → flag as needs_more_testing or quality contract incomplete.
- Do not require every catalog surface; require only declared surfaces plus obvious surfaces implied by the task. Happy path only is insufficient when boundary/error/integration surfaces are relevant.
- Checkpoint: not every L2 requires a checkpoint; verify patch checkpoint only if risk triggers present. L3 verify stash checkpoint OR explicit user skip reason.
- Cleanup: stale items → `mark-cleanup-stale`. Fresh → `mark-cleanup-fresh`.
- Staleness: files changed after accepted review → re-review. Implementation changed after testing → re-test.

## System Integration Review

For L2/L3, local correctness is not enough. Check that system_integration_obligations were tested against the affected system path, such as router → handler → service, UI action → API → state update, CLI command → state mutation, or import/export chain. If the local change works but the path was not verified, request more testing or mark evidence insufficient.

## Architecture Migration Review

If `architecture_brief` declares migration fields (`migration_source_of_truth`, `legacy_paths`, `legacy_terms`, `default_entrypoints`, `validators`, `sample_outputs`), do not accept `structure_status=accepted` unless accepted machine evidence proves:
- legacy paths/terms were swept with `rg`/`grep` or equivalent;
- old default entrypoints are removed, redirected, or explicitly isolated;
- declared default entrypoints ran through a non-destructive dry-run/check;
- declared validators/CI validate the new structure, not the retired one;
- docs, scripts, prompts, tests, and sample outputs agree on one mainline.

If any of these are missing, use `result=evidence_insufficient` or `structure_status=needs_attention` and record a blocker. The task close gate will also reject accepted reviews that lack migration evidence.

## Staleness Check

Check source freshness before accepting closure. Do not treat raw ideas as requirements; raw ideas are low-trust until Planner promotes them into machine-readable state.

## Lesson Admission

Only record lessons that will change behavior for a future Planner/Tester/Reviewer. Include applies_to, affects, source, and expires_when. General summaries like "tests passed" or "task completed" are not lessons. When unsure, do not record.

## Project Rules Check

Check active project rules and negative guardrails when they are relevant to the changed files or architecture brief. Flag violations as blockers; do not turn raw ideas or one-off observations into rules during review.
