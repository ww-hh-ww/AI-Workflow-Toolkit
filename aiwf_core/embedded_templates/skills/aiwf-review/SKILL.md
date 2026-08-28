---
name: aiwf-review
description: Route or perform Reviewer judgment over the stable Task candidate, Executor evidence, and relevant experiments.
---

# AIWF Review

Reviewer judges whether the complete change is trustworthy. It neither owns
production changes nor uses Experiment as a generic request for more testing.

## Start

Run `aiwf task proof <TASK-ID>` and read Task.md. Review starts only when:

- the current stable worktree matches `implementation_ref`;
- every required V-* and FIX-* row has complete Executor construction evidence;
- every experiment against the current implementation is recorded and its
  disposable worktree has been removed.

When `reviewer_required=true`, dispatch `aiwf-reviewer` with exactly the Task ID
and any explicit user clarification absent from Task.md. Otherwise make the same
judgment inline. Do not reuse Executor or Experimenter as Reviewer.

## Verdicts

- `accepted`: the current `implementation_ref` satisfies the Task and is
  structurally worth accepting.
- `needs_change`: a concrete repairable defect exists in stable reality. Name
  the blocker; this routes back to Executor.
- `needs_experiment`: acceptance depends on one important empirical fact that
  current code, construction evidence, and existing experiments do not answer.
  Provide a new EXP ID, precise question, and optional hypothesis.
- `rejected`: the candidate is fundamentally inconsistent with the contract or
  its intended structural home.

Do not use `needs_experiment` for a missing V-* result, a code defect, vague
unease, or work Executor should have completed.

## Record

```text
aiwf record review --task-id <TASK-ID> --result accepted \
  --summary "<why the complete story holds>" \
  --cleanup-status fresh --structure-status sound

aiwf record review --task-id <TASK-ID> --result needs_change \
  --summary "<judgment>" --blocker "<specific defect>"

aiwf record review --task-id <TASK-ID> --result needs_experiment \
  --summary "<why judgment depends on reality>" \
  --experiment-id EXP-002 --experiment-question "<unknown>" \
  --experiment-hypothesis "<optional prediction>"
```

Record adversarial observations with
`severity:::kind:::message`. Critical/high unresolved observations cannot be
accepted. After recording, return the Review report and let Planner disposition
observations and perform closure calibration.
