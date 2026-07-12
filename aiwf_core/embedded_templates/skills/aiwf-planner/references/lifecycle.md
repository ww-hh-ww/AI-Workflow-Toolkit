# Lifecycle

Use this as an orientation map. Follow `aiwf status --prompt` and the active
skill for exact next steps.

Main task loop:

1. `task create` — Planner writes the contract.
2. `task critique` — Planner runs activation critique twice.
3. Create or switch to one feature branch for the Plan. Start with a clean
   project worktree.
4. `task activate` — implementation may start only after the critique gate.
5. Executor implements and records the implementation snapshot.
6. Tester may add test assets, runs testing, and records the tested snapshot.
7. Reviewer reviews that exact snapshot and records review.
8. Planner decides each Reviewer observation. Record it with `aiwf record disposition`.
9. Cleanup happens before final review or close.
10. `task close` — checks snapshot freshness, creates the Task commit, and
   closes the active Task. The Stop hook prevents
   leaving a reviewed Task in the closing stage.
11. After all Plan Tasks close, ask the human to merge the Plan branch. Close
   the Plan only from the merged base branch.

Do not replace this loop with direct JSON edits or remembered state.
