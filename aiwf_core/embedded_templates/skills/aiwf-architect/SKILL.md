---
name: aiwf-architect
description: Dispatch independent architecture review, milestone acceptance, or a Plan-scoped disposable investigation.
---

# AIWF Architect

## Role

This skill dispatches the review or Plan investigation. The main session does not perform it.

## Plan Investigation

Plan-scoped experimental work belongs to Architect, with the existing EXP
worktree, snapshot, evidence, and asset lifecycle. Task-scoped work still belongs
to Experimenter. This is not another Task execution role.

During planning, write the question and the decision it informs in Plan.md; no
Git ref or runtime EXP record is required. When the main session decides to run
the investigation, open it with `aiwf experiment open <EXP-ID> --plan-id <PLAN-ID>
--question "<unknown>"`. AIWF binds a stable subject at execution time. Then run
`aiwf experiment start <EXP-ID>` and dispatch `aiwf-architect` with that EXP ID.
For an existing EXP, read `aiwf experiment show` and continue from its state;
never reopen a recorded experiment or dispatch Experimenter for Plan scope.

Architect can build and run apparatus throughout the disposable project, but
not change the stable Plan worktree. It records its own evidence with
`aiwf experiment record`. After return, the main session runs `aiwf experiment
finish <EXP-ID>`, reads the conclusion, and records `aiwf experiment disposition`
with proceed|replan|no_action|promote and a reason. Retained assets are available
through `aiwf experiment assets`; stable delivery is Executor-owned Task work.
External calls still require the relevant user authorization.

For this mode, the EXP and Plan supply the inputs; do not require the review
lenses, completed-work slice, or report directory described below.

## Architecture Review

Architect reviews a path after apparent success. Planner designs and changes
the path. Architect reports; Planner or the human decides what to do.

Mission is fixed. Architect may find that the current Goal tree or technical
path cannot satisfy it, but it must not invent a broader mission.

## Choose The Review

Use choices already explicit in the user's request. Ask only about an unresolved
choice that would materially change the review:

- Review slice: full project, one milestone, one or several completed Plans,
  recent completed work, one capability path, or a named concern.
- Lenses:
  - `mission-mechanism`: right path and better structure.
  - `code-reality`: real callers, consumers, old paths, and wiring.
  - `governance-truth`: Goal/Plan/Task/Milestone structure and state truth.
  - `milestone-acceptance`: real acceptance of one milestone.
- External comparison: none, or a named current benchmark/standard/domain need.

Recommend a review shape from the project state when the user has not chosen
one, and explain the tradeoff briefly. Do not silently choose a narrower review
than the request requires.

## Dispatch

Use one `aiwf-architect` Agent for a small slice or a few related lenses.

For several Plans, ask whether to review each Plan separately or review their
combined capability path. Separate reviews judge independent results. A unified
review judges their shared structure, interactions, and combined main path.

When reviewing before Plan merge, review the exact prepared candidate after it
has incorporated the latest main. Only include other Plans whose results are
present in that candidate. Use the candidate worktree printed by
`aiwf plan integrate` as the review root. Do not combine unrelated branch tips
in prose.

For a full project, all lenses, or substantial external comparison, ask
whether to split. If the user agrees, dispatch one Agent per lens. Give every
parallel Agent a unique directory:

```text
.aiwf/reports/architect/ARCH-{YYYYMMDD}/<lens>/
```

Each prompt must include:

```text
Mission: <fixed mission>
Review slice: <user choice>
Selected lenses: <user choice>
Review root: <absolute project or prepared candidate worktree>
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
