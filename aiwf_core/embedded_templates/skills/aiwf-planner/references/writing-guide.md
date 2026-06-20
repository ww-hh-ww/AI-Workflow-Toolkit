# Narrative Doc Writing Guide

## Core principle

Define WHAT and set the standard. Sub-agents decide HOW.
Clear enough they don't guess; open enough they use their intelligence.

- DON'T prescribe files or functions.
- DO state outcome, standard, and hard constraints.

## Goal.md — Capability

Intent: 1-2 sentences. What capability? Who benefits?
  Good: "Detect anomalous call patterns and alert."
  Bad: "Set up Elasticsearch pipeline." (that's a Plan)

Success Criteria: Observable behavior, not artifact existence.
  Good: "Agent with telemetry off flagged as degraded in 30s."

Non-goals: Explicitly exclude adjacent capabilities.

Context + Human Decisions: Why now? What needs human input?

## Plan.md — Technical Direction

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

See `task-contract.md` for the full writing guide, dispatch framework,
lifecycle, and emergency procedures.

## Milestone.md — Acceptance Gate

Purpose: What phase result is being proven?

Pass Standard: THE authoritative acceptance criteria. What flows must work
end-to-end? Each new capability consumed on the main path.
Concrete, observable, indisputable.

Covered Plans/Tasks.
