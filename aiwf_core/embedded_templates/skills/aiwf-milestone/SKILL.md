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
1. Read `milestone.md`. If `verification_task_required: true` and
   `verification_task_id` is empty: STOP. Milestone verification requires
   a dedicated task. Return to Planner and ask them to create a TASK-MS-VERIFY
   task with `kind=milestone_verification`, then set `verification_task_id`
   in this milestone. Do not proceed without it.
2. Read `milestone.md`. The Pass Standard is the authoritative acceptance criteria.
3. Trace consumption: for every new capability from this phase, verify it is
   wired into the main path and actually called. If a function or module has
   zero callers, ask: was it abandoned (old code, should be deleted) or built
   but never wired (new code, that's a bug)? Label which one.
4. **Verify every Pass Standard item against the running system.**
   Interact with the system, not just its source code. Verification must be
   repeatable and produce observable output. Record what you did and what
   happened. Code-reading is not verification.
5. Record integration test result for each Pass Standard item.
6. Record assessment:
   ```bash
   aiwf milestone assess MS-001 --verdict PASS --summary "<what was verified>"
   ```
   If FAIL — report what failed and stop. Do not continue.
7. **PASS → HARD STOP. Present findings to the human.** State what was
   verified, which commands were run, and what the outputs were. Ask:
   "Confirm and close this milestone?"
   **Do not proceed to step 8 until the human explicitly says yes.**

8. After human approval, run:
   ```bash
   aiwf milestone confirm MS-001 --summary "<what was accepted>"
   ```
   Then close:
   ```bash
   aiwf milestone close MS-001
   ```

## Commands

```bash
# Integration gate
aiwf milestone integration-test MS-001 --status passed --coverage-mode end_to_end_flow --main-path-status passed --command "<cmd> ::: <output>" --summary "<summary>"
aiwf milestone integration-test MS-001 --status failed --coverage-mode end_to_end_flow --main-path-status failed --command "<cmd> ::: <output>" --summary "<failure>"

# Assessment (after all integration tests)
aiwf milestone assess MS-001 --verdict PASS --summary "<what was verified>"

# After human approval (human may run, or model runs after explicit approval)
aiwf milestone confirm MS-001 --summary "<what was accepted>"
aiwf milestone close MS-001
```

VERIFY: DID YOU FOLLOW EVERY STEP? IF YOU SKIPPED ANY, GO BACK.
VERIFY: Re-read aiwf-project. Any project rule you missed?
