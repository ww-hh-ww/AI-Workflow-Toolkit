# AIWF Development Instructions

## Product Goal

AIWF is not a replacement for Claude Code.

AIWF is the embedded governance and visibility layer around native Claude Code sessions for long-horizon engineering work. It should improve:

- context management
- long-horizon planning
- evidence chains
- deep testing discipline
- review gates
- cleanup and closure
- white-box visibility

AIWF must not reduce Claude Code's native ability to inspect project files, understand architecture, search code, edit code, run commands, analyze errors, iterate after failures, design tests, and explain tradeoffs.

## Architecture Rule

Intelligence belongs to Claude Code.
Governance belongs to AIWF.

Do not turn AIWF into a fake runtime, managed terminal executor, or low-capability agent replacement.

## Source of Truth

The source of truth is the `.aiwf/*.json` state files, not model session memory.

Prompt files define desired behavior and role tendencies. Machine-readable `.aiwf` state files enforce workflow truth. If a rule affects correctness, closure, scope, evidence, testing, review, cleanup, or fix-loop routing, it must be represented as a machine-readable contract and enforced by code/tests.

## Required Flow

```text
Install
-> Planner discussion + pre-planning research
-> Quality policy and evaluation contract
-> Architecture Brief (structural boundaries)
-> Context dispatch (allowed_write / forbidden_write)
-> Scoped implementation (Executor)
-> Independent testing (Tester, adversarial mode L2+)
-> Adversarial review (Reviewer — contract critique)
-> Planner meta-critique (disposition adversarial observations)
-> Cleanup before review
-> Fix loop if needed
-> Closure (prepare_close + Stop hook dual gate)
-> Report/current-state for the next cycle
```

Review must not happen before cleanup.
Testing must not be reduced to a review checklist.
Adversarial observations must be dispositioned before prepare-close.
Architecture review triggers periodically (~10 tasks, gravity ≥ 0.5, PROJECT-MAP stale).

## Correct Mainlines

The supported mainlines are embedded Claude Code and embedded Reasonix:

```bash
aiwf install claude
claude
/aiwf-planner "describe the goal"
```

```bash
aiwf install reasonix
reasonix code .
/skill aiwf-planner "describe the goal"
```

Do not restore the removed external orchestration path. In particular, do not reintroduce:

- `.ai-workflow/`
- legacy runner
- managed runtime
- fake terminal executor
- external `aiwf planner` / `aiwf handoff` / `aiwf action` workflows
- one-shot deterministic planner as default intelligence
- automatic task generation on first user message
- review-before-cleanup flow
- testing-as-checkbox flow

## Code Quality

Keep modules small and separated. Do not mix planner, state operations, context dispatch, executor policy, testing, review, cleanup, closure, hooks, and UI.

A module approaching 300 lines should be split unless there is a clear reason.

## Testing Expectations

Every new workflow rule needs a contract test.

Tests must cover:

- happy path
- wrong order rejection
- stale state handling
- planner rebase behavior
- context dispatch behavior
- no removed external runtime resurrection

## Key Modules

- `task_gravity.py` — Emergent historical pressure (pure function, no writes)
- `task_ledger.py` — Multi-task ledger with execution-window gates
- `cross_task_quality.py` — Cross-task quality signals from task-history
- `current_state.py` — Mechanical carry-forward summary generation
- `closure_contract.py` — Dual-gate closure enforcement (prepare_close + Stop hook)
- `quality_policy.py` — L0-L3 workflow level policies with adversarial flags
- `routing.py` — Resource-based routing with cross-task escalation
- `state_ops.py` — State mutation helpers (skills call these, never hand-edit JSON)
- `state_schema.py` — Schema defaults and validation for all .aiwf/*.json files

## Done Means

A change is done only when:

- embedded self-tests pass
- release audit passes
- removed external paths are not reintroduced
- workflow remains model-centered
- Claude Code native capabilities are preserved
- adversarial observation disposition is machine-readable (not free text alone)
- gravity is pure (no side effects in read paths)
