---
name: aiwf-architecture-doc
description: Architecture snapshot writer — generate a comprehensive architecture document from current project evidence
---

# AIWF Architecture Documentation

This skill writes **summary architecture snapshots**. It is separate from
growth documentation and periodic architecture review.

## Documentation Surfaces

AIWF keeps two documentation modes alive:

1. **Growth documentation** — updated during ordinary work when
   `Impact.docs=yes`. Use `/aiwf-planner-docs`. It grows with the code and stays
   close to the changed subsystem.
2. **Architecture snapshot** — generated at a deliberate boundary. Use this
   skill. It summarizes the current system as a whole for handoff, milestone,
   release, onboarding, or user-requested architecture understanding.

Do not replace one with the other. Growth docs keep daily knowledge current;
architecture snapshots make scattered truth readable at a stable boundary.

## When To Trigger

Use this skill when one of these is true:

- the user explicitly asks for a detailed architecture document
- milestone acceptance, release, or handoff needs a human-readable system view
- periodic Architect review says PROJECT-MAP and code have converged enough for
  a stable snapshot
- an external reviewer or new contributor needs the current system explained
- a large refactor/migration has finished and old architecture notes are stale

Do **not** run this on every task. If the current work only changed one local
subsystem, update growth docs instead.

When the snapshot is a hard requirement, record it before writing:

```bash
aiwf architecture-doc require --reason "milestone handoff"
aiwf architecture-doc status
```

## Required Inputs

Before writing, inspect current evidence rather than relying on memory:

- `.aiwf/artifacts/reports/项目地图.md`
- `.aiwf/assets/project-map.json`
- `.aiwf/state/goals.json`
- `.aiwf/state/plans.json`
- milestone integration and architecture review records, when present
- current README and `docs/`
- source entrypoints, package/config files, and tests relevant to the system

If PROJECT-MAP is missing or stale, say so and update it first when the Plan
scope allows documentation work. If it cannot be updated, include a visible
`Evidence Gaps` section in the snapshot.

## Output Location

Write the main snapshot to:

```text
.aiwf/artifacts/reports/架构详细设计.md
```

If the user asks for a public-facing copy, mirror or adapt it under `docs/`.
The `.aiwf` report remains the AIWF-governed source for lifecycle evidence.

Users should not have to browse `.aiwf/` manually. After writing the snapshot,
summarize the result in conversation and point to the stable artifact path. For
regular project readers, create or update a `docs/` copy when the Plan scope
allows it.

After writing, validate and satisfy the machine contract:

```bash
aiwf architecture-doc validate
aiwf architecture-doc satisfy
```

If Planner decides a snapshot is not appropriate yet, waive with a reason:

```bash
aiwf architecture-doc waive --reason "project still changing; PROJECT-MAP is enough for this cycle"
```

## Snapshot Structure

Use this structure unless the project clearly needs a smaller form:

1. Project Overview
2. Architecture Summary
3. Technology Stack and Runtime Assumptions
4. Capability / Goal Tree Overview
5. Module and Directory Responsibilities
6. Entry Points and Public Interfaces
7. Data Model and State Ownership
8. Key Flows
9. Dependency and Boundary Map
10. Testing, Review, and Quality Gates
11. Operational Notes
12. Known Risks, Evidence Gaps, and Open Decisions
13. Evidence Manifest

The document should explain architecture, not list every file. Include diagrams
when they clarify control flow or dependencies.

## Evidence Rules

- Every major claim must be traceable to source files, PROJECT-MAP, Goal Tree,
  Plan/Task evidence, tests, or architecture review records.
- Distinguish confirmed facts from inferred architecture.
- Do not invent historical intent when the evidence only shows current shape.
- If code and PROJECT-MAP disagree, state the disagreement instead of smoothing
  it over.
- Do not mark the snapshot complete while critical entrypoints, state files, or
  main flows remain unchecked.

## Relationship To Other AIWF Surfaces

- PROJECT-MAP is the durable structure index and direction note.
- Growth docs are subsystem-local maintenance docs.
- Architect review finds drift and forward risks.
- This skill turns the current evidence set into a readable architecture
  snapshot at a boundary.
