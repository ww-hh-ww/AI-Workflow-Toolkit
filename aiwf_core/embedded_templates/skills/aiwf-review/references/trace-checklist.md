# Trace Checklist

Use this when the task touched behavior, public surfaces, state, install output, parser logic, or shared utilities.

## Change surface

- What files changed?
- Are changed files inside Allowed Write?
- Did any generated, installed, or runtime surface change indirectly?

## Ripple surface

Check callers, imports, command registrations, templates, and tests related to the changed files.

## State/record surface

If state or records changed, check:

- `.aiwf/state/*.json`
- `.aiwf/records/*.json`
- command handlers that read/write those files
- close gates that consume those files

## Install surface

If templates changed, check:

- installed `.claude/agents`
- installed `.claude/skills`
- `.aiwf/config/skill-map.json`
- generated `CLAUDE.md`

## Risk signs

- A command is documented but not registered.
- A template writes a path that runtime no longer uses.
- A close gate reads a different record file from the record command.
- A role skill teaches a human-only command as model action.
