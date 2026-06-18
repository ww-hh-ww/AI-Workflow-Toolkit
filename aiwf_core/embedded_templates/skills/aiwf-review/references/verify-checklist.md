# Verify Checklist

## Contract verification

- Task.md was not modified after activation.
- Executor stayed inside Allowed Write.
- Forbidden Write was respected.
- Done When is actually met.

## Evidence verification

- Executor evidence exists when required.
- Evidence summary matches actual changed files.
- Commands recorded are plausible and relevant.

## Testing verification

- Testing record exists when required.
- `passed` is supported by real commands.
- `adequate` explains why runnable tests were unavailable or unnecessary.
- `failed` is not hidden or converted into success.

## Quality verification

- No unnecessary broad rewrite.
- No duplicated mechanism introduced.
- No stale command or path surfaced.
- No hidden coupling ignored.
- No future cleanup debt created without being reported.

## Decision

- `accepted`: all required checks pass.
- `needs_fix`: fixable blocker remains.
- `rejected`: wrong direction or unsafe result.
