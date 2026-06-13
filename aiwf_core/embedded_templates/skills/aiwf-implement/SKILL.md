---
name: aiwf-implement
description: Scoped implementation within context allowed_write boundaries
---

# AIWF Implement

**Surgical change rule:** Every changed line must trace to the active plan's Scope or Verification. Do not refactor, restructure, or improve adjacent code unless the task explicitly requires it. Minimal implementation beats speculative abstraction.

Loading this skill does not create an independent subagent. Follow `.aiwf/state/state.json` `execution_topology`: L0 may be inline; L1 may be single agent with machine evidence; L2/L3 require the planned independent topology unless Planner recorded an explicit substitute. If you are planner-main, no roleplaying executor when the active route requires a separate executor.

## Before Starting (pull what you need)

1. **Context**: Read `.aiwf/state/contexts.json` → `allowed_write`, `forbidden_write`, `purpose`, `non_goals`, `dependencies`, `interface_contract`.
2. **Goal Tree**: Read `.aiwf/state/goals.json` → parent Goal: `module_boundaries`, `architecture_invariants`, `non_goals` propagate from Goal.
3. **Plan**: Read `.aiwf/state/plans.json` → active Plan: `plan_kind`, `work_intent`, `interfaces`, `constraints`, `active_phase`.
4. **Architecture Brief**: Read `.aiwf/state/goal.json` → `quality_brief.architecture_brief`: `protected_files`, `forbidden_restructures`, `allowed_files`, `integration_points`.
5. **State**: Read `.aiwf/state/state.json` → `workflow_level`, `execution_topology`.

## Work Intent Discipline

Your Plan's `work_intent` governs how you work:
- **feature**: implement target capability, document interfaces, do not refactor unrelated code.
- **bugfix**: minimal fix, root cause only, add regression test, preserve existing behavior.
- **refactor**: restructure internals, preserve external behavior, no new features.
- **cleanup**: remove only — do not delete machine truth, do not change registry semantics.
- **migration**: preserve data, provide fallback path, generate migration report.
- **verification**: do NOT change implementation unless explicitly assigned. Focus on evidence.
- **exploration**: isolate from stable structure, use Temporary Root, record findings.
- **documentation**: do NOT change machine semantics. Docs must match current behavior.
- **integration**: do NOT change interfaces. Integrate completed branches, check convergence.
- **release**: do NOT change behavior during packaging. Release hygiene only.

## Implementation Rules

- Stay within `allowed_write`. Treat `forbidden_write`, `protected_files`, and `forbidden_restructures` as hard boundaries.
- Do NOT modify the Goal Tree — no graft, prune, or restructure — unless the active Plan explicitly assigns structural change.
- Follow the active Plan's `plan_kind`, `active_phase`, `interfaces`, and `constraints`.
- Do NOT invent new structure or expand scope. Report gaps to Planner.
- If the Plan's scope or interface is insufficient, stop and report. Do not silently normalize drift.
- For lightweight patches: work inside existing Plan, attach evidence to that Plan.
- If Impact says docs/assets=yes, update `.aiwf/artifacts/reports/项目地图.md`. If no, skip.

## Reading Strategy

Locate first with grep/Glob, then read selectively with offset/limit. Tests show expected behavior more concisely than implementation.

## During Implementation

- Respect `architecture_brief.allowed_files`, `protected_files`, `forbidden_restructures`.
- Respect the active Plan's `plan_kind`, `active_phase`, `interfaces`, and `constraints`. Do not work outside them.
- Do NOT invent new structure unless explicitly allowed by the Plan.
- Do NOT graft, prune, or modify the Goal Tree unless the Plan's scope explicitly assigns structural change.
- If the Plan's scope or interface is insufficient for the work, stop and report to Planner. Do not silently expand.
- For lightweight patches (`action_granularity=patch|task`): work inside the existing Plan; attach evidence to that Plan.
- If the plan says Docs/Assets impact=yes for project-map, update `.aiwf/artifacts/reports/项目地图.md` with new files/directories/renamed modules. If impact=no, skip.
- Follow existing code patterns. Keep changes minimal and focused.

## Architecture Change

If the architecture brief is insufficient, stop and report the gap. Do NOT silently expand architecture. Request changes via:
```
aiwf arch-change request --source executor --reason "..." --proposed-change "..." \
  --affected-file <path> --affected-module <name> --current-contract-gap "..." \
  --scope-impact "..." --risk "..."
```

## After Implementation

Report to planner-main: changed files, commands run with exit codes, scope/architecture concerns. For each piece of evidence, state which Plan and Goal it supports. Evidence is captured automatically by hooks; if missing, use `aiwf state record-role-evidence --role executor --summary "..." --changed-file <path> --scan-git --supports-plan <PLAN-ID> --supports-goal <GOAL-ID>`.

If the Plan's scope was insufficient: report what was needed vs what the Plan allowed. Do not silently normalize drift.

## Scope Rules

- `allowed_write`: paths you may modify.
- `forbidden_write`: paths you must NEVER touch.
- `architecture_brief.allowed_files` / `protected_files` / `forbidden_restructures`: additional hard boundaries.
- If unsure about a boundary, ASK planner-main.
