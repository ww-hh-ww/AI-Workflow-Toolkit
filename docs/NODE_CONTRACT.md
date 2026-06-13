# AIWF Node Contract v2.0

Rooted Functional Tree with Procedural Scaffolds — unified node model for
long-horizon task governance.

**Status:** Frozen candidate after Stage 3.0 calibration.
**Date:** 2026-06-12
**Supersedes:** v1.0 (fixed five-layer chain model).
**Depends on:** `AIWF_DESIGN_AXIOMS.md` (authoritative axioms).

---

## 1. Purpose

This contract defines a unified node model for AIWF's structural layers.
The structure is NOT a fixed five-layer chain. It is a recursive Goal tree
with five core node types (Mission / Goal / Milestone / Plan / Task) and
Evidence as lightweight proof artifacts.

**Five core node types:**
- **Mission** — project-level singleton contract framing root Goals
- **Goal** — functional skeleton unit (recursive, main/temporary/branch)
- **Milestone** — optional structural convergence node (multi-branch stable state)
- **Plan** — procedural scaffold attached to a Goal
- **Task** — atomic construction action under a Plan

**Evidence** is lightweight proof material produced by execution. It is not a core
governance node — it does not have an independent lifecycle, does not drive gates,
and does not participate in the five-node model. Evidence rolls upward through
Plan → Goal → Milestone but is never an orchestration target.

```
Mission (project-level singleton)
  └─ Root Goal (main / temporary / branch)
       ├─ Structural Plan (interfaces, boundaries, decomposition policy)
       ├─ Child Goal (functional sub-unit)
       │    ├─ Implementation Plan (files, tasks, tests)
       │    │    └─ Task
       │    └─ Child Goal (further decomposition)
       └─ Milestone (optional structural convergence node)
```

The active execution path is always a single tree chain from active Goal
through active Plan to active Task.

Sibling relation lines express non-parent-child relationships (depends_on,
blocks, conflicts_with, invalidates, supports). They do not drive default
execution.

Impact Cone analysis replaces abstract weight/attention scores — a node's
importance is estimated by its structural position, not by manually assigned
priority fields.

---

## 2. Unified Node Schema

Every node carries these fields regardless of type:

### 2.1 Core Identity

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | yes | Unique node identifier within the project |
| `type` | enum | yes | `mission` / `goal` / `milestone` / `plan` / `task` |
| `title` | string | yes | Human-readable short title (≤120 chars) |
| `intent` | string | yes | Why this node exists, what it aims to achieve |

Five core node types. Mission is a project-level singleton — it exists in its
own object truth source (mission.json) and is not a regular Goal Tree child.
Evidence is NOT a node type — it is lightweight proof material (§3.6).

### 2.2 Tree Position

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `parent_id` | string \| null | yes | Parent node id; null for root Goals |
| `root_goal_id` | string | yes | The root Goal of this node's tree |
| `child_ids` | string[] | no | Ordered list of direct child node ids |

### 2.3 Status + Lifecycle

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `status` | enum | yes | See per-type lifecycle below |
| `visibility` | enum | yes | `default` / `collapsed` / `debug_only` / `archived_only` / `hidden_from_prompt` |
| `advance_policy` | enum | yes | `auto` / `checkpoint` / `manual` |
| `checkpoint_level` | enum | yes | `task` / `plan` / `milestone` / `goal` |

### 2.4 Sibling Relations

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `relations` | Relation[] | no | Lateral relations to sibling nodes, see §6 |

### 2.5 Evidence Rollup

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `evidence_rollup` | Rollup | no | Aggregated from children on close/reconcile |
| `open_gaps` | string[] | no | Known gaps not yet resolved |

### 2.6 Timestamps

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `created_at` | ISO8601 | yes | Creation timestamp |
| `updated_at` | ISO8601 | yes | Last mutation timestamp |
| `activated_at` | ISO8601 \| null | no | When status became active (if applicable) |
| `closed_at` | ISO8601 \| null | no | When status became terminal (if applicable) |

---

## 3. Node Types

### 3.1 Mission (type=`mission`)

**Purpose:** Project-level singleton contract. Frames what the project exists to do,
what is in/out of scope long-term, and what root Goals should exist. Mission is a
core node type but is NOT a regular Goal Tree child — it lives in its own object
truth source and frames root Goals rather than being grafted/pruned/decomposed.

