---
name: aiwf-review
description: Independent review — dispatch reviewer subagent, load sub-skills by phase
---

# AIWF Review

> **L1+ = native subagent dispatch/check. L0 = inline. If a user-confirmed downgrade already changed the level to L0, follow L0. Otherwise call the native Agent/Task tool — reviewing inline at L2+ is a GATE VIOLATION.**

## DISPATCH GATE — READ FIRST, ACT NOW

Read `.aiwf/state/state.json` → `workflow_level`.

### L0_direct → skip to "L0 Review" section at bottom of this file

### L1_review_light → check then proceed

The testing phase already spawned an `aiwf-reviewer` sub-agent that handled BOTH testing AND review. Read `.aiwf/artifacts/quality/review.json`:

- **Verdict exists (PASS / PASS_WITH_RISK / REVISE / REJECT):** review is complete. Proceed to meta-critique or close.
- **No verdict recorded:** the reviewer-light didn't complete its job. Report to planner: "Reviewer-light did not record review — re-run testing phase." Do NOT review inline and do NOT spawn a new agent.

### L2_standard_team / L3_full_power → CALL NATIVE SUBAGENT TOOL NOW (aiwf-reviewer)

You are planner-main. Reviewing yourself is a gate violation. The close gate checks review.json for an independent reviewer verdict — if YOU recorded it, close REJECTS it.

**Step 1 — Read state to build the prompt:**

1. `.aiwf/state/state.json` — `active_task_id`, `workflow_level`, `review_template`, `review_need`, `execution_topology`
2. `.aiwf/state/plans.json` — active Plan: `allowed_write`, `forbidden_write`, `work_intent`, `plan_kind`, `review_focus`, `interfaces`, `constraints`
3. `.aiwf/state/goal.json` — `quality_brief.architecture_brief` (protected_files, forbidden_restructures, integration_points)
4. `.aiwf/artifacts/quality/testing.json` — testing results to audit
5. `.aiwf/artifacts/evidence/records.json` — executor evidence

**Step 2 — Call Claude Code's native subagent tool (`Agent`/`Task`) with:**

| Parameter | Value |
|-----------|-------|
| subagent_type | `"aiwf-reviewer"` |
| description | `"Review TASK-XXX"` |
| prompt | Task ID + plan ID + `review_template` + `review_need` + `work_intent` + `plan_kind` + `allowed_write` + `review_focus` + `protected_files` + `forbidden_restructures` + `integration_points` + `"Run aiwf status first. Read .aiwf/state/ for full context. You are an INDEPENDENT reviewer — you must NOT be the executor. Audit testing evidence before re-running tests. Load sub-skills in order: aiwf-review-trace → aiwf-review-verify → aiwf-review-output. Record review with aiwf state record-review --verdict PASS (or REVISE/REJECT). If fallback reviewer role evidence is needed, use aiwf state record-role-evidence --role reviewer --task-id <TASK-ID>. Include all 6 review basis items (goal, plan, scope, evidence, testing, impact). CRITICAL/HIGH findings require REVISE/REJECT, not PASS_WITH_RISK. Record adversarial observations."` |

Do not replace this with shell commands, a checklist, or planner-main roleplay.

**Step 3 — Wait for reviewer to finish.** Forward the verdict to meta-critique or close.

---

**>>> STOP HERE IF NOT L0_direct. Content below is L0 only. <<<**

---

## L0 Review (inline, self-review OK)

Before reviewing, verify `.aiwf/artifacts/quality/review.json` has a non-empty `cleanup_verified_at`. If missing, stop and return to Planner: cleanup must be mechanically verified before Reviewer work begins.

Read the active Plan from `.aiwf/state/plans.json`: `review_focus`, `non_goals`, and `interface_contract` define review boundaries. Do not expand beyond them unilaterally.

Read `.aiwf/state/goal.json` `quality_brief.architecture_brief` for `allowed_files`, `protected_files`, `forbidden_restructures`, and module boundaries. If the architecture brief is missing or incomplete for the scope of changes, treat "Architecture contract insufficient" as a potential blocker.

### Review Basis Contract

