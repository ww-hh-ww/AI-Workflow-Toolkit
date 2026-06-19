> **LEGACY — not authoritative for AIWF V1.**
> See docs/V1_DESIGN_CONTRACT.md for current rules.

# AIWF Rooted Functional Tree Design Contract

## 0. Purpose

AIWF is not merely a task runner, checklist system, or project management wrapper.

AIWF is a long-task governance kernel for AI agents. Its job is to preserve the
internal relationships of a project while allowing execution, exploration,
correction, and review to happen without collapsing into unstructured patches.

This contract defines the structural model of AIWF:

**Rooted Functional Tree with Procedural Scaffolds**

In this model:

- Mission frames the project scope and root Goals.
- Goal nodes form the functional skeleton of the system.
- Milestone nodes mark structural convergence — stable states downstream work can depend on.
- Plan nodes are procedural scaffolds attached to Goal nodes.
- Task nodes are concrete construction actions under Plans.
- Evidence is lightweight proof material flowing upward, not a core governance node.
- Temporary Roots allow fast trial growth without polluting the main tree.
- Sibling relation lines express dependencies, conflicts, invalidation, and support.
- Impact Cone replaces abstract weight or attention systems.

The purpose is not to require perfect structure before execution. The purpose is
to ensure that every change gradually clarifies its place, impact, and closure path.

---

## 1. Core Thesis

AIWF should not treat the structure as a fixed five-layer chain:

```text
Mission → Goal → Milestone → Plan → Task
```

This is too rigid.

Instead, AIWF treats these as semantic node types, not fixed depth levels.

The real structure is:

```text
Rooted Goal Tree
  └─ recursive Goal / Subgoal nodes
        └─ Plans attached to any Goal node
              └─ Tasks under Plans
                    └─ Evidence produced by Tasks
```

Milestones are optional sealing nodes that may cover a Goal subtree or a group of Plans.

Temporary Roots are optional trial roots used for exploratory growth.

Sibling relation lines express non-parent-child relations.

Therefore, the core structure is:

```text
Mission = project-level framing contract
Goal Tree = functional skeleton
Plan = procedural scaffold
Task = construction action
Evidence = lightweight proof artifact (not a core governance node)
Milestone = optional structural convergence node
Temporary Root = trial growth root
Sibling Relation = local lateral relation
Impact Cone = affected structure analysis
```
The five core node types are: Mission / Goal / Milestone / Plan / Task.
Evidence and relations are supporting constructs, not core governance nodes.

---

## 2. Design Axioms

### Axiom 1: Goal is structural.

A Goal is not just a task title or user request.

A Goal is a functional unit in the system. It represents a capability,
relationship, boundary, or value-bearing component that can be decomposed,
implemented, reviewed, and supported by evidence.

A Goal may contain child Goals.

A Goal may have Plans attached to it.

A Goal may be stable, temporary, or branch-local.

A node should become a Goal when at least one of the following is true:

1. It represents an independent capability.
2. It has an independent acceptance boundary.
3. Its modification affects multiple upper or sibling parts.
4. It may be reused, replaced, sealed, or reviewed as a functional unit.

Otherwise, the work should remain inside a Plan or Task.

---

### Axiom 2: Plan is procedural.

A Plan is not the skeleton of the system.

A Plan is a procedural scaffold attached to a Goal node.

A Plan describes how a Goal or Goal subtree is to be realized, constrained,
tested, migrated, or verified.

A Plan can change more frequently than a Goal.

A Plan must not silently replace or redefine its parent Goal.

If a Plan changes the meaning of a Goal, that is not a Plan update. It is a
Goal change and must be recorded as a structural change.

---

### Axiom 3: Plans may attach to any Goal level.

A Plan is not restricted to leaf Goals.

A higher-level Goal may have a structural Plan.

A lower-level Goal may have an implementation Plan.

This allows both top-down and bottom-up development.

Example:

```text
Goal: Rooted Functional Tree
  Plan: Define structure, interface, boundary, and child-goal policy

  Goal: Goal Tree Registry
    Plan: Implement goals.json and goal_tree_ops.py

  Goal: Impact Cone
    Plan: Implement read-only impact analysis
```