**Storage:** `.aiwf/state/mission.json` (singleton object truth source).

**Lifecycle:**
```
draft → active → superseded
```

**Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `version` | int | Monotonic version counter |
| `statement` | string | The mission statement |
| `boundaries` | string[] | What is in/out of scope long-term |

**Constraints:**
- Mission is a node but NOT a Goal Tree child — it does not participate in
  graft, prune, or tree traversal.
- Does NOT block close gates for normal tasks.
- Does NOT appear in `status --prompt`.
- Displayed only via `aiwf mission show` or `aiwf status --debug`.
- Root Goals reference mission via optional `mission_id` field.
- A Goal without a mission reference is valid.

---

### 3.2 Goal (type=`goal`)

**Purpose:** A functional unit in the system. Goals form the recursive skeleton
of the project. A Goal may contain child Goals, have Plans attached, be covered
by a Milestone, and have sibling relations.

**Storage:**
- `.aiwf/state/goals.json` — Goal Tree registry (multi-goal, future).
- `.aiwf/state/goal.json` — Legacy singleton active goal (current, maps to `GOAL-001`).

**Lifecycle:**
```
discussion → active → superseded
            ↓
          stable (sealed, not superseded)
```

**Fields (existing from goal.json, preserved):**
| Field | Type | Description |
|-------|------|-------------|
| `goal_version` | int | Monotonic counter |
| `original_intent` | string | First user intent (set once, never mutated) |
| `current_goal` | string | Current goal text |
| `active_goal` | string | Alias, equals current_goal |
| `confirmed` | bool | User confirmed this goal |
| `intent_changes` | Change[] | Versioned change records |
| `decisions` | Decision[] | Key decisions during goal lifecycle |
| `meta_critique` | MetaCritique | Planner's post-close reflection |
| `open_questions` | string[] | Unresolved questions |
| `superseded_goals` | string[] | History of prior goal texts |
| `quality_brief` | QualityBrief | Architecture brief + evaluation contract |

**New fields (Goal Tree model):**
| Field | Type | Description |
|-------|------|-------------|
| `root_type` | enum | `main` / `temporary` / `branch` / null (non-root) |
| `mission_id` | string \| null | Optional reference to mission |
| `parent_goal_id` | string \| null | Parent Goal (null for roots) |
| `child_goal_ids` | string[] | Direct child Goals |
| `children_order` | string[] | Display order of children (≠ dependency) |
| `attached_plan_ids` | string[] | Plans attached to this Goal |
| `acceptance_boundary` | string | Independent acceptance criteria for this unit |

**Constraints:**
- `root_type` only set on root Goals (`parent_goal_id = null`).
- A `temporary` root does not enter default prompt.
- A `branch` root is a non-main permanent root.
- Goal close requires all children (Goals, Plans) in terminal states.
- Sibling order (`children_order`) does not imply dependency.
- Existing singleton `goal.json` maps to legacy node id `GOAL-001`.
- Stage 3.1 does NOT introduce multi-goal mechanics for activation/close gates.

---

### 3.3 Milestone (type=`milestone`)

**Purpose:** Optional structural convergence node. A Milestone represents a
stable intermediate project state formed by a group of Goals, Plans, and Tasks
converging into a structure that downstream work can depend on. It is NOT a
time checkpoint, NOT a fixed layer, and NOT a required stage seal.

A Milestone exists when downstream work genuinely depends on the convergence of
the covered scope. If nothing depends on the convergence, no Milestone is needed.

**Storage:** `.aiwf/state/milestones.json` (object truth source).

**Lifecycle:**
```
pending → active → done → (skipped)
```

**Legacy fields (preserved for compatibility and rollup):**
| Field | Type | Description |
|-------|------|-------------|
| `goal_id` | string | Parent goal (legacy) |
| `plan_ids` | string[] | Plans within this milestone (legacy) |
| `task_ids` | string[] | Tasks within this milestone (legacy) |
| `covered_goal_ids` | string[] | Goals in the converged subtree (legacy) |
| `stage_synthesis` | object | Coherent outcome judgment (legacy) |

