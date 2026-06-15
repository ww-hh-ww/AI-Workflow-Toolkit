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
- Read `.aiwf/assets/project-map.json` `goal_bindings` and run
  `aiwf project-map validate` before comparing structure.
- Each covered Goal should have a current Goal-to-module binding. Does the
  connectivity map show paths crossing those boundaries without a declared relation?
- Missing or stale bindings are mapping defects. Do not reshape Goals around
  files or milestone coverage; route the correction back to Planner.

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
  --issue "HIGH:::Undeclared coupling: <GOAL-A> calls <GOAL-C> but no relation declared" \
  --notes "<summary>"
```

- No structural mismatches → status=intact
- Any broken dependency, violated invariant, or intent gap → status=issues_found
- Every issue must be classified `CRITICAL|HIGH|MEDIUM|LOW`.
- `status=intact` with any issue is rejected as contradictory.
- `issues_found` mechanically blocks milestone close.
- A broken main path, failed authentication/authorization, unusable entrypoint,
  violated security invariant, or disconnected required integration is CRITICAL.
  It must return to Planner/fix-loop, be repaired, re-tested, and re-reviewed.
- CRITICAL/HIGH findings may not be deferred as `PASS_WITH_RISK`.
- Recording `issues_found` automatically invalidates the milestone synthesis to
  `REVISE` and keeps/reopens the milestone as active.
- After fixes, rerun milestone integration first, then rerun architecture review:
  `--status intact --resolution "<what changed and why the issue is resolved>"`
  plus `--resolution-evidence-id` when evidence exists.
- The previous issues remain in review history, and the milestone must be
  assessed again as PASS/PASS_WITH_RISK before close.

## User acceptance before final close

Technical PASS means the milestone is eligible for delivery acceptance; it does
not mean the user has accepted the stage boundary.

After integration, architecture review, and stage synthesis all pass:

1. Present what was completed, what remains outside scope, residual risks, and
   the recommended next stage.
2. For `advance_policy=checkpoint|manual`, ask the user to accept the milestone.
3. For `PASS_WITH_RISK`, always ask, even when `advance_policy=auto`.
4. After explicit acceptance, record:
   `aiwf milestone confirm <ID> --summary "<what the user accepted>"`
5. Only then run `aiwf milestone close <ID>`.

For a low-risk internal milestone with `advance_policy=auto` and verdict=PASS,
Planner may close without asking after showing the technical summary. REVISE or
REJECT can never be confirmed or force-closed. Any rerun of assessment,
integration, or architecture review invalidates prior acceptance.
