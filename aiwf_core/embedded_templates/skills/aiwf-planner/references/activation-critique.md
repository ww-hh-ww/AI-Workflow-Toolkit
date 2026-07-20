# Activation Critique

Use this before `aiwf task activate`. This is critic mode, not author mode.
Its job is to correct the governance files before implementation starts.

Run two passes. Each pass asks the same question:

> What would make this Task false or useless even if completed?

Pass 2 must not copy Pass 1. Re-check the weakest assumption from Pass 1 from
a different angle. When the Plan commits to a technical method, compare that
method with the raw problem, representative inputs, and support boundary. Ask
whether another mechanism fits the problem more directly.

Critical reread before activation. Reread the relevant Goal.md, Plan.md,
Task.md, and Milestone.md as claims to test, not truth to trust. Look for
missing proof, guessed facts, vague handoff, placeholder text, mismatched
boundaries, hidden old paths, and unresolved Unknowns. Do not defend the plan;
try to break it.

## Required Actions

1. Extract what the relevant Goal.md, Plan.md, Task.md, and Milestone.md claim.
2. Use the `Planner memory root` printed by `aiwf status --prompt`. Read
   `project-facts.md` and scan `MEMORY.md` there for facts that may change those
   claims.
3. Explore code reality with `rg` and file reads. Do not rely on memory or the
   governance files.
4. If the contract explicitly requires a named Skill, MCP, or tool, confirm the
   assigned role can use it. Do not try to predict every possible runtime
   failure; Executor must return when new reality breaks the contract.
5. Compare the governance claims against code reality. Check main path,
   consumer, invariant, proof, runtime entrypoints, and old
   path or bypass risk.
   For structural work, check whether module boundaries follow ownership and
   change rather than Goal or Task names. Trace dependency direction and who
   owns shared state and failures.
6. Reread Known Context as Executor's cold start. Keep concise, source-backed
   conclusions and useful code anchors. Remove exploration history, pasted
   output, broad code maps, and local choices that Executor should make.
7. Check Verification Commands against the real scripts and test runner.
   Confirm that selectors narrow the run, commands prove different claims, a
   full regression is not repeated, and runtime tests exercise production code
   in the claimed runtime. If the Task will create a command, verify the runner
   syntax and name the exact target it must execute.
8. If a conclusion changes execution, boundaries, or acceptance, write it into
   the relevant MD and run `aiwf sync` before recording the critique. If it is
   not written back, do not record the critique or activate the Task.
9. If the main path, consumer, invariant, or proof is still guessed, do not
   activate. Create exploration/design work or ask the user.
10. If a chosen technical method has no source-backed basis or was never
   compared against the raw problem, return to Plan formation. Use independent
   option exploration before recording another critique pass.
11. Confirm the project worktree is clean and the current branch is the feature
   branch for this Plan. If project changes already exist, inspect them and ask
   the user whether to keep or discard them. Do not commit, stash, restore, or
   remove them without that decision. Commit kept changes to the Plan branch,
   then activate from that clean baseline. Do not start a Task on main, master,
   trunk, detached HEAD, or a branch already bound to another Plan.

## Boundary

This step must read enough code to judge the design contract. Read as Planner:
trace callers, inspect entrypoints, follow data/control flow, check consumers,
and compare the intended structure with the real one.

It may revise governance MD and run `aiwf sync`.

It must not implement project behavior, edit project source, rewrite tests to
fit the Task, or start solving the engineering problem. If reality shows the
contract is wrong, fix the governance MD and sync. If reality is still unclear,
create exploration/design work or ask the user.

Do not fill a fixed output form. At the end of each pass, briefly state what
reality was checked, the weakest assumption, whether the contract changed, and
whether it can be defended. Only after a pass concludes that activation is
honest, run:

```text
aiwf task critique <TASK-ID>
```

Do not record a critique pass for a guessed or broken contract.
