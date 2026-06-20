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

Task Breakdown: 3-5 Tasks per Plan is typical. One deliverable each.

Risks + Validation Strategy.

## Task.md — Execution Contract

Objective: 1-2 sentences. What exactly gets done.

Scope: Exact work outcome. Small enough for one cycle.

Allowed / Forbidden Write: Default forbidden: `.aiwf/state/` `.aiwf/records/`.
Forbidden Write is mechanically enforced at write time.

Dispatch Decisions: Match effort to risk.
- Trivial (typo, comment, config): all false.
- Simple (single file, isolated): executor=false, tester=true, reviewer=false.
- Normal (multi-file, core logic): all true.
- Complex (API, refactor, state machine): all true + rollback=true.
See `task-contract.md` for detailed decision tables.

Executor Requirements: State the outcome.
  Good: "Replace SHA-256 with bcrypt. Don't break login."
  Bad: "Edit src/auth.py line 42."

Tester Requirements: What to validate, what mode.
  Good: "Verify bcrypt on new passwords, old passwords still validate, login e2e."

Reviewer Requirements: Minimum hard gates. Reviewer brings relational review.
  "Confirm scope/forbidden write. Verify Done When. Apply relational review."

Done When: Observable, indisputable. The standard all downstream roles work toward.

Rollback Strategy: yes/no. See `task-contract.md` for high-risk surface checklist.

Report Policy: `ask` default. `silent_until_done` only when user explicitly asks.

Dependencies: Tasks this must wait for.

## Milestone.md — Acceptance Gate

Purpose: What phase result is being proven?

Pass Standard: THE authoritative acceptance criteria. What flows must work
end-to-end? Each new capability consumed on the main path.
Concrete, observable, indisputable.

Covered Plans/Tasks.
