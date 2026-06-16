---
name: aiwf-planner-execute
description: Task lifecycle state machine, multi-plan approach, routing, and dispatch
---

# AIWF Planner — Execute

**Prerequisite: structure is decided. Plan + Context + Contracts are frozen.**
Structure decisions belong to `/aiwf-planner`. This skill handles execution only.

## Approach: Multi-Plan Ordering (上下逼近)

When multiple Plans exist under one or more Goals, Planner decides activation order.
The default strategy is **top-down refinement, bottom-up verification**.

### Activation Checklist (run before every `aiwf task activate`)

1. **Group by plan_kind** — `structural` first (they define interfaces), then `implementation` (they fill interfaces), then `verification` (they validate the result). Never activate an `implementation` Plan whose interface-defining `structural` Plan is not yet complete.

2. **Read Plan dependencies** — `.aiwf/state/plans.json` → each Plan's `dependencies` field. A Plan dependency is satisfied only when the upstream Plan is `complete`; `aiwf plan activate` and `aiwf task activate` enforce this. Goal `depends_on` relations are advisory display context and never activation gates.

3. **Check Plan completion** — for Plans that define interfaces consumed by other Plans: all tasks must be closed, interfaces must be stable (`interface_stability: stable` in Plan metadata). A downstream Plan activated against a moving interface will need rework.

4. **Cross-verify** — before activating a Plan, ask: do any of its task descriptions or context fields reference interfaces defined by an incomplete upstream Plan? If yes → do not activate. Record the dependency explicitly with `aiwf plan dep add`.

5. **Drift detection** — if a lower Plan's implementation reveals gaps in an upper Plan's design, stop and update the upper Plan (`aiwf plan update`) before continuing the lower Plan. Do not silently patch the lower Plan to work around bad interfaces.

### Out-of-order activation

When you activate a Plan out of the default order, record the reason:
```
aiwf plan update --plan-id PLAN-XXX --section decision --content "Activated before PLAN-YYY because: <reason>"
```

Do NOT auto-select next Plan by weight, score, or DFS/BFS traversal.
Several unlocked Plans may be ready simultaneously. Planner chooses which one to activate from scope, risk, and resources; readiness does not create parallel active Tasks.

## Task-Level Ordering Within a Plan

When creating tasks under a Plan, declare ordering via `--dependency`:

```
aiwf task create T-002 --title "Wire router to handler" --dependency T-001
```

A task with `dependencies` cannot activate until all listed task IDs are `closed`. This is mechanically enforced by `aiwf task activate`.

### Declaring dependencies

Before creating tasks, read the Plan's scope and interface declarations. Identify the natural ordering:

1. **Skeleton first** — tasks that create module scaffolding, directory structure, or interface stubs must complete before tasks that fill them in.
2. **Bottom-up within a module** — if task B calls functions created by task A, A is a dependency of B.
3. **Cross-module wiring last** — tasks that connect modules (router → handler, API → DB) should declare dependencies on the tasks that build each module.

### Dependency rules

- Only declare dependencies that genuinely block the task. Over-declaring creates unnecessary sequential chokepoints.
- A task with zero dependencies is independently executable — it can run in parallel with any `parallel_safe` task.
- Dependency chains must not form cycles. If A depends on B and B depends on A, split them differently.

Read existing task dependencies from `.aiwf/runtime/history/task-ledger.json` before declaring new ones.

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
| L1 | small feature, 1-2 files | Executor + reviewer-light; reviewer-light combines targeted testing + light review |
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
