# Governance Structure Guide

## Node semantics

| Node | Meaning | Key property |
|------|---------|-------------|
| Goal | Capability — WHAT the system can do. Decompose via parent-child tree. ~10 top-level. | `goal link A B --type depends_on` |
| Plan | Execution scaffold — HOW. Technical direction: method, data flow, tech choices. | `plan dep add` for execution gates |
| Task | Execution unit — smallest deliverable. One implement/test/review cycle. | `dependencies` for within-plan order |
| Milestone | Acceptance gate — stable delivery point. Verifies integration and consumption. | `link-plan/link-task` then `assess/confirm/close` |

## Relationship model

- **Goal tree** = decomposition (parent-child). A child is part of its parent's
  capability domain. Not blocking.
- **Goal relations** (`depends_on`, `blocks`, `supports`) = capability deps.
  Logical — explain WHY Plans are ordered the way they are. Not blocking.
- **Plan dependencies** = execution gates. Blocking. Must complete in order.
- **Task dependencies** = within-plan ordering.

Goal deps explain Plan structure; they do not duplicate or replace it.

## Structure discipline

- **Change direction = revise the Plan.md**, not create a new one.
  Re-open or create new Tasks under the revised Plan.
- A cancelled Plan means the approach was wrong; write a better Plan.md.
  Don't leave the corpse and start fresh.

## Anti-patterns

- 1:1 Goal→Plan mapping → merge or split the Goal.
- Leaf goals describing implementation details → move to Plan/Task scope.
- Goal tree deeper than 2-3 levels → collapse leaf goals into parent body.
- New Plan instead of revising → violates structure discipline.
