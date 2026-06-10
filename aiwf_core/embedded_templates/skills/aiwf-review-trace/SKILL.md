---
name: aiwf-review-trace
description: Coupling-aware change analysis — change surface, ripple tracing, hotspots, architecture integrity
---

# AIWF Review — Trace

For tightly-coupled projects, a local change that looks correct in isolation can violate distant assumptions. Your job is to trace the coupling graph and find what broke silently.

## 1. Change Surface

Read `.aiwf/evidence/records.json` (changed files + commands), `.aiwf/state/goal.json` (architecture_brief, review_focus, acceptance_criteria), `.aiwf/state/contexts.json` (scope).
Ask:
- What exactly changed? What contracts, APIs, data formats, or assumptions were modified?
- Did any single-point-of-truth file change (paths, constants, base classes)? These are the most dangerous.
- Was the change scoped correctly? Does the evidence match what the context allowed?

## 2. Ripple Tracing

For every changed file that exports anything (function, class, constant, schema), trace the dependency graph outward:
- **Downstream dependents**: Who imports or calls the changed code? Each importer is a separate correctness question.
- **Integration path chain**: If `architecture_brief.integration_points` pass through changed files, verify the ENTIRE path.
- **Architecture Brief cross-check**: changed files vs `allowed_files`, `protected_files`, `forbidden_restructures`.

If the executor only tested the changed file but didn't verify its dependents, that is `needs_more_testing` or `evidence_insufficient` — not a pass.

## 3. Coupling Hotspots & Pattern Decay

Read `.aiwf/history/task-history.json`, `.aiwf/reports/质量摘要.md`, prior adversarial observations.
- Is any changed file a hotspot (>=3 changes)? Ask whether this change fixes the root cause or just adds another patch.
- Does the change cross `architecture_brief.module_boundaries` without being declared as an integration_point?
- Are there prior adversarial observations about these files or modules? Escalate if unresolved.
- Pattern decay: Is the same fix-loop happening repeatedly? Record as `pattern_fragility`.

## 4. Architecture Integrity

Verify this change complies with the existing architecture brief. You are NOT judging whether the brief is still right — that is the periodic architect's job.
- Do `architecture_brief.architecture_invariants` still hold? If violated or weakened, that is a blocker.
- Did this change introduce new coupling? Record `contract_gap` if a boundary was crossed without brief acknowledgment.
- If the code has drifted from declared structure, record `mechanism_gap`. Do NOT modify PROJECT-MAP or the brief.

## 5. Signal for the Future

Record as adversarial observations:
- `contract_gap`: declared contract doesn't match reality
- `pattern_fragility`: same fix pattern repeating
- `hotspot_warning`: file or module changing too often
- `cross_module`: undocumented coupling discovered
- `mechanism_gap`: system says X but code does Y

## System Integration

For L2/L3, check that system_integration_obligations were tested: router -> handler -> service, UI action -> API -> state update, CLI command -> state mutation, import/export chain. If local change works but path was not verified, request more testing or mark evidence insufficient.
