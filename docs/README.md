# AIWF Documentation

## Authoritative

- [Repository README](../README.md) — current roles, evidence model, lifecycle, commands, and write boundaries
- [Release Gate](../tests/v1_core/test_v1_release_gate.py) — current installed-surface smoke contracts
- Installed Skills and Agent prompts — operational role contracts for the selected host

## Current (living docs, maintained)

- [Lesson Admission Policy](current/AIWF-LESSON-ADMISSION-POLICY.md)
- [Prompt Cache Policy](current/AIWF-PROMPT-CACHE-POLICY.md)
- [Workspace Drift Policy](current/AIWF-WORKSPACE-DRIFT-POLICY.md)

## Legacy (pre-V1, not authoritative)

All docs in [legacy/](legacy/) are frozen pre-current reference material. They may contain retired roles, commands, paths, and workflow models. Do not use them as operational guidance.

The repository README and installed Skills are the operational guide. Use
`aiwf status --prompt`, `aiwf task proof`, and `aiwf doctor` for current runtime
state instead of copying hook or state-file inventories into documentation.
