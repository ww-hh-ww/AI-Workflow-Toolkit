# Narrative Doc Writing Guide

## Core principle

Define the mission capability structure and proof standard. Sub-agents decide
implementation details. Clear enough they don't guess the mission direction;
open enough they use their intelligence.

**MD frontmatter is the single source of truth.** To change a node's title,
status, goal_id, plan_id, parent, or any structural field: **edit the .md
frontmatter, then `aiwf sync`.** No CLI rename/reassign/reparent commands
exist. `aiwf sync` compiles MD → JSON. If the JSON disagrees with MD, the
JSON is wrong.

- DON'T prescribe implementation recipes.
- DO state outcome, structural home, proof standard, and hard constraints.
- If a detail is unknown but necessary for safe execution, create exploration or
  design work before activating an implementation Task.

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

Intent: 1-2 sentences. What mission capability? Who benefits?
  Good: "Detect anomalous call patterns and alert."
  Bad: "Set up Elasticsearch pipeline." (that's a Plan)

Capability Model: what sub-capabilities make this Goal true? Name missing
pieces explicitly instead of hiding them in Tasks.

Success Criteria: Observable mission behavior, not artifact existence.
  Good: "Agent with telemetry off flagged as degraded in 30s."

Non-goals: Explicitly exclude adjacent capabilities.

Fit Notes: why this Goal belongs at this level of the tree. If this is really
a method, tool, module, or phase, move it to Plan/Task/Milestone.

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

Intent + Current Problems: Concrete pain points and the mission capability this
Plan advances.

Target Design — THE KEY SECTION:
- Mission mechanism: what operating loop makes the Goal true?
- Information model: what facts/state/evidence does the system rely on?
- Data/control flow: A → B → C, key interfaces at boundaries.
- Feedback loop and observability: how will wrong direction or failure surface?
- Risk burn-down order: which uncertainty must be proven early?
- Technology choices and why.
- Enough direction for Executor, not code.

Key Decisions: Trade-offs. Empty = you haven't thought hard enough.

Task Breakdown: 3-5 Tasks per Plan. One mission-relevant deliverable each.
Avoid tasks that merely create scaffolding unless they prove a risk or unblock
the main path.

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

Purpose: What stable mission slice is being proven?

Pass Standard: THE authoritative acceptance criteria. What flows must work
end-to-end? Each new capability consumed on the main path.
Concrete, observable, indisputable.

Scope Trace: covered Goals, Plans, Tasks, and capability claims. This is how
Architect `milestone-acceptance` knows what to verify.

Evidence Standard: what observable running-system evidence is enough for the
next Planner to trust the milestone.
