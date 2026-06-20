# LOAD THE PHASE SKILL. LOAD THE PHASE SKILL. LOAD THE PHASE SKILL.

When `aiwf status --prompt` shows `Required skills: X` — load X. Immediately.
Not later. Not "I already know what it says." The skill contains the dispatch
template, the subagent prompt fields, the evidence recording command. Without it
you are guessing and you will skip steps.

## First action

Run `aiwf status --prompt`. Read the `Required skills:` line. Load that skill.

## Phase → skill

| Phase | Load |
|-------|------|
| planning | `/aiwf-planner` |
| executing | `/aiwf-implement` |
| testing | `/aiwf-test` |
| reviewing | `/aiwf-review` |
| closing | `/aiwf-close` |
| blocked | resolve blockers first |
| closed | `/aiwf-planner` (next cycle)

AIWF controls automated/agent writes, not human manual edits. `.aiwf/*.json` is
machine state; `.aiwf/*/*.md` is semantic contract.

`/aiwf-architect` and `/aiwf-milestone` are also triggered by system signals.
When they appear in `Required skills:`, load them — same as any phase skill.

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

## Evidence recording

Evidence is recorded by whoever did the work. The close gate checks it exists.

| Who does the work | Who records | Where the command is |
|---|---|---|
| Subagent (dispatched) | Subagent records | Agent file `Required record` section |
| Inline (not required) | You record | `inline-execution.md` |

You do NOT record after a subagent returns — the subagent already did it.
Verify evidence exists before moving to the next phase, but do not double-record.

Evidence stores two git refs per record: `baseline_ref` (where this role started)
and `head_ref` (where this role finished). `git diff baseline..head` shows exactly
what changed. No commit required — `git stash create` captures working tree as a
dangling commit object, pinned at `refs/aiwf/evidence/<TASK-ID>`.

## Subagent dispatch

Subagent use is controlled by `executor_required`, `tester_required`,
`reviewer_required` in Task.md frontmatter. When a boolean is `true`, you MUST
dispatch the corresponding subagent via the `Agent` tool. Do NOT implement, test,
or review inline — spawn the subagent. The skill file has the exact `Agent(...)`
call with the prompt fields.

| Role | Subagent type | When |
|------|--------------|------|
| Executor | `aiwf-executor` | executor_required=true |
| Tester | `aiwf-tester` | tester_required=true |
| Reviewer | `aiwf-reviewer` | reviewer_required=true |

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
- **Required skills are NOT suggestions.** When `aiwf status --prompt` lists them,
  load every one. Close requires aiwf-close. Architect signal requires aiwf-architect.
  Milestone signal requires aiwf-milestone. No exceptions, no skipping.
- **FORBIDDEN: routing downgrades unless the user explicitly orders it.**
- **FORBIDDEN: `aiwf task force-close` — human emergency override only.**
