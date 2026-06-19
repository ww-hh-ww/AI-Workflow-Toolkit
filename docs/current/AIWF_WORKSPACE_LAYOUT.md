# AIWF Workspace Layout Contract

**Status:** Stage 4.7.3. Defines the five-zone `.aiwf/` directory structure.
**Depends on:** `NODE_CONTRACT.md`, `AIWF_DESIGN_AXIOMS.md`.

---

## 1. Purpose

The `.aiwf/` directory had grown into a flat mix of machine truth, human artifacts,
runtime traces, and input assets. This contract defines a five-zone structure so
that both humans and agents can see at a glance what is authoritative, what is
readable, and what is transient.

---

## 2. Five Zones

```
.aiwf/
  README.md          # Human explanation of each zone

  state/             # Machine truth — registries, indices, canonical state
  artifacts/         # Human-readable — plans, reports, reviews, evidence summaries
  runtime/           # Execution traces — history, checkpoints, internal, cache
  assets/            # Input assets — user/project files referenced by the system
  archive/           # Deprecated — migrated, obsolete, or superseded material
```

### 2.1 state/ — Machine Truth

Sole source of object existence, status, and canonical references.
Must contain only machine-readable structured files (JSON).
No markdown, no long-form prose, no logs.

```
state/
  state.json
  mission.json
  goals.json
  plans.json
  milestones.json
  task-ledger.json          # (or tasks.json)
  fix-loop.json
  contexts.json
  schema_version.json
  evidence_index.json       # (lightweight index, not full records)
```

### 2.2 artifacts/ — Human-Readable

Artifacts are human-authored or human-readable outputs. They are NOT machine truth —
they can be regenerated, archived, or stale without breaking the system.

```
artifacts/
  plans/                    # Plan markdown artifacts (PLAN-XXX.md)
  goals/                    # Goal description markdown
  milestones/               # Milestone synthesis markdown
  admissions/               # Admission Decision records
  frontiers/                # Frontier Decision records
  work-packets/             # Work Packet proposals
  reviews/                  # Review summaries and verdicts
  reports/                  # Quality digests, project map, ideas
  evidence/                 # Evidence summaries (lightweight, not raw data)
  research/                 # External research notes
  quality/                  # Testing and review quality records
```

### 2.3 runtime/ — Execution Traces

System-generated runtime material. Default should not be read by humans.
Agents should not treat these as structural authority.

```
runtime/
  checkpoints/              # Git stash checkpoints
  history/                  # Task history, task ledger history
  internal/                 # Workspace drift, baseline, internal indices
  cache/                    # Transient caches
  locks/                    # File locks
  sessions/                 # Session state
```

### 2.4 assets/ — Input Assets

User or project provided files that the system references but does not own.

```
assets/
  capabilities.json
  capability-decisions.json
  ...
```

### 2.5 archive/ — Deprecated

Material that has been migrated, superseded, or archived.

```
archive/
  old-plans/                # Pre-layout-refactor plans
  old-evidence/             # Pre-layout-refactor evidence
  legacy/                   # Other legacy material
```

---

## 3. Migration Mapping

| Old path | New path |
|----------|----------|
| `.aiwf/plans/` | `.aiwf/artifacts/plans/` |
| `.aiwf/evidence/` | `.aiwf/artifacts/evidence/` |
| `.aiwf/reports/` | `.aiwf/artifacts/reports/` |
| `.aiwf/research/` | `.aiwf/artifacts/research/` |
| `.aiwf/quality/` | `.aiwf/artifacts/quality/` |
| `.aiwf/checkpoints/` | `.aiwf/runtime/checkpoints/` |
| `.aiwf/history/` | `.aiwf/runtime/history/` |
| `.aiwf/internal/` | `.aiwf/runtime/internal/` |
| `.aiwf/state/` | `.aiwf/state/` (unchanged) |
| `.aiwf/assets/` | `.aiwf/assets/` (unchanged) |

---

## 4. Path Resolution Rules

1. Runtime code reads and writes only the current v2 paths.
2. Old paths are detected only by explicit layout migration or audit commands.
3. Normal status, activation, closure, evidence, testing, review, and report paths do not
   silently fall back to old locations.
4. `state/` paths are unchanged — no fallback needed.
5. Path constants are centralized in `aiwf_core/core/paths.py`.

---

## 5. Constraints

- Do NOT put markdown or prose in `state/`.
- Do NOT treat `artifacts/` as machine truth.
- Do NOT copy full Plan/Task/Milestone objects into `artifacts/`.
- Do NOT introduce a single `tree.json` in `state/` that copies all object content.
- `artifacts/` can be regenerated from `state/` + work history.
- `runtime/` can be cleaned up without affecting structural integrity.
- Migration must preserve content; never silently delete.

---

## 6. Status Display

- `status --prompt`: does NOT show layout version or zone structure.
- `status --debug`: may show `workspace_layout: v2` when migrated.
- Default: no layout information in prompt output.

---

## 7. Contract Tests

1. `init` creates new 5-zone layout
2. Old top-level dirs (`plans/`, `evidence/`, `reports/`, etc.) are not created by default
3. Path resolver returns new paths
4. Normal runtime does not read old paths as fallback
5. `migrate-layout --dry-run` lists expected moves
6. `migrate-layout` moves files correctly
7. Migration never moves `state/` or `assets/`
8. Artifact paths are distinct from state paths
9. `status --prompt` unchanged
10. Existing tests pass
