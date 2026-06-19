# AIWF

AIWF controls automated/agent writes, not human manual edits. `.aiwf/*.json` is machine state; `.aiwf/*/*.md` is semantic contract.

## First action

Run `aiwf status --prompt`. It tells you: phase, active task, required skill, required read.

## Phase → skill

| Phase | Load |
|-------|------|
| planning | `/aiwf-planner` |
| executing | `/aiwf-implement` |
| testing | `/aiwf-test` |
| reviewing | `/aiwf-review` |
| closing | `/aiwf-close` |
| blocked | resolve blockers first |
| closed | `/aiwf-planner` (next cycle) |

## Write rules

- **Project writes by AI require an active task.**
- **Governance/planning writes do not require an active task.**
- **Active Task.md is frozen during execution** — do NOT modify it.
- **After editing MD frontmatter, run `aiwf sync`** — this compiles MD into the JSON machine state that gates read.
- Human manual edits are not intercepted. They are detected post-hoc by `aiwf doctor` and `aiwf task close`.

Governance paths (always allowed for AI): `.aiwf/goals/`, `.aiwf/plans/`, `.aiwf/tasks/`, `.aiwf/milestones/`, `.aiwf/config/`, `.aiwf/state/`, `.aiwf/records/`, `.aiwf/runtime/`.

Exception: the active Task.md (`.aiwf/tasks/<active_task_id>.md`) is read-only for AI during executing/testing/reviewing phases.

## Subagent dispatch

Subagent use is decided by **Task.requirements** in `.aiwf/state/tasks.json`:

- `executor_required: true` → dispatch aiwf-executor for project writes
- `executor_required: false` → main can write project files
- `tester_required: true` → dispatch aiwf-tester
- `reviewer_required: true` → dispatch aiwf-reviewer

`workflow_level` / L0 / L1 / L2 / L3 are NOT runtime control paths. Do not use them to decide dispatch or write permissions.

## Task.md is the execution contract

Task.md sections: Executor Requirements, Tester Requirements, Reviewer Requirements, Scope, Forbidden Write, Done When.

Models MUST read active Task.md before project writes. JSON is system state/index/checks only.

## Hard gates (machine-enforced)

- AI project writes require active task
- Active Task.md frozen during execution
- Close requires: evidence (if executor_required), testing (if tester_required), review accepted with no blockers (if reviewer_required), fix-loop not open. Task.md contract hash changes trigger a warning but do not block close (contract uses frozen activation state).
- Fix-loop open blocks close
- Scope violations block activation

## Non-negotiable

- No AI project writes without an active task.
- No closure from prose — `aiwf task close` is the authoritative close gate.
- Fix-loop resolution requires mechanical verification.
- Scope violations clear only after Git confirms reverting.
- **FORBIDDEN: routing downgrades unless the user explicitly orders it for a specific task.**
- **FORBIDDEN: `aiwf task force-close` — human emergency override only. AI is mechanically blocked by command-policy.json.**
- Plan.allowed_write is not a runtime write gate.
- `aiwf task close` is the authoritative close gate. No separate preparation step is needed.
- Do not trigger subagent dispatch, milestone review, or meta-critique by workflow_level.

## Signal priority

1. **Mechanical gate** (hook denial, scope guard, bash guard) — cannot override
2. **Status block** — the state machine's current directive
3. **User explicit decision** — scope, risk, task-specific downgrade
4. **Current phase skill** — role-specific instructions
5. **This constitution** — stable boundaries

## Mechanical truth

These files must change through `aiwf` CLI commands, never direct Write/Edit/Bash:

`.aiwf/state/state.json` `.aiwf/state/goals.json` `.aiwf/state/plans.json` `.aiwf/state/milestones.json`
`.aiwf/state/tasks.json` `.aiwf/state/fix-loop.json`
`.aiwf/records/testing.json` `.aiwf/records/review.json`
`.aiwf/records/evidence.json`

## Skill index

| Phase | Load | Specialist (on-demand) |
|-------|------|------------------------|
| planning | `/aiwf-planner` | — |
| executing | `/aiwf-implement` | — |
| testing | `/aiwf-test` | — |
| reviewing | `/aiwf-review` | — |
| closing | `/aiwf-close` | — |
| architecture | `/aiwf-architect` | — |
| milestone | `/aiwf-milestone` | integration, arch-review (only when Task.md or user requests it) |
