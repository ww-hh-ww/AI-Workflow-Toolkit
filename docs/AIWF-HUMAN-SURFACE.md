# AIWF Human Surface Contract

AIWF has many machine state files. Humans should not read them all.

## Three human-facing entries

| Entry | When | Purpose |
|-------|------|---------|
| `aiwf status` | Anytime, most frequent | Project control panel |
| `.aiwf/artifacts/reports/当前状态.md` | Next task start | Planner carry-forward summary; status reports stale when source JSON/report changed after it |
| `.aiwf/artifacts/reports/闭合报告.md` | Closure review | Human-readable closure basis |
| `.aiwf/runtime/history/task-history.json` | Trend/debug only | Lightweight closed-task trend source for report/status; not a default human reading surface |
| `.aiwf/artifacts/reports/质量摘要.md` | Next task/review/test | Compact cross-task quality signals for Planner, Tester, and Reviewer |
| `.aiwf/runtime/history/task-ledger.json` | Planner/task debug | Candidate/ready/active/closed task graph and execution window |
| `.aiwf/artifacts/plans/*.md` | During one task or plan-driven resume | Human-readable task plan, checklist, decisions, validation notes, and handoff context |
| `.aiwf/artifacts/research/external.json` | When external research influenced planning | Low-trust outside claims plus explicit Planner promotion decisions |

## JSON files are machine source of truth

Machine JSON files under `.aiwf/state/`, `.aiwf/artifacts/quality/`, `.aiwf/artifacts/evidence/`, and `.aiwf/runtime/history/` are the authoritative machine state.
They are NOT the default human reading surface.
Read them only when verifying details, resolving contradictions, or debugging.

Task plan Markdown is deliberately not a source of truth. It is useful for long-horizon continuity and resumption, similar to `plan.md`, but closure, scope, testing, review, and routing are enforced only by machine-readable AIWF contracts.

PROJECT-MAP and task plans do not conflict:
- PROJECT-MAP describes durable project structure, module boundaries, and architecture direction.
- Task plans describe one task's evolving intent, accepted decisions, validation strategy, and handoff notes.

## Before adding a new .aiwf file

Answer:
- Who reads it?
- When?
- Why can't this go into an existing file?
- Does it appear in UserPromptSubmit?
- Does it add long-term noise?

## What `aiwf status` shows

### Control Panel (always first)
Goal, phase, workflow level, health, next action — enough to decide "can I continue?"

### Quality & Closure
Testing, review, evidence, fix-loop, cleanup, structure, closure — enough to decide "can I close?"

### Awareness
Workspace drift, external capabilities, context dispatch, current-state, report — enough to know "what external factors matter?"

Request mode and workflow pattern are also shown. They explain whether the current work is discussion, clarification, research, spike, or execution, and whether a recipe-like pattern is shaping the route.

Task ledger and quality digest are shown as summaries only. They are not meant to flood prompt context.

### Detail entry points
File paths to `.aiwf/artifacts/reports/当前状态.md`, `.aiwf/artifacts/reports/闭合报告.md`, and canonical machine JSON directories — for when more detail is needed.

## What `aiwf status` does NOT show
- Raw JSON
- Full evidence records
- All capabilities
- Drift file names
- Full context dispatch fields
- Full lessons
- Full task plan text
- Raw external research claim lists
