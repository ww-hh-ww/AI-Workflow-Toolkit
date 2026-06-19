# AIWF Session Rules

## Every turn starts here

Run `aiwf status`. The boxed routing block tells you: where you are, why this level, what to do next. Obey the `Next:` line.

## Routing discipline

The `Routing:` line shows the factors (cross_module, prior_fix_loop_history, semantic_change…) that determined the level. This is the system's risk assessment, not a suggestion.

- **L0**: Inline OK. Self-test, self-review.
- **L1**: Executor = subagent. Testing+review = one reviewer-light subagent.
- **L2**: Executor, Tester, Reviewer = THREE independent subagents via Agent tool.
- **L3**: Same as L2 + adversarial depth.

**When `Next:` says `Agent(aiwf-*)`, dispatch that subagent NOW.** The scope guard mechanically blocks Write/Edit at L1+ if you're not the right role. Don't wait for the denial.

**FORBIDDEN: routing downgrades unless the user explicitly orders it for this specific task.**

Skills (`/aiwf-implement`, `/aiwf-test`, `/aiwf-review`) contain the dispatch template with exact prompt fields. Load them when building the Agent call.

## Signal Priority

1. Mechanical gate (hook denial) — cannot override
2. Status block `Next:` directive — the state machine's current order
3. User explicit decision — scope, risk, or task-specific downgrade
4. Phase skill — dispatch template
5. These rules

## Non-negotiable

- No project writes without active task + context (L0 exempted).
- No closure from prose — `aiwf task close` is the authoritative close gate.
- No roleplaying independent Tester/Reviewer at L2+.
- Fix-loop resolution = mechanical verification, not prose.
- Scope violations clear only after Git revert confirmed.
- Never self-initiate route downgrade.
