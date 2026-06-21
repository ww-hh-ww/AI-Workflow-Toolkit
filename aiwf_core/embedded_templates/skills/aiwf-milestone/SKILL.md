---
name: aiwf-milestone
description: Use only when `aiwf status --prompt` lists `aiwf-milestone` under Required skills.
---

# AIWF Milestone

## Role

Verify the milestone's Pass Standard in a real environment. You do not replace
human acceptance.

**Behavior**: `milestone.md` defines what "done" means — your job is to prove it's
actually done, in a real environment, with every piece wired into the main path.

Integration completeness. Every new capability produced in this phase must be
consumed — built but never called is not done. Use the Goal tree and Plan
dependencies to identify what this phase was supposed to deliver, then trace
each piece to a real consumer on the main path.

Real environment. Not a unit test, not a mock. The actual flows the system runs.

If PASS, report and ask the human to confirm and close. If FAIL, report what
failed and stop.

## First action

```bash
aiwf status --prompt
```

Read the milestone specified by status or user request.

## Required read

- `.aiwf/milestones/<MS-ID>.md` — the authoritative Pass Standard
- `.aiwf/state/milestones.json`
- `.aiwf/state/goals.json`
- `.aiwf/state/plans.json`
- `.aiwf/state/tasks.json`
- `.aiwf/records/testing.json`
- `.aiwf/records/review.json`
- `.aiwf/records/architecture-review.json`

## Rules

- Verify in a real environment. Not simulated, not "should work."
- Every new capability must be consumed on the main path.
- Do not auto-commit.
- Do not bypass human confirmation.
- Do not close a milestone with failed integration unless the assessment
  explicitly records risk and the human confirms.

## Workflow

FOLLOW EVERY STEP. CHECK OFF EACH ONE AS YOU GO. SKIP NOTHING.

0. Read `aiwf-project` skill for project-specific rules and knowledge.
1. Read `milestone.md`. The Pass Standard is the authoritative acceptance criteria.
2. Trace consumption: for every new capability from this phase, verify it is
   wired into the main path and actually called. Use the Goal tree and Plan
   dependencies to identify what was supposed to be delivered.
3. Verify in a real environment: run integration tests, end-to-end flows,
   whatever the Pass Standard requires.
4. Two coverage modes:
   - `end_to_end_flow`: exercise the full path from entry to exit.
   - `function_reverse_trace`: when direct execution is unavailable, trace
     from command entry to state/record output and prove equivalent coverage.
5. Record results.
6. If PASS — present findings and ask human to confirm and close.
   If FAIL — report what failed and stop.

## Commands

Integration gate:

```bash
aiwf milestone integration-test MS-001 --status passed --coverage-mode end_to_end_flow --main-path-status passed --command "<command> ::: passed" --summary "<summary>"
```

If failed:

```bash
aiwf milestone integration-test MS-001 --status failed --coverage-mode end_to_end_flow --main-path-status failed --command "<command> ::: failed" --summary "<failure>"
```

Assessment:

```bash
aiwf milestone assess MS-001 --verdict PASS --summary "<summary>"
```

Close after human confirmation:

```bash
aiwf milestone close MS-001
```

## Human-only command

`aiwf milestone confirm` is human-only. The model must not run it.

When confirmation is needed, stop and ask the human to run:

```bash
aiwf milestone confirm MS-001 --summary "<what was accepted>"
```

VERIFY: DID YOU FOLLOW EVERY STEP? IF YOU SKIPPED ANY, GO BACK.
VERIFY: Re-read aiwf-project. Any project rule you missed?
