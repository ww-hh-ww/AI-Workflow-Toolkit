# Narrative Doc Writing Guide

## Principle

Each MD file is a shared human-agent working agreement, as well as a contract
for the next role. The human must be able to understand and correct it without
knowing AIWF internals. It should support engineering judgment without telling
the next role exactly how to code.
Deliberate writing beats bulk generation.

Write narrative content in the user's working language. Preserve required
machine-parsed headings, IDs, and commands, but explain the work in project
language: why it matters, what will change, what will not, how to recognize
success, and what still needs a decision. Keep agreed requirements and important
tradeoffs visible; do not replace them with role instructions or evidence jargon.
Place technical anchors and commands after the readable outcome, not instead
of it. Do not duplicate a separate human summary and agent contract that can drift.

Write:

- outcome;
- structural home;
- known facts;
- unknowns;
- proof;
- handoff.

Do not write filler, guessed facts, or implementation recipes. Do not invent
implementation details. Accuracy beats completeness.

## Source Of Truth

MD body carries meaning. MD frontmatter carries structure. `aiwf sync` derives
JSON machine state from the frontmatter and selected structured sections.
JSON is for gates, routing, evidence, and status; do not use it as the semantic
contract.

Use CLI when a command exists. For structural edits with no CLI command, edit
the MD frontmatter/body and run `aiwf sync`. Never hand-edit JSON.

## Missing Information

Omit optional sections that add no information. Do not fill them with `None`.

Use `Unknown` only for a relevant question that has not been answered. Say what
would resolve it. If it affects the main path, consumer, invariant, owner, or
proof, do not activate implementation; investigate or ask the human first.

## Before Leaving Any MD

Check:

- Structural home: why this node belongs here.
- Decision: what this doc chooses and what it leaves open.
- Known / Unknown: facts have a source; uncertain facts are labeled.
- Consistency: shared truth, owner, and proof exist when crossing boundaries.
- Proof: success is observable on the mission path.
- Handoff: the next role has enough context and enough judgment space.

## Required Frontmatter

Every Goal, Plan, Task, and Milestone node MD must have:

```yaml
---
id: <NODE-ID>
type: goal | plan | task | milestone
---
```

## Per-doc Guides

These are the shared writing principles for every AIWF MD.

- `goal-writing.md` — capability boundary.
- `plan-writing.md` — mechanism and consistency.
- `task-contract.md` — execution contract.
- `milestone-writing.md` — acceptance gate.

## Common Failure Modes

- Many nodes are created quickly, but their boundaries and proof are vague.
- A node repeats the user request instead of deciding structure.
- A Task is activated before consumer, invariant, owner, or proof is known.
- Unknown facts are written as if verified.
- Proof shows a file or component exists, not mission behavior.
- The next role must rediscover basic context.
- The doc micromanages code and removes role judgment.
