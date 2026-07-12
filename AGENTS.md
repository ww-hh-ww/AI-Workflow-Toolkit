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

Markdown holds mission, structure, and task meaning. JSON under `.aiwf/state/` and `.aiwf/records/` holds runtime status and concise records. State changes go through the CLI; `aiwf sync` compiles supported Markdown frontmatter into JSON.

## Required Flow

```text
Install
-> Planner discussion + pre-planning research
-> Mission, Goal, Plan, and Task design
-> Activation critique against project reality
-> Scoped implementation (Executor)
-> Independent testing (Tester)
-> Independent review (Reviewer)
-> Planner disposition and Closure Calibration
-> Fix loop if needed
-> Closure (`aiwf task close` + Stop hook)
-> Task.md records the actual outcome for the next cycle
```

Testing must not be reduced to a review checklist.
Adversarial observations must be dispositioned before task close.

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

Keep modules small and separated. Do not mix planning, state operations, role dispatch, write policy, testing, review, closure, hooks, and UI.

A module approaching 300 lines should be split unless there is a clear reason.

## Testing Expectations

Every new workflow rule needs a contract test.

Tests must cover the happy path, wrong-order rejection, stale state, installed
Claude hooks, and absence of the removed external runtime.

## Key Modules

- `task_ledger.py` — Multi-task ledger with execution-window gates
- `closure_contract.py` — Stop hook enforcement while a reviewed Task still needs close
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