Review must evaluate Goal + Plan + Scope + Evidence + Testing + Impact as one contract. Read `.aiwf/state/goal.json`, `.aiwf/artifacts/plans/<PLAN-ID>.md`, `.aiwf/state/plans.json`, `.aiwf/artifacts/evidence/records.json`, `.aiwf/artifacts/quality/testing.json`, and the active plan's `Impact` section before recording review.

If the active plan does not match the actual changed files, evidence, testing, or Impact declarations, record a blocker or request Planner plan update before acceptance. Do not accept by testing status alone.

Cross-task quality observation is part of Reviewer responsibility: note repeated-change hotspots, architecture drift, or testing debt when they affect the reviewed change.

### Work Intent Discipline

Review checklist varies by work_intent. Read the active Plan's `work_intent`:
- **feature**: goal fit, acceptance criteria pass, interfaces documented, no unrelated changes.
- **bugfix**: root cause addressed, regression coverage exists, scope stayed local.
- **refactor**: external behavior preserved, no source-of-truth drift, no feature creep.
- **cleanup**: no required files removed, machine truth untouched, debug/review ability preserved.
- **migration**: old data preserved, compatibility maintained, no double source of truth.
- **verification**: evidence supports Plan/Goal, no implementation drift, uncertainties explicit.
- **exploration**: exploration isolated, learnings captured, next structural decision clear.
- **documentation**: docs match implementation, no overclaiming, terminology consistent.
- **integration**: branches coherent, interfaces stable, gaps explicit, downstream safe.
- **release**: package clean, version boundary clear, tests/audit pass, docs and package match.

### Admission & Structure Review (Stage 4.6)

Before the standard review dimensions, verify the structural integrity of every change:

1. **Ownership** — does every change have a structural home? (Admission Decision, lightweight existing-plan, or Day-1 Foundation Tree Proposal.) If none: flag as **orphan patch**.

2. **Plan integrity**: Plan has `target_goal_id`, `plan_kind` set. Changed files stay within Plan scope (`allowed_write` / `constraints`).

3. **Task integrity**: Task has `plan_id`. Task is attached to the correct Plan for its scope.

4. **Lightweight patch check** (when no new Plan was created): Has `target_plan_id` or `active_plan_id`. Does not silently expand scope.

5. **Graft check** (when new Goal was grafted): Has `interface_consumed`, `capability_provided`, `relation_to_parent` declared. Parent Goal's interface boundary is respected.

6. **Cross relations check**: Cross-parent sibling relations have an explicit `reason`. Relations do not silently mutate Goals.

7. **Evidence rollup**: Evidence references which Plan and Goal it supports. Implementation evidence does not skip the Plan level to directly claim Goal completion. Task must never directly complete a Goal.

8. **Scope boundary check**: Implementation did not exceed Plan constraints. No silent Goal mutation. No Goal graft without interface declaration.

Record in review output:
```
## Admission Review
- trace_status: clean | issues_found
- orphan_patch_status: none | warning | blocker
- structural_risk: low | medium | high
- evidence_rollup: valid | incomplete | missing
- next_review_focus: <concrete next step or "none">
```

**Severity:**
- Orphan patch → **blocker**. Do not accept.
- Silent Goal mutation → **blocker**. Do not accept.
- Missing `target_goal_id` or `plan_id` → `review_attention` minimum. L2/L3: **blocker**.
- Missing graft interface fields → `review_attention`. Request Planner to record them.
- Evidence not rolling up → `review_attention`. Request evidence re-attribution.

### Review Depth (from `.aiwf/state/state.json` review_template)

| Depth | Scope |
|-------|-------|
| review_lite | scope + goal match + basic evidence. Do NOT expand. |
| reviewer_light | above + test adequacy + overengineering check |
| standard_review | scope, correctness, test, evidence, simplicity, structure. Adversarial observations enabled. |
| full_review | all above + architecture + cleanup + deferred risks. Adversarial observations enabled. |

Do NOT expand depth unilaterally. Request escalation if template too weak. When testing evidence is insufficient, record `needs_more_testing` rather than accepting.

### Evidence-First Testing Boundary

do not default to rerunning the Tester full suite or real-usage matrix. Audit testing evidence first; run only small spot-check commands unless evidence is missing, stale, contradictory, unusually high-risk, or appears fabricated. Request Tester rerun for missing/stale full validation and record why any broad rerun was necessary.