A high-level Plan reduces lower-level coupling by defining interfaces, boundaries,
and decomposition rules before detailed implementation proceeds.

---

### Axiom 4: There are at least two major Plan kinds.

AIWF should not overcomplicate Plan types, but it must distinguish structural
Plans from implementation Plans.

#### Structural Plan

A structural Plan usually attaches to a higher-level Goal.

It defines:
- System structure
- Interface boundaries
- Ownership boundaries
- Child Goal decomposition policy
- State ownership
- CLI contract
- Compatibility boundaries
- Testing and review expectations

A structural Plan may have few or no Tasks. Its output may be a design contract,
node contract, schema contract, or interface agreement.

#### Implementation Plan

An implementation Plan usually attaches to a lower-level Goal.

It defines:
- Files to modify
- State changes
- CLI behavior
- Tests
- Evidence expectations
- Acceptance criteria
- Review scope

Implementation Plans usually own concrete Tasks.

Other Plan kinds may exist later, such as verification, migration, or exploration,
but the first stable distinction is `structural` and `implementation`.

---

### Plan Phase Loading

A Plan is not a static instruction document. A Plan attached to a high-level Goal
is a **phase-loadable procedural scaffold**: it is loaded differently across the
lifecycle of its parent Goal.

A high-level structural Plan has at least two major roles:

**1. Framing role (early phase):**
- Define system structure
- Define interface relationships
- Define boundaries
- Define child Goal decomposition policy
- Define constraints lower-level Plans must obey
- Define how evidence rolls upward

At this stage the Plan acts like architectural blueprints and interface specs
before construction begins. It may have few or no concrete Tasks.

**2. Integration role (later phase):**
- Load lower-level outputs
- Check whether implementation respects upper interfaces
- Reconcile evidence upward
- Identify branch conflicts
- Decide whether to graft, prune, revise, or seal
- Prepare Milestone stage synthesis

At this stage the Plan acts like an integration scaffold — it calibrates,
validates structural consistency, and prepares for sealing.

Therefore, Plan loading is **phase-sensitive**. The `active_phase` field
determines which parts of a Plan enter context:

| Phase | Primary role | Typical for |
|-------|-------------|-------------|
| `framing` | Define structure, interfaces, boundaries | Early structural Plans |
| `implementation` | Guide concrete Tasks, produce evidence | Lower-level Plans |
| `integration` | Reconcile outputs, check consistency | Later-stage loading |
| `seal` | Prepare Milestone synthesis, final validation | Pre-close loading |

A structural Plan at a high-level Goal cycles through: framing → implementation →
integration → seal.

An implementation Plan at a lower-level Goal typically stays in: implementation →
verification.

**Prompt discipline:**

Default prompts must not include the full high-level Plan. They should include
only the relevant phase summary and interface constraints needed by the active
execution path.

When executing a leaf Task, the prompt loads:
- Current Plan (implementation phase)
- Current Goal
- Upper structural Plan's interface constraints (summary only, not full document)

When entering integration or seal phases, the prompt loads:
- Upper structural Plan
- Child Goal outputs
- Interface conformance status
- Open gaps and residual risks

This keeps the structure present without polluting the default prompt.

---

### Axiom 5: Execution is top-down and realization is bottom-up.

AIWF must support two opposite but complementary flows.

#### Top-down decomposition

```text
Root Goal
→ Structural Plan
→ Child Goals
→ Implementation Plans
→ Tasks
```

This flow is used by Planner and Architect.

It answers:
- What are we trying to build?
- What functions must exist?
- What interfaces and boundaries should constrain implementation?
- How should child Goals be separated?
- Which Plans are needed?

#### Bottom-up realization

```text
Task
→ Evidence
→ Plan progress
→ Goal support
→ Parent Goal confidence
→ Milestone synthesis
```

This flow is used by Executor, Tester, Reviewer, and Architect.

It answers:
- What was actually built?
- What evidence supports it?
- Which Plan did the evidence satisfy?
- Which Goal did the Plan support?
- Does the upper structure still hold?
- Is the branch ready to seal?

