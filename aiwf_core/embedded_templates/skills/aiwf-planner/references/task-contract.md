# Task Contract Reference

Task.md is the stable meaning of one execution unit. Once activated it is
frozen; runtime facts go to machine records, and a material contract change
requires human interruption, revision, fresh critique, and reactivation.

Before writing it, read the owning Goal, Plan, relevant Milestone, completed
Task Calibrations, and project reality. Correct contradictions in planning
instead of asking a downstream role to guess.

Task.md is also the human's record of what was agreed, not an agent-only packet.
Use the user's working language for prose while retaining parsed headings and
IDs. A reader should understand the intended change and open decisions before
reading commands or code paths. Use the existing sections, not a second contract:

- Objective: explain the present problem and what will be different when done.
- Contract Responsibility: preserve agreed scope, important constraints, and
  explicit exclusions in project terms.
- Done When: describe recognizable results; keep Built/Wired/Running and V-*
  references as supporting labels rather than the substance of the promise.
- Dispatch Decisions: explain what fact would change the next action and why;
  role names alone do not communicate the decision.
- Known Context and Open Judgment: put technical anchors here and make unresolved
  choices explicit, including which need the human's input.

Do not turn the Task into an inventory of edits or commands. The human should
be able to spot an omitted requirement or a wrong assumption by reading it.

For example, a Done When clause can say: "[Running] 登录失效后，保存操作提示重新
登录，并保留未提交内容（V-003）." The matching V row supplies the exact command and
observed behavior to check. Neither the human-readable promise nor the runnable
probe replaces the other; keep exact symbols, paths, and commands where needed.

## Frontmatter

An implementation Task has a real `goal_id` and `plan_id`. A milestone
verification Task uses `kind=milestone_verification` and `milestone_id`.
`kind=integration` is reserved for semantic conflict resolution after Plan
integration identifies a real behavior, interface, dependency, or product
meaning conflict.

Set only these workflow role requirements:

- `executor_required`: stable project changes require an independent Executor;
- `reviewer_required`: acceptance benefits from independent judgment.

When false, Planner may perform the same responsibility inline. Experimenter has
no requirement boolean because it is orthogonal: open an EXP record when a real
empirical unknown exists, before or after implementation. It receives its own
disposable full-project worktree and never writes the stable Task worktree.

## Fixed Contract

Keep `## Fixed Contract` and its `### Structural Home`, `### Objective`,
`### Contract Responsibility`, and `### Proof Standard` headings exact. AIWF
parses them for activation and evidence gates.

Every Task states:

- why it belongs under this Goal and Plan;
- the observable outcome, not a file-edit recipe;
- the result it owns and must prove;
- Done When clauses tagged Built, Wired, or Running;
- stable V-* rows with runnable baseline probes and expected observables;
- main-session dispatch decisions for implementation, optional experiments,
  and review.

Add Forbidden Write, Rollback Strategy, or Unsupported Cases only when they are
real. Omit empty optional sections. Keep design history in Plan.md and state
each hard requirement once.

## V-* Is Construction Evidence

Planner owns the quality of the proof contract; Executor owns executing it for
the stable candidate. Do not write guessed commands and defer discovery to a
later role.

Every Verification Command row needs:

- a stable ID (`V-001`, `V-002`, ...);
- a command directly runnable in the declared environment, or the exact command
  this Task is responsible for creating;
- an expected observable that expresses semantic success rather than a copied
  transcript or exit code.

Before activation, verify scripts, selectors, entrypoints, setup, and runtime.
Target distinct obligations: focused probes first, each necessary full
regression once. Runtime claims must exercise the real production path.

Executor records one result for every V-* and active FIX-* ID with the actual
observation, verdict, basis, and `executed_command` when it used an equivalent
probe. `matched`, `mismatched`, and `blocked` are honest construction states;
only complete matched evidence can reach Reviewer. A new implementation snapshot
replaces the old V evidence and invalidates Review.

The machine gate checks stable identities, current-snapshot ownership, evidence
presence, and verdict shape. Reviewer checks whether the observation actually
proves the expected meaning.

## Experiments

Do not make Experimenter a mandatory phase or a second owner for V-*.
Within this Task, every EXP is subordinate empirical work: name the Task
decision it informs, and return its evidence to that decision. An EXP ID
identifies an investigation, not a separate acceptance contract.

