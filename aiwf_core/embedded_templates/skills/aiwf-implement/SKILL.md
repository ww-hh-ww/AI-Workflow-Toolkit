---
name: aiwf-implement
description: Scoped implementation within context allowed_write boundaries
---

# AIWF Implement

**Surgical change rule:** Every changed line must trace to the active plan's Scope or Verification. Do not refactor, restructure, or improve adjacent code unless the task explicitly requires it. Minimal implementation beats speculative abstraction.

Loading this skill does not create an independent subagent. Follow `.aiwf/state/state.json` `execution_topology`: L0 may be inline; L1 may be single agent with machine evidence; L2/L3 require the planned independent topology unless Planner recorded an explicit substitute. If you are planner-main, no roleplaying executor when the active route requires a separate executor.

## Before Starting

1. Read your assigned context from `.aiwf/state/contexts.json` — `allowed_write` / `forbidden_write`.
2. Read `.aiwf/state/goal.json` `quality_brief.architecture_brief` — structural boundaries, protected files, forbidden restructures.
3. Do NOT write outside `allowed_write`. Report to planner-main if you need to expand scope.

## Reading Strategy

Locate first with grep/Glob, then read selectively with offset/limit. Tests show expected behavior more concisely than implementation.

## During Implementation

- Respect `architecture_brief.allowed_files`, `protected_files`, `forbidden_restructures`.
- Do NOT invent new structure unless explicitly allowed.
- If the plan says Docs/Assets impact=yes for project-map, update `.aiwf/reports/项目地图.md` with new files/directories/renamed modules. If impact=no, skip.
- Follow existing code patterns. Keep changes minimal and focused.

## Architecture Change

If the architecture brief is insufficient, stop and report the gap. Do NOT silently expand architecture. Request changes via:
```
aiwf arch-change request --source executor --reason "..." --proposed-change "..." \
  --affected-file <path> --affected-module <name> --current-contract-gap "..." \
  --scope-impact "..." --risk "..."
```

## After Implementation

Report to planner-main: changed files, commands run with exit codes, scope/architecture concerns. Evidence is captured automatically by hooks; if missing, use `aiwf state record-role-evidence --role executor --summary "..." --changed-file <path> --scan-git`.

## Scope Rules

- `allowed_write`: paths you may modify.
- `forbidden_write`: paths you must NEVER touch.
- `architecture_brief.allowed_files` / `protected_files` / `forbidden_restructures`: additional hard boundaries.
- If unsure about a boundary, ASK planner-main.