The tree is not merely planned from the top. It is made real from the bottom.

---

### Axiom 6: Evidence must roll upward.

A Task does not directly complete a high-level Goal.

A Task produces Evidence.

Evidence supports a Plan.

A Plan supports a Goal.

A Goal contributes to its parent Goal.

This protects the system from fake completion.

Correct rollup:

```text
Task evidence
→ Plan progress
→ Goal support
→ Parent Goal support
→ Milestone synthesis
```

Incorrect shortcut:

```text
Task done
→ Root Goal done
```

AIWF should prevent this shortcut in review and close logic.

---

### Axiom 7: Milestone is an optional structural convergence node.

A Milestone is not a time checkpoint and not a fixed layer between Goal and Plan.

A Milestone is an optional structural convergence node. It represents a stable
intermediate project state formed by a group of Goals, Plans, and Tasks converging
into a structure that downstream work can depend on.

A Milestone should be created when:
- Multiple Plan/Goal/Task branches form a nameable stable intermediate state
- Downstream work genuinely depends on that convergence
- A Temporary Root or exploration is ready to stabilize into main structure
- A release, context pack, or major phase boundary depends on the outcome

A Milestone should NOT be created:
- Because time passed or "a stage is done"
- Because a task is large
- Automatically at any boundary

Milestone assessment must not be a mechanical checklist.

It must synthesize:
- Whether the covered convergence is coherent as a structural state
- Whether structural interfaces between covered nodes are stable
- What downstream work depends on this convergence
- How stable the converged state is (draft/usable/stable/risky)
- Whether open gaps are known and residual risks are acceptable

A Milestone does not replace Goal or Plan. It describes what the convergence of
those nodes enables downstream.

---

### Axiom 8: Temporary Roots support exploration without polluting the main tree.

Exploratory work should not be forced into the main Goal Tree before its place is
understood.

When an idea, branch, or design direction is unclear, it may start as a Temporary Root.

A Temporary Root is a small independent trial tree.

It can contain Goals, Plans, Tasks, and Evidence.

It does not enter the default prompt.

It does not affect the main tree unless explicitly grafted.

Temporary Roots have two main outcomes:

```text
graft → adopted into the main Goal Tree
prune → archived or rejected without polluting the main tree
```

This allows fast trial growth without requiring a perfect structure up front.

---

### Axiom 9: Graft and Prune are structural operations.

Adding a branch is not a trivial append. A new branch changes relationships.

Therefore AIWF should eventually distinguish ordinary child insertion from grafting.

#### Graft

Graft means attaching a Temporary Root or branch to a target parent Goal.

A graft must record:
- Source root or branch
- Target parent Goal
- Reason
- Relation to parent
- Sibling relations
- Affected Plans
- Whether existing Plans become invalid or need revision

#### Prune

Prune means cutting off a failed, obsolete, or superseded branch.

Prune should archive by default, not delete.

A prune must record:
- Target branch
- Reason
- Whether evidence remains valid
- Whether any Plans or Tasks are abandoned
- Whether any sibling relations are removed

---

### Axiom 10: Sibling order is not dependency.

The order of child Goals may express time, narrative, or recommended construction order.

But order does not imply dependency.

Therefore AIWF must separate `children_order` from explicit relation lines.

Example:

```text
Goal A
  children_order: [A1, A2, A3]
```

This means A1 is listed before A2 and A3. It does not mean A2 depends on A1.

If dependency exists, it must be explicit:

```text
A2 depends_on A1
```

---

### Axiom 11: Use local relation lines, not a heavy graph engine.

AIWF should avoid becoming a graph-first system.

The tree carries the main structure.

Relation lines only express what the tree cannot express.

Allowed initial relation types:

```text
depends_on
blocks
conflicts_with
invalidates
supports
```

Relation lines are used for:
- Impact analysis
- Review scope
- Context selection
- Delta verification
- Risk awareness

Relation lines must not bypass gates.

Relation lines must not become an independent execution engine.

---

### Axiom 12: Impact Cone replaces abstract weights.

AIWF should not introduce abstract node weights or attention scores unless strictly
necessary.

The tree hierarchy already carries structural importance.

