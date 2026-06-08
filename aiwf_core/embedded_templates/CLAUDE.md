# AIWF-Embedded Claude Code Instructions

AIWF (AI Workflow Toolkit) is embedded in this project as Claude Code skills, hooks, subagents, and state files.

## Runtime Protocol

On every new turn, resume, compaction, or task continuation:

1. Run `aiwf status` before deciding the next workflow action.
2. Obey `Recovery`, `PRIMARY`, and `REQUIRED NEXT` unless you resolve the blocker with an AIWF command.
3. If your intended next action conflicts with AIWF status, stop and explain the conflict.
4. If status reports `plan_only_drift`, stop expanding the plan and freeze the execution contracts/context/task activation before project writes.
5. If Claude Code auto mode blocks an AIWF lifecycle command, ask the user to approve that exact governance command and do not bypass it by hand-editing `.aiwf` state.
6. Do not roleplay Executor, Tester, or Reviewer in planner-main when the selected workflow level requires an independent role.
7. Do not move to Review before cleanup, and do not close from prose. Use task close plus `prepare-close`.

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
| `.aiwf/plans/*.md` | Human-readable task plans; continuity only, not mechanical truth |
| `.aiwf/research/external.json` | Low-trust external research and Planner promotion decisions |

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

## Request Modes and Advisory Templates

Planner must classify uncertainty before execution:

- `discussion`, `clarification`, and `research` are non-execution modes and must not activate implementation tasks.
- `spike` explores feasibility and must be followed by `execution` before final implementation closes.
- `execution` is the only mode that freezes contracts, activates tasks, and writes project code.

Use `aiwf state set-workflow-mode` to record the mode and pattern. Workflow patterns such as `clarification_first`, `research_first`, `spike_first`, and `adversarial_early` shape the route but never lower workflow Level or remove gates.

`aiwf plan create/update` may maintain a `plan.md`-style task artifact for continuity. It does not replace Project Map, goal.json, contexts.json, testing.json, review.json, or evidence records.

`aiwf recipe recommend` provides workflow templates; recipes are advisory and cannot override AIWF gates. External skills, hooks, commands, MCP servers, or community workflows must be classified with `aiwf capability scan`. Capabilities with `lifecycle_overlap=true` require an explicit Planner decision and may assist only after their outputs are promoted through AIWF contracts/evidence.

## Rules

- `.aiwf/state/`, `.aiwf/quality/`, `.aiwf/evidence/`, and `.aiwf/history/` JSON files are the source of truth (not prose, not Markdown).
- Evidence comes from git diff, never from model claims.
- Scope expansion requires user decision.
- Review must be independent (reviewer != executor).
- Closure gates are mechanical — `prepare-close` is authoritative; Claude Stop checks close_attempt again.
- Machine routing selects minimum depth. Planner must explain semantic risk and may increase depth or breadth.
- Testing and review are independent stages. Cleanup must happen before review. Fixes require downstream re-test/re-clean/re-review.