### Sub-Skills (load in order)

| Step | Load |
|------|------|
| 1. Trace coupling | `/aiwf-review-trace` — Change surface, ripple tracing, hotspots, architecture integrity, system integration |
| 2. Verify quality | `/aiwf-review-verify` — Evidence integrity, acceptance criteria, solution quality, adversarial observations |
| 3. Record output | `/aiwf-review-output` — Review command, key checks checklist, evidence-first testing boundary |

### Key Checks

- Architecture Brief: changed files vs allowed_files, protected_files touched?, invariants preserved?, over-engineering?, boundary pollution?
- If the Architecture Brief is missing or boilerplate for a structural change, record blocker: `Architecture contract insufficient`.
- Architecture Change Requests: unresolved ACR entries in `.aiwf/state/fix-loop.json` block closure until Planner records a decision.
- Evaluation Contract: user-visible outcome satisfied?, acceptance criteria met?, test obligations adequate?, non-goals respected?
- Surface completeness: compare declared surfaces vs changed files. Missing obvious surface -> flag as needs_more_testing.
- Cleanup: stale items -> `mark-cleanup-stale`. Fresh -> `mark-cleanup-fresh`.
- Staleness: files changed after accepted review -> re-review. Implementation changed after testing -> re-test.
- Quality dimensions: requirement_fit, architecture_fit, minimality, correctness, test_adequacy, maintainability, risk_debt, human_trust.
- Root cause: reject symptom-only fixes unless explicitly scoped as temporary risk.

### Impact-Aware Docs Check

Use `--docs-checked yes` only when `Impact.docs=yes` and required docs were updated or verified.
Use `--docs-checked not_applicable` when `Impact.docs=no`.
Use `--docs-checked no` when `Impact.docs=yes` but docs were missed.

### Quality Dimension Questions

Score each dimension from evidence, not intuition:
- `requirement_fit`: does the delivered behavior actually satisfy the Goal, Evaluation Contract, and active plan Done Means?
- `architecture_fit`: does the implementation respect module boundaries, architecture_brief invariants, protected files, and integration points?
- `minimality`: is this the smallest sufficient change, without speculative abstraction, broad refactor, or unnecessary configuration?
- `correctness`: does the code handle the intended behavior and important failure paths, not just the happy path?
- `test_adequacy`: do recorded tests verify Plan.Verification, changed-file risk, acceptance criteria, and the selected routing level?
- `maintainability`: will future engineers understand and safely extend this change without hidden coupling or unclear ownership?
- `risk_debt`: are residual risks, deferred tests, hotspots, and technical debt explicit and acceptable for this task?
- `human_trust`: would a human reviewer trust the evidence chain and explanation enough to rely on this result?

### Recording Review (REQUIRED — gate will block closure without this)

If machine evidence is missing or attribution is unclear, add role evidence with
`aiwf state record-role-evidence --role reviewer --scan-git ...`; this records
an `AIWFRoleEvidence` entry. Do not hand-edit evidence or review JSON.

Full V2 example for standard_review / full_review / L2/L3:
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

For review_lite on L0/L1 tasks:
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

CRITICAL/HIGH findings require REVISE/REJECT. After changes, Tester must rerun. Follow-up review must include `--resolution "..." --resolution-evidence-id <ID>`.

Verdicts:
- `PASS`: all quality dimensions are PASS.
- `PASS_WITH_RISK`: no FAIL dimensions, no CRITICAL/HIGH observation, at least one RISK dimension, every RISK has a `--dimension-note`.
- `REVISE`: implementation can likely be corrected in fix-loop. Requires `--blocker`.
- `REJECT`: wrong direction, unsafe structure. Requires `--blocker`.

### Review Basis Recording

Every V2 verdict must record all six review basis items:
- `--basis-status goal=covered|gap|not_applicable`
- `--basis-status plan=covered|gap|not_applicable`
- `--basis-status scope=covered|gap|not_applicable`
- `--basis-status evidence=covered|gap|not_applicable`
- `--basis-status testing=covered|gap|not_applicable`
- `--basis-status impact=covered|gap|not_applicable`

Use `gap` when that source contradicts closure or is insufficient. `gap` and `not_applicable` require `--basis-note`.
