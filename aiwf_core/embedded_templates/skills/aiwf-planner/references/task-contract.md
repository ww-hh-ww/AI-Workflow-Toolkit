# Task Contract Reference

Task.md is the execution contract. The active Task.md is frozen by hash at
activation and must not be edited by the model during execution.

## Writing a Task.md

Objective: 1-2 sentences. What exactly gets done.

Scope: Exact work outcome. Small enough for one cycle.

Allowed / Forbidden Write: Default forbidden: `.aiwf/state/` `.aiwf/records/`.
Forbidden Write is mechanically enforced at write time.

Executor Requirements: State the outcome, not the edit location.
  Good: "Replace SHA-256 with bcrypt. Don't break login."
  Bad: "Edit src/auth.py line 42."

Tester Requirements: What to validate, what mode.
  Good: "Verify bcrypt on new passwords, old passwords still validate, login e2e."

Reviewer Requirements: Minimum hard gates. Reviewer brings relational review.
  "Confirm scope/forbidden write. Verify Done When. Apply relational review."

Done When: Observable, indisputable. The standard all downstream roles work toward.

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
- Done When repeats the title.
- Tester Requirements only say "run tests."
- Reviewer Requirements don't mention scope or forbidden paths.
- High-risk work has no rollback strategy.
- Role opened for a change that doesn't deserve it (wasted dispatch).
- Role closed for a change that does deserve it (missed risk).
