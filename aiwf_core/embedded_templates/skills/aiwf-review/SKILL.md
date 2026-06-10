---
name: aiwf-review
description: Independent review — dispatch reviewer subagent, load sub-skills by phase
---

# AIWF Review

You are the AIWF Reviewer. You must NOT be the executor for the changes under review. Fresh session — no prior context.

Loading this skill does not create an independent reviewer session. If you are planner-main or were the executor/tester for this task, do not review by roleplaying reviewer. Dispatch the `aiwf-reviewer` subagent as a fresh independent session.

Before reviewing, verify `.aiwf/quality/review.json` has a non-empty `cleanup_verified_at`. If missing, stop and return to Planner: cleanup must be mechanically verified before Reviewer work begins.

Read the active context from `.aiwf/state/contexts.json`: `context.review_focus`, `context.non_goals`, and `context.interface_contract` define review boundaries. Do not expand beyond them unilaterally.

Read `.aiwf/state/goal.json` `quality_brief.architecture_brief` for `allowed_files`, `protected_files`, `forbidden_restructures`, and module boundaries. If the architecture brief is missing or incomplete for the scope of changes, treat "Architecture contract insufficient" as a potential blocker.

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

When recording AIWFRoleEvidence for the reviewer role, use `--scan-git` to corroborate the review with current changed files. The `aiwf state record-review --closure-allowed` flag sets the closure gate.

## Sub-Skills (load in order)

| Step | Load |
|------|------|
| 1. Trace coupling | `/aiwf-review-trace` — Change surface, ripple tracing, hotspots, architecture integrity, system integration |
| 2. Verify quality | `/aiwf-review-verify` — Evidence integrity, acceptance criteria, solution quality, adversarial observations |
| 3. Record output | `/aiwf-review-output` — Review command, key checks checklist, evidence-first testing boundary |
