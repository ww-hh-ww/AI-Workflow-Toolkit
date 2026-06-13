---
name: aiwf-review
description: Independent review — dispatch reviewer subagent, load sub-skills by phase
---

# AIWF Review

## STOP — Check topology BEFORE any other action

Read `.aiwf/state/state.json` → `execution_topology`.

**If execution_topology is "standard_team" or "fanout_merge":**
You are planner-main. You do NOT review.

```
Agent({subagent_type: "aiwf-reviewer", prompt: "..."})
```

**If execution_topology is "light_review" and you are planner-main:**
The testing subagent (aiwf-reviewer) also handles review. Do NOT spawn a new one.

```
SendMessage(to: "<aiwf-reviewer-agent-id>", prompt: "now review. record-review.")
```

**Only continue below if execution_topology IS "single_agent" or "single_agent_with_machine_evidence".**

---

Before reviewing, verify `.aiwf/artifacts/quality/review.json` has a non-empty `cleanup_verified_at`. If missing, stop and return to Planner: cleanup must be mechanically verified before Reviewer work begins.

Read the active context from `.aiwf/state/contexts.json`: `context.review_focus`, `context.non_goals`, and `context.interface_contract` define review boundaries. Do not expand beyond them unilaterally.

Read `.aiwf/state/goal.json` `quality_brief.architecture_brief` for `allowed_files`, `protected_files`, `forbidden_restructures`, and module boundaries. If the architecture brief is missing or incomplete for the scope of changes, treat "Architecture contract insufficient" as a potential blocker.

## Review Basis Contract

Review must evaluate Goal + Plan + Scope + Evidence + Testing + Impact as one contract. Read `.aiwf/state/goal.json`, `.aiwf/artifacts/plans/<PLAN-ID>.md`, `.aiwf/state/contexts.json`, `.aiwf/artifacts/evidence/records.json`, `.aiwf/artifacts/quality/testing.json`, and the active plan's `Impact` section before recording review.

If the active plan does not match the actual changed files, evidence, testing, or Impact declarations, record a blocker or request Planner plan update before acceptance. Do not accept by testing status alone.

Cross-task quality observation is part of Reviewer responsibility: note repeated-change hotspots, architecture drift, or testing debt when they affect the reviewed change.

## Work Intent Discipline

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

## Admission & Structure Review (Stage 4.6)

Before the standard review dimensions, verify the structural integrity of every change. The Rooted Functional Tree requires that every change has a structural home and every piece of evidence rolls up to a Plan and Goal.

### Structural Checklist

1. **Ownership** — does every change have a structural home?
   - An Admission Decision exists and is valid, OR
   - A valid lightweight existing-plan ownership exists (`action_granularity=patch|task` with `target_plan_id` or `active_plan_id`), OR
   - A Day-1 Foundation Tree Proposal was accepted.
   - If none of these: flag as **orphan patch**.

2. **Plan integrity**:
   - Plan has `target_goal_id` in `plans.json`.
   - Plan has `plan_kind` set.
   - Changed files stay within Plan scope (`allowed_write` / `constraints`).

3. **Task integrity**:
   - Task has `plan_id`.
   - Task is attached to the correct Plan for its scope.

4. **Lightweight patch check** (when no new Plan was created):
   - Has `target_plan_id` or `active_plan_id`.
   - Does not silently expand scope beyond the existing Plan.

5. **Graft check** (when a new Goal was grafted):
   - Has `interface_consumed` declared.
   - Has `capability_provided` declared.
   - Has `relation_to_parent` declared.
   - Parent Goal's interface boundary is respected.

6. **Cross relations check**:
   - Cross-parent sibling relations have an explicit `reason`.
   - Relations do not silently mutate Goals.

7. **Evidence rollup**:
   - Evidence references which Plan and Goal it supports.
   - Implementation evidence does not skip the Plan level to directly claim Goal completion.
   - Task must never directly complete a Goal.

8. **Scope boundary check**:
   - Implementation did not exceed Plan constraints.
   - No silent Goal mutation (Plan did not redefine its Goal).
   - No Goal graft without interface declaration.

### Admission Review Output

Record in the review output (before the standard review sections):

```
## Admission Review
- trace_status: clean | issues_found
- orphan_patch_status: none | warning | blocker
- structural_risk: low | medium | high
- evidence_rollup: valid | incomplete | missing
- next_review_focus: <concrete next step or "none">
```

**Severity rules:**
- Orphan patch (no structural home) → **blocker**. Do not accept.
- Silent Goal mutation → **blocker**. Do not accept.
- Missing `target_goal_id` or `plan_id` → `review_attention` at minimum. For L2/L3: **blocker**.
- Missing graft interface fields → `review_attention`. Request Planner to record them.
- Cross relation without reason → `review_attention`. Advisory only.
- Evidence not rolling up to Plan/Goal → `review_attention`. Request evidence re-attribution.

The Admission Review is not advisory decoration — it is the structural gatekeeper. If the change's structural home is unclear, the rest of the review rests on uncertain ground.

## Review Depth (from `.aiwf/state/state.json` review_template)

| Depth | Scope |
|-------|-------|
| review_lite | scope + goal match + basic evidence. Do NOT expand. |
| reviewer_light | above + test adequacy + overengineering check |
| standard_review | scope, correctness, test, evidence, simplicity, structure. Adversarial observations enabled. |
| full_review | all above + architecture + cleanup + deferred risks. Adversarial observations enabled. |

Do NOT expand depth unilaterally. Request escalation if template too weak. When testing evidence is insufficient, record `needs_more_testing` rather than accepting.

## Evidence-First Testing Boundary

do not default to rerunning the Tester full suite or real-usage matrix. Audit testing evidence first; run only small spot-check commands unless evidence is missing, stale, contradictory, unusually high-risk, or appears fabricated. Request Tester rerun for missing/stale full validation and record why any broad rerun was necessary.

When recording review, use `--accepted-evidence-id` to reference accepted evidence IDs (`accepted_evidence_ids`) and `--rejected-evidence-id` for rejected ones (`rejected_evidence_ids`). Accepted evidence IDs must be relevant, machine-observed where possible, and sufficient for the claim being closed.

When recording AIWFRoleEvidence for the reviewer role, use `--scan-git` to corroborate the review with current changed files. Prefer `aiwf state record-review --verdict ...` for V2 quality outcomes; `review_lite` may use V1 `--result accepted --closure-allowed` when risk is low.

## Sub-Skills (load in order)

| Step | Load |
|------|------|
| 1. Trace coupling | `/aiwf-review-trace` — Change surface, ripple tracing, hotspots, architecture integrity, system integration |
| 2. Verify quality | `/aiwf-review-verify` — Evidence integrity, acceptance criteria, solution quality, adversarial observations |
| 3. Record output | `/aiwf-review-output` — Review command, key checks checklist, evidence-first testing boundary |
