---
name: aiwf-review
description: Route or perform Reviewer judgment over the stable Task candidate, Executor evidence, and relevant experiments.
---

# AIWF Review

Reviewer judges whether the complete change is trustworthy. It neither owns
production changes nor uses Experiment as a generic request for more testing.

## Start

Run `aiwf task proof <TASK-ID>` and read Task.md. Review starts only when:

- Task proof reports `snapshot_binding.candidate_tree_status=matched`;
- every required V-* and FIX-* row has complete Executor construction evidence;
- every experiment against the current implementation is recorded and its
disposable worktree has been removed.

`implementation_ref` is an AIWF hidden snapshot. Branch HEAD normally remains
at the Task origin and Git may show the candidate as uncommitted. Neither is a
freshness failure when the project tree is `matched`; never move HEAD to make
the commit IDs equal.

On Codex only, the stable main task may perform a
permission-bearing freshness preflight that a fixed-sandbox Reviewer child cannot
repeat. When the child sees `unavailable`, it may continue only from a dispatch
packet naming the exact current `implementation_ref`, equal non-empty
`implementation_tree` and `candidate_tree`, and
`candidate_tree_status=matched`. This delegates only the mechanical tree read;
Reviewer still owns the complete-story judgment. Never treat bare `unavailable`
or `changed` as matched.

When `reviewer_required=true`, dispatch `aiwf-reviewer` with one Task ID,
necessary verified repair context, the Codex freshness packet when applicable,
and any explicit user clarification absent from Task.md. Do not prescribe the
verdict or duplicate the contract. Otherwise make the same
judgment inline. Do not reuse Executor or Experimenter as Reviewer.

Do not stop at the first defect: continue across the remaining independent
contract, evidence, structural, caller, and boundary paths and return the
fullest actionable finding set in one pass, stopping early only when stale or
inaccessible state invalidates further judgment. Group symptoms with a shared
root cause, but still inspect independent paths and disclose unexamined scope.

## Verdicts

- `accepted`: the current `implementation_ref` satisfies the Task and the whole
  Task story is complete. If the report says any required link remains
  incomplete, use the corresponding non-accepted verdict instead.
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
  --story-complete \
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
accepted. `--story-complete` is the Reviewer judgment represented mechanically
as `closure_allowed`; it is not a main-session or Planner judgment. Never add it
merely to pass the close gate. After recording, return the Review report and let
Planner disposition observations and perform closure calibration.

After Reviewer returns to the stable main session, run `aiwf status --prompt`.
It routes `needs_change` to Executor, `rejected` to Planner,
`needs_experiment` to the already-open EXP, and `accepted` toward Planner
calibration or close.
