# AIWF

AIWF is the governance layer for this project. It tracks phase, scope, evidence, and quality gates. `.aiwf/*.json` is mechanical truth.

## First action

Run `aiwf status`. Obey `PRIMARY` and `REQUIRED NEXT`. If blocked, each blocker includes the exact `fix:` command — run it.

First time? Load `/aiwf-init` for the full decision tree and CLI reference.

## Mechanical truth

These files must change through `aiwf` CLI commands, never direct Write/Edit/Bash:

`.aiwf/state/state.json` `.aiwf/state/goal.json` `.aiwf/state/contexts.json` `.aiwf/state/fix-loop.json`
`.aiwf/state/goals.json` `.aiwf/state/plans.json` `.aiwf/state/milestones.json`
`.aiwf/artifacts/quality/testing.json` `.aiwf/artifacts/quality/review.json`
`.aiwf/runtime/history/task-ledger.json`

The Write Guard and Bash Guard enforce this mechanically.

## Non-negotiable

- No project writes without an active task and context (L0 exempted).
- No closure from prose — `prepare-close` is the authoritative gate.
- No roleplaying independent Tester or Reviewer when workflow level requires independence.
- Fix-loop resolution requires mechanical verification; prose is not proof.
- Scope violations clear only after Git confirms reverting files were reverted.
- Never silently downgrade scope, depth, or quality.

## Signal priority

1. **Mechanical gate** (hook denial, scope guard, bash guard) — cannot override
2. **User explicit decision** — can change scope, risk, depth
3. **AIWF PRIMARY / REQUIRED NEXT** — the state machine's current directive
4. **Current phase skill** — role-specific instructions
5. **This constitution** — stable boundaries

## Skill index

| Phase | Load |
|-------|------|
| first time / orientation | `/aiwf-init` |
| discussing / planned | `/aiwf-planner` → `/aiwf-planner-contracts` |
| implementing | `/aiwf-planner-execute` + `/aiwf-implement` |
| testing | `/aiwf-test` |
| reviewing | `/aiwf-review` → `/aiwf-review-trace` → `/aiwf-review-verify` → `/aiwf-review-output` |
| closing | `/aiwf-close` + `/aiwf-planner-docs` |
| milestone verification | `/aiwf-milestone-integration` → `/aiwf-milestone-arch-review` |
| architecture review | `/aiwf-architect` (periodic, never blocks current task close) |
