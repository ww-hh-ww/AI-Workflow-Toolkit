---
name: aiwf-init
description: AIWF system orientation — decision tree, CLI reference, and phase gate guide
---

# AIWF System Guide

AIWF is the governance layer for this project. It tracks what phase you're in, what files you can write, what evidence you need, and what gates must pass before work is considered done. You don't need to memorize the rules — the state machine tells you what to do next.

## Your first action every session

```
aiwf status
```

Run this. Always. The output tells you exactly what to do:

- **PRIMARY** — your current task. Do this.
- **REQUIRED NEXT** — blocked until you complete this step. Each blocker includes the exact `fix:` command.
- **[ATTN]** — which skill to load for this phase.
- **Recovery** — if something is wrong (fix_loop, scope_violation, plan_only_drift), this section explains the problem and legal options.

**Obey PRIMARY and REQUIRED NEXT.** If your intended action conflicts with status, stop and explain.

## Decision tree

```
aiwf status
│
├─ PRIMARY says "discuss/plan" 
│   → Load /aiwf-planner
│   → Shape the Goal Tree (aiwf goal-tree ...)
│   → Create Plan (aiwf plan create ...)
│   → Freeze contracts (/aiwf-planner-contracts)
│   → aiwf plan activate <PLAN-ID>
│
├─ PRIMARY says "activate a task"
│   → aiwf task plan <ID> --plan <PLAN-ID> --title '...' --allowed-write '...'
│   → aiwf task activate <ID>
│   → If blocked by phase gate: read the blocker message, run the fix command
│
├─ PRIMARY says "implement"
│   → Load /aiwf-planner-execute + /aiwf-implement
│   → Write code within allowed_write
│   → Record evidence: aiwf state record-role-evidence --role executor --scan-git
│
├─ PRIMARY says "test"
│   → Load /aiwf-test
│   → Evidence must exist before testing (implementing→testing gate)
│   → Run tests, record: aiwf state record-testing --status adequate ...
│
├─ PRIMARY says "review"
│   → Load /aiwf-review
│   → Testing must be adequate, cleanup verified (testing→reviewing gate)
│   → aiwf cleanup check && aiwf state mark-cleanup-fresh
│   → Review, record: aiwf state record-review --verdict PASS ...
│
├─ PRIMARY says "close"
│   → Load /aiwf-close
│   → aiwf state prepare-close
│   → If passed=False: read blockers, fix them, re-run
│   → If passed=True: aiwf task close <TASK-ID>
│
├─ Recovery: plan_only_drift
│   → Plan exists but no task. Edit the Plan artifact to fill required fields (Impact, scope),
│     then aiwf task plan ... && aiwf task activate ...
│     Plan files (.aiwf/artifacts/plans/) are editable during drift.
│
├─ Recovery: fix_loop
│   → Fix the listed required_fixes, verify with required_verification,
│     then aiwf fixloop resolve --resolution '...'
│
├─ Recovery: scope_violation
│   → Revert the violating files (git confirms), then
│     aiwf fixloop resolve --resolution '...'
│
└─ [ATTN] tells you which skill to load. Load it.
```

## Key CLI commands

### Navigation
```
aiwf status                    — what phase am I in? what must I do next?
aiwf status --debug            — full state dump
```

### Goal Tree (structure)
```
aiwf goal-tree show            — see the whole tree
aiwf goal-tree init-root <ID> --type main --title '...'
aiwf goal-tree add <ID> --parent <PARENT-ID>
aiwf goal-tree graft <ID> --target <PARENT> --interface-consumed '...' --capability-provided '...'
aiwf goal-tree prune <ID> --reason '...'
aiwf goal-tree validate        — check tree integrity (cycles, orphans)
```

### Mission (why)
```
aiwf mission show
aiwf mission update --statement '...' --boundary '...' --status active
```

### Plan (how)
```
aiwf plan create <PLAN-ID> --goal-id <GOAL-ID> --kind implementation --work-intent feature
aiwf plan activate <PLAN-ID>   — explicitly choose which Plan is active (NOT automatic)
aiwf plan deactivate            — clear active plan, return to discussing
aiwf plan update --task-id <ID> --section impact --content "..."
```

### Task (execution unit)
```
aiwf task plan <TASK-ID> --plan <PLAN-ID> --title '...' --allowed-write 'src/...'
aiwf task activate <TASK-ID>
aiwf task close <TASK-ID>      — only after prepare-close passes
```

### Context (boundaries)
```
aiwf state start-context --context-id CTX-001 --allowed-write 'src/...' --purpose '...'
```

### Quality gates
```
aiwf state record-quality-brief --acceptance-criterion '...' --non-goal '...'
aiwf state record-testing --status adequate --supports-plan <ID> --supports-goal <ID>
aiwf state record-review --verdict PASS --accepted-evidence-id <ID>
aiwf state prepare-close       — authoritative: tests passed? review accepted? cleanup fresh?
```

