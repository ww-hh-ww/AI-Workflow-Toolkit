# Design Review

Critique the design as expressed in Plans, Goals, and Tasks. You are checking
whether the design itself is sound, not whether the code implements it well
(that's code review).

## Plan Design

- Is the technical approach still sound given what we now know?
- Are the methods, data flows, and key interfaces described in Plan.md coherent?
- Do the technology choices and trade-offs still make sense?
- Is there a simpler approach that was overlooked?
- Has the implementation revealed flaws in the design that should be corrected?
- Are there gaps — things the plan didn't anticipate that now need design attention?

## Goal Design

- Are the Goals still the right capabilities? Have priorities shifted?
- Are Success Criteria still accurate and testable?
- Are Non-goals still holding, or has scope silently expanded?
- Do Goals need to be split, merged, or redefined based on what's been learned?

## Task Design

- Are Tasks decomposed at the right granularity?
- Are task boundaries clear, or do tasks overlap and create confusion?
- Are dependencies between tasks correctly captured?
- Are there tasks that should have been broken into multiple, or merged into one?

## Design Drift

- Has the implicit design (what the code actually does) diverged from the explicit
  design (what Plan.md and Goal.md say)?
- Are there design decisions made during implementation that should be promoted
  into Plan.md?
- Is the design documentation still a reliable map of the project?
