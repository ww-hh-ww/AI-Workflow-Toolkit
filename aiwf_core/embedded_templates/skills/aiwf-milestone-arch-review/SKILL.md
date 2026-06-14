---
name: aiwf-milestone-arch-review
description: Cross-check empirical connectivity against Goal tree at milestone boundaries
---

# AIWF Milestone Architecture Review

## STOP — Check topology BEFORE any other action

Read `.aiwf/state/state.json` → `workflow_level`.
L0=inline, L1/L2/L3=SPAWN subagent.

**If workflow_level is NOT "L0_direct":**
You are planner-main. You do NOT review.

```
Agent({subagent_type: "aiwf-reviewer", prompt: "Milestone architecture review for <MILESTONE-ID>. ..."})
```

**Only continue if workflow_level IS "L0_direct".**

---

## Purpose

The integration tester produced an empirical connectivity map — what actually
connects to what. Your job: cross-check that map against the declared Goal tree.

You are looking for STRUCTURAL mismatches between reality and intent.

## Before starting

1. Read the tester's output: `.aiwf/artifacts/reports/里程碑-<MILESTONE-ID>-描述.md`
2. Read `.aiwf/state/goals.json` → covered goals, their relations (depends_on,
   conflicts_with), module_boundaries, architecture_invariants
3. Read `.aiwf/state/milestones.json` → the milestone itself

## What to check

### Reality vs declared relations
- Goal tree says `<GOAL-A> → depends_on → <GOAL-B>`. Does the connectivity map
  show an actual path from A to B? If not → `broken dependency`.
- Connectivity map shows `<GOAL-A>` consuming `<GOAL-C>`. Is that relation
  declared in the Goal tree? If not → `undeclared coupling` (may be fine,
  may need a new relation)

### Boundary violations
- Each covered goal has `module_boundaries`. Does the connectivity map show
  paths crossing those boundaries without a declared relation?

### Invariants
- Each covered goal has `architecture_invariants`. Does the connectivity map
  suggest any of these are violated? (e.g., "auth always required" but a path
  reaches BACKEND without touching AUTH)

### Dead structure
- A goal with no incoming connections from any other goal and no outgoing
  connections to any other goal → `structural silo`. Is this intentional?

### Documentation match
- Does the connectivity map match the milestone's own description of what
  should work? If the milestone intent says "AUTH + BACKEND integrated" but
  the map shows them disconnected → `intent gap`.

## Recording

```
aiwf milestone arch-review <MILESTONE-ID> \
  --status intact|issues_found \
  --interface "<GOAL-A>→<GOAL-B>" \
  --issue "Undeclared coupling: <GOAL-A> calls <GOAL-C> but no relation declared" \
  --notes "<summary>"
```

- No structural mismatches → status=intact
- Any broken dependency, violated invariant, or intent gap → status=issues_found
- Undeclared couplings are advisory (--issue), not blockers — Planner decides
