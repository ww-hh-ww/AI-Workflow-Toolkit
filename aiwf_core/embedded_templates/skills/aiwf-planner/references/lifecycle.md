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
- Give the Agent exactly one Task ID. Add `USER_DELTA` only when needed. AIWF
  adds the current control-root Task.md path and assigned worktree without
  removing Planner context, then routes every project tool call to that worktree.
- Do not use `isolation: worktree`, call `EnterWorktree`, or copy changes
  between worktrees. The Task roles share the Plan worktree.
- `.aiwf` governance always comes from the control root. Plan worktrees do not
  carry an independent `.aiwf` working-tree copy; project code and tests come
  from the assigned Plan worktree.
- Task.md is the baseline. Add `USER_DELTA` only for an explicit user
  clarification Task.md does not contain. It must not change execution,
  boundaries, or acceptance. A material change requires human interrupt,
  write-back to the relevant MD, sync, critique, and reactivation.
  Pass it faithfully to every affected Task role when it is allowed.
- Do not add a Planner fallback, substitute method, acceptance change, or
  reinterpretation. The active role skill defines the rest of the prompt.

## SendMessage

Send a running Agent only new verified information that helps it avoid a wrong
path. State the fact, its source, and the needed adjustment. Do not repeat
Task.md, ask for progress, or ask a working Agent to record early.

Resume a completed Agent only when Claude Code can access it in the current
session or the resumed original session. Read the current fix-loop facts, then
write a concise repair or verification brief that names the confirmed finding
and source, affected expected behavior, what remains valid, and the focused
proof. Be specific about the problem and outcome while leaving implementation
judgment to the role Agent. Send the Task ID and this brief with `SendMessage`
once. If it is unavailable or fails, dispatch a new Agent with the same brief.
Once resumed, wait for its real return before starting the Task's next role.

Keep `USER_DELTA` separate from the brief. It is only an explicit user
clarification missing from Task.md, not a label for fix-loop evidence. Do not
repeat the full Task, proof, or earlier report in either message.

If the message would change execution, boundaries, or acceptance, do not send
it as an adjustment. Ask the user to interrupt, then revise and critique the
contract. Do not resume an Agent the user explicitly stopped.

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

Process each Plan as soon as its Agent returns. Do not wait for the other
parallel Plans before routing that Task to its next role.

## Findings And Repair

Verify a returned finding before acting. Route a compatible repair to the
right role. If the Plan or Task must change, explain why and ask whether to
interrupt.

Record each Reviewer observation decision with `aiwf record disposition`.
Do not leave a machine-recorded observation resolved only in conversation.
Read the complete Reviewer report, not only machine observations. Do not
silently discard a concrete finding. Fix it, disposition it when tracking is
needed, or explain why it is not applicable. In the Task closeout to the user,
briefly state what was fixed and any remaining deferred, accepted, or dismissed
finding with its reason. Suggestions and unverified concerns stay visible in
the report but do not need governance state.

For each pending observation:

- Read the finding and the relevant Task promise. Do not repeat Reviewer's code
  search, tests, or call-path analysis; check only enough evidence to route it.
- If the finding makes the current Task contract false, do not disposition it
  as non-blocking. Open a fix-loop with the observation, required repair, and
  verification.
- If the contract itself must change, ask the user whether to interrupt and
  replan.
- If the finding can be fixed safely in this cycle without changing
  responsibility or acceptance, fix and verify it now. Do not defer it merely
  to close the Task sooner.
- Otherwise record the appropriate disposition.

Before marking a finding `deferred`, tell the user what remains, its consequence,
why fixing it now is the wrong choice, and when it should return. Ask the user to
agree. Then give it a place Planner will read again.
If a downstream Task is known, write the finding and its source observation into
that Task. Otherwise add a short entry with its trigger to
`.aiwf/memory/notes/deferred-findings.md` and make sure the note is indexed in
`MEMORY.md`. Remove the finding from the note when it moves into a Task, is
resolved, accepted as a limitation, or dismissed. The source Task record keeps
the history.

For an out-of-Task issue affecting the main path, deployment, safety, data, or
user trust, ask whether to fix it now or defer it with a visible reason. Never
turn a finding into a silent pass.

Use inline repair only after Executor has worked once and the correction is
tiny, local, and fully understood. Record the repaired implementation; AIWF then
routes the fix-loop to verification. After Tester has worked once, a narrow
repair with an exact reproducer may be retested inline; higher-risk repairs go
back to Tester. Always record a fresh testing snapshot.

When status says `Planner decision`, do not use Reviewer observation
disposition. Read the returned report and run:

```text
aiwf fixloop status --task-id <TASK-ID>
```

If escalation blocks further Agents, show the user what failed and what still
needs verification. Ask the user to choose: continue with
`aiwf fixloop continue --task-id <TASK-ID>`, pause and replan with
`aiwf task interrupt <TASK-ID>`, or accept the unmet checks and close with
`aiwf task force-close <TASK-ID>`. These commands are human-only. After the
human continues, run `aiwf status --prompt` again and follow its route. Do not
resolve the loop until Testing passes against the current implementation.

If the Task was interrupted while its fix-loop was open, reactivate that same
Task and continue the loop; do not resolve an unfixed problem. If Git HEAD
changed while it was suspended, inspect the commits and ask the user. After
explicit approval, run `aiwf task activate <TASK-ID> --accept-head-change`.

