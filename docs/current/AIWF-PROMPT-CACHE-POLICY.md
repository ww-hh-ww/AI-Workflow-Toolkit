# AIWF Prompt Cache Preservation Policy

AIWF must not break Claude Code / model service prompt cache.

## Hard Rules

1. **No dynamic modification of CLAUDE.md** — AIWF managed block is written at install time only. No runtime edits.
2. **No dynamic modification of .claude/settings.json / tools / MCP** — Install-time only.
3. **No runtime model/effort switching** — Model selection is user-controlled.
4. **UserPromptSubmit injects only short state** — Typical injection: <400 chars. Never inject template text or JSON dumps.
5. **Detailed templates in docs/references** — Read on demand by skills, not injected into context.
6. **State injection stays referential** — inject Task IDs, phases, blockers, and file references; never full role instructions, contracts, or records.
7. **Plan, Task, Milestone, and research documents are read on demand** — keep them as file references until the active role needs them.

## What is cache-safe (static at install time)

- `CLAUDE.md` managed block
- `.claude/settings.json` hooks
- `.claude/skills/*.md`
- `.claude/agents/*.md`
- `scripts/aiwf_*.py`

## What is cache-safe (short, deterministic)

- `UserPromptSubmit` ~67-367 chars
- `PreToolUse` scope check output (JSON decision, <200 chars)
- `PostToolUse` evidence capture (writes to disk, no stdout injection)

## What must NOT be injected into context

- Full role or Skill templates
- Raw `.aiwf/state/` or `.aiwf/records/` dumps
- Full Plan, Task, Milestone, or research documents unrelated to the active role
- Full `PROJECT-MAP.md` contents when a focused reference is enough
- Long review/cleanup/structure prose
- Escalation history as narrative

## On-demand lookup pattern

The current phase loads its installed Skill and follows references from that
Skill. It reads the relevant Mission, Goal, Plan, Task, Milestone, Memory, and
record files only when they help the role make its next decision.

`aiwf status --prompt` exposes concise routing state and required Skill names.
It does not inject the full contract or choose a model. The role reads the
current files from disk after it has been routed.
