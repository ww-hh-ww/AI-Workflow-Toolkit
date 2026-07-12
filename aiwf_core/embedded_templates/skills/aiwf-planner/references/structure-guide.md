# Governance Structure Guide

## Node Meanings

| Node | Meaning | Key property |
|------|---------|--------------|
| Goal | Mission capability: what outcome the system can produce. | Parent-child Goal tree |
| Plan | Mechanism: how this Goal becomes true. | Plan dependencies are execution gates |
| Task | Execution contract: one deliverable with proof. | Task dependencies order work inside a Plan |
| Milestone | Acceptance proof: integrated, consumed, stable slice. | Architect `milestone-acceptance` verifies it |

## Relationships

- Goal tree: capability decomposition. Not blocking.
- Goal relations: capability logic. Explain why Plans are ordered. Not blocking.
- Plan dependencies: execution gates. Blocking.
- Task dependencies: order inside a Plan.

Goal dependencies explain Plan structure; they do not replace it.

## Planning Order

Think in this order:

1. mission capability model.
2. Goal tree and visible gaps.
3. Plan mechanism: operating model, information model, feedback, risk order,
   technical direction.
4. Cross-boundary consistency: shared truth, owner, proof.
5. Task contracts: next smallest deliverable that proves progress. Do not invent it.
6. Milestone proof: running-system acceptance point.

## Task Activation Readiness

Critical reread before activation. Before activating implementation, reread the
relevant Goal.md, Plan.md, Task.md, and Milestone.md as a critic, not as their
author.
Before `aiwf task activate`, reread the relevant Goal.md, Plan.md, Task.md, and Milestone.md as a critic, not as their author.

Answer:

- Capability: what Goal capability does this Task advance?
- Main path: what entry -> transform -> consume -> observe path matters?
- Consumer: who consumes this Task output?
- Invariant: what shared truth must not be guessed?
- Proof: what observable result proves it works?
- Old path: who owns removal, deprecation, compatibility, or migration?
- Unknowns: are unresolved boundaries converted into exploration/design work or
  deferred with a reason?

If any answer is missing, do not activate implementation.
Fix the Plan/Task contract first.

## Structure Discipline

- Change direction by revising Plan.md, not by creating a new parallel Plan.
- If a Plan is cancelled because the approach was wrong, write the better
  Plan.md and make the old decision visible.
- If Architect reports a mission-required gap, revise the Goal tree or record a
  deferred reason before creating more Tasks under the old shape.
- If Planner cannot name main path, evidence path, or integration risk, create
  exploration/design work first.
- Put consistency at the lowest common boundary future work will reliably read.
  Capture the smallest shared truth. Do not list functions unless the function
  itself is the public boundary.

## Anti-patterns

- 1:1 Goal -> Plan mirror.
- Leaf Goals that describe implementation details.
- Goal tree deeper than 2-3 useful levels.
- New Plan instead of revising the old direction.
- Task used as design discovery.
- Milestone used as a date checkpoint.
- Plan with Tasks but no mechanism, data/control flow, risk order, or proof.
- Cross-boundary work with no verified Shared truth, Owner, Proof, or Basis.
