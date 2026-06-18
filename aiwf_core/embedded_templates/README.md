# AIWF Workspace

This directory is AIWF's governance workspace. Humans do not normally read raw `.aiwf` files.
Ask the agent, run `aiwf status`, or read narrative docs when you need a human explanation.

## Zones

- `state/` — machine truth: registries, canonical state, gate inputs. JSON only.
- `records/` — evidence, testing, review, architecture-review, events. JSON only.
- `goals/` — goal narrative docs (Markdown).
- `plans/` — plan narrative docs (Markdown).
- `tasks/` — task narrative docs (Markdown, execution contract).
- `milestones/` — milestone narrative docs (Markdown).
- `config/` — configuration (skill-map, command-policy).
- `runtime/internal/` — toolkit-path, drift, diag, routing-debug.

## Human Entry Points

- `aiwf status` — default control panel.
- `aiwf doctor` — installation health check.
- `aiwf status --debug` — full state dump for debugging.
- Narrative docs in `goals/`, `plans/`, `tasks/`, `milestones/` — human-readable project structure.

## Rules

- Do not hand-edit JSON machine truth.
- State changes go through `aiwf` commands and hooks.
- Markdown narrative docs are semantic contracts, not machine truth.
- `runtime/` can be inspected for debugging but should not drive planning by itself.
