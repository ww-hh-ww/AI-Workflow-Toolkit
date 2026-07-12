# Milestone Acceptance

Use this when the selected lens is `milestone-acceptance`.

This is a gate for one milestone. It is not a broad architecture review.

## Acceptance Boundary

Ask:

- What exactly does the milestone Pass Standard require?
- Which Goals, Plans, Tasks, and capability claims feed this milestone?
- Is a separate `kind=milestone_verification` task required? If yes and it is
  missing, stop and return that to Planner.

## Real Verification

Verify each Pass Standard item in the running system.

Do not accept:

- code reading alone;
- mocks alone;
- "should work" reasoning;
- a component that exists but is not consumed on the real main path.

Record enough observable evidence for a future agent to understand what was
checked and what happened.

## Records And Close

- Record observable commands with `aiwf milestone integration-test`.
- Record interface and main-path integrity with
  `aiwf milestone arch-review <ID> --status intact --notes "<what held>"`.
  When integrity does not hold, use
  `--status issues_found --issue "high:::<specific issue>"`.
- Record `aiwf milestone assess --verdict PASS` only after all required checks
  pass.
- Use `REVISE` or `REJECT` when a required check fails.
- If PASS, ask the human: "Confirm and close this milestone?"
- Do not run `aiwf milestone confirm` or `aiwf milestone close` before explicit
  human approval.
- After approval, the main session runs `aiwf milestone confirm`, follows
  `aiwf status --prompt` to calibrate and close the verification Task, then runs
  `aiwf milestone close`.
- Report architecture risks separately for Planner. Do not turn acceptance into
  broad mission review.
