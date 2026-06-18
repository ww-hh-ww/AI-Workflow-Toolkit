# Review Output Reference

## Accepted

Use only when the result satisfies Task.md, evidence is coherent, testing is adequate, and no blocking quality issue remains.

```bash
aiwf record review --result accepted --summary "<why accepted>"
```

## Needs fix

Use when the direction is basically right but a blocker remains.

```bash
aiwf record review --result needs_fix --summary "<summary>" --blocker "<specific blocker>"
```

Good blockers are concrete:

- file path
- failing condition
- violated requirement
- missing validation

## Rejected

Use when the change is the wrong direction, violates core scope, or cannot be safely salvaged inside the current task.

```bash
aiwf record review --result rejected --summary "<summary>" --blocker "<fundamental issue>"
```

## Do not

- Do not use milestone verdicts for ordinary task review.
- Do not accept untested high-risk changes.
- Do not accept scope expansion because it looks useful.
