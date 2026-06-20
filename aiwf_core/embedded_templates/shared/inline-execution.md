# Inline Execution

FOLLOW EVERY STEP. CHECK OFF EACH ONE AS YOU GO. SKIP NOTHING.

When `*_required` is false, the task doesn't need a subagent for that role.
Execute directly, then record evidence yourself.

- Read active `.aiwf/tasks/<TASK-ID>.md` before doing anything.

## Implement

- Trivial task: fix it correctly, don't overthink.
- Simple task: do good work, check obvious impact.
- After implementing, record:
  ```bash
  aiwf record evidence --role executor --scan-git --summary "<what changed>" --command "<command>"
  ```

## Test

- Trivial: run what exists, confirm green.
- Simple: check the changed surface, one extra path.
- Match testing mode to Task.md. Honest failed > lazy passed.
- After testing, record:
  ```bash
  aiwf record testing --scan-git --status passed|failed|adequate --summary "<summary>"
  ```

## Review

- Trivial: sanity check, no scope violation, done.
- Simple: check scope, done when, obvious issues.
- Normal: full relational review (prove justified, zero downgrade, interface shape).
- After reviewing, record:
  ```bash
  aiwf record review --result accepted|needs_fix|rejected --summary "<why>"
  ```

VERIFY: DID YOU FOLLOW EVERY STEP? IF YOU SKIPPED ANY, GO BACK.
