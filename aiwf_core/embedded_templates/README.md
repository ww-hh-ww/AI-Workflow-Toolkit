# AIWF Workspace

This directory is AIWF's governance workspace. Humans do not normally read raw `.aiwf` files.
Ask the agent, run `aiwf status`, or read generated reports when you need a human explanation.

## Zones

- `state/` — machine truth: registries, canonical state, gate inputs. JSON only.
- `artifacts/` — human projections: plans, reports, reviews, evidence summaries.
- `runtime/` — execution traces: history, checkpoints, internal files, caches.
- `assets/` — input assets referenced by AIWF, such as environment/capability data.
- `archive/` — deprecated, migrated, or superseded material.

## Human Entry Points

- `aiwf status` — default control panel.
- `.aiwf/artifacts/reports/当前状态.md` — carry-forward summary, when generated.
- `.aiwf/artifacts/reports/闭合报告.md` — closure basis, when generated.
- `.aiwf/artifacts/reports/质量摘要.md` — cross-task quality signals, when requested.
- `.aiwf/artifacts/plans/*.md` — compact plan artifacts, not machine truth.

## Rules

- Do not hand-edit JSON machine truth.
- State changes go through `aiwf` commands and hooks.
- Markdown under `artifacts/` is readable projection, not source of truth.
- `runtime/` can be inspected for debugging but should not drive planning by itself.
