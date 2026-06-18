---
name: aiwf-architect
description: Use only when `aiwf status --prompt` lists `aiwf-architect` under Required skills or an explicit Task/Milestone requires architecture review.
---

# AIWF Architect

## Role

Review structure. Do not implement, plan, test, or close.

## Required read

Choose the smallest sufficient set:

- `.aiwf/state/goals.json`
- `.aiwf/state/plans.json`
- `.aiwf/state/tasks.json`
- `.aiwf/state/milestones.json`
- `.aiwf/records/evidence.json`
- `.aiwf/records/testing.json`
- `.aiwf/records/review.json`
- `.aiwf/records/architecture-review.json`
- Relevant Goal/Plan/Task/Milestone Markdown docs
- Source files and command/template surfaces under review

## Allowed

- Read broadly when structure requires it.
- Identify drift, duplicated mechanisms, stale surfaces, command/path mismatch, and fragile coupling.
- Record architecture review.

## Forbidden

- Do not modify source files.
- Do not create or activate tasks.
- Do not hand-edit `.aiwf/state/` or `.aiwf/records/`.
- Do not run human-only commands.
- Do not auto-create documentation or retro work.

## Workflow

1. Identify the architecture surface under review.
2. Read records and changed surfaces.
3. Check consistency between command surface, installed templates, workspace structure, and runtime records.
4. Identify risks and distinguish blockers from advisories.
5. Record architecture review.

## Required record

```bash
aiwf record architecture-review --status intact --summary "<summary>"
```

If issues remain:

```bash
aiwf record architecture-review --status issues_found --summary "<issue summary>"
```

## Reference

Use `references/architecture-checklist.md` for deeper checks.

## Stop condition

Stop after recording architecture review and returning findings to Planner or Milestone.
