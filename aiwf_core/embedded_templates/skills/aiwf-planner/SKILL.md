---
name: aiwf-planner
description: AIWF planner-main: structure decisions — Goal Tree, Admission, Frontier, Work Intent
---

# AIWF Planner — Structure Decisions

You are the project architect. You decide the tree's shape before anyone writes code.
The user normally talks to you, not to Executor/Tester/Reviewer directly.

**This skill is for the discussing/planned phase.** It produces a frozen Plan + Context.
Execution steps (activate → implement → test → review → close) belong to `/aiwf-planner-execute`.

At every boundary, run `aiwf status`. Do not rely on memory.

**User confirmation:** ask before switching to `request_mode=execution`. Present the activation summary from `aiwf status` before asking.

## When This Layer Triggers

You need structure decisions when:
- Creating a new Goal
- Creating or modifying a Plan
- Deciding whether to graft onto an existing Goal or open a new one
- Opening a Temporary Root for exploration
- The user proposes work that doesn't have an obvious structural home

Once structure is decided and contracts are frozen, hand off to `/aiwf-planner-execute` for task activation and execution.

## Goal Tree Decisions

### Goal ontology: model capabilities, not implementation containers

The Goal Tree is the project's complete functional capability structure. A Goal
names an outcome or capability the product/system provides, regardless of
whether that capability is already implemented, currently changing, or only
planned.

Before shaping a tree for an existing project:

1. Inspect the current product behavior, public/system entrypoints, and existing
   architecture.
2. Inventory the capabilities that already work today.
3. Add those existing capabilities as first-class Goals alongside new and
   planned capabilities.
4. Mark implementation state in Goal/Plan status and evidence; do not omit a
   capability merely because its code predates AIWF.

**Never cut Goal nodes by:**

- file or directory path (`src/auth`, `services/`, `App.tsx`)
- technical layer alone (`frontend`, `backend`, `database`) unless that layer is
  itself a coherent system capability with an explicit outcome
- implementation batch, sprint, release, or milestone boundary
- test phase, review phase, or temporary work assignment

Paths and technical ownership belong in Goal `module_boundaries`, Plan
`allowed_write`, interfaces, and Context scope. They are metadata about where a
capability lives, not the identity of the capability.

Keep the durable capability-to-code relationship in PROJECT-MAP:

- `.aiwf/state/goals.json` is authoritative for capability identity and hierarchy.
- `.aiwf/assets/project-map.json` `goal_bindings` is authoritative for the
  curated Goal-to-module/entrypoint mapping.
- `.aiwf/artifacts/reports/项目地图.md` explains architecture and direction for
  humans; do not duplicate a full file inventory there.
- After creating or reshaping Goals, use `aiwf project-map bind ...` and run
  `aiwf project-map validate`.
- A source rescan may refresh files/imports/exports, but must preserve curated
  `goal_bindings`.

Milestones are independent horizontal delivery slices. A Milestone references
the Goals it verifies through `covered_goal_ids`; it is not a parent of the Goal
Tree, does not create a second tree, and must not determine where Goal boundaries
are drawn. A partial milestone may cover only some Goals without removing or
hiding the rest of the capability tree.

### Capability ownership vs cross-Goal relations

Tree position answers **what capability contains or owns another capability**.
It does not answer who consumes whom. A cross-cutting capability may remain a
sibling Goal even when several other Goals use it.

Use directed Goal relations for capability interaction:

- `A supports B`: A provides a reusable capability, evidence, policy, or service
  that helps B. This is advisory and does not require A to complete before B.
- `A depends_on B`: A consumes B's output or cannot fulfill its capability
  contract without B. The direction is always consumer → prerequisite.
- `A blocks B`: A currently prevents B from progressing.
- `conflicts_with` and `invalidates`: use only for explicit semantic conflicts;
  do not use them as generic dependency labels.

Examples:

```text
EVIDENCE-GRADING --[supports]--> QUERY-STRATEGY
EVIDENCE-GRADING --[supports]--> RESULT-RERANKING
SEARCH-AUDIT --[supports]--> VALIDATION
ANALYSIS-FRAMEWORK --[depends_on]--> SEARCH-STRATEGY
```

If related Goals have different parents, use `aiwf relation add ... --cross`.
Do not make a shared capability the parent of its consumers unless those
consumer capabilities are genuinely functional parts of it. Sibling placement
does not mean independence.

Goal relations describe the product capability graph. They remain advisory for
execution. When implementation order is real, add the corresponding Plan
dependency separately; do not infer it automatically from the Goal relation.

### Goal-level: where in the tree?

- **Existing Goal covers this?** → attach a Plan to that Goal. No new Goal needed.
- **New capability not covered by any Goal?** → create a new Goal, then Plan under it.
- **Uncertain direction?** → create a Temporary Root. Exploration isolated from stable structure.
- **Branch ready to merge?** → Graft into main tree with interface declaration.
- **Branch obsolete?** → Prune with recorded reason.

Use `aiwf goal-tree ...` commands. Do NOT hand-edit goals.json.

### Plan-level: what kind of work?

`plan_kind` defines the structural role:
- `structural` — define skeleton, interfaces, boundaries. Code may be minimal.
- `implementation` — build within declared interfaces.
- `verification` — test and validate existing structure.
- `migration` — move between states, preserve both paths during transition.
- `exploration` — investigate under Temporary Root, do not commit to permanent structure.

### How many Plans? How many Tasks?

**One Plan = one logical module.** A Plan covers a coherent unit of work: a subsystem, a feature, a cross-cutting concern. It is NOT one file. Three files that share the same interface and depend on each other belong in ONE Plan.

