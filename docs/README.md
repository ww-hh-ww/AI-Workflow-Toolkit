# AIWF Documentation

## Authoritative (V1)

- [V1 Design Contract](V1_DESIGN_CONTRACT.md) — MD/JSON boundary, frontmatter schema, sync rules, close gate
- [V1 Release Gate](../tests/v1_core/test_v1_release_gate.py) — 22 tests covering full lifecycle

## Current (living docs, maintained)

- [Workspace Layout](current/AIWF_WORKSPACE_LAYOUT.md)
- [Workflow Levels](current/AIWF-WORKFLOW-LEVELS.md)
- [Quality Policy](current/AIWF-QUALITY-POLICY.md)
- [Lesson Admission Policy](current/AIWF-LESSON-ADMISSION-POLICY.md)
- [Prompt Cache Policy](current/AIWF-PROMPT-CACHE-POLICY.md)
- [Workspace Drift Policy](current/AIWF-WORKSPACE-DRIFT-POLICY.md)
- [Work Intent Discipline](current/WORK_INTENT_DISCIPLINE.md)

## Legacy (pre-V1, not authoritative)

All docs in [legacy/](legacy/) are frozen pre-V1 reference material. They may contain retired commands (`aiwf state`, `prepare-close`, `aiwf route`, `aiwf goal-tree`, `aiwf project-map`) and old paths (`quality/`, `evidence/`, `artifacts/`). Do not use them as operational guidance.

## Hook Architecture (V1)

6 scripts installed by `aiwf install`:

| Script | Hook Event | Role |
|--------|-----------|------|
| `aiwf_status.py` | UserPromptSubmit | Inject phase/required skill/blockers |
| `aiwf_pre_snapshot.py` | PreToolUse | Pre-tool filesystem snapshot |
| `aiwf_scope_check.py` | PreToolUse | Block writes outside active context |
| `aiwf_bash_guard.py` | PreToolUse | Block dangerous shell commands |
| `aiwf_capture_evidence.py` | PostToolUse | Diff snapshot, write evidence |
| `aiwf_review_gate.py` | Stop | Report closure gate status |

## State Machine (V1)

Phase flow: `planning → executing → testing → reviewing → closing → closed`

State files (`.aiwf/state/`): `state.json`, `goals.json`, `plans.json`, `tasks.json`, `milestones.json`, `fix-loop.json`

Record files (`.aiwf/records/`): `evidence.json`, `testing.json`, `review.json`, `architecture-review.json`, `events.json`
