# Lifecycle

Use this before activating or dispatching a Task, running Plans in parallel,
routing a finding, preparing the next Task, or closing a Plan. Run
`aiwf status --prompt` and follow the active skill for role-specific steps.

## Task Loop

1. `aiwf task create` creates the Task; Planner writes its contract.
2. Planner runs two real passes and records each defensible pass with
   `aiwf task critique`.
3. From the control root, run
   `aiwf plan bind-worktree <PLAN-ID> --create`. It creates or reuses the
   Plan's persistent worktree.
4. `aiwf task activate` activates one Task for that Plan.
5. Executor implements and records the implementation snapshot.
6. Tester may add test assets, tests the result, and records the tested snapshot.
7. Reviewer reviews that tested snapshot and records review.
8. Planner records a decision for every finding and writes Closure Calibration.
9. Complete any required repair and cleanup before final acceptance.
10. `aiwf task close` checks freshness, creates the Task commit, and closes it.

Do not replace this loop with direct JSON edits or remembered state.

## Task Role Dispatch

This section applies to Executor, Tester, and Reviewer. Explorer, Architect, and
Critic use their own prompts.

- Read the complete Task.md and `aiwf task proof <TASK-ID>` before dispatch.
- Give the Agent exactly one Task ID, the Task.md path, and the assigned
  worktree. Dispatch it from this Planner session. AIWF routes its relative
  file, search, and Bash tools to that worktree on every call.
- Do not use `isolation: worktree`, call `EnterWorktree`, or copy changes
  between worktrees. The Task roles share the Plan worktree.
- Task.md is the baseline. Add `USER_DELTA` only for an explicit user
  requirement Task.md does not contain. Pass it faithfully to every affected
  Task role.
- Do not add a Planner fallback, substitute method, acceptance change, or
  reinterpretation. The active role skill defines the rest of the prompt.

## Parallel Plans

One Planner owns governance from the control root. Every Plan worktree is a peer;
the control root is not a Plan worktree. Tasks inside one Plan remain sequential.
Plans may run together only when separate worktrees and the design make them
independent. Each Plan must be implementable, testable, and reviewable on its
own, with a clear merge order and combined proof.

Planner does not switch worktrees to manage Task roles. Use the exact Task ID
and assigned worktree for every dispatch or Task command. When several Tasks
are active, `aiwf status --prompt` shows all Plan worktrees and marks the one
matching the current directory.

Before parallel activation, read both Plans and relevant code. Check:

- responsibilities and shared files;
- interfaces, data/control flow, and shared state;
- runtime, deployment, and integration paths;
- merge order and combined proof.

Different filenames do not prove independence. If one Plan needs another's
output or behavior, run:

```text
aiwf plan dep add <PLAN-ID> <DEPENDENCY-PLAN-ID>
```

Merge the prerequisite first. If Plans change the same responsibility or
shared mechanism, change their boundary or run them in sequence.

Create or reuse each Plan worktree from the control root:

```text
aiwf plan bind-worktree <PLAN-ID> --create
```

The command is idempotent and uses a stable path and branch. To bind a worktree
the user already created, pass its path without `--create`. A new worktree
omits uncommitted project changes; resolve those with the user first.

Keep parallel Plan records separate. After they return, choose merge order,
inspect the merged change, and run integration proof.

## Findings And Repair

Verify a returned finding before acting. Route a compatible repair to the
right role. If the Plan or Task must change, explain why and ask whether to
interrupt.

Record each Reviewer observation decision with `aiwf record disposition`.
Do not leave a machine-recorded observation resolved only in conversation.

For an out-of-Task issue affecting the main path, deployment, safety, data, or
user trust, ask whether to fix it now or defer it with a visible reason. Never
turn a finding into a silent pass.

Use inline repair only after Executor has worked once and the correction is
tiny, local, and fully understood. Otherwise dispatch Executor again.

## After A Task

Before the next Task, read the Plan, completed Task Calibration, review, and
proof. Compare the actual result with the Plan and remaining Task assumptions.

If responsibility, connections, shared behavior, or the main path changed,
correct the Plan and run `aiwf sync`. Keep only memory future planning needs.

## Close Out A Plan

When no Tasks remain, read the Plan and Task Calibrations. Confirm the parts
work together on the real main path. Inspect the cumulative Git diff when
needed, and require integration evidence for the Plan, not only separate Tasks.

Tell the user what the Plan now delivers and any remaining gap. Ask whether to
add another Task, leave the Plan open, or merge it. Do not merge before the user
chooses.

If the user leaves it open, run:

```text
aiwf plan hold <PLAN-ID>
```

Do not ask again while the Plan result is unchanged. If the user chooses to
merge, follow the dependency order, verify the integrated result on the base
branch, then run:

```text
aiwf plan close --summary "<what the Plan delivered>"
```

Do not modify a closed Plan or link new work to it. Create a new Plan instead.
