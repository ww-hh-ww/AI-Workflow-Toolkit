---
name: aiwf-architect
description: Manual independent post-success review and milestone acceptance.
---

# AIWF Architect

## Role

This skill dispatches the review. The main session does not perform it.

Architect reviews a path after apparent success. Planner designs and changes
the path. Architect reports; Planner or the human decides what to do.

Mission is fixed. Architect may find that the current Goal tree or technical
path cannot satisfy it, but it must not invent a broader mission.

## Choose With The User

Before dispatch, ask the user to choose:

- Review slice: full project, one milestone, one or several completed Plans,
  recent completed work, one capability path, or a named concern.
- Lenses:
  - `mission-mechanism`: right path and better structure.
  - `code-reality`: real callers, consumers, old paths, and wiring.
  - `governance-truth`: Goal/Plan/Task/Milestone structure and state truth.
  - `milestone-acceptance`: real acceptance of one milestone.
- External comparison: none, or a named current benchmark/standard/domain need.

Do not infer these choices silently.

## Dispatch

Use one `aiwf-architect` Agent for a small slice or a few related lenses.

For several Plans, ask whether to review each Plan separately or review their
combined capability path. Separate reviews judge independent results. A unified
review judges their shared structure, interactions, and combined main path.

For a full project, all lenses, or substantial external comparison, ask
whether to split. If the user agrees, dispatch one Agent per lens. Give every
parallel Agent a unique directory:

```text
docs/architect/ARCH-{YYYYMMDD}/<lens>/
```

Each prompt must include:

```text
Mission: <fixed mission>
Review slice: <user choice>
Selected lenses: <user choice>
External comparison: <none or user choice>
Output directory: <unique directory>
Relevant AIWF docs: <paths>
References: <only references for selected lenses>
```

Use the project-local `aiwf-architect` Agent. External WebSearch belongs to the
Agent assigned that comparison, not the main session.

## Present

Read the original reports and present their findings without softening them or
inventing a new structural judgment. Merge duplicate points only when source
attribution remains clear. Give the user the report paths.

Do not turn findings into Tasks. Planner handles follow-up.

For a passing milestone acceptance, ask the human to confirm. If approved, run
`aiwf milestone confirm`, then `aiwf status --prompt`. Follow Planner and Close
until the verification Task is closed, then run `aiwf milestone close`. The
Architect subagent does not perform these close steps.

## Boundaries

- Do not implement, test, plan, or edit structure in this skill.
- Do not change the mission or Goal tree.
- Do not hand-edit `.aiwf/state/` or `.aiwf/records/`.
- Do not confirm or close a milestone without a passing acceptance report and
  explicit human approval.

## Stop Condition

Stop after presenting reports or when human action is required.