- If the issue has been decided and its required evidence is recorded, run
  `aiwf fixloop resolve --task-id <TASK-ID> --source planner --resolution "<decision and evidence>"`.
- If implementation or testing still remains, run `aiwf fixloop open` with the
  correct route and exact remaining work, then follow status.
- If the Task contract must change, ask the user whether to interrupt it.

For an integration Task, do not repair an unchanged implementation merely
because Tester expected the Plan to already be in main. Verify the recorded
base merge and combined behavior on the same snapshot, record the narrow
testing correction inline, then resolve the loop. A missing or wrong
`MERGE_HEAD` still routes to implementation repair.

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
merge, run `aiwf plan integrate <PLAN-ID>`. This is stage 1/2: it prepares a
candidate against the latest base without merging into the base branch. Run the
Plan's integration checks against that exact candidate. Stage 2/2 is the later
`--status passed` or explicitly accepted `--status accepted_with_gaps` call.

Once the Plan's Tasks are terminal, Planner owns its Integration Stage. Normal
editing and Git remain available in the Plan worktree and, when needed for base
hygiene, through an explicit base path. AIWF may first return a soft integration
audit instead of a candidate. Classify tracked and untracked changes, ignored
assets, empty directory skeletons, generated output, and open Git operations as
local residue, deliverable assets, reproducible output, or unknown risk. Resolve
what matters and rerun the same command. Do not create a repair workflow merely
to clean the environment. Ignored and empty paths are advisory because Git
cannot decide whether the project needs them in the next clean checkout.

Planner may change files while resolving the audit or a conflict. That does not
violate the workflow; it makes any older candidate stale. Prepare again before
proof. Use ordinary merge, rebase, staging, and commits as the situation needs.
Do not destroy recovery data with `git reset --hard`, `git clean -f`, or
`git stash pop/drop/clear`; leave destructive disposition to the user and
prefer `git stash apply` when a stash is needed.

Before `--status passed`, ask whether the user wants `/aiwf-architect`. The user
chooses the slice and lenses. For several Plans, only include results already
present in this candidate through the integration branch. Architect reviews the exact candidate,
not separate branch tips. It reports; Planner presents the findings and the
user decides what to do. If a finding changes the candidate, classify the
repair by the same Integration Stage rule: resolve environment, generated, and
non-semantic work directly; create a Task in an appropriate open Plan only
when the repair changes behavior, interfaces, dependencies, or product meaning.
Then prepare and verify a fresh candidate. Architect remains optional and does
not replace integration proof.

After the user declines Architect, or its report is handled, record the expected
and observed results. Write `## Closure Calibration` in Plan.md with what the
Plan actually delivers. Add only a difference from the original Plan or a
remaining gap that future work must know. Keep it concise. Do not checkpoint
this edit separately.

When every promised outcome used for closure is met, run `--status passed`.
The command reads the Calibration, records its first paragraph as the machine
summary, immediately merges the passing candidate, closes the Plan, and
checkpoints governance.

When the candidate is verified but an original Plan outcome remains unmet, do
not relabel it passed and do not merge manually. Explain the observed result,
consequence, and alternatives. Only after the user explicitly accepts closing
with the limitation, run `--status accepted_with_gaps` with at least one
machine-readable `--known-gap` and an `--acceptance-reason` grounded in that
decision. Record an observed verification result for every command, including
mismatches. This merges the exact candidate and closes the Plan with
`closure.mode=accepted_with_gaps`. A gap that needs continued work belongs in a
new Plan after this one closes; otherwise keep this Plan open with
`aiwf plan hold <PLAN-ID>`.

If either accepted merge command is interrupted after the project merge, rerun
the same command with the same status, proof, gaps, and reason; it finishes
governance closure without merging again. If the user changes their mind, use
`aiwf plan hold <PLAN-ID>` instead.

Plan integration targets the Plan's recorded base branch. AIWF does not choose
`develop`, `main`, or another branch for the user and does not infer release
status from a branch name. The user decides which branch is the Plan base and
whether any later branch-to-branch merge should happen.

If preparation reports a conflict, classify it before creating a Task. When
resolution does not change project behavior, interfaces, dependencies, or
product meaning, resolve it directly in the Plan worktree with native editing and Git,
without dispatching roles or creating a repair workflow. Then rerun
the same `aiwf plan integrate <PLAN-ID>` command; AIWF recognizes the resolved
merge and prepares the candidate. Explain any meaningful choice or consequence
under Plan.md Closure Calibration. Only semantic conflicts become a
`kind=integration` Task. This classification is Planner judgment grounded in
the actual diff, not a filename or command-driven gate.

If an integration Task already exists, recheck the classification instead of
continuing mechanically. Keep it only for a semantic resolution. If it was
created before the diff was understood and has produced no governed work,
explain that and ask the user before cancelling it; then use the direct path.

If that preflight becomes stale before the integration Task activates, run
`aiwf plan integrate <PLAN-ID>` again. It may refresh around one pending or
suspended integration Task. Governance-only commits are adopted
automatically. Other Plan-branch commits appear in the integration audit;
inspect and disposition them, then rerun the same command. Recheck Task.md and
repeat both critique passes when a semantic integration Task's inputs change.

For several Plans, follow dependencies and integrate one at a time against the
moving base. Each next Plan candidate includes the latest integration branch. The user may
choose Architect for any candidate. Passing integration closes each Plan.

Do not modify a closed Plan or link new work to it. Create a new Plan instead.