A modification's importance is better estimated through its Impact Cone.

An Impact Cone includes:

1. Ancestor Goals
2. Child Goals
3. Sibling relation lines
4. Attached Plans
5. Active Tasks
6. Relevant Evidence
7. Related Milestones
8. Potentially invalidated reviews or tests

This is more precise than weight.

Example:

```text
Changed node: GOAL-Plan-Registry

Impact Cone:
- Ancestors: GOAL-Long-Task-Foundation, GOAL-AIWF-V1
- Sibling relation: GOAL-Milestone depends_on GOAL-Plan-Registry
- Attached Plans: PLAN-Registry-Authority
- Tasks: TASK-Activation-Check, TASK-Close-Reconcile
- Milestones: MS-Stage-1
```

Impact Cone is advisory at first. It should not become a hard gate until the model
is stable.

---

## 3. Node Semantics

### 3.1 Goal Node

A Goal node represents a functional unit.

It may be a root, branch, or child Goal.

A Goal may have child Goals.

A Goal may have Plans attached to it.

A Goal may be covered by a Milestone.

A Goal may have sibling relation lines.

Minimal Goal fields:

```json
{
  "id": "GOAL-001",
  "title": "Goal title",
  "root_type": null,
  "parent_goal_id": null,
  "child_goal_ids": [],
  "children_order": [],
  "intent": "",
  "acceptance_boundary": "",
  "attached_plan_ids": [],
  "status": "active",
  "created_at": "",
  "updated_at": ""
}
```

Allowed `root_type` values:

```text
main
temporary
branch
null
```

Root Goals must have `parent_goal_id = null`.

Non-root Goals should have `root_type = null`.

A temporary root should not enter the default prompt.

---

### 3.2 Plan Node

A Plan node represents a procedural scaffold.

A Plan must attach to a Goal.

A Plan may be structural or implementation-oriented.

Minimal new Plan fields:

```json
{
  "id": "PLAN-001",
  "goal_id": "GOAL-001",
  "target_goal_id": "GOAL-001",
  "plan_kind": "structural",
  "interfaces": [],
  "constraints": [],
  "child_goal_policy": "",
  "task_ids": []
}
```

`goal_id` may remain for compatibility, but `target_goal_id` is the clearer future field.

For now, implementations may keep `goal_id == target_goal_id`.

Plan kind values:

```text
structural
implementation
verification
migration
exploration
```

Only `structural` and `implementation` are required for the first implementation.

A structural Plan may define no concrete Tasks yet.

An implementation Plan usually owns concrete Tasks.

---

### 3.3 Task Node

A Task node represents a concrete construction action.

A Task belongs to a Plan.

A Task should inherit its functional target from the Plan unless explicitly overridden.

Task should not directly mutate the Goal Tree.

Task produces Evidence.

Task close should update Plan progress.

Plan progress may then update Goal support.

Correct relationship:

```text
Task → Plan → Goal
```

Not:

```text
Task → Goal directly
```

---

### 3.4 Evidence (lightweight proof artifact, not a core node)

Evidence is lightweight proof material produced by execution. It is NOT a core
governance node in the five-node model (Mission / Goal / Milestone / Plan / Task).

Evidence may include test output, changed files, review notes, validation logs,
CLI output, human confirmation, or external references.

Evidence supports a Plan or Task. Evidence may roll up to Goal support only
through Plan progress.

Evidence can be invalidated. Invalidation should affect the relevant Plan, Goal,
or Milestone assessment.

**Do NOT build a heavy Evidence Registry.** Evidence records are referenceable
but lightweight. No evidence graph engine. No evidence lifecycle beyond creation
and optional invalidation. Evidence is proof, not project structure.

---

### 3.5 Milestone Node

A Milestone is an optional structural convergence node. It represents a stable
intermediate project state formed by a group of Goals, Plans, and Tasks.

It may cover a Goal subtree, a Plan set, a Task group, or a mixed scope.
It exists when downstream work depends on the convergence of the covered scope.

Milestone is not a time checkpoint, not a fixed layer, and not a required
stage seal. It should not be required for ordinary L0/L1 work. It should not
expand in `status --prompt`.

