# Milestone Acceptance

Milestone acceptance is a gate, not architecture reflection. It asks whether the
selected milestone can be closed under its current Pass Standard.

## Scope Trace

- Read the milestone Pass Standard as the authoritative acceptance criteria.
- Trace the milestone scope through related Goals, Plans, Tasks, and capability
  claims before testing.
- If `verification_task_required: true` and `verification_task_id` is empty,
  stop and return to Planner for a `kind=milestone_verification` task.

## Real Environment Verification

- Verify each Pass Standard item against the running system.
- Do not treat code reading, mocks, or "should work" reasoning as verification.
- Every new capability from the milestone must be consumed on the real main
  path; built but never called is not done.
- Record observable evidence sufficient for a future agent to understand what
  was verified and what happened.

## Records And Closure

- Record one `aiwf milestone integration-test` result for each Pass Standard
  item.
- Record `aiwf milestone assess --verdict PASS` only after all required checks
  pass.
- If any required check fails, record/return FAIL and stop.
- If PASS, ask the human to confirm and close. Do not run confirm or close
  before explicit human approval.
- Surface architecture risks separately for Planner disposition. Do not turn
  milestone acceptance into mission leverage review.
