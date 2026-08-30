---
name: aiwf-experiment
description: Resolve an explicit empirical unknown through a disposable full-project experiment without changing the stable Task or Plan candidate.
---

# AIWF Experiment

Experimenter learns about reality. It is an orthogonal capability, not a phase
between Executor and Reviewer and not a replacement for Executor self-checks.

## Enter at the recorded state

An Experiment needs one falsifiable or decision-relevant question, exactly one
Task or Plan scope, and an immutable subject commit.

First run `aiwf experiment show <EXP-ID>` when the EXP already exists. Follow
its state instead of replaying the whole lifecycle:

- missing: the stable main session opens it when the current Task.md dispatch
  decision selects Experimenter, then starts it;
- `open`: run `aiwf experiment start <EXP-ID>` once;
- `running`: dispatch or resume Experimenter; do not reopen or restart it;
- `recorded`: the stable main session runs `aiwf experiment finish <EXP-ID>`;
- `closed`: Planner or Reviewer consumes the immutable evidence.

When the main session is following a declared question, the missing-state
commands are:

```text
aiwf experiment open EXP-001 --task-id <TASK-ID> \
  --question "<unknown fact>" --hypothesis "<optional prediction>"
aiwf experiment start EXP-001
```

Reviewer `needs_experiment` already creates an `open` post-implementation EXP.
Do not run `open` again in that path.

For post-implementation work, `implementation_ref` is an AIWF hidden snapshot,
not necessarily the Plan branch HEAD. `candidate_tree_status=matched` in Task
proof is the freshness rule; a different HEAD and dirty status relative to it
are expected. Never fast-forward, checkout, merge, or commit the snapshot to
make the refs equal.

Use `--plan-id` for pre-Task planning research. Pass `--subject-ref` when the
scope has no recorded stable ref. The start command creates a detached,
full-project worktree. Dispatch `aiwf-experimenter` with exactly the EXP ID; AIWF
binds it to that worktree.

Do not create an Experiment when ordinary source inspection, implementation
diagnosis, a required V-* run, or Reviewer code reasoning can answer the issue.

## Evidence lifecycle

Experimenter may change any project file inside its disposable worktree to build
a reproducer, prototype, benchmark, fixture, fault injection, or measurement. It
must not change the stable Task/Plan worktree or make acceptance decisions.

It records an immutable experiment snapshot plus concise evidence:

```text
aiwf experiment record EXP-001 --conclusion supported|falsified|inconclusive \
  --summary "<decision-relevant fact>" \
  --command "<what was run>" \
  --observation "<concrete observed result>" \
  --promotion-candidate "<asset worth considering>"
```

`supported` and `falsified` describe the hypothesis, not acceptance of the
Task. `inconclusive` must say what prevented a decision. A promotion candidate
is only a recommendation; it does not move files into stable reality.

After Experimenter returns, the main session runs:

```text
aiwf experiment finish EXP-001
aiwf status --prompt
```

Finish removes the disposable worktree but retains the subject ref, experiment
snapshot ref, commands, observations, conclusion, and promotion candidates.
The stable main session follows Task.md dispatch after the evidence returns;
Reviewer or Planner decides what the facts mean within its own authority. If an asset should survive,
Executor implements or promotes it in the stable worktree and records fresh V
evidence.

For Plan-scoped or pre-implementation evidence, Planner must read
`aiwf experiment show <EXP-ID>` and record one meaning-level decision:

```text
aiwf experiment disposition <EXP-ID> \
  --decision proceed|replan|no_action|promote --reason "<why>"
```

For a Task-scoped `replan`, ask the user to interrupt the active Task before
recording the disposition; this prevents an invalid contract from routing into
Executor. Other decisions do not rewrite Task.md.

Post-implementation evidence needs no extra Planner disposition; Reviewer
consumes it as part of acceptance judgment.