**New fields (structural convergence meaning — Stage 4.7.2):**
| Field | Type | Description |
|-------|------|-------------|
| `scope_type` | enum \| null | `goal_subtree` / `plan_set` / `task_set` / `mixed` |
| `scope_refs` | string[] | IDs of Goals/Plans/Tasks in the convergence scope |
| `convergence_meaning` | string \| null | What stable state this group of nodes has formed |
| `downstream_dependency` | string \| null | What subsequent work depends on this convergence |
| `stability_claim` | enum \| null | `draft` / `usable` / `stable` / `risky` |
| `risk_summary` | string \| null | Known risks in the converged state |
| `recommended_next_frontier` | string \| null | Suggested frontier after convergence |

**Structural Convergence Assessment:**
- Does the covered scope form a coherent structural state?
- Can downstream work depend on this state?
- How stable is it? (draft/usable/stable/risky)
- Are interfaces between covered nodes stable?
- What risks remain in the converged state?
- What frontier should be dispatched next?

**Constraints:**
- Milestones are NOT created automatically by time or task size.
- Planner creates a Milestone only when downstream work depends on convergence.
- L0/L1 tasks do NOT require milestones.
- Milestone close is NOT a mechanical checklist.
- `status --prompt` shows at most `milestone=<MS-ID>`, never full synthesis.
- Old fields (`goal_id`, `plan_ids`, `task_ids`, `covered_goal_ids`, `stage_synthesis`)
  remain for compatibility and rollup; new fields express structural meaning.

---

### 3.4 Plan (type=`plan`)

**Purpose:** A procedural scaffold attached to a Goal. Describes how a Goal or
Goal subtree is to be realized, constrained, tested, migrated, or verified.
A Plan is NOT the skeleton — the Goal is.

**Storage:**
- `.aiwf/state/plans.json` — machine-readable registry (sole authority).
- `.aiwf/artifacts/plans/<PLAN-ID>.md` — human-authored markdown artifact.

**Lifecycle:**
```
draft → active → complete → superseded
                   └→ paused
```

**Machine-readable fields (plans.json entry):**
| Field | Type | Description |
|-------|------|-------------|
| `plan_id` | string | Unique plan id (NOT tied to a task id) |
| `goal_id` | string | Legacy parent goal reference |
| `target_goal_id` | string | Target Goal this Plan attaches to (future authority) |
| `plan_kind` | enum | `structural` / `implementation` / `verification` / `migration` / `exploration` |
| `active_phase` | enum | `framing` / `implementation` / `integration` / `seal` |
| `milestone_id` | string \| null | Parent milestone (optional) |
| `task_ids` | string[] | Child task ids in this plan |
| `interfaces` | string[] | Interfaces this Plan defines or constrains (structural Plans) |
| `constraints` | string[] | Boundaries this Plan enforces (structural Plans) |
| `child_goal_policy` | string | Decomposition policy for child Goals (structural Plans) |
| `status` | enum | draft / active / complete / superseded / paused |

**Plan kind semantics:**
| Kind | Typical attachment | Has Tasks? | Output |
|------|-------------------|-----------|--------|
| `structural` | Higher-level Goal | Few or none | Design contracts, interfaces, boundaries |
| `implementation` | Lower-level Goal | Yes | File changes, tests, evidence |
| `verification` | Any Goal | Optional | Test plans, review criteria |
| `migration` | Any Goal | Yes | Migration scripts, compatibility evidence |
| `exploration` | Temporary Root | Optional | Feasibility evidence, design notes |

**Active phase semantics:**
| Phase | Role | Typical for |
|-------|------|-------------|
| `framing` | Define structure, interfaces, boundaries, decomposition policy | Early structural Plans |
| `implementation` | Guide concrete Tasks, produce evidence | Lower-level Plans |
| `integration` | Reconcile outputs, check interface conformance, resolve conflicts | Later-stage loading |
| `seal` | Prepare Milestone synthesis, final validation, gap assessment | Pre-close loading |

A structural Plan at a high-level Goal cycles through all four phases.
An implementation Plan at a lower-level Goal typically stays in `implementation`.

**Plan Phase Loading:**

A Plan is not a static instruction document. A Plan attached to a high-level
Goal is a **phase-loadable procedural scaffold**: it is loaded differently
across the lifecycle of its parent Goal.

- **Early (framing):** The Plan defines structure, interfaces, boundaries, and
  decomposition policy. It acts like architectural blueprints. It may have few
  or no Tasks.
