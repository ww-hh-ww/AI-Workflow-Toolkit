# Design Review

Use this when the selected lens is `mission-mechanism`.

The mission is fixed. Do not invent a larger product strategy. Ask whether the
current structure is the right road to that mission.

## Mission Fit

Ask:

- Does the current capability boundary match what the mission needs?
- Does the main path hit the central mission risk, or spend most effort around
  the edges?
- Do the abstractions, module boundaries, data flow, and control flow make the
  mission easier to finish?
- Do runtime entry points, deployment, integration, and user workflow support
  the mission?
- Does the evidence prove the mission direction, not just the existence of a
  component?
- If work continues in this shape, will it get closer to the mission or become
  heavier and more indirect?

If the current path is good, say why. If it is not, name the structural reason.

## Mission Leverage

Ask:

- Is there a shorter way to prove the mission outcome?
- Would a different capability, module, agent, state, or integration boundary
  make the problem simpler?
- Can the biggest uncertainty be tested earlier?
- Is a compatibility layer, process layer, or abstraction hiding the main path?
- What one trace, metric, integration test, or evidence point would make future
  planning much clearer?
- Should work be deleted, merged, reordered, or replaced?
- Is each new mechanism clearly increasing mission progress?

This is not ordinary optimization. Only recommend a better path when it helps
the fixed mission.

## Capability Gaps

Think broadly, then report only gaps that matter to the selected review:

- What capability does the fixed mission require that is still missing?
- What missing capability is directly revealed by the completed slice?
- If external comparison was requested, what does it reveal and what is the
  consequence of ignoring it?

Label a gap that comes only from external comparison. Do not hide a mission
gap because current Goals or Plans forgot it, and do not turn mature-product
features into automatic requirements.

## External Comparison

Use WebSearch only when the prompt asks for external comparison: current domain
expectations, standards, compliance facts, or a named project/product baseline.

When external comparison finds something:

- say what the outside source suggests;
- say why it matters for this mission or slice;
- say the risk of ignoring it;
- say when it would become required.

Do not turn outside comparison into a new mission.
