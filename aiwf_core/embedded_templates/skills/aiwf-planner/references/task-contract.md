# Task Contract Reference

Task.md is the execution contract. The active Task.md is frozen by hash at
activation and must not be edited by the model during execution.

## Dispatch Decisions

Planner sets these booleans in Task.md frontmatter. They control whether
implement/test/review skills dispatch subagents or work inline.

| Task type | executor | tester | reviewer | rollback |
|-----------|----------|--------|----------|----------|
| Trivial (typo, comment, config) | false | false | false | false |
| Simple (single file, isolated) | false | true | false | false |
| Normal (multi-file, core logic) | true | true | true | false |
| Complex (API, refactor, state) | true | true | true | true |

### executor_required

| true | false |
|------|-------|
| Multi-file, core logic, public API | Single-file, isolated code |
| Refactoring, new module, shared utility | Pure documentation, config |
| Any change another dev would review | Typo, formatting |

### tester_required

| true | false |
|------|-------|
| Executor changed code, runnable tests exist | Trivial (inline-tested by executor) |
| Public API, shared utility, cross-module | Pure docs, no code to test |
| Normal/complex task | Simple task where tester+reviewer overlap |

### reviewer_required

| true | false |
|------|-------|
| Normal/complex task | Trivial (inline review enough) |
| Multi-file, cross-module, public API | Simple (tester covers it) |
| | Pure documentation |

For simple tasks: pick ONE of tester or reviewer, not both.

### rollback_required

| true | false |
|------|-------|
| State schema, record format, directory layout | Ordinary feature, bug fix |
| Install output, parser, command surface | Documentation, config |
| Batch rename, broad removal of old code | |

When true, include in Task.md:
```
Rollback Strategy required: yes
Method: Git
Before work: inspect git status and git diff
Rollback: git restore for selected files; git reset only by human decision
```

### report_policy

- `ask` (default) — report every task close to the human.
- `silent_until_done` — only when user explicitly asked for quiet mode.
- Do not set `silent_until_done` on your own judgment.

## Lifecycle

Normal path:
```
planner creates task → planner activates → implement records evidence →
test records testing → review records review → close closes active task →
planner resumes
```

Failure path:
- Record the actual result honestly.
- Let Planner decide: revise, fix-loop, new Task, or ask human.
- Do not force-close unless human explicitly does it.

Runtime rules:
- `task close` closes the current active task only.
- `task suspend` suspends the current active task only.
- `task force-close` is human-only.
- Active Task.md must remain unchanged after activation.

## Emergency procedures

**Fix-loop exhausted**: When `aiwf status` shows `fix-loop open` with
`escalation_required=true`, stop. Tell the human:
"Fix-loop exhausted after N attempts. Recommend: review task scope,
consider `aiwf task force-close`."

**TUI freeze / terminal corruption**: Tell the human: "Run `reset`."

**Force-close**: `aiwf task force-close` is human-only. The model must NOT run it.

## Bad contract signs

- Allowed Write broader than needed.
- Done When repeats the title.
- Tester Requirements only say "run tests."
- Reviewer Requirements don't mention scope or forbidden paths.
- High-risk work has no rollback strategy.
- `executor_required: false` on multi-file core change.
- `executor_required: true` on one-line typo.
