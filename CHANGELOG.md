# Changelog

## 1.0 — Embedded Claude Code and Reasonix Governance (2026-06)

### Reasonix Compatibility
- Added native `aiwf install reasonix` integration using Reasonix skills and hooks
- Mapped independent roles to `runAs: subagent` skills without duplicating `.reasonix/agents`
- Added connection-recovery contracts that preserve Tester and Reviewer depth after interrupted subagent runs
- Made `prepare-close` the authoritative Reasonix closure gate because Reasonix Stop is report-only
- Added target-aware prompt adaptation so Claude-only Stop semantics are never rewritten into contradictory Reasonix rules
- Validated the complete Planner state machine in real Claude Code and Reasonix Code sessions

### Core Architecture
- Seven `.aiwf/*.json` state files as machine-readable source of truth
- Six skills: aiwf-planner, aiwf-implement, aiwf-test, aiwf-review, aiwf-close, aiwf-architect
- Five subagents: explorer, executor, tester, reviewer, curator
- Eight hook scripts: status, pre-snapshot, scope-check, bash-guard, evidence-capture, review-gate, rebase, export-report
- Workflow levels L0-L3 with resource-based routing and hard upgrade triggers
- Claude Code native integration (hooks in settings.json, skills in .claude/skills/, agents in .claude/agents/)

### Emergent Governance
- **Task gravity** (`task_gravity.py`): Pure function computing historical pressure from task-history. Zero weight at cold start, auto-scales with project age. Serves three consumers: UserPromptSubmit (advisory), start_context (≤3 notes injected), activation_blockers (mechanical gate).
- **Cross-task quality** (`cross_task_quality.py`): Repeated change hotspots, fix-loop trends, architecture drift, testing debt detection. Compact adversarial observation summaries in task-history.
- **Architecture trend signals** (`architecture_trend_signals()`): Module coupling growth, surface expansion, recurring change pattern detection — from task-history alone, no code scanning.

### Adversarial Review Loop
- Reviewer records contract gaps (`adversarial_observations`) without blocking closure result
- Planner must disposition each observation (ignored/accepted/deferred/brief_updated)
- Pending disposition mechanically blocks both prepare_close and Stop hook
- Adversarial observations carry forward into task-history for next task awareness

### Periodic Architecture Review
- `/aiwf-architect` role triggered every ~10 closed tasks, gravity ≥ 0.5, PROJECT-MAP stale >30 days, or 3+ escalate signals
- Forward-looking: project-wide, read-only, advisory
- Output: PROJECT-MAP updates, architecture trends → quality-digest

### Task Ledger
- Multi-task management with execution-window gates
- Default single active task; parallel-safe with write boundary conflict detection
- Suspend/resume with lightweight state snapshot
- Dependency enforcement on activation

### Context Management
- Machine-readable `current-state.md`: auto-rebuilt from `.aiwf/*.json` + `PROJECT-MAP.md`; Planner reads only
- Structure validation on carry-forward summary
- Freshness detection against source files

### Reading Strategy
- Executor: grep + offset/limit precision reads (not full files)
- Tester: full test suite → read only failed output (not passing tests)
- Reviewer: evidence + changed files + Brief + history — comprehensive where judgment matters

### Layers of Defense
- Scope check (PreToolUse Hook): mechanical enforcement of allowed_write/forbidden_write
- Bash guard (PreToolUse Hook): block dangerous commands (rm -rf, sudo, npm publish...)
- Evidence capture (PostToolUse Hook): git diff, not model prose
- Review gate (Stop Hook): mechanical closure condition verification
- Dual ADV gate: prepare_close + Stop hook both block on pending dispositions
- Checkpoint system: git stash/patch rollback with HEAD guard + pre-restore backup
- Fix-loop limits: L0=1, L1=1, L2=2, L3=3; escalation on limit breach
