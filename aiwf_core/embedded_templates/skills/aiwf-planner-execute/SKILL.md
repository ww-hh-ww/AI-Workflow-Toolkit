---
name: aiwf-planner-execute
description: Task lifecycle state machine, multi-plan approach, routing, and dispatch
---

# AIWF Planner — Execute

**Prerequisite: structure is decided. Plan + Context + Contracts are frozen.**
Structure decisions belong to `/aiwf-planner`. This skill handles execution only.

## Approach: Multi-Plan Ordering (上下逼近)

When multiple Plans exist under a Goal, Planner decides activation order.
The default strategy is **top-down refinement, bottom-up verification**:

1. **Top-down pass** — activate structural/framing Plans first to establish interfaces and boundaries.
2. **Implementation pass** — activate implementation Plans within declared interfaces.
3. **Bottom-up verification** — verify each Plan's output validates the Plan above it.
4. **Drift detection** — if a lower Plan's implementation reveals gaps in an upper Plan's design, stop and update the upper Plan before continuing.

Do NOT auto-select next Plan by weight, score, or DFS/BFS traversal.
Judge semantically: which frontier is ready and unblocked.

When activating a Plan out of order, record the reason in the Plan's decision section.

## Mandatory State Machine

```
discussing → planned → implementing → testing → reviewing → closing → closed
```

1. **Orient** — run `aiwf status`; read state, goal, fix-loop, task ledger.
2. **Activate** — `aiwf task activate <ID>`. Activation mechanically recomputes routing.
3. **Implement** — Executor works within `allowed_write`. L0 may be inline; L1+ follow execution topology.
4. **Test** — Tester validates at selected `test_template`. Commands + results, not prose. L2/L3 require independent Tester.
5. **Cleanup before review** — `aiwf cleanup check`; resolve stale items; `aiwf state mark-cleanup-fresh`.
6. **Review** — Reviewer critiques against contracts. L2/L3 require independent Reviewer.
7. **Fix loop when needed** — route failures, repeat affected stages, re-test/re-clean/re-review.
8. **Meta-critique** — Planner dispositions adversarial observations.
9. **Closure gate** — `aiwf state prepare-close` while task is still active.
10. **Task close** — `aiwf task close <ID>` after prepare-close passes.
11. **Carry forward** — current-state.md tells next cycle what changed and what remains risky.

At every transition, trust `.aiwf/*.json` over conversational memory.

## How to Run a Task

**All levels: Plan + Context must already exist from structure decision phase.**

### L0 (trivial: <=5 files, linear, self-review ok)

1. `aiwf state record-quality-policy --task-type small_function --workflow-level L0_direct`
2. `aiwf task activate TASK-001`
3. Implement → self-test → cleanup → self-review → prepare-close → task close

### L1+ (standard: cross-module, >5 files, refactor, API)

1. `aiwf state record-quality-policy --task-type <T> --workflow-level <L> --risk-flag <F>`
2. `aiwf task activate TASK-001`
3. `aiwf status`
4. Executor → Tester → cleanup → Reviewer → fix-loop if needed → meta-critique → prepare-close → task close → carry-forward

### Forced L3 (mechanical — cannot override)

- `destructive_command`: deletes/purges/wipes user data
- `security_sensitive`: encryption, auth, secrets, PII
- `data_migration`: moving data between backends/formats

## Workflow Level & Routing

| Level | When | Team |
|-------|------|------|
| L0 | typo, label, simple script | Planner inline |
| L1 | small feature, 1-2 files | single agent + light review |
| L2 | API, multi-module, refactor | independent Tester + Reviewer |
| L3 | security, migration, destructive | full team + checkpoint + user decision |

Route L0→L1 on: bug_fix, refactor, api_endpoint, risk_flags present.
Route→L2 on: cross-module semantic changes, public API change, active fix-loop.
Route→L3 on: destructive, security, data_migration (mechanical).

Task activation computes routing from file breadth, cross-module scope,
Architecture Brief, risk flags, fix-loop history, and Gravity.

## Plan Drift During Execution

If implementation discovers the active Plan no longer matches reality:
1. `aiwf plan update --task-id <ID> --section scope|verification|impact --content "..."`
2. Re-run `aiwf task activate <ID>` if routing/context may change.
3. Expand context only through Planner-approved updates.

Do not let Executor, Tester, or Reviewer silently normalize drift.

## Quality & Environment

- `aiwf workspace scan` — detect workspace drift.
- Impact governs asset refresh: only run quality digest, project-map, or env scan when the active Plan's Impact block declares them needed.
- surface_type determines test/review depth direction. Prioritize user-facing surfaces. Summarize first, then expand.
- **System Integration (L2+):** Planner MUST write system integration obligations covering each affected system path. L0/L1: no full system test by default.

## Carry-Forward

After prepare-close passes and task is closed, `aiwf status` provides the carry-forward anchor. current-state.md is a human summary; the next session's Planner reads state.json and the active plan as source of truth.
