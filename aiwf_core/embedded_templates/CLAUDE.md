# AIWF Constitution

## Product Boundary

Coding agents own engineering intelligence: inspect, reason, design, edit, run, test, debug.
AIWF owns governance: machine-readable state, scope, evidence, quality gates, closure.
`.aiwf/*.json` is mechanical truth. Model memory and prose are advisory.

## Runtime Discipline

1. Every turn: read the `[AIWF]` status block. Obey `PRIMARY` and `REQUIRED NEXT`.
2. Do not act from memory. At each phase transition, re-load the skill named by `[ATTN]`.
3. If your intended action conflicts with status, stop and explain the conflict.
4. Mechanical truth files (`.aiwf/state/*.json`, `.aiwf/quality/*.json`) must change through `aiwf` CLI commands, never direct Write/Edit.

## Non-Negotiable Boundaries

- Never silently downgrade scope, depth, or quality. State the decision explicitly.
- No project writes without an active task and context (L0 exempted).
- No closure from prose — `prepare-close` is the authoritative gate.
- No roleplaying independent Tester or Reviewer when workflow level requires independence.
- Fix-loop resolution requires mechanical verification; prose is not proof.
- Scope violations clear only after Git confirms reverting files were reverted.

## Skill Index

| Phase | Load |
|-------|------|
| discussing / planned | `/aiwf-planner` → `/aiwf-planner-contracts` to freeze contracts |
| implementing | `/aiwf-planner-execute` + `/aiwf-implement` |
| testing | `/aiwf-test` |
| reviewing | `/aiwf-review` → `/aiwf-review-trace` → `/aiwf-review-verify` → `/aiwf-review-output` |
| closing | `/aiwf-close` + `/aiwf-planner-docs` |
| architecture review | `/aiwf-architect` (periodic, never blocks current task close) |

Detailed workflow steps, request modes, state file schemas, and rules live in the skills
loaded at each phase. This constitution defines stable boundaries; skills define how to act.

## Signal Priority

When signals conflict, obey in this order:
1. **Mechanical gate** (hook denial, scope guard, bash guard) — cannot override
2. **User explicit decision** — the user can change scope, risk, or depth
3. **AIWF PRIMARY / REQUIRED NEXT** — the state machine's current directive
4. **Current phase skill** — role-specific instructions for this phase
5. **This constitution** — stable boundaries that never change mid-cycle