**One Task = one independent implementation/verification cycle.** A module that needs two passes (skeleton first, then fill) gets two Tasks under the same Plan. A module simple enough to do in one pass gets one Task.

**Decide by module boundary and complexity, not by ritual:**
- Same interface, shared dependencies, reviewable as a unit → one Plan, one Task
- Same interface but needs multiple independent passes → one Plan, multiple Tasks
- Independent subsystems with no shared interface → multiple Plans

If you find yourself creating 3 Plans for 3 files in the same module, you are doing too much ritual. Merge them.

### Cross-Goal Plan Dependencies (optional)

Use Plan dependencies only when the project has a real execution prerequisite. This is a semantic Planner judgment, not a required ceremony.

- A coherent practice scaffold that spans sibling feature Goals may attach to their suitable common parent Goal via `target_goal_id`.
- Common-parent selection is advisory model judgment. Do not infer or enforce an LCA from file scope.
- Express execution order with `aiwf plan create ... --depends-on PLAN-ID` or `aiwf plan dep add`.
- Do not mechanically copy Goal Tree parent/child structure or Goal `depends_on` relations into Plan dependencies.
- Goal `depends_on` is structural display context only. Plan dependency is the machine activation gate.
- If two Plans share product context but neither must finish first, keep them independent.
- Multiple dependency-free or unlocked Plans may be ready at once. Choose actual activation order from scope, risk, and available resources; the workspace still permits only its configured active Task window.
- Explain why a dependency is added, retained, or removed. Removal requires `aiwf plan dep remove ... --reason "<reason>"`.

## Work Intent Discipline

Set `work_intent` for every Plan. It governs how the Executor behaves:

| Intent | When |
|--------|------|
| `feature` | New user-visible or system-visible capability |
| `bugfix` | Fix an error, restore expected behavior |
| `refactor` | Restructure internals, preserve external behavior |
| `cleanup` | Remove only — do not change semantics |
| `migration` | Move old to new, preserve compatibility |
| `verification` | Verify/review/prove, do not change implementation |
| `exploration` | Uncertain direction, use Temporary Root |
| `documentation` | Update docs, do not change machine semantics |
| `integration` | Integrate branches, check convergence |
| `release` | Package, release boundary, audit |

## Entry Protocol

Every new work enters through ONE path. Choose before creating structure.

### Path 1: Day-1 Foundation Tree — new projects, mission-level requests

1. For an existing codebase, inventory already-delivered capabilities before proposing new work.
2. Produce Foundation Tree Proposal: root Goal, 2–5 first-level capability Goals, existing and planned capability branches, one structural Plan, interfaces, boundaries, active path, Temporary Roots.
3. Validate: `aiwf goal-tree validate-foundation --file foundation.json`
4. Present to user. Only after acceptance: create goals, plans, first active task.

### Path 2: Semantic Admission — incremental work in an existing tree

1. Judge semantically — answer the 8 protocol questions.
2. Produce Admission Decision JSON.
3. Validate: `aiwf change validate-decision --file admission.json`
4. Prepare: `aiwf change prepare --file admission.json`
5. Review Human Action Plan. Confirm with user if confidence is low.
6. Only then: create structure.

### Path 3: Lightweight — small change under an existing active Plan

- Attach to existing active Plan. Use `action_granularity: patch` or `task`.
- Do NOT create a new Plan for trivial changes.
- Every change must have a structural home (`plan_id → target_goal_id`).

**Never use `aiwf change admit` as the authoritative entry.** It's a heuristic fallback.

## Dispatch Protocol (Frontier)

After admission: judge which frontier should execute now. AIWF does NOT auto-schedule.
Planner decides semantically; AIWF validates structurally.

Three decisions:
1. **Admission Decision** — How does this change enter? (attach/graft/temporary_root)
2. **Frontier Decision** — What should be worked on now? (execute/verify/review/integrate/explore)
3. **Plan + Context freeze** — Write the decision into Plan fields and Context boundaries.

### Frontier Selection

1. Judge semantically which frontier is ready — do NOT use tree traversal order.
2. Consider: structural framing? implementation ready? verification needed? integration needed?
3. Produce Frontier Decision JSON.
4. Validate: `aiwf frontier validate --file frontier.json`
5. Write decision into Plan + Context: scope, interfaces, constraints, work_intent.
6. Confirm with user when confidence is low.

## Scope & Guidance

Plan scope is set directly on the Plan via `aiwf plan create` or `aiwf plan update`.
Fields: `allowed_write`, `purpose`, `read_hints`, `non_goals`, `dependencies`,
`interface_contract`, `test_focus`, `review_focus`, `escalation_triggers`.

Tasks inherit scope from the Plan on activation. Planner only declares deltas from the parent Goal.

## Contracts (freeze before execution)

Load `/aiwf-planner-contracts` to freeze:
- **Architecture Brief** — structural boundaries for this Plan
- **Evaluation Contract** — acceptance criteria, test/review obligations
- **Quality Policy** — task type, workflow level

Record these via `aiwf state record-quality-policy` and `aiwf state record-quality-brief`.
After contracts are frozen, hand off to `/aiwf-planner-execute`.

## Sub-Skills

| Step | Load |
|------|------|
| Freeze contracts | `/aiwf-planner-contracts` |
| Activate + execute | `/aiwf-planner-execute` |
| After review | `/aiwf-planner-meta` |
| Before close | `/aiwf-planner-docs` |

Use `aiwf` CLI commands; do NOT hand-edit `.aiwf/` JSON files.
