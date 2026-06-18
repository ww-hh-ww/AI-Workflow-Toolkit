# Milestone Architecture Review Gate

The architecture gate checks whether the phase kept the system coherent.

## Read

- Milestone doc
- Linked Plan and Task docs
- `.aiwf/records/evidence.json`
- `.aiwf/records/testing.json`
- `.aiwf/records/review.json`
- `.aiwf/records/architecture-review.json`
- Changed command/parser/template surfaces when relevant

## Check

- Public command surface matches docs and skills.
- Runtime paths match installed workspace structure.
- Records are read and written consistently.
- Human-only commands remain protected.
- Removed mechanisms do not reappear in installed surfaces.
- The milestone did not increase structural complexity unnecessarily.

## Command

```bash
aiwf milestone arch-review MS-001 --status intact --notes "<summary>"
```

If issues remain:

```bash
aiwf milestone arch-review MS-001 --status issues_found --notes "<issue summary>"
```
