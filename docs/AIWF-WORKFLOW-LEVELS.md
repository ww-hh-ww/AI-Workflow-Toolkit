# AIWF Workflow Levels

Date: 2026-06-01

## Level Summary

| Level | Time | Subagents | Adversarial | Gates | Best For |
|-------|------|-----------|-------------|-------|----------|
| **L0_direct** | ~30s | executor only | off | scope + evidence + test + review-lite + close | trivial edits, rename, typo |
| **L1_review_light** | ~90s | executor + reviewer-light | gravity-triggered | L0 + reviewer-light tests + light gates | 2-file feature, small fix |
| **L2_standard_team** | ~6min | executor + tester + reviewer | on (review + test) | full gates, adversarial observations | multi-module, API change |
| **L3_full_power** | variable | full team + architect | forced on | full + checkpoint + human decisions + architect | architecture, security, publish |

## Routing Score

```
score = file_count + cross_module + semantic_change + security_risk + ...
0–1  → L0_direct
2–3  → L1_review_light
4–6  → L2_standard_team
7+   → L3_full_power
```

Hard upgrades:
- security/data risk → L3
- cross-module + semantic → ≥L2
- prior fix-loop → ≥L2
- user decision needed → ≥L2

## Request Mode and Workflow Pattern

Workflow Level answers "how deep must validation/review be once execution starts." Request mode answers "are we executing yet?"

| Mode | Meaning | Execution allowed |
|------|---------|-------------------|
| `discussion` | compare ideas, explain process, answer questions | no |
| `clarification` | requirements grill, acceptance criteria, non-goals, risk decisions | no |
| `research` | external or broad read-only research before contract freeze | no |
| `spike` | feasibility exploration that must later convert to execution | no final close |
| `execution` | freeze contract, activate scoped task, write project code | yes |

Workflow patterns (`linear`, `clarification_first`, `research_first`, `spike_first`, `adversarial_early`) shape the route and role breadth. They do not lower Level, skip cleanup-before-review, weaken Tester/Reviewer duties, or replace `.aiwf` JSON gates.

This absorbs useful ideas from dynamic workflows without turning AIWF into a fully open-ended multi-agent scheduler: topology is chosen when uncertainty requires it, while mechanical contracts still preserve closure and evidence.

## Adversarial Mode Trigger

Adversarial review and testing are triggered by three overlapping conditions (any one is sufficient):
1. **Workflow level**: L2+ default on
2. **Task type**: security_sensitive, refactor, api_endpoint, data_migration → forced on
3. **Gravity signals**: hotspot count ≥ 3 hitting task files, fix_loop_trend escalate, architecture_drift present → auto on

Planner can add adversarial mode to L0/L1. Planner cannot disable it when conditions 2 or 3 are met.

## Emergent Gravity

Gravity is a pure function that auto-scales with project age:
- `history_weight = min(closed_tasks / 20, 1.0)` — grows from 0.0 to 1.0
- Hard constraints (≥3 same-file hotspot, no Architecture Brief) → block activation
- Soft warnings (2x hotspots, testing debt, mild drift) → advisory only
- Architecture trend signals (module coupling, surface expansion) → context messages

Gravity serves three consumers:
1. UserPromptSubmit → advisory display
2. start_context → ≤3 notes injected
3. activation_blockers → mechanical gate

## Periodic Architect

`/aiwf-architect` is a periodic role, not a per-task role:
- Triggers: every ~10 closed tasks, gravity ≥ 0.5, PROJECT-MAP stale >30 days, 3+ escalate signals, user request
- Scope: full project read-only
- Output: PROJECT-MAP updates, architecture trends to quality-digest
- Throttled: won't re-trigger within 5 tasks of last review

## Key Principle

**AIWF is not always full process. It scales from executor-only to full team based on risk. The protection grows with the project — early projects feel almost nothing, mature projects feel the weight of their own history.**

- Default to the lowest viable level.
- Escalate only when risk triggers it.
- Adversarial thinking is not a switch — it emerges with level, task type, and gravity.
- All levels preserve invariant gates: scope → evidence → test → review → close.
