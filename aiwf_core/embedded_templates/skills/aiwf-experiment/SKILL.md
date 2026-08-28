---
name: aiwf-experiment
description: Resolve an explicit empirical unknown through a disposable full-project experiment without changing the stable Task or Plan candidate.
---

# AIWF Experiment

Experimenter learns about reality. It is an orthogonal capability, not a phase
between Executor and Reviewer and not a replacement for Executor self-checks.

## Open and start

An Experiment needs one falsifiable or decision-relevant question, exactly one
Task or Plan scope, and an immutable subject commit.

```text
aiwf experiment open EXP-001 --task-id <TASK-ID> \
  --question "<unknown fact>" --hypothesis "<optional prediction>"
aiwf experiment start EXP-001
```

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
Reviewer or Planner decides what the facts mean. If an asset should survive,
Executor implements or promotes it in the stable worktree and records fresh V
evidence.
