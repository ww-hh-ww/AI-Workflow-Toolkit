# AIWF V1 Design Contract

Status: **FROZEN**. Changes to this document require a new Plan + Task cycle.

---

## 1. Dual-Surface Model

```
MD  = human/model semantic form     (editing surface)
JSON = compiled machine state        (execution surface)
sync = MD frontmatter → JSON         (the ONLY compiler)
```

| Surface | Who writes | Who reads | Format |
|---------|-----------|-----------|--------|
| `.aiwf/goals/*.md` `.aiwf/plans/*.md` `.aiwf/tasks/*.md` `.aiwf/milestones/*.md` | Human, Planner subagent | Human, all subagents, status | Markdown + YAML frontmatter |
| `.aiwf/state/*.json` | `aiwf` CLI commands, `aiwf sync` | Machine gates (hooks), status, doctor, close gate | JSON |
| `.aiwf/records/*.json` | `aiwf record` commands | Close gate, status, review | JSON |

**Non-negotiable:** Humans and models do NOT hand-edit `.aiwf/state/*.json` or `.aiwf/records/*.json`.

---

## 2. Workspace Layout

```
.aiwf/
  state/          — machine truth (JSON)
    state.json    — phase, active pointers, blocked
    goals.json    — goal registry
    plans.json    — plan registry
    tasks.json    — task registry + runtime state
    milestones.json — milestone registry
    fix-loop.json — open fix-loops
  records/        — evidence, testing, review (JSON)
    evidence.json
    testing.json
    review.json
    architecture-review.json
    events.json
  goals/          — goal narrative docs (MD)
  plans/          — plan narrative docs (MD)
  tasks/          — task narrative docs (MD, execution contract)
  milestones/     — milestone narrative docs (MD)
  config/         — skill-map, command-policy
  runtime/internal/ — toolkit-path, drift, diag
```

Dead zones (must NOT exist after install): `artifacts/`, `assets/`, `archive/`, `runtime/history/`, `runtime/checkpoints/`.

---

## 3. MD Frontmatter Schema

Each MD file starts with YAML frontmatter delimited by `---`.

### 3.1 Goal.md

```yaml
---
id: GOAL-001
type: goal
title: "<title>"
status: open             # open | closed | cancelled
parent_goal_id:          # "" for root goals
child_goal_ids: []       # computed by sync from parent_goal_id
attached_plan_ids: []    # computed by sync from plan goal_id
---
```

**Machine-owned fields (NOT in frontmatter):** `created_at`, `updated_at`, `doc_hash`, `doc_updated_at`, `goal_version`, `original_intent`, `current_goal`, `active_goal`, `goal_status`, `confirmed`, `quality_brief`.

### 3.2 Plan.md

```yaml
---
id: PLAN-001
type: plan
title: "<title>"
status: open             # open | closed | cancelled
goal_id: GOAL-001
milestone_id:            # "" if none
dependencies: []         # plan IDs this plan depends on
---
```

**Machine-owned / computed fields:** `task_ids`, `task_status`, `remaining_task_ids` (derived from Task.plan_id by sync), `created_at`, `updated_at`, `doc_hash`, `doc_updated_at`, `evidence_rollup`, `plan_status`.

### 3.3 Task.md

```yaml
---
id: TASK-001
type: task
title: "<title>"
contract_status: ready   # ready (only value humans set)
goal_id: GOAL-001
plan_id: PLAN-001
milestone_id:            # "" if none
kind: implementation     # implementation | milestone_verification | exploration
executor_required: true
tester_required: true
reviewer_required: true
rollback_required: false
dependencies: []         # task IDs this task depends on
---
```

**Machine-owned fields:** `status` (draft → ready → active → suspended → closed → cancelled), `frozen_contract_hash` (SHA-256 of canonical frontmatter keys + body), `activated_at`, `closed_at`, `close_mode`, `changed_files`, `evidence_ids`, `test_ids`, `review_ids`, `created_at`, `updated_at`, `doc_hash`, `doc_updated_at`.

### 3.4 Milestone.md

```yaml
---
id: MS-001
type: milestone
title: "<title>"
status: open             # open | closed | cancelled
goal_id: GOAL-001
plan_ids: []             # linked plans
task_ids: []             # linked tasks
covered_goal_ids: []     # goals this milestone covers
integration_test_required: true
architecture_review_required: true
human_acceptance_required: true
verification_task_required: true
verification_task_id:    # set when verification task created
---
```

**Machine-owned fields:** `created_at`, `updated_at`, `doc_hash`, `doc_updated_at`, `integration_test`, `architecture_review`, `user_acceptance`.

---

## 4. Active Task Compile Lock

### 4.1 Activation

`aiwf task activate TASK-001`:

1. Verify `state.active_task_id` is null
2. Verify task has `contract_status: ready` and `kind` is set
3. Verify `goal_id` and `plan_id` point to existing, non-closed nodes
4. Compute `frozen_contract_hash = sha256(canonical frontmatter keys + body)`
5. Set JSON: `active_task_id = TASK-001`, `status = active`, `phase = executing`, `frozen_contract_hash`, `activated_at`

### 4.2 Active-period rules

```
While active_task_id != null:
  - Only the active Task.md is frozen. All other governance MDs can be edited and synced.
  - sync skips the active Task.md (hash check only, no frontmatter→JSON compilation).
  - Changing the active Task.md does NOT change the running contract.
  - The contract in force = JSON frozen at activation time.
  - Other goals, plans, milestones, and non-active tasks can be freely edited and synced.
  - Plan.task_ids is a JSON computed field derived from Task.plan_id. It is NOT in Plan.md frontmatter.
```

### 4.3 Deactivation

Compile lock releases on `task close`, `task suspend`, or `task force-close`.

---

