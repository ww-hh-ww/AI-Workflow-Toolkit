# Code Implementation Review

Critique the current code implementation against the design described in Plan.md
and Goal.md. You are checking whether the implementation is well-built under the
current design, not whether the design itself is right (that's design review).

## Module Structure

- Does the module layout make sense? Are related things together?
- Are module responsibilities clear, or are modules doing too many unrelated things?
- Are there modules that should be split? Modules that should be merged?

## Abstraction Quality

- Are abstractions holding their weight, or are they crumbling under new requirements?
- Is there unnecessary abstraction — layers that don't carry their own weight?
- Are there missing abstractions where duplicated logic should be unified?
- Does each abstraction have a single clear responsibility?

## Decay

- Dead code: functions, classes, config with zero callers. Distinguish:
  - **Abandoned**: old code whose callers were removed. Should be deleted.
  - **Unwired**: new code built for a purpose but never connected. Bug, not cleanup.
- Duplicated mechanisms: two or more paths doing the same thing. Consolidation candidates.
- Stale surfaces: commands, templates, or config keys that no longer match what the code does.
- Vestigial patterns: old conventions half-removed, leaving inconsistent style.

## Coupling

- Fragile coupling: changing A breaks B, but the connection isn't visible.
- Cross-layer calls: is anything reaching past a module boundary to call internals?
- Import chains that pull in more than they need.
- Circular dependencies or near-circular import paths.

## Interface Consistency

- Do new interfaces follow the same conventions as existing ones?
- Are parameter shapes, return types, and error patterns consistent across modules?
- Is one module using snake_case while another uses camelCase for the same concept?
- One inconsistent interface is a wart; ten is a codebase no one can navigate.

## Drift from Design

- Has the code implementation drifted from what Plan.md described?
- Were architectural decisions made during implementation that were never written down?
- Does the code reveal a different design than the docs describe?
