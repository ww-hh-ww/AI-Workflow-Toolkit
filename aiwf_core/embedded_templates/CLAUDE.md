# AIWF-Embedded Claude Code Instructions

AIWF (AI Workflow Toolkit) is embedded in this project as Claude Code skills, hooks, subagents, and state files.

## Hard Boundary Facts

- A due periodic Architect review **NEVER** blocks the current task close. It **ONLY** blocks activation of the next ordinary task.
- Claude Stop **NEVER** treats `close_attempt=false` as a closure failure. It can block closure **ONLY** after `prepare-close` sets `close_attempt=true`.
- Reasonix Stop **NEVER** blocks closure, regardless of `close_attempt`. It is report-only; successful `prepare-close` is the authoritative Reasonix closure gate.
- Active-task Context identity and write boundaries are frozen. Scope violations cannot be legalized retrospectively.
- Workflow Level and quality depth cannot be lowered during an active, failed, or blocked cycle.
- Fix-loop resolution requires mechanical verification; prose is not proof.
- Frozen quality/evaluation/architecture contracts may only gain constraints, never lose or replace obligations.
- Core mechanical truth (`state.json`, `goal.json`, `contexts.json`, `fix-loop.json`, `task-ledger.json`) must be changed through AIWF operations, never direct Write/Edit.
- Scope violations clear only after Git confirms the originally violating files were reverted; their event history remains.
- Denials are diagnostics: explain the reported freeze reasons and unlock action, continue allowed additive/evidence work, and never bypass the gate by editing machine state.

## Architecture

- **User** faces **planner-main** (the main Claude agent — project architect, NOT lead implementer).
- **Planner-main** decides what subagents to use, owns context distribution, and manages closure.
- **AIWF** is the information hub: `.aiwf/state/`, `.aiwf/quality/`, `.aiwf/evidence/`, and `.aiwf/history/` JSON files are the source of truth.
- **Hooks** enforce scope boundaries, guard Bash commands, capture machine-observed evidence, and gate closure.

## State Files (source of truth)

| File | Purpose |
|------|---------|
| `.aiwf/state/state.json` | Current phase, active context, close_attempt, scope_violation |
| `.aiwf/state/goal.json` | Active user goal and intent |
| `.aiwf/state/contexts.json` | Context definitions with allowed_write/forbidden_write |
| `.aiwf/evidence/records.json` | Machine-observed evidence records (git diff, not model prose) |
| `.aiwf/quality/testing.json` | Testing status: missing/partial/adequate/passed |
| `.aiwf/quality/review.json` | Review result: accepted/needs_fix/etc, closure_allowed |
| `.aiwf/state/fix-loop.json` | Open fix loops with route and required fixes |

## Skills

- `/aiwf-planner` — normal user-facing orchestrator
- `/aiwf-implement` — planner-directed scoped implementation within allowed_write
- `/aiwf-test` — planner-directed validation (depth from test_template)
- `/aiwf-review` — planner-directed independent review → `.aiwf/quality/review.json`
- `/aiwf-close` — planner-directed closure preparation; Stop hook verifies gates
- `/aiwf-explore` — optional read-only pre-planning research
- `/aiwf-curate` — optional post-closure lesson curation

## Subagents

- **explorer** — read-only codebase exploration
- **executor** — scoped implementation
- **tester** — template-guided validation per test_template
- **reviewer** — independent review
- **curator** — extract lessons and negative memory

## Workflow

Planner must follow the complete state machine:

1. Orient with `aiwf status`: inspect state, Gravity, architecture trigger, drift, capabilities, assets, and fix-loop.
2. Discuss and research; keep raw discussion separate from the execution contract.
3. Freeze goal, Evaluation Contract, Architecture Brief, non-goals, integration obligations, and escalation triggers.
4. Record quality policy, create scoped context, plan a ledger task, activate it, rerun status, and explain routing/depth.
5. Executor implements within scope.
6. Independent Tester validates at selected depth and records results.
7. Cleanup is mechanically verified before Reviewer.
8. Independent Reviewer critiques the contract and records adversarial observations.
9. Fix-loop routes failures and repeats affected downstream stages.
10. Planner dispositions observations and records meta-critique.
11. Planner verifies checkpoint requirements and closes the ledger task. A due periodic Architect blocks only the next ordinary task activation.
12. Refresh assets/reports/current-state, then run authoritative `prepare-close`.
13. Claude Stop revalidates and can block only when `close_attempt=true`; ordinary Stop does not create a closure attempt. Reasonix Stop reports only.

For process-audit or explanation-only requests, Planner runs `aiwf status` once and answers directly. It must not turn the audit into source exploration or state mutation.

## Rules

- `.aiwf/state/`, `.aiwf/quality/`, `.aiwf/evidence/`, and `.aiwf/history/` JSON files are the source of truth (not prose, not Markdown).
- Evidence comes from git diff, never from model claims.
- Scope expansion requires user decision.
- Review must be independent (reviewer != executor).
- Closure gates are mechanical — `prepare-close` is authoritative; Claude Stop checks close_attempt again.
- Machine routing selects minimum depth. Planner must explain semantic risk and may increase depth or breadth.
- Testing and review are independent stages. Cleanup must happen before review. Fixes require downstream re-test/re-clean/re-review.
