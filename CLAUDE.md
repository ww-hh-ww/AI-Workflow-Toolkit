# AIWF Development Instructions

AIWF is the embedded governance and visibility layer for long-horizon Claude Code and Reasonix engineering sessions.

## Runtime Protocol

On every new turn, resume, compaction, or task continuation, run `aiwf status` before deciding the next workflow action. Obey `Recovery`, `PRIMARY`, and `REQUIRED NEXT` unless an AIWF command resolves the blocker. If your intended action conflicts with status, stop and explain the conflict instead of relying on memory. If status reports `plan_only_drift`, stop expanding the plan and freeze the execution contracts/context/task activation before project writes. If Claude Code auto mode blocks an AIWF lifecycle command, ask the user to approve that exact governance command and do not bypass it by hand-editing `.aiwf` state. After drafting a plan in discussion/clarification, ask the user to confirm execution unless they already explicitly requested implementation. At stable version boundaries, surface git status and ask whether to commit/push meaningful changes; a stable version is a coherent rollback point, not every task boundary.

## Product Boundary

- Coding agents own engineering intelligence: inspect, reason, design, edit, run, test, and debug.
- AIWF owns governance: machine-readable state, scope, evidence, routing, testing discipline, review gates, cleanup, closure, and carry-forward.
- `.aiwf/*.json` is the source of truth. Model memory and prose are advisory.
- Do not reintroduce `.ai-workflow/`, an external orchestrator, managed runtime, fake terminal executor, or one-shot deterministic planner.

## Supported Mainlines

Claude Code:

```bash
aiwf install claude
claude
/aiwf-planner "describe the goal"
```

Reasonix:

```bash
aiwf install reasonix
reasonix code .
/skill aiwf-planner "describe the goal"
```

## Required Flow

```text
Planner discussion and research
-> Evaluation Contract and Architecture Brief
-> Context dispatch and task activation
-> Scoped implementation
-> Independent testing
-> Cleanup before review
-> Adversarial review
-> Fix-loop replay when needed
-> Planner meta-critique
-> Task close
-> prepare-close
-> Current-state and report carry-forward
```

`prepare-close` is the authoritative closure gate: it requires testing passed/adequate, review accepted with closure_allowed=true, cleanup fresh, and accepted evidence before setting phase=closed. The Stop hook performs supplementary revalidation using the same gates. `aiwf state cancel-close` recovers from a stuck closing state by resetting close_attempt and reverting phase to reviewing.

## Development Rules

- Every new workflow rule needs a contract test.
- Preserve Planner-first interaction and independent Tester/Reviewer depth.
- Keep Gravity pure and read-only.
- Keep modules separated; split modules approaching 300 lines unless clearly justified.
- Never auto-commit or auto-push from Executor or Close.

<!-- AIWF MANAGED BLOCK START -->
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
<!-- AIWF MANAGED BLOCK END -->
