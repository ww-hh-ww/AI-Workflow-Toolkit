---
name: aiwf-planner-execute
description: Mandatory state machine, task routing, and dispatch procedures
---

# AIWF Planner — Execute

## Mandatory State Machine

1. **Orient** — run `aiwf status`; read state, goal, fix-loop, task ledger, drift. Load additional context only per the active plan Impact block.
2. **Discuss and research** — keep raw discussion separate from execution state.
3. **Freeze the contract** — after user confirmation, record goal, Evaluation Contract, Architecture Brief, non-goals, integration obligations, escalation triggers.
4. **Route and dispatch** — record quality policy, create context with `allowed_write`/`forbidden_write`, plan ledger task, activate it, run `aiwf status`. Explain selected Level, mechanical factors, semantic risks.
5. **Implement** — follow `execution_topology`. L0 may be inline; L1 may be single agent with machine evidence; L2/L3 require independent execution topology unless explicitly substituted.
6. **Test** — follow `verification_need`. Tests must record commands/results, not prose; L2/L3 require independent Tester or explicit substitute.
7. **Cleanup before review** — run `aiwf cleanup check`; resolve stale items; `aiwf state mark-cleanup-fresh`. Never dispatch Reviewer before this.
8. **Review** — follow `review_need`. L1 may use review_lite; L2/L3 require independent Reviewer or explicit substitute.
9. **Fix loop when needed** — route failures, repeat affected stages, re-test/re-clean/re-review.
10. **Planner meta-critique** — L2/L3 default; L0/L1 only when there are pending adversarial observations, review risks, or repeated fix-loop signals.
11. **Closure gate** — run `aiwf state prepare-close` while the active task is still active, so Impact can be checked against the active plan.
12. **Task completion** — after prepare-close passes, create/verify checkpoint, close active ledger task. If Impact.quality_summary=yes, run `aiwf quality digest`. If Impact.project_map=yes, run `aiwf project-map`. Due periodic Architect blocks only next ordinary task activation.
13. **Carry forward** — ensure current state tells next cycle what changed and what remains risky.

At every transition, trust `.aiwf/*.json` and command results over conversational memory.

## How to Run a Task

**L0 (<=5 files, ~500 lines, linear):**
1. `aiwf state record-quality-policy --task-type small_function --workflow-level L0_direct`
2. `aiwf state start-context --context-id CTX-001 --allowed-write "..." --purpose "..."`
3. `aiwf task plan TASK-001 --title "..." --allowed-write "..."`
4. `aiwf task activate TASK-001`
Then: implement -> self-test -> cleanup -> self-review (review_lite) -> prepare-close -> task close

**L1+ (standard: cross-module, >5 files, refactor, API):**
1. `aiwf state record-quality-policy --task-type <T> --workflow-level <L> --risk-flag <F>`
2. `aiwf state start-context --context-id CTX-001 --allowed-write "..." --purpose "..." --test-focus "..." --review-focus "..."`
3. `aiwf task plan TASK-001 --title "..." --allowed-write "..."`
4. `aiwf task activate TASK-001`
5. `aiwf status`
Then: Executor -> Tester -> cleanup -> Reviewer -> fix-loop if needed -> meta-critique -> prepare-close -> task close -> carry-forward

**Forced L3 (mechanical — cannot override):**
- `destructive_command`: deletes/purges/wipes user data
- `security_sensitive`: encryption, auth, secrets, PII
- `data_migration`: moving data between backends/formats

## Workflow Level & Routing

| Level | When | Subagents |
|-------|------|-----------|
| L0 | typo, label, simple script | Planner inline |
| L1 | small feature, 1-2 files | single agent + machine evidence + light review |
| L2 | API, multi-module, refactor | independent Tester + Reviewer, or explicit substitute |
| L3 | security, migration, destructive | full team + checkpoint + user decision |

Route L0 -> L1 on: bug_fix, refactor, api_endpoint, risk_flags present.
Route -> L2 on: cross-module semantic changes, public API change, explicit architecture impact, active fix-loop.
Route -> L3 on: destructive, security, data_migration (mechanical).

## Task Ledger

Plan many candidates, activate one at a time: `aiwf task plan/activate/close`. Activation blocked if: dependency not closed, execution window occupied, gravity hard_constraints active.

Task activation computes routing from file breadth, cross-module scope, Architecture Brief, risk flags, fix-loop history, and Gravity, then writes matching test depth, review depth, and exploration breadth into state.

## Plan Drift During Execution

If implementation discovers the active plan no longer matches reality, stop forward execution and update the plan before continuing:
1. `aiwf plan update --task-id <TASK-ID> --section scope|verification|impact --content "..."`
2. Re-run `aiwf task activate <TASK-ID>` or `aiwf status` if routing/context may need to change.
3. Expand context only through Planner-approved `allowed_write` / `forbidden_write` updates.

Do not let Executor, Tester, or Reviewer silently normalize drift. Plan is the pre-work contract; prepare-close is the post-work gate.

## System Integration (L2+)

- L0/L1: full system integration test is Usually not needed. L1: 1 obligation if touching public API.
- L2/L3: Planner MUST write system integration obligations, covering each affected system path. System Integration Obligations are part of the Evaluation Contract.

## Environment & Workspace

- `aiwf workspace scan` — detect untracked files and dirty working tree (workspace drift).
- `aiwf cleanup check` — stale items, structure drift; run before review.
- Impact governs asset refresh: check the active plan Impact block before running env scan, project-map, or quality digest. Do NOT refresh these by default.

## Quality Surfaces

- Plan minimum guidance: choose the shallowest defensible Level, explain semantic risk, escalate when unsure. surface_type determines depth direction.
- Prioritize human-visible surfaces in quality policy. Not every catalog surface must be tested — focus on user-facing and integration surfaces.
- Summarize first, then expand. escalation_required=true means stop execution until resolved.

## Carry-Forward

- After prepare-close passes and the task is closed, `aiwf status` provides the carry-forward anchor. `current-state.md` is a human carry-forward summary; the next session's Planner reads state.json and the active plan as source of truth. Impact governs what docs/assets are refreshed.
