# Code Reality Review

Read code to test the mission claim, not to perform a task-level review.

## Main Path

- What is the main path that should realize the reviewed capability?
- Is the new capability actually consumed on that path?
- Are there zero-caller functions, modules, config keys, or commands?
  - Abandoned old code: cleanup candidate.
  - New unwired code: bug.

## Structure

- Are module responsibilities clear?
- Are two mechanisms doing the same job?
- Are old and new paths both still live?
- Are abstractions carrying their weight, or hiding simple behavior?
- Are public interfaces consistent with local conventions?
- Do the governed project's public entry points still match its real main path?

## Drift

- Does code reality match the Plan/Goal/Task story?
- Did implementation introduce a design decision that was never promoted back
  into planning docs?
- Does duplicated or unwired code show the design has split into competing
  paths?
