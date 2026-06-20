# Inline Execution

When `*_required` is false, the task doesn't need that role's full depth.
Execute directly at the effort level the task deserves.

- Read active `.aiwf/tasks/<TASK-ID>.md` before doing anything.

## Implement

- Trivial task: fix it correctly, don't overthink.
- Simple task: do good work, check obvious impact.
- Record changed files.

## Test

- Trivial: run what exists, confirm green.
- Simple: check the changed surface, one extra path.
- Match testing mode to Task.md. Honest failed > lazy passed.

## Review

- Trivial: sanity check, no scope violation, done.
- Simple: check scope, done when, obvious issues.
- Normal: full relational review (prove justified, zero downgrade, interface shape).
