# Milestone.md Writing Guide

Milestone.md defines acceptance for a stable mission slice. It must prove that
the covered capabilities work together on the real path.

## Frontmatter

Keep Goal, Plan, Task, verification Task, and requirement links accurate. A
milestone that requires verification must link a
`kind=milestone_verification` Task.

## Must Say

- Purpose: the stable mission slice being accepted.
- Coverage: the Goals, Plans, Tasks, and capability claims included.
- Pass Standard: observable running-system behavior required for acceptance.
- Real Verification: commands or scenarios that exercise the actual main path.
- Architecture Questions: interfaces, runtime paths, and capability boundaries
  Architect must check.
- Human Acceptance: what the human is being asked to accept after technical
  proof passes.

Use headings that fit the milestone. The names above are not a required form.

## Add Only When Useful

- Evidence Trace when several claims need explicit links to different proof.
- Documentation Requirements when documentation is part of acceptance.
- Residual Risk Policy when a known risk may be accepted rather than fixed.
- Support or platform limits when the milestone does not cover every runtime.

Omit empty optional sections. If a required claim has no evidence path, mark it
Unknown and fix the acceptance design before verification.

## Quality Check

- Does Pass Standard prove integration, not merely closed Tasks or files?
- Does verification exercise a real environment and real consumer path?
- Can a fresh Architect trace every accepted claim to observable evidence?
- Are architecture integrity and human confirmation both explicit?
- Are remaining risks blocked or accepted with a reason?