- **Late (integration/seal):** The Plan loads lower-level outputs, checks
  whether implementation respects upper interfaces, reconciles evidence,
  identifies branch conflicts, and prepares for Milestone sealing.

The `active_phase` field determines which parts of a Plan enter context.
Default prompts must not include the full high-level Plan — only the relevant
phase summary and interface constraints needed by the active execution path.

**Markdown artifact (plans/<PLAN-ID>.md):**
Preserves: Goal, Route, Scope, Risks, Current Decision, Verification, Impact,
Done Means, Goal Progress, Next Steps.

Adds:
- `Plan ID: <PLAN-ID>` (replaces task-id header).
- `Target Goal: <target_goal_id>` (machine reference).
- `Plan Kind: <plan_kind>`.
- `Parent Milestone: <milestone_id>` (when applicable).
- `Task IDs: <task_id, ...>`.

**Constraints:**
- A Plan can have 0..N child Tasks.
- `plan_id` is independent of `task_id`.
- `plans.json` is the sole machine authority; markdown is artifact-only.
- Legacy `<TASK-ID>.md` without a registry entry blocks activation with a
  remediation message.
- A structural Plan may define no concrete Tasks yet.

---

### 3.5 Task (type=`task`)

**Purpose:** Execution closure. Concrete construction action under a Plan.
The most mature layer. Resident in prompt.

**Storage:** `.aiwf/runtime/history/task-ledger.json`.

**Lifecycle (preserved):**
```
candidate → ready → active → closed
              ↓         ↓
          rejected   blocked → active
                       ↓
                    suspended → active
```

**Existing fields (preserved):**
id, title, status, dependencies, allowed_write, parallel_safe, notes,
created_at, updated_at, activated_at, closed_at, suspended_at, suspended_context.

**Modified fields:**
| Field | Old | New |
|-------|-----|-----|
| `parent_goal` | free-text | alias for `goal_id` |
| `parent_plan` | free-text (equals task_id) | alias for `plan_id` |
| `milestone` | free-text | legacy label only; not a gate |

**New fields:**
| Field | Type | Description |
|-------|------|-------------|
| `plan_id` | string | Machine reference to parent Plan (validated) |
| `goal_id` | string | Machine reference to root Goal (validated) |
| `milestone_id` | string \| null | Optional; inherited from Plan when present |

**Constraints:**
- Task `active` requires parent Plan `active`.
- Task close triggers reconcile to parent Plan.
- Task must never directly complete a Goal — evidence rolls up through Plan.
- `parent_goal` and `parent_plan` are aliases populated from authoritative fields.

---

### 3.6 Evidence (lightweight proof artifact, not a node type)

**Purpose:** Lightweight proof material produced by execution. Evidence is NOT
a core governance node — it has no independent lifecycle, does not drive gates,
does not participate in the five-node model, and is never an orchestration target.

Evidence may include test output, changed files, review notes, validation logs,
CLI output, human confirmation, or external references.

Evidence supports a Plan or Task. Evidence rolls upward through Plan → Goal →
Milestone but is never the thing being managed — it is the proof that management
happened. Evidence can be invalidated; invalidation affects the relevant Plan,
Goal, or Milestone assessment.

**Do NOT build a heavy Evidence Registry.** Evidence records are referenceable
but lightweight. No evidence graph engine. No evidence-to-evidence relations.
No evidence lifecycle beyond creation and optional invalidation.

---

## 4. Truth Source Contract

This section defines the authoritative sources of truth in AIWF.

### 4.0 Object Truth vs Relationship Truth

AIWF separates **object truth** (what a node is) from **relationship truth**
(how nodes connect). Object registries own the full node content. The tree is
a relationship view — it does not copy or duplicate object content.

**Object truth sources:**
| File | Owns | Authority |
|------|------|-----------|
| `.aiwf/state/mission.json` | Mission object | Singleton project-level contract |
| `.aiwf/state/goals.json` | Goal objects + parent-child structure | Sole Goal truth |
| `.aiwf/state/plans.json` | Plan objects + `target_goal_id` attachment | Sole Plan truth |
| `.aiwf/runtime/history/task-ledger.json` | Task objects + `plan_id` ownership | Sole Task truth |
| `.aiwf/state/milestones.json` | Milestone objects + `scope_refs` convergence | Sole Milestone truth |

