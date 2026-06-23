# Task Contract Reference

Task.md is the execution contract. The active Task.md is frozen by hash at
activation and must not be edited by the model during execution.

## Writing a Task.md

Every Task.md frontmatter MUST include:

```
id: TASK-XXX
type: task
title: ...
goal_id: GOAL-XXX      # required — which Goal this serves
plan_id: PLAN-XXX      # required — which Plan this belongs to
milestone_id: MS-XXX   # optional — which Milestone verifies this
```

These are not optional. A task without `goal_id` breaks the Goal→Plan→Task
hierarchy and the Milestone view. A task without `plan_id` is an orphan.

Structural home: 1-2 sentences explaining why this Task belongs under its
Goal and Plan. A Task without a mission-relevant home is probably hidden
planning work.

Objective: 1-2 sentences. What exactly gets done, stated as an outcome, not an
implementation recipe.

Scope: Exact work outcome. Small enough for one cycle.

Context: Planner explores ONCE, subagents read. Record known truth and
constraints, not a fake implementation recipe. Include:
  - Known surfaces: files, modules, commands, schemas, APIs, or runtime flows
    that are relevant.
  - Existing interfaces and invariants the implementation must respect.
  - Dependencies: crates/packages/services already available that should be
    used or avoided.
  - Likely integration points when known, plus the evidence needed to prove the
    new behavior is consumed on the main path.
  - Unknowns that were resolved before activation, or explicitly deferred with
    a reason.

  For new modules or public APIs, Planner MUST identify the expected consumer
  or runtime path. An exact file:line is ideal when known, but do not invent it.
  If the consumer/main path is unknown, the Task is not ready; create
  exploration/design work or request Architect/code-reality review first.

  Example:
    Known surfaces: crates/edr-agent/src/runner.rs, src/storage/
    Expected consumer: agent startup/runtime event loop consumes storage events
    Interface constraint: fn on_event(&mut self, event: StorageEvent) -> Result<()>
    Proof of wiring: command must trigger runtime path and show storage event handled
    Dependencies: serde, tokio::sync::RwLock (already in Cargo.toml)
  If you (Planner) skip Context, every subagent re-discovers it. That is waste.

Allowed / Forbidden Write: Default forbidden: `.aiwf/state/` `.aiwf/records/`.
Forbidden Write is mechanically enforced at write time.

Executor Requirements: State the outcome AND what the executor should self-verify.
The executor covers basic correctness (happy path, obvious edge cases). Be specific
enough that the executor knows the target but doesn't micromanage HOW.
  Good: "Replace SHA-256 with bcrypt. Self-verify: new passwords use bcrypt,
         old SHA-256 passwords still validate, login e2e passes."
  Bad: "Edit src/auth.py line 42."

Tester Requirements: Dimensions the executor did NOT cover. No overlap with
executor's self-verification. Tester adds value by going beyond happy path:
boundary values, error paths, concurrency, resource exhaustion, surprising
combinations. At least three distinct failure modes.
  Executor covers: happy path, basic correctness (specified above).
  Tester covers: boundary (empty, max, negative), error injection, concurrency.
  Good: "Boundary: empty password, 1MB password, null. Error: db connection
         refused, auth timeout. Concurrency: 100 simultaneous logins."

Reviewer Requirements: Minimum hard gates. Reviewer brings relational review.
  "Confirm scope/forbidden write. Verify Done When. Apply relational review."

Done When: Observable, indisputable proof. Pick the right proof level for this
task:

| Level | Meaning | How to verify | When to use |
|-------|---------|--------------|-------------|
| **Built** | struct/fn exists and compiles | grep for the symbol, `cargo build` | Internal refactors, utility functions, private helpers |
| **Wired** | call chain is reachable — the new code is actually called | `grep` the caller site, trace imports, verify the registration point calls it | New modules, new `pub` APIs, config wiring |
| **Running** | end-to-end executable — a real action produces the expected effect | `cargo run` + trigger the flow + observe the output | Subsystems, user-visible features, cross-module integration |

"Built" is the minimum for tasks that refactor internals.
"Wired" is required whenever Context lists a registration point.
"Running" is required whenever the task creates a user-visible behavior.

Every Done When item must state which level it targets. Every Wired or Running
item must include a verification command. The last Done When item is always the
highest applicable level.

