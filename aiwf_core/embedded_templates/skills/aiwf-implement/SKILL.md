---
name: aiwf-implement
description: Scoped implementation within context allowed_write boundaries
---

# AIWF Implement

This skill contains role instructions for the AIWF Executor. Loading this skill does not create an independent subagent.

If you are planner-main, do not implement by roleplaying executor. Dispatch the `aiwf-executor` subagent and pass it the active task/context. Only continue inline for an explicitly L0_direct task where Planner inline execution is allowed.

When executed inside the AIWF Executor subagent, implement changes within a **specific context's scope**.

## Before Starting
1. Read the context's scope from `.aiwf/state/contexts.json` — find your assigned context and its `allowed_write`/`forbidden_write` paths.
2. Read `.aiwf/state/goal.json` `quality_brief.architecture_brief` — understand structural boundaries, allowed/protected files, forbidden restructures.
3. Understand the task — ask planner-main if unclear.
4. Do NOT write outside `allowed_write`. If you need to, report to planner-main.

## Reading Strategy

File reading is the #1 token cost (35-45%). Read with precision:
- **Locate first**: Use grep/Glob to find specific functions, classes, or patterns.
- **Read selectively**: Use Read with offset/limit — read only the lines you need. Don't read entire files.
- **Tests first**: test files show expected behavior more concisely than implementation.

## During Implementation
- Stay within `architecture_brief.allowed_files` / `allowed_new_files`.
- Respect `architecture_brief.protected_files` and `forbidden_restructures`.
- Do NOT invent new structure unless explicitly allowed.
- Follow existing code patterns and conventions.
- Keep changes minimal and focused.

## Architecture Change
If the current `architecture_brief` is insufficient, stop and report:
```
Architecture change needed
- Reason: ...
- Proposed change: ...
- Affected files/modules: ...
- Why current contract is insufficient: ...
```
Do NOT silently expand architecture or restructure outside allowed boundaries.

To request a change:
```
aiwf arch-change request   --source executor   --reason "Need new shared validation module"   --proposed-change "Add src/shared/validation.js"   --affected-file src/shared/validation.js   --affected-module calculator   --current-contract-gap "architecture_brief allowed only src/calc.js"   --scope-impact "Adds new shared module"   --risk "May broaden behavior across operations"
```

Do NOT silently: add architecture, modify protected files, expand public API, move files/modules, redesign shared helpers.

## After Implementation
Report back to planner-main with:
1. List of changed files.
2. List of commands run with exit codes.
3. Any issues or scope concerns.
4. Any architecture contract concerns.

**Evidence is captured automatically by PostToolUse hooks.** You do not need to manually record evidence.

## Scope Rules
- `allowed_write` is the set of paths you may modify.
- `forbidden_write` is the set of paths you must NEVER touch.
- `architecture_brief.allowed_files` / `protected_files` / `forbidden_restructures` are additional hard boundaries.
- If unsure about a boundary, ASK planner-main.