**Relationship truth sources:**
- Goal parent-child: `goals.json` (parent_goal_id, child_goal_ids)
- Plan attachment: `plans.json` (target_goal_id)
- Task ownership: `task-ledger.json` (plan_id)
- Milestone convergence scope: `milestones.json` (scope_type + scope_refs)

**Derived views (rebuildable, never authoritative):**
- Goal Tree display: derived from goals.json parent-child + plans.json attachment
- Impact Cone: derived from tree position + relations
- Status active path: derived from active node pointers

### 4.1 Constraints

- Do NOT introduce a single `tree.json` that copies all object content.
- Do NOT duplicate Plan/Task/Milestone full objects into the Goal Tree.
- Do NOT make Milestone a fixed `Goal → Milestone → Plan → Task` layer.
- The derived tree view is rebuildable from object truth sources.
- `plans.json` is the sole machine authority for Plans.
- When object truth and derived view disagree, object truth wins.

---

## 5. Tree Rules

### 4.1 Active Path Uniqueness

At any moment, exactly ONE active execution path:

```
Goal (active) → [Milestone (active)] → Plan (active) → Task (active)
```

The system enforces:
- At most one active main Goal.
- At most one active Milestone per Goal.
- At most one active Plan per (Goal, Milestone).
- At most one active Task per Plan (unless `parallel_safe`).

### 4.2 Parent/Child Invariants

1. A node's `root_goal_id` is always the topmost root Goal in its tree.
2. A child cannot be `active` unless its parent is `active`.
3. Closing a parent requires all children in terminal states.
4. A parent's `evidence_rollup` aggregates all children's evidence.
5. `children_order` defines display order; it does NOT define dependency.

### 4.3 Goal Recursion

- A Goal may contain child Goals to arbitrary depth.
- A Goal should be created only when it represents a meaningful functional unit
  (independent capability, acceptance boundary, multi-sibling impact, or
  reusable/replaceable/sealable/reviewable as a unit).
- Otherwise work stays inside a Plan or Task.

---

## 5. Plan Decoupling (from Task)

### 5.1 Current State (pre-contract)

```
.aiwf/artifacts/plans/<TASK-ID>.md   # Retired incorrect pattern: task-named Plan artifact
state.active_plan_id = task_id       # Retired incorrect pattern: 1:1 task/plan identity
task.parent_plan = ""                # Retired free-text alias
```

### 5.2 Target State

```
.aiwf/artifacts/plans/<PLAN-ID>.md   # Human artifact named by Plan id
state.active_plan_id = plan_id       # Independent Plan identity
task.plan_id = plan_id               # Foreign key reference
plan.task_ids = [task_id, ...]       # One Plan, many Tasks
.aiwf/state/plans.json entry         # Machine-readable registry (sole authority)
```

### 5.3 Migration Path

1. Add `plans.json` as empty Plan registry on install/init.
2. Do NOT auto-migrate legacy `<TASK-ID>.md` files. Legacy markdown is artifact-only.
3. `aiwf plan create <PLAN-ID> --goal-id GOAL-001` creates registry entry + artifact.
4. Legacy `--task-id` flag creates `PLAN-<TASK-ID>` in registry, not raw markdown.
5. New task entries set authoritative `plan_id` and `goal_id`.
6. `active_plan_id` references `plans.json`, validated on read.
7. Legacy `<TASK-ID>.md` without registry Plan produces activation blocker with
   remediation message: `"Create a registry-backed plan with aiwf plan create PLAN-001 --goal-id GOAL-001 && aiwf plan attach PLAN-001 TASK-001"`.

---

## 6. Sibling Relations

Sibling relations express non-parent-child relationships between nodes.
They are advisory — they inform planning, review, and impact analysis, but
do not drive execution ordering. Only `task.dependencies[]` gates activation.

### 6.1 Relation Types

| Type | Semantics |
|------|-----------|
| `depends_on` | Source should not complete before target |
| `blocks` | Source prevents target from progressing |
| `conflicts_with` | Source and target cannot both be active |
| `invalidates` | Source evidence invalidates target's assumptions |
| `supports` | Source work feeds into target (weaker than depends_on) |

### 6.2 Relation Schema

```json
{
  "source_id": "node-id",
  "target_id": "node-id",
  "type": "depends_on",
  "reason": "short human explanation",
  "created_at": "ISO8601"
}
```