Milestone close requires structural convergence assessment. Assessment should
include: coherence as a structural state, evidence sufficiency, interface
stability between covered nodes, what downstream work depends on this convergence,
stability claim (draft/usable/stable/risky), open gaps, residual risks, and
recommended next frontier.

---

## 4. Structural Operations

### 4.1 Grow

Grow means adding child Goals under an existing Goal.

Grow is appropriate when the parent Goal is already known and the child belongs
naturally under it.

Grow must preserve:
- Parent-child consistency
- Children order consistency
- No cycles
- Acceptance boundary clarity

---

### 4.2 Attach Plan

Attach Plan means creating or linking a Plan to a Goal node.

The Plan must declare:
- Target Goal
- Plan kind
- Scope
- Expected output
- Whether it is structural or implementation-oriented

A structural Plan may later guide child Goal creation.

An implementation Plan may later generate Tasks.

---

### 4.3 Graft

Graft means moving or adopting a branch or Temporary Root into the main tree.

Graft is required when a branch was grown outside the main structure and later
becomes valid.

Graft must answer:
1. Where is this branch attached?
2. Why does it belong there?
3. Does it change the parent Goal's meaning?
4. What sibling relations does it have?
5. Which Plans become affected?
6. Which Evidence remains valid?
7. Is any old branch superseded?

---

### 4.4 Prune

Prune means archiving or removing a failed or obsolete branch from active structure.

Prune must answer:
1. Why is this branch no longer active?
2. Is it rejected, superseded, or merely dormant?
3. Does its evidence remain useful?
4. Are any Plans or Tasks abandoned?
5. Are any relation lines invalidated?

Prune should archive by default.

Deletion should only happen for generated noise with no evidence value.

---

### 4.5 Seal

Seal means declaring that a branch or Milestone has reached a stable stage boundary.

Seal does not mean no future change is possible.

It means future change must be explicit:

```text
reopen
graft
revise
supersede
```

Seal should be supported by assessment.

---

## 5. Bidirectional Planning and Realization

AIWF must support two valid planning directions.

### 5.1 Top-down path

Used when mission and architecture are relatively clear.

```text
Root Goal
→ Structural Plan
→ Child Goals
→ Implementation Plans
→ Tasks
→ Evidence
```

This is suitable for:
- Systematic engineering
- Architecture changes
- Interface-sensitive work
- Large refactors
- Multi-agent coordination
- Release-hardening

Top-down planning reduces rework by stabilizing interfaces early.

---

### 5.2 Bottom-up path

Used when uncertainty is high.

```text
Temporary Root or local Goal
→ Trial Plan
→ Task / prototype
→ Evidence
→ Goal refinement
→ possible graft
```

This is suitable for:
- Exploratory research
- Unclear design
- Technical feasibility testing
- New architecture ideas
- Rapid trial and rejection

Bottom-up work must not pollute the main tree until it is grafted.

---

### 5.3 Bidirectional convergence

The best AIWF flow uses both.

```text
Top-down structure constrains implementation.
Bottom-up evidence corrects structure.
```

The system converges when:
- Structural Plans define useful boundaries.
- Implementation Plans produce evidence.
- Evidence validates or challenges the structure.
- Goal Tree becomes clearer after execution.
- Temporary branches are grafted or pruned.
- Milestones seal coherent stages.

---

## 6. Interface and Coupling Principle

A major purpose of upper-level Plans is to reduce lower-level coupling.

When an upper Goal has a structural Plan, lower implementation work should happen
under its interfaces and boundaries.

This means bottom-level changes should not automatically shake the entire upper
structure.

If a lower change respects the upper interface, its Impact Cone remains local.

If a lower change breaks the upper interface, the Impact Cone expands upward.

Therefore, structural Plans are not bureaucracy. They are coupling control.

---

## 7. Change Admission Rule

AIWF does not allow unowned changes. Every change must enter the system through
one of two paths.

### Path 1: Plan Attachment

If the functional skeleton does not change, the change must attach as a Plan
under an existing Goal.

This includes: implementation work, verification work, migration work,
refactoring work, integration work, and structural planning work that serves
an existing Goal without redefining it.

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

