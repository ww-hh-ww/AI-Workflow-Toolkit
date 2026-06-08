# AIWF Development Instructions

AIWF is the embedded governance and visibility layer for long-horizon Claude Code and Reasonix engineering sessions.

## Runtime Protocol

On every new turn, resume, compaction, or task continuation, run `aiwf status` before deciding the next workflow action. Obey `Recovery`, `PRIMARY`, and `REQUIRED NEXT` unless an AIWF command resolves the blocker. If your intended action conflicts with status, stop and explain the conflict instead of relying on memory.

## Product Boundary

- Coding agents own engineering intelligence: inspect, reason, design, edit, run, test, and debug.
- AIWF owns governance: machine-readable state, scope, evidence, routing, testing discipline, review gates, cleanup, closure, and carry-forward.
- `.aiwf/*.json` is the source of truth. Model memory and prose are advisory.
- Do not reintroduce `.ai-workflow/`, an external orchestrator, managed runtime, fake terminal executor, or one-shot deterministic planner.

## Supported Mainlines

Claude Code:

```bash
aiwf install claude
claude
/aiwf-planner "describe the goal"
```

Reasonix:

```bash
aiwf install reasonix
reasonix code .
/skill aiwf-planner "describe the goal"
```

## Required Flow

```text
Planner discussion and research
-> Evaluation Contract and Architecture Brief
-> Context dispatch and task activation
-> Scoped implementation
-> Independent testing
-> Cleanup before review
-> Adversarial review
-> Fix-loop replay when needed
-> Planner meta-critique
-> Task close
-> prepare-close
-> Current-state and report carry-forward
```

Claude Stop may revalidate closure only after `close_attempt=true`. Reasonix Stop is report-only; successful `prepare-close` is authoritative.

## Development Rules

- Every new workflow rule needs a contract test.
- Preserve Planner-first interaction and independent Tester/Reviewer depth.
- Keep Gravity pure and read-only.
- Keep modules separated; split modules approaching 300 lines unless clearly justified.
- Never auto-commit or auto-push from Executor or Close.