## 5. Sync Compiler (`aiwf sync`)

### 5.1 `aiwf sync --check`

Read-only. Validates:

| # | Check | Severity |
|---|-------|----------|
| 1 | MD frontmatter exists and is parseable | error |
| 2 | `id` matches filename (TASK-001.md → id: TASK-001) | error |
| 3 | `type` matches directory (tasks/ → type: task) | error |
| 4 | `title` is non-empty | error |
| 5 | `status` / `contract_status` is valid for this type | error |
| 6 | `goal_id` points to existing goal in goals.json (if set) | error |
| 7 | `plan_id` points to existing plan in plans.json (if set) | error |
| 8 | `milestone_id` points to existing milestone (if set) | error |
| 9 | `dependencies` do not form a cycle | error |
| 10 | `task_ids` bidirectional references are consistent | warn |
| 11 | active task: MD changed since frozen_contract_hash | warn |

### 5.2 `aiwf sync`

Runs `--check`. If all errors pass:

1. Write all frontmatter-derived fields to JSON
2. Update `doc_hash` for all synced docs
3. Update `title_cache` from `# heading` or frontmatter title
4. Does NOT overwrite machine-owned fields (status, frozen_doc_hash, timestamps)

Returns: count of synced entities, list of changes.

### 5.3 Atomic write

```
Write to .tmp file → validate JSON → os.rename to final path
```

---

## 6. Command Semantics

### 6.1 Create commands

`goal create`, `plan create`, `task create`, `milestone create`:

1. Create the MD file with full frontmatter
2. Use default template body with `(fill)` sections
3. Write minimal JSON registry entry (id, type, status, doc_path)
4. Run `aiwf sync` to populate JSON from frontmatter

Do NOT: write full JSON by hand, skip MD creation, or generate MD from JSON.

### 6.2 Update commands

`rename`, `link-task`, `unlink-task`, `link-plan`, `dep add/remove`:

1. Modify MD frontmatter
2. Run `aiwf sync`

Do NOT: directly modify JSON.

Blocked while `active_task_id != null` only if the target MD is the active Task.md. Other governance MDs may be edited and synced.

### 6.3 Close/cancel commands

- **Goal, Plan, Milestone close/cancel**: modify MD frontmatter `status`, then sync.
- **Task close**: writes JSON `status: closed`, `closed_at`, `close_mode`. Does NOT modify Task.md.
- **Task suspend**: writes JSON `status: suspended`. Does NOT modify Task.md.
- **Task force-close**: human-only, writes JSON `status: closed`, `close_mode: force`. Does NOT modify Task.md.

### 6.4 Record commands

`record evidence|testing|review|architecture-review`:

- Write directly to `.aiwf/records/*.json`
- NOT an MD operation
- All handler args use `getattr(args, "field", default)` for safety
- Parser must define all args the handler accesses

---

## 7. Close Gate

`aiwf task close` checks (in order):

1. `active_task_id` is not null
2. Active Task.md contract hash check — warning only. If `frozen_contract_hash != current`, close still proceeds using frozen JSON contract.
3. If `executor_required`: `evidence.json` has at least one accepted record for this task
4. If `tester_required`: `testing.json` has `status: passed` or `status: adequate`
5. If `reviewer_required`: `review.json` has `result: accepted`
6. `review.json` has no unresolved blockers
7. `fix-loop.json` has `status != open`

All checks are against JSON only. MD is not consulted.

---

## 8. Command Registry

### 8.1 Whitelist (11 commands)

```
install    doctor     status     sync
fixloop    mission    goal       plan
task       record     milestone
```

### 8.2 Non-whitelist commands (must fail)

```
route, workspace, goal-tree, relation, project-map,
research, frontier, change, claim, checkpoint,
prepare-close, cancel-close, state (all subcommands)
```

### 8.3 Documentation rule

Every `aiwf <command>` in docs/skills/CLAUDE.md/status must be in the whitelist. The parser is the single source of truth.

---

## 9. Doctor

`aiwf doctor` checks:

| # | Check |
|---|-------|
| 1 | `.aiwf/` directory structure matches layout |
| 2 | All state JSON files exist and are valid JSON |
| 3 | All record JSON files exist |
| 4 | `aiwf sync --check` passes (no errors) |
| 5 | Active task: `frozen_contract_hash` matches (warning if dirty) |
| 6 | Skill dirs: exactly 7 (planner, implement, test, review, close, milestone, architect) |
| 7 | Agent files: exactly 4 (explorer, executor, tester, reviewer) |
| 8 | Scripts: all 6 hook scripts exist and are executable |
| 9 | No dead zone directories (artifacts/, assets/, archive/) |
| 10 | No stale command references in docs/skills |

---

## 10. Tests

### 10.1 V1 release gate (`tests/v1_core/`)

Must pass:

```
install → init → doctor → sync --check →
goal create → plan create → task create → milestone create →
task activate → active Task.md frozen (frozen_contract_hash) →
record evidence → record testing → record review → record architecture-review →
task close → plan close → milestone assess/confirm/close →
non-whitelist command rejection → doc command scan
```

### 10.2 Legacy quarantine (`tests/legacy_quarantine/`)

Pre-existing tests that are skipped, test old behavior, or reference retired commands. Not part of the release gate.

---

## 11. Status Hook

`scripts/aiwf_status.py --prompt` output rules:

- `Required skills`: from `config/skill-map.json` phase_skills
- `Required read`: active Task.md path
- `[ATTN]`: the primary skill to load
- Must NOT reference: retired commands, old paths, `workflow_level` as control
- Must NOT suggest: `aiwf state`, `aiwf route`, `aiwf checkpoint`, `aiwf goal-tree`

---

## 12. Revision History

| Date | Change |
|------|--------|
| 2026-06-19 | Initial freeze |
