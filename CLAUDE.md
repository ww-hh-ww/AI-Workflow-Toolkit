# AIWF Session Rules

## Every turn starts here

Run `aiwf status`. The boxed routing block tells you: where you are, why this level, what to do next. Obey the `Next:` line.

## Routing discipline

The `Routing:` line shows the factors (cross_module, prior_fix_loop_history, semantic_change…) that determined the level. This is the system's risk assessment, not a suggestion.

- **L0**: Inline OK. Self-test, self-review.
- **L1**: Executor = subagent. Testing+review = one reviewer-light subagent.
- **L2**: Executor, Tester, Reviewer = THREE independent subagents via Agent tool.
- **L3**: Same as L2 + adversarial depth.

**When `Next:` says `Agent(aiwf-*)`, dispatch that subagent NOW.** The scope guard mechanically blocks Write/Edit at L1+ if you're not the right role. Don't wait for the denial.

**FORBIDDEN: routing downgrades unless the user explicitly orders it for this specific task.**

Skills (`/aiwf-implement`, `/aiwf-test`, `/aiwf-review`) contain the dispatch template with exact prompt fields. Load them when building the Agent call.

## Signal Priority

1. Mechanical gate (hook denial) — cannot override
2. Status block `Next:` directive — the state machine's current order
3. User explicit decision — scope, risk, or task-specific downgrade
4. Phase skill — dispatch template
5. These rules

## Non-negotiable

- No project writes without active task + context (L0 exempted).
- No closure from prose — `aiwf task close` is the authoritative close gate.
- No roleplaying independent Tester/Reviewer at L2+.
- Fix-loop resolution = mechanical verification, not prose.
- Scope violations clear only after Git revert confirmed.
- Never self-initiate route downgrade.

<!-- AIWF MANAGED BLOCK START -->
# AIWF

AIWF controls automated/agent writes, not human manual edits. `.aiwf/*.json` is
machine state; `.aiwf/*/*.md` is semantic contract.

## First action

Run `aiwf status --prompt`. It tells you: phase, active task, required skill,
required read.

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

On-demand: `/aiwf-architect` (periodic signal or user request), `/aiwf-milestone`
(status signal or milestone gate).

## Write rules

- **Project writes require an active task** — mechanically enforced.
- **Governance writes do not require an active task** — `.aiwf/goals/`,
  `.aiwf/plans/`, `.aiwf/tasks/`, `.aiwf/milestones/`, `.aiwf/config/`,
  `.aiwf/assets/` are always allowed.
- **Active Task.md is frozen during execution** — mechanically enforced.
  Read-only for AI during executing/testing/reviewing phases.
- **Forbidden Write is mechanically enforced** — patterns in Task.md's
  Forbidden Write section block writes at the scope checker.
- **After editing MD frontmatter, run `aiwf sync`** — compiles MD into the
  JSON machine state that gates read.
- Human manual edits are not intercepted. Detected post-hoc by `aiwf doctor`
  and `aiwf task close`.
- Do not invent commands beyond `aiwf --help`.

## Subagent dispatch

Subagent use is controlled by `executor_required`, `tester_required`,
`reviewer_required` in Task.md frontmatter. Each implement/test/review skill
reads its boolean and dispatches the corresponding agent or executes inline.
See `aiwf-planner` references for the dispatch framework.

## Hard gates (machine-enforced)

- AI project writes require active task.
- Forbidden Write patterns block writes at write time.
- Active Task.md frozen during execution.
- `.aiwf/state/` and `.aiwf/records/` must be changed through CLI, never
  direct Write/Edit/Bash.
- Close requires: evidence (if executor_required), testing (if tester_required),
  review accepted with no blockers (if reviewer_required), fix-loop not open.
- Fix-loop open blocks close.

## Non-negotiable

- No AI project writes without an active task.
- No closure from prose — `aiwf task close` is the authoritative close gate.
- Fix-loop resolution requires mechanical verification.
- **FORBIDDEN: routing downgrades unless the user explicitly orders it.**
- **FORBIDDEN: `aiwf task force-close` — human emergency override only.**
<!-- AIWF MANAGED BLOCK END -->
