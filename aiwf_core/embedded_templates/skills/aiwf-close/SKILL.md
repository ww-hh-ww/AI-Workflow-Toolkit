---
name: aiwf-close
description: Verify gates and write closure — prepares close only after preflight passes
---

# AIWF Close

You handle workflow closure. Before closing, verify all gates.

## Hard Boundary Facts

- Claude Stop can block closure **ONLY** after `prepare-close` sets `close_attempt=true`; it does not treat `close_attempt=false` as a failed closure.
- Reasonix Stop **NEVER** blocks closure, regardless of `close_attempt`. It is report-only; successful `prepare-close` is authoritative.

## Closure Gates
0. **Quality brief exists** — `.aiwf/state/goal.json` `quality_brief` should have acceptance_criteria before closure.
1. **Evidence exists** — `.aiwf/evidence/records.json` has records
2. **Testing adequate** — `.aiwf/quality/testing.json` status is "adequate" or "passed"
3. **Review accepted** — `.aiwf/quality/review.json` has `closure_allowed: true`
4. **No open fix-loop** — `.aiwf/state/fix-loop.json` status is not "open"
5. **No scope violation** — `.aiwf/state/state.json` has `scope_violation: false`

## To Attempt Closure
1. Generate/update `.aiwf/reports/闭合报告.md` via `scripts/aiwf_export_report.py`.
2. Run `aiwf state prepare-close` — promotes evidence and sets `close_attempt=true` only if evidence, testing, review, cleanup, structure, scope, and fix-loop preflight checks pass.
3. The **Stop hook** (`scripts/aiwf_review_gate.py`) mechanically verifies all gates only after `prepare-close` sets `close_attempt=true`. Claude Code can then block Stop; an ordinary Stop without a close attempt is not treated as workflow closure. Reasonix Stop is non-gating, so `prepare-close` is the authoritative Reasonix closure gate.
4. If gates pass: update `phase: "closed"`, `closure_allowed: true`, then run `python3 scripts/aiwf_rebase_state.py`.
5. If gates fail: report which gates are failing, route to fix. Do NOT rebase to closed state.

## Git Policy
- Neither executor nor /aiwf-close may create commits automatically.
- Close does not auto-checkpoint. But if risky changes remain, Planner should create checkpoint by default unless user skips.
  `aiwf checkpoint create --mode stash --label "before close"` (or `--mode patch` fallback)
- Checkpoint = rollback safety; git commit = formal history. Both require user confirmation.
- After closure allowed, if user confirms commit:
  `aiwf git commit --message "..." --confirm`
- Do not auto-commit. Do not push. Planner may suggest a commit message; user must explicitly confirm.
- Reviewer should check git diff against scope before closure.

## Project Rules Cleanup

Before closure, optionally run `aiwf cleanup check` for L2/L3 tasks. For project rules specifically:

- Warn if `project-rules.md` becomes a history dump (too large, stale rules, raw ideas mixed in).
- Warn if too many active rules exist (>30); suggest review/retire/supersede.
- Retired/superseded rules stay archived; do NOT keep them active.
- PROJECT-MAP should not duplicate full `project-rules.md`.
- Raw ideas must remain in `ideas.md`, not `project-rules.md`.
- Do NOT auto-delete or auto-retire rules. Planner/Reviewer must explicitly retire or supersede outdated rules.
- Do NOT inject full `project-rules.md` into UserPromptSubmit or closure report.
- Identify stale ideas, stale PROJECT-MAP, stale environment; suggest Planner actions without auto-cleaning.

## Do NOT
- Do NOT declare closure done unless authoritative `prepare-close` passes. On Claude, also require the blocking Stop revalidation; on Reasonix, Stop is report-only.
- Do NOT skip evidence promotion before closure.
- Do NOT skip the mechanical gate check.
- Do NOT infer completion from conversation context.
