# Inline Execution

When `*_required` is false, the task doesn't need a subagent for that role.
Execute that role directly, then record its result yourself.

Inline does not mean casual. Before doing anything, read the active
`.aiwf/tasks/<TASK-ID>.md` and understand:

- Fixed Contract: Objective, Contract Responsibility, Proof Standard,
  Verification Commands, and explicit Forbidden Write if present.
- Known Context: surfaces, invariants, integration evidence, unknowns.
- Open Judgment: the role-specific questions you still need to answer.

If Contract Responsibility, main-path consumer, invariant, or proof is unclear,
stop and return to Planner instead of guessing.

For `kind=integration`, main remains unchanged during the Task. Implementation
merges the exact `integration_base_ref` from Task proof into the Plan worktree
with `git merge --no-ff --no-commit <ref>` and leaves the merge open. Testing
and review confirm `MERGE_HEAD`, the combined behavior, and the current
snapshots there. They do not require the Plan to be in main before Task close.

## Implement

- Trivial task: fix it correctly, check obvious impact.
- Simple task: trace callers/imports/config enough to prove the change is
  consumed where the contract says it matters.
- Run every Verification Command and judge the actual observable against the
  contract. Expected may describe a semantic condition, not literal stdout.
- Record the implementation. Git refs carry the full change;
  keep the summary short and use the strongest exact self-check:
  ```bash
  aiwf record implementation --task-id <TASK-ID> --summary "<what changed; how consumed; observed result>" --command "<strongest exact self-check>"
  ```

## Test

- Trivial: run what exists, confirm green.
- Simple: check the changed surface plus at least one false-pass risk: old
  path, bypass, fixture/mock, boundary/error case, or integration consumer.
- Match testing mode to Task.md. Honest failed > lazy passed.
- Record actual observable output, not just "passed".
- Record one testing result for every stable Verification Command ID in Task.md.
  Use `--check`, `--observed` (or `--observed-file`), and an explicit
  `--verdict`; use `--basis` when the judgment needs explanation. The Task owns
  the command and expected observable. Do not record by command text or infer a
  pass from non-empty output; if the contract is unclear, return to Planner:
  ```bash
  aiwf record testing --task-id <TASK-ID> --status passed --check V-001 --observed "<actual output>" --verdict matched --basis "<why it satisfies the contract>" --summary "<what the output proved>"
  aiwf record testing --task-id <TASK-ID> --status failed --check V-001 --observed "<actual output>" --verdict mismatched --basis "<verified failure>" --summary "<failure>"
  ```

## Review

- Trivial: sanity check, no unrelated change, done.
- Simple: check Contract Responsibility, Done When, record truth, and obvious
  caller/old-path issues.
- Normal: full relational review belongs in `aiwf-reviewer`; do not inline it
  just because it is convenient.
- After reviewing, record:
  ```bash
  aiwf record review --task-id <TASK-ID> --result accepted --summary "<why accepted>"
  aiwf record review --task-id <TASK-ID> --result needs_fix|rejected --summary "<why>" --blocker "<specific blocker>"
  ```

Before each record, make sure the actual output supports the claim. Do not add
an extra checklist to prove that you followed this reference.