### 6.3 Constraints

- Relations are stored on the source node.
- `depends_on` in relations is advisory. Only `task.dependencies[]` blocks activation.
- If Planner wants a relation to become a gate, copy it into `task.dependencies[]`.
- Broken relations (target deleted) become grooming warnings, not blockers.
- No graph engine. No traversal. Simple iteration only.

---

## 7. Impact Cone (replaces abstract weights)

AIWF does not use abstract priority/risk/effort/confidence/freshness scores.
A modification's importance is estimated through its structural position.

### 7.1 Impact Cone Composition

Given a changed node, the Impact Cone includes:

1. **Ancestor Goals** — all Goals up to the root
2. **Child Goals** — all Goals in the subtree
3. **Sibling relations** — directly related sibling nodes
4. **Attached Plans** — Plans on affected Goals
5. **Active Tasks** — Tasks under affected Plans
6. **Relevant Evidence** — Evidence records tied to affected nodes
7. **Related Milestones** — Milestones covering affected nodes
8. **Potentially invalidated reviews/tests** — quality artifacts on affected nodes

### 7.2 CLI

```
aiwf goal-tree impact GOAL-ID
```

Output is advisory. Not a gate. Becomes a gate only after the model stabilizes.

---

## 8. Temporary Roots, Graft, and Prune

### 8.1 Temporary Root

A Goal with `root_type: "temporary"`. Independent trial tree outside the main
structure. Does not enter default prompt. Does not affect the main tree.

Created via:
```
aiwf goal-tree init-root TMP-001 --type temporary
```

### 8.2 Graft

Adopt a Temporary Root or branch into the main Goal Tree.

```
aiwf goal-tree graft <SOURCE-ID> --target <PARENT-GOAL-ID> --reason "..."
```

Records: source, target parent, reason, affected Plans, sibling relations,
whether existing Plans become invalid.

### 8.3 Prune

Archive a failed, obsolete, or superseded branch.

```
aiwf goal-tree prune <BRANCH-ID> --reason "..."
```

Archives by default (does not delete). Records: target branch, reason,
evidence validity, abandoned Plans/Tasks, removed relations.

---

## 9. Reconcile Rules

When a child node closes, its parent is reconciled.

| Child closes | Parent reconciles | Action |
|-------------|-------------------|--------|
| Task → closed | Plan | Update `evidence_rollup`, `closed_task_ids`, `Goal Progress` section |
| Plan → complete | Goal | Update `evidence_rollup`, check goal completeness |
| Plan → complete | Milestone | Update `evidence_rollup`, contribute to `stage_synthesis` |
| Milestone → done | Goal | Write `stage_synthesis`, update `evidence_rollup` |

### Reconcile Fields

```json
{
  "intent": "Parent's understanding of what this child contributed",
  "evidence_rollup": {
    "summary": "Aggregated outcome from closed children",
    "child_count": 3,
    "closed_count": 2,
    "key_files_changed": ["path/a.py", "path/b.py"],
    "testing_status": "passed",
    "review_status": "accepted"
  },
  "open_gaps": ["Known issue X not yet addressed"],
  "parent_alignment": "aligned | drift_detected | needs_replan"
}
```

Drift detection: if child outcome doesn't match parent intent, set
`parent_alignment = drift_detected` and surface as a warning (not a blocker).

---

## 10. Grooming (Dry Run Only)

### 10.1 `aiwf goal-tree groom --dry-run`

| Issue | Detection | Severity |
|-------|-----------|----------|
| Orphan node | `parent_id` points to non-existent node | warn |
| Broken relation | `relations[].target_id` does not exist | warn |
| Stale active node | `status=active` with no recent activity | warn |
| Duplicate plan | Two active plans with overlapping intent on same goal | warn |
| Closed task not rolled up | Task `closed` but parent Plan not updated | warn |
| Invalidated evidence | Evidence from a task whose dependency was invalidated | warn |
| Cycle in depends_on | Task dependency traversal finds a cycle | escalate |
| Temporary root never resolved | `root_type=temporary` with no graft/prune decision | info |

### 10.2 Constraints

- Does NOT auto-delete, auto-close, or auto-hide nodes.
- Does NOT block any gate.
- All output is advisory.

---

## 11. File Layout