Open an Experiment only when a decision depends on an empirical fact that
ordinary planning inspection, Executor implementation work, required V-* runs,
or Reviewer reasoning cannot answer cleanly. Good questions are specific and
decision-relevant: actual API behavior, environment constraints, performance
baseline, competing mechanism viability, a suspected bypass, or a runtime
failure surface requiring disposable instrumentation.

Each EXP record binds:

- exactly one active owning Task;
- an immutable subject commit derived from that Task at execution time;
- a question and optional falsifiable hypothesis;
- a disposable full-project worktree;
- commands/operations, concrete observations, conclusion, experiment snapshot,
  and optional promotion candidates.

An Experiment may occur before Executor, after Executor, both, or not at all.
Its conclusion describes the question or hypothesis; it does not accept or
reject the Task. Reviewer/Planner decides the consequence. If an experimental
asset should become maintained project code, Executor recreates or promotes it
in the stable worktree and records fresh construction evidence.
The immutable experiment snapshot already retains experimental assets.

Planning an experiment requires only its question, purpose, and decision path in
this Task.md, not an EXP record or Git ref. Task activation binds the execution
baseline; an actual pre-implementation EXP inherits it. A post-implementation
EXP instead uses this Task's current implementation snapshot. Neither becomes
an independent Plan-level work item.

## Known Context

Known Context is the cold-start handoff. Include only verified facts that help a
participating role reach its first consequential judgment:

- real paths, symbols, entrypoints, callers, consumers, tests, or commands;
- established decisions and where they were proved;
- invariants, owners, interfaces, main paths, and old-path expectations;
- environment traps, likely false paths, and important unresolved facts.

Use concise source-backed bullets. Do not paste logs, inventories, whole-file
summaries, exploration history, repeated Goal/Plan text, or implementation
recipes. Unknown consumer, invariant, owner, main path, or baseline proof means
the Task is not ready.

For a crossed boundary, preserve the smallest slice later roles must not guess:
Input, Output, Consumer, Invariant, Owner, Proof, and Basis.

## Open Judgment

Leave useful decisions open without scripting answers:

- Executor: which local implementation choice requires code-based judgment?
- Experimenter: if an EXP is already known to be needed, what observation would
  decide its question?
- Reviewer: which relationship, semantic change, old path, or complexity needs
  independent doubt?

Do not invent an Experiment question merely to populate this section.

## Proof Levels

| Level | Meaning | Use for |
|-------|---------|---------|
| Built | code exists and compiles | private helpers and internal refactors |
| Wired | the intended caller or consumer uses it | APIs, config, registration |
| Running | a real action produces the result | user behavior and cross-component flows |

One easy case does not prove broad support. Name representative cases in Plan
or Task when the claim needs them.

## Dispatch Decisions

Describe the meaningful decision points and their allowed successor paths in
Task.md. The stable main session evaluates them from current records and role
reports; child roles supply facts but do not choose or dispatch their successor.

Ask:

1. Does stable implementation need meaningful code exploration, design, or
   impact tracing? Require Executor.
2. Does acceptance need independent relational/structural judgment? Require
   Reviewer.
3. Is there a concrete empirical unknown whose apparatus should be disposable?
   Open an Experiment; do not add a role boolean.

When both post-construction paths are legitimate, declare the distinction rather
than forcing one global sequence:

```text
Executor -> Reviewer
Executor -> Experimenter -> Reviewer
```

AIWF exposes both paths and enforces their mechanical prerequisites. It does not
infer the semantic branch from universal experiment categories.

Role booleans alone are not a dispatch decision. State what returned fact matters
and which allowed path the main session should select from it. Do not enumerate
imaginary branches or preselect an experimental conclusion. Keep the question
and apparatus in the EXP record; Task.md holds why that knowledge matters.

File count is not the deciding signal.

## Failure and close

Executor mismatches remain Executor work. Experiment conclusions remain facts.
Reviewer converts facts and code findings into `accepted`, `needs_change`,
`needs_experiment`, or `rejected`. Contract or user decisions return to Planner.

Before close, Planner dispositions Reviewer observations and writes Closure
Calibration with the actual outcome. `task interrupt`, `task force-close`,
`task restore`, `task reopen`, and escalated `fixloop continue` remain human-only.

## Quality check

- Can Executor find the stable main path and own all V evidence?
- Are runtime claims proved through real consumers rather than artifact existence?
- Are shared interfaces, invariants, old paths, and failure ownership visible?
- Is every proposed Experiment a real unknown rather than deferred execution?
- Does Reviewer still have a meaningful whole-change judgment?
