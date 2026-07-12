# Goal.md Writing Guide

Goal.md defines one capability the fixed mission needs. It says what the system
must become able to do, not how to build it.

## Frontmatter

Keep `id`, `type`, `title`, `status`, and real parent/link fields accurate.
Use CLI for supported changes; otherwise edit Markdown and run `aiwf sync`.

## Must Say

- Mission Capability: what capability is gained and who or what uses it.
- Success: observable mission-path behavior that proves the capability exists.
- Structural Home: why this capability belongs here and how it relates to its
  parent or neighboring Goals.
- Missing Pieces: capability gaps that prevent the Goal from being true.
- Plan Handoff: what later Plans must preserve, decide, or prove.

Use any clear headings. The names above are not a required form.

## Add Only When Useful

- Non-goals when an adjacent capability could be confused with this Goal.
- Capability Relations when another Goal supports, blocks, or overlaps it.
- Core Files after project setup or a meaningful structural change.
- Human Decisions when a user choice materially shapes the boundary.
- Known/Unknown when an unresolved fact changes planning.

Omit empty optional sections. Do not add `None` merely to fill space.

## Quality Check

- Is this a capability rather than a phase, tool, module, or method?
- Does success prove mission behavior rather than artifact existence?
- Are adjacent capabilities and missing pieces visible where they matter?
- Could a Planner choose a technical mechanism without guessing the boundary?

If an important boundary is Unknown, say what must be learned before planning.
