# Governance Structure Guide

## Node semantics

| Node | Meaning | Key property |
|------|---------|-------------|
| Goal | Mission capability — WHAT outcome the system can produce. Decompose the mission capability model, not the implementation. | Parent-child Goal tree |
| Plan | Mission mechanism — HOW this Goal will become true: operating model, information model, data/control flow, technical direction. | `plan dep add` for execution gates |
| Task | Execution contract — one deliverable with proof standard, scope, and role dispatch. | `dependencies` for within-plan order |
| Milestone | Acceptance proof — stable delivery point that proves integration, consumption, and readiness to continue. | `link-plan/link-task` then Architect `milestone-acceptance` |

## Relationship model

- **Goal tree** = decomposition (parent-child). A child is part of its parent's
  capability domain. Not blocking.
- **Goal relations** (`depends_on`, `blocks`, `supports`) = capability deps.
  Logical — explain WHY Plans are ordered the way they are. Not blocking.
- **Plan dependencies** = execution gates. Blocking. Must complete in order.
- **Task dependencies** = within-plan ordering.

Goal deps explain Plan structure; they do not duplicate or replace it.

## Planning order

Think in this order:

1. Mission capability model: what capabilities must exist for the fixed mission
   to be true?
2. Goal tree: where does each capability belong, and are gaps visible?
3. Plan mechanism: what operating model, information model, feedback loop, risk
   burn-down order, and technical direction make the Goal true?
4. Task contracts: what is the next smallest deliverable that proves progress
   without over-prescribing implementation?
5. Milestone proof: what running-system acceptance point proves a stable slice
   of the mission?

## Structure discipline

- **Change direction = revise the Plan.md**, not create a new one.
  Re-open or create new Tasks under the revised Plan.
- A cancelled Plan means the approach was wrong; write a better Plan.md.
  Don't leave the corpse and start fresh.
- If Architect reports a goal-level completeness gap, revise the Goal tree or
  record a deferred reason before creating more Tasks under the old shape.
- If Planner cannot name the main path, evidence path, or integration risk,
  create exploration/design work first. Do not activate an implementation Task
  to discover the architecture accidentally.

## Anti-patterns

- 1:1 Goal→Plan mapping → merge or split the Goal.
- Leaf goals describing implementation details → move to Plan/Task scope.
- Goal tree deeper than 2-3 levels → collapse leaf goals into parent body.
- New Plan instead of revising → violates structure discipline.
- Task used as design discovery → create exploration/design work first.
- Milestone used as a date checkpoint → rewrite as acceptance proof.
- Plan lists Tasks but has no mechanism, data/control flow, risk order, or
  validation strategy.
