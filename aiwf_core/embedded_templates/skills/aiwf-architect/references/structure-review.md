# Governance Structure Review

Critique the AIWF governance structure: Goal tree, Plan dependencies, and the
relationship between them.

## Goal Tree

- Does the Goal tree reflect true capability decomposition?
- Are there 1:1 Goal→Plan mappings? (anti-pattern: Goal and Plan describe the same thing)
- Do leaf Goals describe implementation details instead of capabilities?
- Is the tree deeper than 2–3 levels? (collapse leaf goals into parent body text)
- Are there orphan Goals (no plans attached, no clear path to execution)?
- Are there overlapping Goals that should be merged?

## Plan Dependencies

- Do Plan dependencies reflect genuine execution gates?
- Are there missing dependencies — Plans that should be sequenced but aren't?
- Are there unnecessary dependencies — Plans blocked by something they don't actually need?
- Can the dependency graph be simplified?

## Relationship Model

- Do Goal relations (depends_on, blocks, supports) correctly explain WHY Plan
  dependencies are structured the way they are?
- Are Goal deps being confused with Plan deps? (Goal deps are logical, not blocking)
- Are Task dependencies correctly capturing within-plan ordering?

## Anti-pattern Checklist

- [ ] No 1:1 Goal→Plan mapping
- [ ] No leaf Goals describing implementation
- [ ] Tree depth ≤ 3
- [ ] Every Goal has a path to execution
- [ ] Plan dependencies are blocking only what needs blocking
- [ ] Goal relations explain Plan structure, not duplicate it
