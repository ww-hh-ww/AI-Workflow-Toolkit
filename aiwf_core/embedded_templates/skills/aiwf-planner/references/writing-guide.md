# Narrative Doc Writing Guide

## Core principle

Define WHAT and set the standard. Sub-agents decide HOW.
Clear enough they don't guess; open enough they use their intelligence.

**MD frontmatter is the single source of truth.** To change a node's title,
status, goal_id, plan_id, parent, or any structural field: **edit the .md
frontmatter, then `aiwf sync`.** No CLI rename/reassign/reparent commands
exist. `aiwf sync` compiles MD → JSON. If the JSON disagrees with MD, the
JSON is wrong.

- DON'T prescribe files or functions.
- DO state outcome, standard, and hard constraints.

## Every doc — required frontmatter

Every `.md` MUST have:

```yaml
---
id: <NODE-ID>
type: goal | plan | task | milestone
---
```

Without `id` and `type`, `aiwf sync` will flag an error and the node won't
appear in the TUI.

## Goal.md — Capability

Frontmatter:
```yaml
id: GOAL-XXX
type: goal
title: ...
status: open
parent_goal_id: GOAL-PARENT   # only for child goals
report_policy: ask            # ask or silent_until_done
```

Intent: 1-2 sentences. What capability? Who benefits?
  Good: "Detect anomalous call patterns and alert."
  Bad: "Set up Elasticsearch pipeline." (that's a Plan)

Success Criteria: Observable behavior, not artifact existence.
  Good: "Agent with telemetry off flagged as degraded in 30s."

Non-goals: Explicitly exclude adjacent capabilities.

Core Files (project start or structural change — not every cycle):
  - `src/<dir>/` — what capability this directory provides
  - Focus on the skeleton, not every file. A new engineer should know
    where to open first. Don't repeat what `tree` already shows.
  - Revisit when the structure changes meaningfully, not every task.

Context + Human Decisions: Why now? What needs human input?

## Plan.md — Technical Direction

Frontmatter:
```yaml
id: PLAN-XXX
type: plan
title: ...
status: open
goal_id: GOAL-XXX       # required
milestone_id: MS-XXX    # optional, set when linked
dependencies: []        # plan-level execution gates
report_policy: ask
```

Intent + Current Problems: Concrete pain points.

Target Design — THE KEY SECTION:
- Method: event-driven or polling? push or pull?
- Data flow: A → B → C, key interfaces at boundaries.
- Technology choices and why.
- Enough direction for Executor, not code.

Key Decisions: Trade-offs. Empty = you haven't thought hard enough.

Task Breakdown: 3-5 Tasks per Plan. One deliverable each.

Risks + Validation Strategy.

## Task.md

See `task-contract.md` for the full frontmatter, writing guide, dispatch
framework, lifecycle, and emergency procedures.

## Milestone.md — Acceptance Gate

Frontmatter:
```yaml
id: MS-XXX
type: milestone
title: ...
status: open
goal_id: GOAL-XXX
plan_ids: [PLAN-XXX, ...]
task_ids: [TASK-XXX, ...]
covered_goal_ids: [GOAL-XXX, ...]
integration_test_required: true
architecture_review_required: true
human_acceptance_required: true
verification_task_required: true
verification_task_id: TASK-XXX   # set when verification task is created
report_policy: ask
```

Purpose: What phase result is being proven?

Pass Standard: THE authoritative acceptance criteria. What flows must work
end-to-end? Each new capability consumed on the main path.
Concrete, observable, indisputable.

Covered Plans/Tasks.
