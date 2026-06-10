---
name: aiwf-planner-execute
description: Mandatory state machine, task routing, and dispatch procedures
---

# AIWF Planner — Execute

## Mandatory State Machine

1. **Orient** — run `aiwf status`; read state, goal, fix-loop, quality digest, task ledger, Gravity, drift, capabilities.
2. **Discuss and research** — keep raw discussion separate from execution state.
3. **Freeze the contract** — after user confirmation, record goal, Evaluation Contract, Architecture Brief, non-goals, integration obligations, escalation triggers.
4. **Route and dispatch** — record quality policy, create context with `allowed_write`/`forbidden_write`, plan ledger task, activate it, run `aiwf status`. Explain selected Level, mechanical factors, semantic risks.
5. **Implement** — dispatch independent Executor for L1+. L0 may be inline.
6. **Test** — dispatch independent Tester. Tests must record commands/results, not prose.
7. **Cleanup before review** — run `aiwf cleanup check`; resolve stale items; `aiwf state mark-cleanup-fresh`. Never dispatch Reviewer before this.
8. **Review** — dispatch independent Reviewer at selected depth.
9. **Fix loop when needed** — route failures, repeat affected stages, re-test/re-clean/re-review.
10. **Planner meta-critique** — disposition every adversarial observation.
11. **Task completion** — create/verify checkpoint, close active ledger task. Due periodic Architect blocks only next ordinary task activation.
12. **Closure** — refresh quality digest, PROJECT-MAP; run `aiwf state prepare-close`.
13. **Carry forward** — ensure current state tells next cycle what changed and what remains risky.

At every transition, trust `.aiwf/*.json` and command results over conversational memory.

## How to Run a Task

**L0 (<=5 files, ~500 lines, linear):**
1. `aiwf state record-quality-policy --task-type small_function --workflow-level L0_direct`
2. `aiwf state start-context --context-id CTX-001 --allowed-write "..." --purpose "..."`
3. `aiwf task plan TASK-001 --title "..." --allowed-write "..."`
4. `aiwf task activate TASK-001`
Then: implement -> self-test -> cleanup -> self-review (review_lite) -> task close -> prepare-close

**L1+ (standard: cross-module, >5 files, refactor, API):**
1. `aiwf state record-quality-policy --task-type <T> --workflow-level <L> --risk-flag <F>`
2. `aiwf state start-context --context-id CTX-001 --allowed-write "..." --purpose "..." --test-focus "..." --review-focus "..."`
3. `aiwf task plan TASK-001 --title "..." --allowed-write "..."`
4. `aiwf task activate TASK-001`
5. `aiwf status`
Then: Executor -> Tester -> cleanup -> Reviewer -> fix-loop if needed -> meta-critique -> task close -> prepare-close -> carry-forward

**Forced L3 (mechanical — cannot override):**
- `destructive_command`: deletes/purges/wipes user data
- `security_sensitive`: encryption, auth, secrets, PII
- `data_migration`: moving data between backends/formats

## Workflow Level & Routing

| Level | When | Subagents |
|-------|------|-----------|
| L0 | typo, label, simple script | Planner inline |
| L1 | small feature, 1-2 files | Executor + Reviewer(light) |
| L2 | API, multi-module, refactor | Executor + Tester + Reviewer + adversarial |
| L3 | security, migration, destructive | full team + checkpoint + user decision |

Route L0 -> L1 on: bug_fix, refactor, api_endpoint, risk_flags present.
Route -> L2 on: cross-module semantic changes, public API change, explicit architecture impact, active fix-loop.
Route -> L3 on: destructive, security, data_migration (mechanical).

## Task Ledger

Plan many candidates, activate one at a time: `aiwf task plan/activate/close`. Activation blocked if: dependency not closed, execution window occupied, gravity hard_constraints active.

Task activation computes routing from file breadth, cross-module scope, Architecture Brief, risk flags, fix-loop history, and Gravity, then writes matching test depth, review depth, and exploration breadth into state.

## System Integration (L2+)

- L0/L1: full system integration test is Usually not needed. L1: 1 obligation if touching public API.
- L2/L3: Planner MUST write system integration obligations, covering each affected system path. System Integration Obligations are part of the Evaluation Contract.

## Environment & Workspace

- `aiwf env show` / env scan — environment profile; suspected-environment route needs env evidence before blaming executor.
- `aiwf workspace scan` — detect untracked files and dirty working tree (workspace drift).
- `aiwf cleanup check` — stale items, structure drift, PROJECT-MAP freshness; run before review. PROJECT-MAP holds project-level state and direction, distinct from report ideas.

## Quality Surfaces

- Plan minimum guidance: choose the shallowest defensible Level, explain semantic risk, escalate when unsure. surface_type determines depth direction.
- Prioritize human-visible surfaces in quality policy. Not every catalog surface must be tested — focus on user-facing and integration surfaces.
- Summarize first, then expand. escalation_required=true means stop execution until resolved.

## Carry-Forward

- After task close, use `aiwf state rebase` to generate `.aiwf/reports/current-state.md` — the carry-forward summary for the next session.