```
.aiwf/
  state/
    state.json              # Central control plane
    mission.json            # Optional singleton background annotation
    goal.json               # Legacy singleton active goal (GOAL-001)
    goals.json              # Goal Tree registry (multi-goal, future)
    milestones.json         # Milestone nodes
    plans.json              # Plan registry (sole machine authority)
    contexts.json           # Context registry
    fix-loop.json           # Fix loop tracking
  quality/
    testing.json
    review.json
  evidence/
    records.json
  history/
    task-ledger.json        # Task entries (plan_id, goal_id, milestone_id)
    task-history.json       # Cross-task quality metrics
  plans/
    <PLAN-ID>.md            # Human-authored plan artifacts
  reports/                  # Quality digests, project map, ideas
```

---

## 12. Status Display Boundaries

### 12.1 `aiwf status` (default, ~15 lines)

Shows active path only:
```
Goal: <active_goal.title>
Milestone: <active_milestone.title>  (if present)
Plan: <active_plan.title>
Task: <active_task.title> <status>
Phase: <phase>
Next: <PRIMARY action>
Health: ok | BLOCKED: <reason>
```

No full tree, no relations, no temporary roots, no Impact Cone.

### 12.2 `aiwf status --prompt` (~10 lines, AI-facing)

Same as default. Excludes Mission completely. Milestone is at most a compact
`milestone=<MS-ID>` token. Budget: ~200-800 characters.

### 12.3 `aiwf status --debug` (expanded)

Full tree, siblings, relations, Impact Cone (on request), temporary roots,
grooming issues, gravity signals.

---

## 13. CLI Commands

### New commands

| Command | Tier | Purpose |
|---------|------|---------|
| `aiwf mission show` | ADVANCED | Display current mission |
| `aiwf mission set <text>` | ADVANCED | Set or update mission |
| `aiwf goal-tree init-root <id> [--type main\|temporary\|branch]` | ADVANCED | Create a root Goal |
| `aiwf goal-tree add <id> --parent <parent-id>` | ADVANCED | Add child Goal |
| `aiwf goal-tree show [<id>]` | ADVANCED | Display Goal Tree |
| `aiwf goal-tree list` | ADVANCED | List all Goals |
| `aiwf goal-tree validate` | ADVANCED | Validate tree integrity |
| `aiwf goal-tree impact <id>` | ADVANCED | Show Impact Cone (advisory) |
| `aiwf goal-tree graft <id> --target <parent-id>` | ADVANCED | Graft branch into main tree |
| `aiwf goal-tree prune <id> --reason "..."` | ADVANCED | Archive a branch |
| `aiwf goal-tree groom --dry-run` | ADVANCED | Scan for issues |
| `aiwf milestone list` | ADVANCED | List milestones |
| `aiwf milestone show <id>` | ADVANCED | Show milestone + synthesis |
| `aiwf milestone create <title>` | ADVANCED | Create milestone |
| `aiwf milestone close <id>` | ADVANCED | Close with stage synthesis |
| `aiwf plan create <id> --goal-id <id> [--kind structural\|implementation]` | PRIMARY | Create plan |
| `aiwf relation add <src> <tgt> <type>` | ADVANCED | Add sibling relation |
| `aiwf relation remove <src> <tgt>` | ADVANCED | Remove sibling relation |
| `aiwf relation show <id>` | ADVANCED | Show relations for a node |

### Changed commands

- `aiwf plan create` — `<id>` is plan-id, requires `--goal-id`, accepts `--kind`.
- `aiwf task plan` — `--plan <plan-id>` added; `--milestone` flag replaced by `--milestone-id`.
- `aiwf task activate` — validates `plan_id` against `plans.json`.
- `aiwf status` — shows tree path, not flat task.

---

## 14. Change Admission Rule

AIWF does not allow unowned changes. Every change must enter the system through
one of two paths.

### Path 1: Plan Attachment

If the functional skeleton does not change, the change must attach as a Plan
under an existing Goal.

```text
Change → Plan → existing Goal
```

The Goal does not change. The Plan describes how the Goal is realized,
verified, migrated, or integrated under this change.

### Path 2: Goal Graft

If the functional skeleton changes, the change must enter as a new Goal
grafted through an explicit interface into the Goal Tree.

A grafted Goal must declare:
- Target parent Goal
- Interface consumed from the parent
- Capability provided back to the parent
- Sibling relations
- Affected Plans
- Whether the parent Goal's meaning changes

