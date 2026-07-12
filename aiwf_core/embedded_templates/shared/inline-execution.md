# Inline Execution

When `*_required` is false, the task doesn't need a subagent for that role.
Execute directly, then record the implementation yourself.

Inline does not mean casual. Before doing anything, read the active
`.aiwf/tasks/<TASK-ID>.md` and understand:

- Fixed Contract: Objective, Contract Responsibility, Proof Standard,
  Verification Commands, and explicit Forbidden Write if present.
- Known Context: surfaces, invariants, integration evidence, unknowns.
- Open Judgment: the role-specific questions you still need to answer.

If Contract Responsibility, main-path consumer, invariant, or proof is unclear,
stop and return to Planner instead of guessing.

## Implement

- Trivial task: fix it correctly, check obvious impact.
- Simple task: trace callers/imports/config enough to prove the change is
  consumed where the contract says it matters.
- Run every Verification Command and compare expected observable output to
  actual output.
- Record the implementation. Git refs carry the full change;
  keep the summary short and use the strongest exact self-check:
  ```bash
  aiwf record implementation --summary "<what changed; how consumed; observed result>" --command "<strongest exact self-check>"
  ```

## Test

- Trivial: run what exists, confirm green.
- Simple: check the changed surface plus at least one false-pass risk: old
  path, bypass, fixture/mock, boundary/error case, or integration consumer.
- Match testing mode to Task.md. Honest failed > lazy passed.
- Record actual observable output, not just "passed".
- Record one testing result for the validation pass. Repeat `--command` and
  `--verification-result` inside that record for every required command:
  ```bash
  aiwf record testing --status passed --command "<exact command>" --verification-result "<command>:::<expected>:::<observed>:::matched" --summary "<what the output proved>"
  aiwf record testing --status failed --command "<exact command>" --verification-result "<command>:::<expected>:::<observed>:::mismatched" --summary "<failure>"
  ```

## Review

- Trivial: sanity check, no unrelated change, done.
- Simple: check Contract Responsibility, Done When, record truth, and obvious
  caller/old-path issues.
- Normal: full relational review belongs in `aiwf-reviewer`; do not inline it
  just because it is convenient.
- After reviewing, record:
  ```bash
  aiwf record review --result accepted --summary "<why accepted>"
  aiwf record review --result needs_fix|rejected --summary "<why>" --blocker "<specific blocker>"
  ```

Before each record, make sure the actual output supports the claim. Do not add
an extra checklist to prove that you followed this reference.
