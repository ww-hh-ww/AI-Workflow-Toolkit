# Task Contract Reference

Task.md is the execution contract. The active Task.md is frozen by hash at activation and must not be edited by the model during execution.

## Required sections

### Scope

State the exact work outcome. Keep it small enough for one implementation/testing/review cycle.

### Allowed Write

List files, directories, or narrow surfaces that may be modified. If a broad directory is allowed, explain why.

### Forbidden Write

List files and directories that must not be modified. Include AIWF state and records by default:

```text
.aiwf/state/
.aiwf/records/
```

### Executor Requirements

State what implementation must change. Avoid vague wording such as "clean up" unless paired with concrete acceptance.

### Tester Requirements

State expected validation. Include command expectations when known.

Allowed outcomes:

- `passed` when runnable checks pass.
- `failed` when checks fail.
- `adequate` when no runnable test exists but honest validation is still possible.

### Reviewer Requirements

State what reviewer must verify:

- Scope compliance
- Forbidden Write compliance
- Done When compliance
- Evidence/testing adequacy
- Quality or architecture risks

### Done When

Use observable completion criteria, not subjective satisfaction.

### Rollback Strategy required: yes/no

Use `yes` for high-risk tasks such as state migration, directory structure changes, batch rename, broad parser changes, install output migration, or generated surface rewrites.

When `yes`, include:

```text
Method: Git
Before work: inspect git status and git diff
Rollback: use git restore for selected files; use git reset only by human decision
```

## Subagent Dispatch Decisions

Planner sets these booleans in Task.md frontmatter. They control whether implement/test/review skills dispatch subagents or work inline.

**Not every task needs the full team.** Match the effort to the risk:

```
Trivial task (typo, comment, config one-liner):
  executor_required: false    tester_required: false    reviewer_required: false
  → main model does everything inline. One record testing --status adequate is enough.

Simple task (single file, isolated, no shared imports):
  executor_required: false    tester_required: true     reviewer_required: false
  → main writes inline. Dispatch tester to validate. Reviewer would just duplicate tester.

Normal task (multi-file, core logic, shared utility):
  executor_required: true     tester_required: true     reviewer_required: true
  → full team. This is the default for any real code change.

Complex task (public API, state machine, refactor, cross-module):
  executor_required: true     tester_required: true     reviewer_required: true
  rollback_required: true
  → full team + rollback strategy. Also consider splitting into smaller tasks.
```

### executor_required

Dispatch `aiwf-executor` for writes. Set `false` when the main model can write directly.

| true | false |
|------|-------|
| Multi-file (3+), core logic, public API, state machine | Single-file edits, isolated code |
| Refactoring, new module, shared utility | Pure documentation, comments, config |
| Any change another developer would want to review | Typo, formatting, trivial fix |

### tester_required

Dispatch `aiwf-tester` for validation. Set `false` when inline check is enough or no test surface exists.

| true | false |
|------|-------|
| Executor changed code AND runnable tests exist | Trivial task (inline-tested by executor) |
| Public API, shared utility, cross-module | Pure docs, no code to test |
| Normal/complex task | Simple task where tester+reviewer would overlap |

### reviewer_required

Dispatch `aiwf-reviewer` for contract and quality audit. Combine with tester for simple tasks — one is enough.

| true | false |
|------|-------|
| Normal/complex task (any real code change) | Trivial task (inline review is enough) |
| Multi-file, cross-module, public API | Simple task (tester covers it) |
| | Pure documentation |

**For simple tasks**: pick ONE of tester or reviewer, not both. Tester is better when runnable tests exist; reviewer is better for structural/contract concerns. They overlap on simple diffs.

### rollback_required

Set `true` for high-risk surfaces. Fill the Rollback Strategy section with `Method: Git`.

| true | false |
|------|-------|
| State schema, record format, directory layout | Ordinary feature, bug fix |
| Install output, parser, command surface | Documentation, config |
| Batch rename, broad removal of old code | |

### report_policy

Default is `ask` — always report close summary to human. Only set `silent_until_done` when the user explicitly asks for it.

```
ask                 — report every task close to the human, wait for instructions
silent_until_done   — user explicitly requested quiet mode for this task/plan/milestone
```

Do NOT set `silent_until_done` on your own judgment. The user controls when they want silence.

---

## Bad contract signs

- Allowed Write is broader than needed.
- Done When repeats the title.
- Tester Requirements say only "run tests" without naming likely commands or validation type.
- Reviewer Requirements do not mention scope or forbidden paths.
- High-risk work has no rollback strategy.
- `executor_required: false` on a multi-file core change (too risky for inline).
- `executor_required: true` on a one-line typo fix (wastes a subagent dispatch).
- `report_policy` left at default for every task under a milestone (noisy for humans).