A Goal is not simply appended. It is grafted through interface.

### Temporary Root (fallback)

If neither path is clear, the change must first live under a Temporary Root.
It does not enter the stable tree until its place is understood. Then it is
either grafted or pruned.

### The Rule

```text
Function skeleton unchanged → attach Plan
Function skeleton changed → graft Goal through interface
Ownership unclear → Temporary Root
```

No orphan patch. No silent Goal mutation. No Plan that secretly redefines its
Goal. No new Goal without an interface.

---

## 8. Patch Policy (consequence of Change Admission Rule)

AIWF must not pretend that real engineering has no patches.

Patches are allowed.

Unowned patches are not allowed.

A patch is acceptable when it declares:
1. Which root or Goal it belongs to
2. Which Plan it supports
3. Which interface or boundary it touches
4. Whether it is temporary or stable
5. What evidence verifies it
6. What follow-up or cleanup is required

A patch that cannot answer these should not enter the stable tree.

It may live under a Temporary Root until its relationship becomes clear.

The policy is:

```text
Do not reject patches.
Reject orphan patches.
```

---

## 9. Prompt and Context Policy

The Goal Tree must not make prompts large.

Default prompt should show only:
- Current active root or Goal
- Current active Plan
- Current active Task
- Required next action
- Critical blockers

The full tree should only appear in:

```text
status --debug
goal-tree show
goal-tree impact
milestone show
review context
architect context
```

Temporary Roots should not enter default prompt.

Archived or pruned branches should not enter default prompt.

Relation lines should not enter default prompt unless they directly affect the
active path.

---

## 10. Review Policy

Reviewer should use the Goal Tree to ask:
1. Does the Task evidence support the Plan?
2. Does the Plan support its target Goal?
3. Did the Plan silently change the Goal?
4. Did the change violate structural interfaces?
5. Did the change affect sibling relations?
6. Did the Impact Cone require additional validation?
7. Is this a local patch, structural patch, or orphan patch?
8. Should a Temporary Root be grafted or pruned?
9. Is the Milestone ready to seal?

Review should not only inspect code diffs.

Review should inspect whether the bottom-up realization still supports the top-down
structure.

---

## 11. Tester Policy

Tester should use the Goal Tree to ask:
1. Which Goal does this Task support?
2. Which Plan owns the acceptance criteria?
3. Is this testing a local implementation behavior or a structural interface?
4. If structural, are interface tests required?
5. If implementation, are regression tests sufficient?
6. Does failing evidence invalidate a Plan, Goal, or Milestone?
7. Does the test result require Impact Cone review?

Testing should not only verify task completion.

Testing should verify that evidence can roll upward.

---

## 12. Architect Policy

Architect should use the Goal Tree to ask:
1. Is this Goal a real functional unit?
2. Is this child Goal placed under the correct parent?
3. Does this branch need a structural Plan?
4. Should this be a Temporary Root instead of a main branch?
5. Does this new branch change the parent Goal?
6. Should this branch be grafted, pruned, or sealed?
7. Are sibling relation lines needed?
8. Does this structure reduce or increase coupling?

Architecture is not only file structure.

Architecture is the relationship between functional Goals, procedural Plans,
implementation Tasks, and evidence rollup.

---

## 13. Minimal Implementation Boundary

The first implementation should not attempt everything.

Stage 3.0 and Stage 3.1 should only implement:
1. Design documents
2. goals.json skeleton
3. goal_tree_ops.py
4. recursive Goal registry
5. root Goal support
6. temporary root field support
7. child Goal relation support
8. validation for cycles and parent-child consistency

The first implementation must not:
- Change task activation
- Change task close
- Change Plan Registry authority
- Change Milestone Registry behavior
- Add heavy graph engine
- Add weights
- Add context pack
- Add multi-agent behavior
- Expand status --prompt
- Force all old Tasks into the new Goal Tree

---

## 14. Implementation Sequence

### Stage 3.0: Design Contract

Create or update:
```text
docs/AIWF_DESIGN_AXIOMS.md
docs/NODE_CONTRACT.md
docs/TREE_FOUNDATION_MIGRATION.md
```

