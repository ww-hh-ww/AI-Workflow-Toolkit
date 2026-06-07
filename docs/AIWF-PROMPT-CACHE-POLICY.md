# AIWF Prompt Cache Preservation Policy

AIWF must not break Claude Code / model service prompt cache.

## Hard Rules

1. **No dynamic modification of CLAUDE.md** — AIWF managed block is written at install time only. No runtime edits.
2. **No dynamic modification of .claude/settings.json / tools / MCP** — Install-time only.
3. **No model/effort switching by workflow_level** — Model selection is user-controlled.
4. **UserPromptSubmit injects only short state** — Typical injection: <400 chars. Never inject template text or JSON dumps.
5. **Detailed templates in docs/references** — Read on demand by skills, not injected into context.
6. **State records template keys only** — `workflow_level: "L1_review_light"`, `test_template: "targeted"`. Never full template text.
7. **Plan and research artifacts are on-demand** — task plans and external research registries are file references, not prompt payloads.

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

- Full template text from quality_policy.py
- Raw evidence.json dumps
- Full `.aiwf/plans/*.md` task plans
- Full `.aiwf/research/external.json` research registries
- Full project-map.json contents
- Long review/cleanup/structure prose
- Escalation history as narrative

## Template lookup pattern

Skills read template definitions from:
- `aiwf_core/core/quality_policy.py` (Python module, imported on demand)
- `docs/AIWF-QUALITY-POLICY.md` (human reference)
- `${CLAUDE_PROJECT_DIR}/.aiwf/assets/conventions.md` (project-specific)

They do NOT inject the full text; they reference the key and look up the definition when needed.

Task plans and workflow recipes follow the same pattern. `aiwf status` may expose the active plan id, request mode, and workflow pattern, but agents read the full plan or recipe only when they are actively using it.
