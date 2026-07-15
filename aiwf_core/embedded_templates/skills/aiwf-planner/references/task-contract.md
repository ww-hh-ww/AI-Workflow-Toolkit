# Task Contract Reference

Task.md is the execution contract. Once activated, it is frozen and the model
must not edit it.

Before writing Task.md, read its owning Goal, parent Plan, and any completed
Task Calibration it depends on. Carry forward the capability boundary,
technical direction, shared constraints, Task order, and proof. If they conflict
with each other or project reality, correct the planning first.

## Frontmatter

An implementation Task needs a real `goal_id` and `plan_id`. A milestone
verification Task uses `kind=milestone_verification` and `milestone_id` instead.

Set `executor_required`, `tester_required`, and `reviewer_required` from the
work's real need. When true, the role must be dispatched. When false, the role
may be performed inline. First implementation requires Executor only when
`executor_required=true`; later repair may be inline when it is tiny and clear.

## Fixed Contract

Every Task must say:

- Structural Home: why this Task belongs under its Goal and Plan, or milestone.
- Objective: the outcome, not a file-edit recipe.
- Contract Responsibility: the result this Task owns and must prove.
- Done When: observable criteria marked Built, Wired, or Running.
- Verification Commands: exact commands and expected observable results for
  Wired and Running claims.
- Dispatch Decisions: which independent roles are worth using.

Add these only when real:

- Forbidden Write for explicit user or project no-go paths.
- Tester Write when tests may be written outside obvious `tests/` or `test/`
  locations.
- Rollback Strategy for schema, directory layout, install, parser, broad
  removal, or batch rename.
- Unsupported Cases when the chosen support boundary is intentional and known
  before failure.

Omit empty optional sections.

## Known Context

Use free bullets. Record only verified facts that help the next role start in
the right place or avoid a likely wrong edit.

Useful facts may include:

- real files, symbols, commands, schemas, fixtures, and runtime entry points;
- expected consumer and main path;
- interfaces, invariants, data shape, state, permissions, IDs, timestamps, and
  error semantics;
- integration, registration, config, install, deployment, CLI, help, or
  generated surfaces needed to prove wiring;
- representative inputs, difficult cases, platform or environment traps;
- old paths, bypasses, duplicate mechanisms, and compatibility paths;
- nearby patterns, dependencies, or helpers worth reusing;
- important Unknowns and what would resolve them.

These are anchors, not instructions. Do not list every function. Do not invent
facts to complete the section. If consumer, invariant, owner, main path, or
proof is important and Unknown, the implementation Task is not ready.

When a Task crosses a boundary, include the smallest shared slice later roles
must not guess: Input, Output, Consumer, Invariant, Owner, Proof, and Basis.

## Open Judgment

Leave room for independent roles to think. Write only useful questions:

- Executor: what local implementation choice needs code-based judgment?
- Tester: how could the promised behavior fail or false-pass?
- Reviewer: what connection, semantic change, old path, or complexity should be
  doubted?

Omit a role's questions when there is no meaningful open judgment. Do not
script the answer.

## Proof

| Level | Meaning | Use for |
|-------|---------|---------|
| Built | code exists and compiles | private helpers and internal refactors |
| Wired | expected caller or consumer uses it | APIs, modules, config, registration |
| Running | a real action produces the result | user behavior and cross-component flows |

One easy case does not prove a broad support claim. Verification must cover the
representative cases named by the Plan and the Task.

Executor leaves one concise implementation evidence record with git refs and a
strong self-check. Tester records one validation result containing every exact
required command, expected result, observed result, and match decision.
Reviewer judges the contract, diff, callers, evidence, testing, and old paths.

## Dispatch

Ask:

1. Does implementation need code exploration, design judgment, or impact
   tracing? If yes, require Executor.
2. Could independent testing find meaningful failure modes? If yes, require
   Tester.
3. Could relational review catch missing wiring, interface drift, or unjustified
   complexity? If yes, require Reviewer.

File count is not the deciding signal.

## Failure And Close

Record failures when found. Confirmed implementation defects route to Executor.
Contract or user decisions return to Planner. Do not soften a failure into a
pass.

Before close, Planner writes Closure Calibration with what actually happened.
`task interrupt` and `task force-close` remain human-only.

## Quality Check

- Is the responsibility broad enough to justify the real change?
- Can Executor find the main path without being told how to code?
- Do commands prove consumption or behavior rather than artifact existence?
- Are shared interfaces and old paths visible where they matter?
- Do independent roles still have a real question to answer?