Purpose:
- Replace fixed five-layer thinking.
- Establish Rooted Functional Tree.
- Define Plan as scaffold.
- Define bidirectional planning and realization.
- Define Temporary Root, Graft, Prune, Seal.
- Define sibling relations and Impact Cone as future work.

### Stage 3.1: Goal Tree Registry Skeleton

Create:
```text
.aiwf/state/goals.json
aiwf_core/core/state/goal_tree_ops.py
```

Minimal schema:
```json
{
  "schema_version": 1,
  "active_goal_id": null,
  "roots": [],
  "goals": [],
  "relations": []
}
```

Required operations:
```text
load_goal_tree
save_goal_tree
list_goals
get_goal
upsert_goal
add_child_goal
validate_goal_tree
```

Validation:
- roots reference existing Goals
- root Goals have no parent
- child IDs exist
- children order references only child IDs
- parent-child consistency
- no cycles

### Stage 3.2: Goal Tree CLI

Add:
```text
aiwf goal-tree init-root
aiwf goal-tree add
aiwf goal-tree show
aiwf goal-tree list
aiwf goal-tree validate
```

No activation integration yet. No close integration yet.

### Stage 3.3: Plan attaches to any Goal

Extend Plan Registry:
```text
target_goal_id
plan_kind
interfaces
constraints
child_goal_policy
```

Plan create should support:
```text
aiwf plan create PLAN-001 --target-goal GOAL-001 --kind structural
aiwf plan create PLAN-002 --target-goal GOAL-003 --kind implementation
```

### Stage 3.4: Plan-to-Goal rollup

Add read-only or soft rollup first:
```text
Plan progress → Goal support_rollup
```

Do not auto-close Goals. Do not make this a hard gate initially.

### Stage 3.5: Temporary Root

Allow:
```text
aiwf goal-tree init-root TMP-001 --type temporary
```

Temporary roots do not enter default prompt.

### Stage 3.6: Graft and Prune

Add explicit structural operations:
```text
aiwf goal-tree graft
aiwf goal-tree prune
```

Both must record reasons. Prune archives by default.

### Stage 3.7: Sibling Relations

Add lightweight relation lines:
```text
depends_on
blocks
conflicts_with
invalidates
supports
```

Use them for review and impact analysis. Do not build a full graph engine.

### Stage 3.8: Impact Cone

Add:
```text
aiwf goal-tree impact GOAL-ID
```

Output ancestors, children, relations, attached Plans, active Tasks, Evidence,
and Milestones.

Impact Cone is advisory first.

---

## 15. Anti-Goals

AIWF must not:
1. Turn Goal Tree into a heavyweight project management tree.
2. Require a perfect tree before execution.
3. Force exploratory work into the main root too early.
4. Treat Plan as the main skeleton.
5. Treat child order as dependency.
6. Add abstract weights when structural impact is enough.
7. Build a graph engine before sibling relations prove insufficient.
8. Let status --prompt expand with full tree details.
9. Let unowned patches enter stable structure.
10. Let Task completion directly imply Goal completion.
11. Let a Plan silently redefine its Goal.
12. Let Milestone become a mechanical checklist.

---

## 16. Final Contract Statement

AIWF's structural foundation is:

```text
Rooted Functional Tree with Procedural Scaffolds
```

The system is governed by these principles:

```text
Mission is the project-level framing contract.
Goal is the functional skeleton.
Plan is the phase-loadable procedural scaffold.
Task is the construction action.
Evidence is lightweight proof material, not a core governance node.
Milestone is an optional structural convergence node.
Temporary Root is trial growth.
Graft and Prune manage structural change.
Sibling relations express local lateral dependency.
Impact Cone replaces abstract weight.
Object truth registries own node content; derived views own relationships.
Top-down planning and bottom-up realization converge through review.
High-level Plans frame early and integrate late; low-level Plans implement.
```

AIWF does not require perfect relationships at the start.

AIWF requires every change to clarify its root, target Goal, Plan, impact, and
closure path.

The goal is not to eliminate patches.

The goal is to make every patch digestible by the structure.
