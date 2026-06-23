# Design Review

Design critique is mission fit plus mission leverage. Mission is fixed; review
whether the current Goal tree and system mechanism can produce that mission.

## Mission Fit

- Does the current capability model, operating model, and information model
  directly produce the mission outcome, or optimize a nearby concern?
- Are capability boundaries drawn around mission outcomes, not convenient
  implementation chunks?
- Do the main abstractions, data flow, control flow, integration boundaries,
  and feedback loops make the mission easier to deliver and reason about?
- Is the central mission risk confronted on the main path, or deferred behind
  scaffolding, adapters, compatibility layers, or governance paperwork?
- Did implementation feedback reveal a wrong boundary, missing architectural
  constraint, or indirect route?
- Is there a goal-level completeness gap that prevents the stated mission from
  being true? If so, mark it for Planner disposition; do not edit the Goal tree.

## Mission Leverage

- Is there a simpler or more direct route to prove the mission outcome?
- Would a different capability model, operating loop, information structure,
  feedback point, or risk burn-down order move the mission further?
- If the user requested an external benchmark, do current domain expectations,
  standards, compliance facts, or the named baseline reveal a goal-level gap or
  stronger architecture mechanism?
- Is work accumulating around low-value edges while the central risk remains
  unproven?
- Should planned work be merged, cut, reordered, or replaced?
- Which small structural change would most increase the probability of mission
  success without changing the mission?

## Drift

- Has the implicit design in code diverged from the explicit design in
  Goal/Plan/Task/Milestone docs?
- Are Tasks decomposed around real capability increments, or around convenient
  local implementation chunks?
- Is the design documentation still a reliable map for the next Planner?