### Fix-loops & recovery
```
aiwf fixloop resolve --resolution '...'
aiwf state cancel-close        — recover from stuck closing state
```

### Milestones (delivery checkpoints)
```
aiwf milestone create <ID> --mission-id MISSION-001 --covered-goal <GOAL-ID>
aiwf milestone assess <ID> --verdict PASS --summary '...'
aiwf milestone close <ID>
```

## The structural model

```
Mission ("why this project exists")
  └── Milestones ("delivery checkpoints — horizontal cuts across Goals")
       └── Goal Tree ("functional skeleton — recursive Goals")
            └── Plan ("procedural scaffold — how to achieve a Goal")
                 └── Task ("execution unit")
```

- **Mission**: semantic anchor, no hard gates. Defines statement + boundaries. Injected into Context on start.
- **Milestone**: horizontal delivery checkpoint. Has a mechanical verdict gate (PASS/PASS_WITH_RISK/REVISE/REJECT). Covers specific Goals.
- **Goal**: functional skeleton node. Can be grafted, pruned, nested. The tree's operation unit.
- **Plan**: how a Goal is achieved. Has `plan_kind`, `work_intent`, `interfaces`, `constraints`. Must be explicitly activated.
- **Task**: execution unit. Bounded by `allowed_write`. Moves through the state machine.

## Phase gates

Every phase transition checks that required fields are filled. Blockers have this format:

```
[field_name] What is missing? — fix: aiwf command ...
```

**Do not hand-edit JSON. Run the fix command.**

Common blockers and fixes:

| Blocker | Fix |
|---------|-----|
| `plan.plan_kind` empty | `aiwf plan update --task-id <ID> --section goal --content 'plan_kind: implementation'` |
| `plan.work_intent` empty | `aiwf plan update --task-id <ID> --section goal --content 'work_intent: feature'` |
| `plan.target_goal_id` empty or missing | `aiwf plan create PLAN-ID --target-goal <GOAL-ID>` |
| `context.purpose` empty | `aiwf state start-context --context-id <ID> --purpose '...'` |
| `context.allowed_write` empty | `aiwf state start-context --context-id <ID> --allowed-write 'src/path/'` |
| `contract.non_goals` empty | `aiwf state record-quality-brief --non-goal '...'` |
| `contract.acceptance_criteria` empty | `aiwf state record-quality-brief --acceptance-criterion '...'` |
| `evidence` no records | `aiwf state record-role-evidence --role executor --summary '...' --scan-git` |
| `testing.status` not adequate | Run tests, then `aiwf state record-testing --status adequate ...` |
| `cleanup` not verified | `aiwf cleanup check && aiwf state mark-cleanup-fresh` |
| `review.verdict` pending | `aiwf state record-review --verdict PASS ...` |
| `goal.graft_interface` missing (L2+) | `aiwf goal-tree graft <ID> --target <PARENT> --interface-consumed '...' --capability-provided '...'` |
| `relation.reason` missing (L2+) | `aiwf relation add <A> <B> --type <T> --cross --reason '...'` |

## Mechanical truth

These files must change through `aiwf` CLI commands, never direct Write/Edit/Bash:

- `.aiwf/state/state.json` `.aiwf/state/goal.json` `.aiwf/state/contexts.json` `.aiwf/state/fix-loop.json`
- `.aiwf/state/goals.json` `.aiwf/state/plans.json` `.aiwf/state/milestones.json`
- `.aiwf/artifacts/quality/testing.json` `.aiwf/artifacts/quality/review.json`
- `.aiwf/runtime/history/task-ledger.json`

The Write Guard blocks Write/Edit to these. The Bash Guard blocks Bash commands referencing `.aiwf/state/` or `.aiwf/artifacts/quality/`. If blocked, the error message includes the fix command.

## Workflow levels (L0–L3)

| Level | When | Team |
|-------|------|------|
| L0 | typo, label, simple script | Planner inline, self-review |
| L1 | small feature, 1-2 files | single agent + light review |
| L2 | API, multi-module, refactor | independent Tester + Reviewer |
| L3 | security, migration, destructive | full team + checkpoint + user decision |

Task activation computes the level mechanically from file breadth, cross-module scope, fix-loop history, and risk flags.

## Work intent discipline

Every Plan must declare a `work_intent`. It governs what the Executor may and may not do:

| Intent | Allowed | Forbidden |
|--------|---------|-----------|
| `feature` | implement capability, document interfaces | refactor unrelated code |
| `bugfix` | minimal fix, root cause, regression test | new features, API changes |
| `refactor` | restructure internals, preserve behavior | new features, API changes |
| `cleanup` | remove dead code | delete machine truth, change semantics |
| `migration` | preserve data, fallback path | delete old path, break compatibility |
| `verification` | focus on evidence | change implementation |
| `exploration` | isolate, record findings | commit to stable structure |
| `documentation` | match current behavior | change machine semantics |
| `integration` | integrate branches, check convergence | change interfaces |
| `release` | release hygiene, audit | change behavior, new features |
