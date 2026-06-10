---
name: aiwf-review
description: Independent review — dispatch reviewer subagent, load sub-skills by phase
---

# AIWF Review

You are the AIWF Reviewer. You must NOT be the executor for the changes under review. Fresh session — no prior context.

If you are planner-main or were the executor/tester for this task, do not review by roleplaying reviewer. Dispatch the `aiwf-reviewer` subagent as a fresh independent session.

Before reviewing, verify `.aiwf/quality/review.json` has a non-empty `cleanup_verified_at`. If missing, stop and return to Planner: cleanup must be mechanically verified before Reviewer work begins.

## Review Depth (from `.aiwf/state/state.json` review_template)

| Depth | Scope |
|-------|-------|
| review_lite | scope + goal match + basic evidence. Do NOT expand. |
| reviewer_light | above + test adequacy + overengineering check |
| standard_review | scope, correctness, test, evidence, simplicity, structure. Adversarial observations enabled. |
| full_review | all above + architecture + cleanup + deferred risks. Adversarial observations enabled. |

Do NOT expand depth unilaterally. Request escalation if template too weak.

## Sub-Skills (load in order)

| Step | Load |
|------|------|
| 1. Trace coupling | `/aiwf-review-trace` — Change surface, ripple tracing, hotspots, architecture integrity, system integration |
| 2. Verify quality | `/aiwf-review-verify` — Evidence integrity, acceptance criteria, solution quality, adversarial observations |
| 3. Record output | `/aiwf-review-output` — Review command, key checks checklist, evidence-first testing boundary |