Verification Commands: For each Wired or Running criterion, list the exact command that
proves the outcome or consumption path. Executor records the output of every command in evidence (use
`aiwf record evidence --command "<cmd> ::: <output>"` for each). Tester checks
evidence has output for every command — blank = executor didn't finish.
Reviewer spot-checks 1-2 commands by re-running them (the only defense against
fabricated evidence).
```
## Verification Commands
| 命令 | 期望输出 |
|------|---------|
| cargo build 2>&1 \| grep "warning:" \| wc -l | 0 |
| cargo test -p <crate> | 0 failures |
| grep <OLD_CONSTANT> <path>/ | 空 |
```
Executor records actual output for each command in evidence. Tester checks
the evidence, not the table.

Rollback Strategy: yes/no. yes for schema, directory layout, install, parser,
batch renames. When yes, include:
```
Rollback Strategy required: yes
Method: Git
Before work: inspect git status and git diff
Rollback: git restore for selected files; git reset only by human decision
```

Report Policy: `ask` default. `silent_until_done` only when user explicitly asks.

Dependencies: Tasks this must wait for.

## Dispatch — Judgment Framework

Don't read a table mechanically. Ask, in order:

1. Can this be implemented safely inline? If the code requires design judgment,
   exploration of impact, or craftsmanship — don't inline. Open executor.
2. Can this be tested safely inline? If a destructive mindset could find bugs
   you'd miss — don't inline. Open tester.
3. Can this be reviewed safely inline? If someone reading the full diff could
   spot unjustified complexity, missing connections, or interface problems
   you'd overlook — don't inline. Open reviewer.

File count is not a signal. A 20-file rename is trivial. A one-file new
abstraction deserves review. Pick the roles the change is worth.

## Dispatch — Reference Table

| Change nature | executor | tester | reviewer | rollback |
|---------------|----------|--------|----------|----------|
| Trivial (typo, comment, rename, config) | false | false | false | false |
| Simple (no new abstraction, low consumer impact) | false | true | false | false |
| Normal (new abstraction, shared utility, consumer impact) | true | true | true | false |
| Complex (public API, refactor, state machine) | true | true | true | true |

For simple tasks: pick ONE of tester or reviewer, not both.

### What each role brings

**executor** — Independent implementation. Full exploration of impact, best
quality within boundaries. Worth it when: new abstraction, design judgment
needed, shared utility, public API, refactoring.

**tester** — Independent testing. Destructive mindset, new tests against
objectives, multiple attack angles. Worth it when: change has meaningful
failure modes, public API, shared utility, cross-module impact.

**reviewer** — Independent relational review. Full-diff connected analysis,
prove justified, zero downgrade, interface shape. Worth it when: new
abstraction, consumers affected, public API, structural impact.

**rollback** — Git-based rollback plan. Worth it when: state schema, record
format, directory layout, install output, parser, batch rename, broad removal.

## Lifecycle

Normal path:
```
planner creates → planner activates → implement evidence →
test testing → review review → close → planner resumes
```

Failure path:
- Record the actual result honestly.
- Let Planner decide: revise, fix-loop, new Task, or ask human.
- Do not force-close unless human explicitly does it.

Runtime:
- `task close` closes the current active task only.
- `task force-close` is human-only.
- Active Task.md must remain unchanged after activation.

## Emergency

**Fix-loop exhausted**: `aiwf status` shows `fix-loop open` + `escalation_required=true`.
Stop. Tell the human: "Fix-loop exhausted after N attempts. Review scope,
consider `aiwf task force-close`."

**TUI / terminal corruption**: Tell the human: "Run `reset`."

**Force-close**: `aiwf task force-close` is human-only.

## Bad contract signs

- Allowed Write broader than needed.
- Structural home missing or copied from the title.
- Done When repeats the title.
- Done When proves an artifact exists but not the mission-relevant outcome.
- Tester Requirements only say "run tests."
- Executor and Tester test the same things — overlap waste. Executor covers
  happy path; Tester covers boundary, error, concurrency. No overlap.
- Executor Requirements don't specify what to self-verify — executor does
  bare minimum, Tester finds basic bugs that should've been caught round 1.
- Reviewer Requirements don't mention scope or forbidden paths.
- High-risk work has no rollback strategy.
- Context section missing — Planner explored it but didn't write it down,
  forcing every subagent to re-discover file paths, interfaces, and deps.
- Context claims an exact implementation path that Planner has not verified.
- Consumer/main path unknown for new code, but task activated anyway.
- Role opened for a change that doesn't deserve it (wasted dispatch).
- Role closed for a change that does deserve it (missed risk).
