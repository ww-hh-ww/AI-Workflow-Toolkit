# Activation Critique

Use this before `aiwf task activate`. Correct the contract before implementation
starts. Do not implement project code here.

Run two passes.

## Pass 1: Check The Contract

Read the relevant Goal.md, Plan.md, Task.md, and Milestone.md. Use the memory
snapshot from `aiwf status --prompt` when it may change the design.

Ask whether Task.md is ready to hand to a new Executor:

- Are the required Fixed Contract headings present at the exact levels defined
  in `task-contract.md`?
- Is the outcome clear, useful, and consistent with its Goal and Plan?
- Are responsibility, interfaces, invariants, consumers, main path, and old
  path clear enough to implement without guessing?
- Do Built, Wired, and Running describe the whole result without contradiction
  or repetition?
- Does Known Context contain reliable entry points, important facts, traps, and
  real unknowns? Remove exploration history, pasted output, broad code maps,
  and choices the Executor should make.
- Are dependencies and handoffs to other Tasks accurate?
- Are required Skills, MCP tools, and role capabilities named only when the
  contract really depends on them?
- Do Verification Commands exist or name the exact command that this Task must
  create? Does each command prove a distinct claim with an expected observable
  result?
- Is the Task small enough to complete and prove, but broad enough to cover all
  relevant entry points and consumers?

Resolve missing, vague, guessed, or conflicting parts. Inspect the project when
needed. If the contract changes, edit the relevant MD and run `aiwf sync`.

## Pass 2: Check Against Reality

Reread the updated contract as claims to test, not truth to trust. Explore the
actual project with the best available native tools. Use text search, code
navigation, LSP, and focused file reads where they help.

- Trace real entry points, callers, consumers, data flow, and control flow.
- Check every main-path variant that the outcome must support.
- Check current interfaces, ownership, shared state, failure ownership, and
  dependency direction. Confirm module boundaries follow ownership and change,
  rather than Goal or Task names.
- Look for an old path, bypass, duplicate implementation, or unsupported
  runtime path that would make the Task appear complete while the product still
  behaves the old way.
- Check Verification Commands against the real scripts and test runner. Confirm
  that selectors narrow the run, repeated full regressions are removed, and
  runtime tests exercise production code in the claimed runtime.
- Challenge the weakest design assumption. When the Plan chose a technical
  method, compare it with the raw problem, representative inputs, and support
  boundary.

If reality changes execution, boundaries, interfaces, or proof, update the
relevant MD and run `aiwf sync` before recording this pass. If the main path,
consumer, invariant, or proof is still guessed, do not activate. Explore
further, revise the design, or ask the user.

## Before Recording

Confirm the project worktree is clean and the current branch belongs to this
Plan. If project changes already exist, inspect them and ask the user whether
to keep or discard them. Do not commit, stash, restore, or remove them without
that decision.

If the contract explicitly requires a named Skill, MCP, or tool, confirm the
assigned role can use it. Do not try to predict every possible runtime failure;
Executor must return when new reality breaks the contract.

A critique may correctly conclude that no MD change is needed. It still must be
based on a real check. At the end of each pass, briefly state what was checked,
the weakest assumption, whether the contract changed, and why it is ready or
not ready.

Only record a pass that you can defend:

```text
aiwf task critique <TASK-ID>
```

Do not record the critique or activate the Task while the contract is guessed,
contradictory, or out of date.
