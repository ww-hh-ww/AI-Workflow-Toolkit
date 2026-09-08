# Activation Critique

Use this before `aiwf task activate`. Correct the contract before implementation
starts. Do not implement project code here.

Run two passes.

## Pass 1: Check The Contract

Read the relevant Goal.md, Plan.md, Task.md, and Milestone.md. Use the memory
snapshot from `aiwf status --prompt` when it may change the design.

Ask whether Task.md is ready for its declared work, including an initial Experiment:

- Are the required Fixed Contract headings present at the exact levels defined
  in `task-contract.md`?
- Is the outcome clear, useful, and consistent with its Goal and Plan?
- Are responsibility, interfaces, invariants, consumers, main path, and old
  path grounded enough to execute the contract? If implementation depends on an
  empirical unknown, is its question and decision boundary explicit rather than
  presented as an established fact?
- Do Built, Wired, and Running describe the whole result without contradiction
  or repetition?
- Does Known Context contain reliable entry points, important facts, traps, and
  real unknowns? Remove exploration history, pasted output, broad code maps,
  and choices the Executor should make.
- Are dependencies and handoffs to other Tasks accurate?
- Are required Skills, MCP tools, and role capabilities named only when the
  contract really depends on them?
- Do Verification Commands provide a real baseline probe, or name the exact
  command that this Task must create? Is each row executable and reproducible in
  the declared runtime, with a stable ID, a distinct claim, and an observable
  result that lets Executor decide and record the construction obligation?
- Is the Task small enough to complete and prove, but broad enough to cover all
  relevant entry points and consumers?

Resolve missing, vague, guessed, or conflicting parts. Inspect the project when
needed. If the contract changes, edit the relevant MD and run `aiwf sync`.
Formal activation syncs again as a backstop.
This pass owns whether the proof is real; the activation check only catches
obvious structural defects and must not be treated as a command-design tool.

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
- Check Verification Command baselines against the real scripts and test runner. Confirm
  that selectors narrow the run, repeated full regressions are removed, and
  runtime tests exercise production code in the claimed runtime.
- Do not accept a command merely because it looks concrete. If its runtime,
  target, setup, or observable was not verified from the project, revise the
  Task instead of deferring Executor's construction evidence. Open an EXP only
  when the remaining issue is genuinely empirical and needs disposable
  full-project work.
- Challenge the weakest design assumption. When the Plan chose a technical
  method, compare it with the raw problem, representative inputs, and support
  boundary.

If reality changes execution, boundaries, interfaces, or proof, update the
relevant MD and run `aiwf sync` before recording this pass. Do not activate when
the promised outcome, scope, consumer, invariant, or proof obligation is guessed.
A bounded empirical question is not a guessed contract: activation may lead to
Experimenter first, with the main session consuming its evidence before assigning
dependent implementation to Executor in the same Task. If the conclusion would
invalidate that contract, return for revision rather than silently changing it.

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
