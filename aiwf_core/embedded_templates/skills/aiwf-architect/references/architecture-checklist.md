# Architecture Checklist

## Command surface

- Registered commands match user-facing docs and installed skills.
- No skill teaches a command that is not registered.
- Human-only commands are not presented as model actions.

## Workspace structure

- Installed `.aiwf/` structure matches runtime read/write paths.
- Record commands write the same files that gates read.
- Install does not create stale directories.

## Lifecycle consistency

- Planner creates contracts.
- Implement records evidence.
- Test records testing.
- Review records review.
- Close closes only the active task.
- Milestone uses integration, architecture review, assessment, human confirmation, and close.

## Complexity

- No duplicate mechanism for the same lifecycle decision.
- No broad compatibility layer hiding stale behavior.
- No automatic work that should be an explicit Task.

## Risk classification

- `intact`: structure is coherent enough to proceed.
- `issues_found`: unresolved structure issues remain and should be planned or fixed.
