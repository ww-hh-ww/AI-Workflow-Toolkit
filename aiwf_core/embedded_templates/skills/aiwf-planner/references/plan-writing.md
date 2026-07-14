# Plan.md Writing Guide

Plan.md defines the mechanism and technical direction that make one Goal true.
It is not only a Task list.

## Frontmatter

Keep `id`, `type`, `title`, `status`, `goal_id`, dependencies, and milestone
links accurate. Use CLI when supported; otherwise edit Markdown and run
`aiwf sync`.

## Must Say

- Goal Link: which capability this Plan makes true.
- Current Problem: the verified limitation or risk being changed.
- Target Mechanism: where responsibility lives, how the parts connect, and the
  main data or control path from entry to consumer to observable result.
- Key Decisions: important technical choices, their source-backed basis, and
  credible alternatives rejected.
- Delivery: ordered Tasks or experiments that burn down risk and prove the
  mechanism works together.
- Validation: how the largest uncertainties and real main path will be tested.

Use clear headings that fit the Plan. The names above are not a required form.

## Add Only When Useful

- Consistency Contract when later work crosses a shared data, API, state,
  lifecycle, permission, timestamp, ID, or error-semantics boundary. State the
  shared truth, owner, consumer, proof, and source.
- Old Path / Migration when this Plan replaces or competes with an existing
  path. State removal, deprecation, compatibility, or ownership.
- Delivery surfaces when the change really affects installation, configuration,
  migration, deployment, or public documentation. Include those surfaces in
  the mechanism and Tasks instead of leaving them for later.
- Support Boundary when behavior varies by input, platform, or environment.
- Non-goals when nearby work could be mistaken as part of this Plan.
- Open Questions when an unresolved fact changes the mechanism or Task order.

Omit empty optional sections. An important Unknown blocks implementation; it
does not become a placeholder Task.

## Choosing Direction

Do not choose a method from familiarity alone. Inspect representative inputs,
difficult cases, operating constraints, and expected outcomes. Use code,
observed evidence, a relevant standard, an experiment, or an explicit user
decision as the basis.

If credible mechanisms cannot yet be distinguished, return to Planner
exploration before creating implementation Tasks.

Do not mirror the Goal tree in code. Choose module boundaries by responsibility,
the data and state each part owns, dependency direction, failure ownership, and
what changes together. Put a decision likely to change behind a stable boundary
only when that reduces real coupling.

For structural work, inspect only the views that matter: code responsibilities
and dependencies; runtime data, control, state, and failure paths; deployment
and integration. A Plan may cross modules, and one module may support several
Goals.

Do not write only "fast", "reliable", "secure", or "easy to change". Describe
the real condition, expected response or threshold, and the tradeoff that
changes the design.

Decide public behavior, support boundaries, shared interfaces, and Task order
here. Leave local and reversible code choices to Executor.

## Quality Check

- Does the Plan explain a mechanism, not just list work?
- Does the main path reach the Goal's hardest risk?
- Do module boundaries contain change instead of copying Goal or Task shape?
- Are the conditions and tradeoffs that change the design testable?
- Are shared truths and old paths owned when they matter?
- Does Task order prove uncertainty early and integration before completion?
- If this Plan may run beside another, can each be implemented, tested, and
  reviewed independently? Check shared files, responsibilities, interfaces,
  state, runtime paths, merge order, and combined proof.
- Could each Task deliver mission progress without inventing missing design?