```text
Change → new Goal → graft through interface → parent Goal
```

### Fallback: Temporary Root

If neither path is clear, the change must first live under a Temporary Root.
It does not enter the stable tree until its place is understood.

### Summary

```text
Function skeleton unchanged → attach Plan
Function skeleton changed → graft Goal through interface
Ownership unclear → Temporary Root
```

No orphan patch. No silent Goal mutation. No Plan that secretly redefines its Goal. No new Goal without an interface.

---

## 15. Design Constraints (What NOT to Build)

- **No fixed five-layer chain.** Goal tree is recursive, not depth-locked.
- **No graph engine.** Relations are simple inline arrays with iteration-only queries.
- **No abstract weights.** Impact Cone replaces priority/risk/effort/confidence/freshness scores.
- **No multi-agent parallel scheduling.** `parallel_safe` remains the only concurrency signal.
- **No context pack auto-generation.** Context assembly remains prompt-diet governed.
- **No UI.** CLI only.
- **No forced milestone for L0/L1.**
- **No Mission or full Milestone expansion in `status --prompt`.**
- **No Task→Goal direct completion.** Evidence always rolls up through Plan.

---

## 16. Backward Compatibility

### 15.1 Field Aliases

| Old field | New field | Behavior |
|-----------|-----------|----------|
| `task.parent_goal` | `task.goal_id` | Alias; `goal_id` is authoritative |
| `task.parent_plan` | `task.plan_id` | Alias; `plan_id` is authoritative |
| `task.milestone` | `task.milestone_id` | Legacy label only; no gate effect |
| `state.active_plan_id` (task id) | `state.active_plan_id` (plan id) | Validated against `plans.json` |

### 15.2 Registry Authority

- `plans.json` is sole Plan machine truth. Markdown is artifact-only.
- Legacy `<TASK-ID>.md` without registry entry blocks activation.
- Existing singleton `goal.json` maps to `GOAL-001`.
- `goals.json` introduced in Stage 3.1 alongside, not replacing, `goal.json`.

### 15.3 Schema Versions

- `task-ledger.json`: `schema_version` 1 → 2.
- `goal.json`: add `node_version` field (1).
- New files: `node_version` field (1).

---

## Appendix A: Current State Audit (2026-06-12)

| Layer | State File | CLI | Lifecycle | Relations | Reconcile |
|-------|-----------|-----|-----------|-----------|-----------|
| Mission | none | none | none | none | none |
| Goal | goal.json (full) | `aiwf goal` (ADVANCED) | implicit | none | none |
| Goal Tree | none | none | none | none | none |
| Milestone | none (string on task) | `--milestone` flag only | none | none | none |
| Plan | none (markdown only) | `aiwf plan` (PRIMARY) | none | none | none |
| Task | task-ledger.json (full) | `aiwf task` (PRIMARY) | full FSM | dependencies[] | partial |

---

## Appendix B: Contract Test Requirements

| Rule | Test |
|------|------|
| Active path uniqueness | Activate two tasks under same plan → second blocked |
| Plan requires active Goal | Activate plan with goal not active → blocked |
| Task requires active Plan | Activate task with plan not active → blocked |
| Plan close requires all Tasks closed | Close plan with open tasks → blocked |
| Mission hidden from prompt | `status --prompt` output has no mission text |
| Goal recursion: no cycles | Create cycle in child_goal_ids → validation error |
| Goal recursion: root_type on non-root | Set root_type on child Goal → validation error |
| Temporary root hidden from prompt | `status --prompt` output has no temporary root text |
| Sibling relation does not block activation | Add `depends_on` relation → not in activation_blockers |
| Grooming is dry-run | `aiwf goal-tree groom --dry-run` → no file mutations |
| Reconcile on task close | Close task → parent plan evidence_rollup updated |
| Drift detection | Mismatched outcome → parent_alignment=drift_detected |
| Old parent_goal alias works | Read task.parent_goal → returns goal_id value |
| Old milestone field is non-authoritative | Write task.milestone → no gate effect |
| Plan registry authority | Legacy `<TASK-ID>.md` without registry → activation blocked |
| Plan kind validation | Create plan with invalid plan_kind → error |
| Graft requires reason | Graft without --reason → error |
| Prune archives by default | Prune → node archived, not deleted |
