---
name: aiwf-planner-meta
description: Meta-critique, fix-loop handling, checkpoints, and architecture change requests
---

# AIWF Planner — Meta

## Meta-Critique (after Review, before close)

Disposition each adversarial observation: `aiwf state disposition-adversarial --id ADV-001 --disposition accepted --reason "..."`
(ignored | accepted | deferred | brief_updated). Pending dispositions block prepare-close.
Then record structured meta-critique: `aiwf state record-meta-critique --summary "..."`.

Then answer: did this Review expose Brief gaps? What should the NEXT task know?
Record key decisions via `aiwf goal decide --decision "..."`.

## Fix-Loop Handling

Example open:
```
aiwf fixloop open --route executor --reason "divide by -0 did not throw RangeError" \
  --required-fix "Add divisor validation" --required-verification "rerun npm test"
```

Read route from `.aiwf/state/fix-loop.json`:
- executor/tester: distribute required_fixes, preserve original contract
- route=planner: your decision needed — discuss with user before dispatching more work
- environment: tooling issue, not code; use the environment route and inspect `aiwf env show`

When `escalation_required=true`: STOP. Do NOT send more fixes. Re-evaluate scope/contract/environment. Consider rollback checkpoint.

## Checkpoint Policy

- L0/L1: no checkpoint needed by default. L2: risk-triggered (multi-file change, shared/core logic, public API, refactor touching existing behavior). Use `aiwf checkpoint create --mode patch`. L3: MUST create stash checkpoint (`aiwf checkpoint create --mode stash`).
- Executor must not commit. Commits are Planner/Close-stage actions only after closure is allowed and user confirms.

## Architecture Change Requests

When Executor reports "Architecture change needed": inspect reason + affected files + scope impact. Reject (overengineering), approve within scope (update brief + context), or ask user (scope/API/risk high). Do NOT silently accept.
Record decision: `aiwf arch-change decide --id <ACR-ID> --status accepted|rejected|deferred --decision "..."`, then update Architecture Brief and context before resuming.
