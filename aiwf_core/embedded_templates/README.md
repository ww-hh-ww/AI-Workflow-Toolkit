# AIWF Workspace

This directory is AIWF's governance workspace. Humans do not normally read raw `.aiwf` files.
Ask the agent, run `aiwf status`, or read narrative docs when you need a human explanation.

## Zones

- `state/` — machine state: registries, active IDs, derived links, gate inputs. JSON only.
- `records/` — current implementation, testing, review, and event records.
- `goals/` — goal narrative docs (Markdown).
- `plans/` — plan narrative docs (Markdown).
- `tasks/` — task narrative docs (Markdown, execution contract).
- `milestones/` — milestone narrative docs (Markdown).
- `memory/` — Planner's tiny long-term planning memory: `project-facts.md`,
  `MEMORY.md`, and optional `notes/`.
- `config/` — configuration (skill-map, command-policy, write-policy,
  agent-models).
- `runtime/internal/` — toolkit-path, drift, hook, and agent logs.

## Human Entry Points

- `aiwf status` — default control panel.
- `aiwf doctor` — installation health check.
- `aiwf status --debug` — full state dump for debugging.
- Narrative docs in `goals/`, `plans/`, `tasks/`, `milestones/` — human-readable project structure.
- `memory/project-facts.md` — tiny Planner memory; keep only durable planning facts.

## Rules

- Do not hand-edit JSON machine state or records.
- State changes go through `aiwf` commands and hooks.
- Markdown narrative docs are the semantic contracts. JSON supports gates,
  routing, proof, and status; it is not the semantic contract.
- Memory is not a document dump. Planner checks it before handoff and when work
  returns, then keeps it, changes it, deletes it, or adds to it only when durable
  planning facts require that.
- `runtime/` can be inspected for debugging but should not drive planning by itself.
