# Governance Truth Review

Use this when the selected lens is `governance-truth`.

AIWF structure is not the mission. It is the map for the next Planner. If the
map makes progress look safer than the code and evidence prove, report it.

## Tree Shape

Ask:

- Does the Goal tree describe mission capabilities?
- Are leaf Goals real capabilities, not implementation details?
- Are there overlapping Goals with unclear ownership?
- Are there missing leaves that the mission or selected slice requires?
- Is the tree shallow enough for the next Planner to navigate?

## Alignment

Ask:

- Does each level do its own job: Goal, Plan, Task, Milestone?
- Are Plans grouped around useful capability or module boundaries?
- Are Plan dependencies real execution gates?
- Are Task dependencies the order inside a Plan?
- Does the Milestone represent a real capability increment?
- Does any structure hide deferred risk that Planner must see?

## State Drift

Ask:

- Do `ready`, `cancelled`, `closed`, `interrupted`, and other visible states
  match the Markdown story?
- Do completed Tasks and Milestones still lack evidence, testing, review, or
  architecture proof?
- Were structure changes made in Markdown but not through the supported
  CLI/state path?
- Were CLI/state changes made without updating the visible Markdown story?
- Would a fresh Planner choose the right next action from this state?
