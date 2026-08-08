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
Use `kind=integration` only after `aiwf plan integrate <PLAN-ID>` reports a Git
conflict and Planner confirms that resolving it changes project behavior,
interfaces, dependencies, or product meaning. Non-semantic conflicts use the
Plan worktree and native Git directly and never create a Task or repair
workflow. For a semantic Task, state
the combined behavior that must survive, conflict surfaces, and integration
checks. Do not prescribe a line-by-line resolution.

Set `executor_required`, `tester_required`, and `reviewer_required` from the
work's real need. When true, the role must be dispatched. When false, the role
may be performed inline. First implementation requires Executor only when
`executor_required=true`; later repair may be inline when it is tiny and clear.

Before activation, inspect where the project keeps tests, fixtures, snapshots,
expected outputs, and validation harnesses.

- Leave `tester_write` empty when all likely writes use common test directories
  or recognizable test file names.
- If any required test asset belongs elsewhere, list narrow, verified path
  patterns in `tester_write`. A non-empty list is the complete whitelist for
  this Task, so include every test location the Tester may need.
- Do not add broad implementation directories or implementation files merely to
  avoid a write rejection. Precise co-located test patterns are valid. Inspect
  the project instead of guessing. If an unexpected location becomes necessary
  after activation, the Tester must return to Planner.

## Fixed Contract

Keep `## Fixed Contract` and its required `### Structural Home`,
`### Objective`, `### Contract Responsibility`, and `### Proof Standard`
headings exact. AIWF reads these headings to enforce activation and proof.

Every Task must say:

- Structural Home: why this Task belongs under its Goal and Plan, or milestone.
- Objective: the outcome, not a file-edit recipe.
- Contract Responsibility: the result this Task owns and must prove.
- Done When: observable criteria marked Built, Wired, or Running.
- Verification Commands: stable IDs plus exact commands and expected observable
  results for Wired and Running claims.
- Dispatch Decisions: which independent roles are worth using.

State each requirement once. Carry into Task.md the chosen direction and
constraints Executor needs, but keep the design history and detailed rationale
in the Plan. Do not repeat a hard requirement in Known Context, Open Judgment,
or a second delivery list.

Add these only when real:

- Forbidden Write for explicit user or project no-go paths.
- Rollback Strategy for schema, directory layout, install, parser, broad
  removal, or batch rename.
- Unsupported Cases when the chosen support boundary is intentional and known
  before failure.

Omit empty optional sections.

## Author The Proof Contract

The author owns proof quality; the activation check is only a last-resort
structural guard. Before writing a Verification Command, locate the real
script, selector, entry point, and runtime, and run or inspect enough of it to
know the command is usable. Do not write a guessed command and wait for the
Tester or validator to discover that it is shorthand, unavailable, or aimed at
the wrong suite. Write Expected as the observable meaning of success, not a
copied transcript or a promised count. If the command or observable cannot yet
be made concrete, keep the Task in planning and fix the contract first.

## Known Context

Known Context is the shared cold-start handoff for every role that will actually
participate, whether inline or independent. It should let each role reach the
real code and its first consequential judgment without repeating Planner's
exploration.

Derive it from those judgments, not from the volume of facts Planner learned:
where Executor must choose or preserve behavior, how Tester can observe failure
or a false pass, and what relationship or downstream effect Reviewer must
trace. Keep shared facts once. Do not require role headings or write a separate
manual for each role.

Use free bullets. There is no required bullet format. Record only verified
facts that help the next role start in the right place, reuse an established
conclusion, or avoid a likely wrong edit. Give each non-obvious fact a usable
source such as a file and symbol, command result, completed Task Calibration,
proof record, or user decision.

Useful facts may include:

- where to start: real paths, symbols, runtime entry points, tests, or commands;
- what is already established and where it was proved;
- what must remain true: consumer, interface, invariant, owner, main path,
  old-path expectation, and proof;
- what may mislead the next role: representative cases, environment traps,
  rejected dead ends worth remembering, and important Unknowns.

Do not include exploration history, directory inventories, pasted logs or
diffs, whole-file descriptions, repeated Goal or Plan text, or facts that do
not affect this Task. Do not repeat a completed Task's report; cite the useful
conclusion and its source. Omit facts the next role can get from one obvious
lookup unless the exact anchor prevents meaningful rediscovery. Keep rejected
approaches only when they prevent a likely repeated mistake.

These are anchors, not instructions. Do not list every function or choose local
implementation details for Executor. Do not invent facts to complete the
section. If consumer, invariant, owner, main path, or proof is important and
Unknown, the implementation Task is not ready.

When a Task crosses a boundary, include the smallest shared slice later roles
must not guess: Input, Output, Consumer, Invariant, Owner, Proof, and Basis.

Before activation, reread Known Context as each participating role. Every
bullet should help at least one of them locate the work, reuse a trustworthy
conclusion, avoid a real trap, or recognize an unresolved question. Remove the
rest.

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

Verification Commands are final proof, not a log of the development loop. Every
row must have a stable ID (`V-001`, `V-002`, ...). The ID is the machine identity
of the check; the command text is only the command to execute and display.
Commands must be directly executable in the declared runtime. Do not write
prose shorthand or unresolved setup into the command cell; put the runnable
command there and explain required environment setup in Known Context.
Changing this table changes the proof contract: interrupt and reactivate the
Task, then collect fresh results for the current IDs. Do not combine results
from the old table with the new one.
Before activation, check them against the project's real test runner and
scripts:

- each command proves a distinct observable claim;
- a selector really targets the named test instead of rerunning the full suite;
- targeted checks come first and each necessary full regression runs once at
  the end;
- several labels do not invoke the same underlying suite;
- runtime claims use the production path in the claimed runtime, not a copied
  implementation or a simulated environment.

When the Task must create a new script or harness, name the exact test file,
production entry, and runtime it must execute. Do not pretend an unbuilt command
already exists.

Executor leaves one concise implementation evidence record with git refs and a
strong self-check. Tester records one validation result for every required check
ID, containing the Task-owned expected result, observed result, verdict, and a
short basis.
Reviewer judges the contract, diff, callers, evidence, testing, and old paths.

Expected output should describe the observable meaning of success, not prescribe
a transcript. Tester decides whether the actual result satisfies it and records
`matched` or `mismatched`; Reviewer checks that judgment against the evidence.
The machine gate only checks check-ID coverage, current-snapshot ownership,
non-empty evidence or an explicit environment block, and valid verdict values.
It does not compare natural-language expected and observed text or infer a
semantic pass from non-empty output. Reviewer independently checks the Tester
verdict.

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
- Can Tester write the needed test assets without broadly opening implementation code?
- Do independent roles still have a real question to answer?
