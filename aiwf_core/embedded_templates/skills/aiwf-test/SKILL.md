---
name: aiwf-test
description: Template-guided testing based on planner-selected test_template
---

# AIWF Test

## STOP — Check topology BEFORE any other action

Read `.aiwf/state/state.json` → `execution_topology`.

**If execution_topology is "standard_team" or "fanout_merge":**
You are planner-main. You do NOT test.

```
Agent({subagent_type: "aiwf-tester", prompt: "..."})
```

**If execution_topology is "light_review":**
Testing and review are done by ONE subagent.

```
Agent({subagent_type: "aiwf-reviewer", prompt: "..."})
```

The reviewer-light subagent handles both testing AND review. Tell it to test first, then review.

**Only continue below if execution_topology IS "single_agent" or "single_agent_with_machine_evidence".**

---

## Work Intent Discipline

Testing strategy varies by work_intent. Read the active Plan's `work_intent`:

**Before testing, pull from the tree:**
1. **State**: `.aiwf/state/state.json` → `workflow_level`, `test_template`, `surface_types`.
2. **Goal Tree**: `.aiwf/state/goals.json` → parent Goal's `surface_types`, sibling relations.
3. **Plan**: `.aiwf/state/plans.json` → active Plan: `test_focus`, `interfaces`, `constraints`, `work_intent`.
4. **Evaluation Contract**: `.aiwf/state/goal.json` → `quality_brief.evaluation_contract`.
5. **Context**: `.aiwf/state/contexts.json` → `allowed_write`, `test_focus`, `escalation_triggers`.
6. **Evidence**: `.aiwf/artifacts/evidence/records.json` → executor's changed files.

## Testing Basis Contract

Testing must verify the active plan's `Verification` section and the risk implied by changed files. Read `.aiwf/artifacts/plans/<PLAN-ID>.md`, `.aiwf/artifacts/evidence/records.json`, `.aiwf/state/state.json`, `.aiwf/state/contexts.json`, and `.aiwf/state/goal.json` before choosing commands.

If the active plan no longer matches the observed changed files or feasible verification path, stop and return to Planner to update the plan before continuing. Do not paper over plan drift with ad hoc tests.

## Plan-Type-Based Testing (Stage 4.6)

Testing strategy must match the active Plan's `plan_kind` and `active_phase`. Read these from the active Plan before choosing tests.

### By plan_kind

- **`implementation` plan** → Test functional behavior: inputs, outputs, error paths, edge cases. The implementation must work correctly.
- **`structural` plan** → Test interface integrity, boundary enforcement, prompt/status invariants. The structure must hold — code may be minimal. Test that contracts are enforced, not that every path is exercised.
- **`migration` plan** → Test old→new path consistency, state compatibility, legacy reference removal. Both the old and new paths must be independently verifiable.
- **`verification` plan** → Test evidence sufficiency, coverage completeness, validation rigor. The evidence must convince an independent Reviewer.
- **`exploration` plan** → Test hypotheses, record findings. Scope is investigative; tests document what was learned, not what was built.

### By active_phase

- **`framing`** → Test that scope and interfaces are well-defined. Are boundaries clear? Are acceptance criteria testable?
- **`implementation`** → Test that the implementation satisfies declared interfaces.
- **`integration`** → Test cross-module paths and integration points. System coverage is required.
- **`seal`** → Test that all obligations are discharged and evidence is complete.

### Evidence Attribution

Every test result must state which Plan and Goal it supports. When recording testing:
```
aiwf state record-testing ... --supports-plan PLAN-XXX --supports-goal GOAL-XXX
```
Evidence without a Plan/Goal target does not roll up and will be flagged in Admission Review.

## Validation Layers Before Declaring Adequate

Do not confuse a passing unit-test command with adequate validation.

Before testing, identify the project's actual validation layers from its scripts, CI config, package metadata, and user-facing entrypoints:

1. **Targeted** — focused tests for the changed behavior.
2. **Full regression** — the repository's complete available test suite, not only a test file or directory selected for the change.
3. **Integration/system path** — affected modules working together across declared integration points.
4. **Real usage** — exercise the actual user-facing entrypoint: installed CLI command, API request, application startup/UI workflow, package import/export, build artifact, or equivalent production-shaped path.

Full regression and real usage requirements are determined by `test_template` from `state.json`, not by a universal rule:

- **`targeted` (L0)**: run the exact changed behavior. Full suite and real usage are not required.
- **`targeted_plus_small_regression` (L1)**: target + nearby regression. Full suite recommended but not required.
- **`regression_plus_boundary_adverse` (L2)**: full project regression is required. Real usage is required. Run them.
- **`risk_matrix_plus_integration_adversarial` (L3)**: everything above plus risk matrix and integration adversarials. All surfaces mandatory.

Record `validation_layers` matching the depth you actually executed, with `full_suite_status` and `real_usage_status` dispositions.

- **When the template requires it, run it.** The depth was chosen by mechanical routing for a reason.
- **Only skip with a concrete, named reason.** "not_available" without naming the blocker is not acceptable. Name the specific environment, credential, hardware, service, or destructive-risk boundary. Record it as an `untested_risk`.
- **Not feasible ≠ not convenient.** Record `not_feasible` only when the test physically cannot be automated — not when it would take effort.
- **Never record `adequate` or `passed` on targeted tests alone when the template requires more.** A passing unit test does not satisfy `regression_plus_boundary_adverse`.
- **A mocked integration test is not real usage.** Name the actual entrypoint and what the user-observable result was.

## Reading Strategy

Command output is the #2 token cost. Filter ruthlessly:
- **Run full tests → read only failures**: pipe through `grep -E "FAIL|Error|assert|Traceback"`. Passing tests don't need reading.
- **Read source only when tests fail**: let test results tell you what to read.

## Evidence Traceability — Make Testing Verifiable

Testing results must be traceable to actual execution. The Reviewer needs to verify that tests ran, not just read a status summary.

- **Cite the execution trace**: for each test command, reference where the output can be found — a CI log URL, a saved output file, a timestamped shell session. "pytest passed" with no provenance is indistinguishable from not running tests at all.
- **Run tests through tool execution**: prefer running test commands as actual shell invocations that leave machine-captured traces, rather than summarizing results in prose. The trace is the evidence; the summary is just commentary.
- **If a test cannot run** (missing environment, credentials, hardware dependency, destructive risk), record what was blocked and why — and what surface remains untested as a result. Never fabricate or guess results.

## Test Depth (from `.aiwf/state/state.json`)

- **targeted**: exact changed behavior only. Do NOT build a test matrix.
- **targeted_plus_small_regression**: target + nearby regression + one cheap boundary.
- **regression_plus_boundary_adverse**: regression + boundary + adverse input/error paths.
- **risk_matrix_plus_integration_adversarial**: full risk matrix + integration + adversarial.

Do NOT expand unilaterally. Request escalation if too weak.

## Coupling-Aware Thinking Path

For tightly-coupled projects, a local change can break distant assumptions. Before writing a single test, trace the coupling graph. This is not optional reading — it is the core thinking structure.

### 1. Change Surface
Read `.aiwf/artifacts/evidence/records.json` (changed files), `.aiwf/state/goal.json` (architecture_brief).
Ask: what files changed? What public APIs, contracts, or data formats? Did any global constants, base classes, or shared utilities change? (These have the widest ripple — every importer is affected.)

### 2. Ripple Tracing
For every changed file that is a dependency of other code (library, utility, base class, constant definition), trace outward:
- **Who imports this?** Search for imports of the changed module. Each importer is a potential breakage site.
- **Which integration_points pass through here?** (from architecture_brief.integration_points). If a declared integration path touches a changed file, the whole path needs testing.
- **Architecture Brief cross-check**: changed files vs `allowed_files`, `protected_files`, `forbidden_restructures`.

Pay special attention to **single-point-of-truth files** (like `paths.py`, `state_schema.py`, `constants.py`) — a one-line change there can silently affect dozens of call sites.

### 3. Coupling Hotspots
Read `.aiwf/runtime/history/task-history.json` (hotspots), `.aiwf/artifacts/reports/质量摘要.md` (prior cross_task_risks, testing_debt).
- Is this file a **hotspot** (changed >=3 times)? If so, existing tests aren't catching the real problem — don't just re-run them, strengthen them.
- Does this change cross `architecture_brief.module_boundaries`? Cross-module changes are the #1 source of integration bugs.
- Prior `cross_task_risks` or `testing_debt` for these files? Past warnings are the best predictor of present failures.

### 4. Architecture Consistency
- Do `architecture_brief.architecture_invariants` still hold?
- Did the change introduce new coupling that should be recorded as a `forbidden_restructure`?
- Are module responsibilities still clear, or is this change blurring a boundary?

### 5. Signal for the Next Task
What did you learn that a future tester/reviewer/Planner needs to know? Record as:
- `--cross-task-risk "..."` for systemic fragilities
- `--testing-debt "..."` for tests you had to skip
- `--repeated-change-hotspot "..."` if this file keeps changing

Use context.test_focus first, respect context.escalation_triggers, and keep context.non_goals out of test expansion.
When failures look environment-related, run `aiwf env show` and record suspected_route=environment instead of blaming implementation.

Check surface obligations: `aiwf quality surface <name>`. If Planner missed an obvious surface, infer it and test it if in scope. Record: `--inferred-surface <name>`.

## Adversarial Mode (L2+)

Full project test suite + real user-facing entrypoint validation + targeted reading of failures. Use `task-history.json` hotspots to prioritize re-runs. Let test results guide what to read — don't read first.
Cross-task quality observation is part of Tester responsibility.

## Acceptance & System Coverage

Acceptance coverage is required. Map acceptance criteria to coverage: covered/not covered/manual.

System Coverage is required when system_integration_obligations exist. Verify the affected system path end to end when feasible, not just the local function. Record it with `--system-coverage "..."` alongside acceptance coverage. Record cross_task_risks if systemic issues found.

## Architecture Awareness

Check: integration_points tested?, public_api_changes verified?, forbidden_restructures violated in evidence? If testing reveals gap → suspected_route=executor (path declared but missed) or planner (path never declared → request ACR).

## Architecture Migration Evidence

If `architecture_brief` declares `migration_source_of_truth`, `legacy_paths`, `legacy_terms`, `default_entrypoints`, or `validators`, treat this as an architecture migration task. You must produce behavior-level evidence, not only local tests:
- Run a legacy sweep such as `rg "old_term|old_path"` or equivalent over the repository. If old references remain, classify whether they are archived/legacy-only or still on the mainline.
- Run each declared default entrypoint with `--dry-run`, `--check`, or the closest non-destructive equivalent.
- Run each declared validator/CI command.
- Check declared sample outputs if present.

Record these commands with `aiwf state record-testing` and/or role evidence so Reviewer can accept the machine evidence. Unit tests alone are never adequate for an architecture migration.

## Recording Results (REQUIRED — gate will block closure without this)

You MUST call `aiwf state record-testing` before exiting. Without testing.json with status=adequate|passed, prepare_close will reject.

Every recording MUST include `--supports-plan <PLAN-ID> --supports-goal <GOAL-ID>` so evidence rolls up to the correct structural home.

```bash
# Pass (keep this as one shell command; do not use line-continuation backslashes):
# aiwf state record-testing --status adequate --supports-plan PLAN-XXX --supports-goal GOAL-XXX --command "pytest tests/unit/test_changed.py" --validation-layer targeted --command "pytest" --validation-layer full_regression --full-suite-status passed --command "mycli --version" --validation-layer real_usage --real-usage-status passed --real-usage-reason "installed CLI started and returned its version"
# Explicit environmental deferral:
# aiwf state record-testing --status adequate --supports-plan PLAN-XXX --supports-goal GOAL-XXX --validation-layer targeted --full-suite-status not_feasible --full-suite-reason "suite requires unavailable GPU" --real-usage-status not_available --real-usage-reason "staging API credentials unavailable" --untested-risk "GPU and staging API paths remain unverified"
# Fail:
# aiwf state record-testing --status failed --supports-plan PLAN-XXX --supports-goal GOAL-XXX --command "npm test" --failure-summary "divide by -0 did not throw RangeError" --failed-obligation "Cover +0/-0 divisor behavior" --suspected-route executor --required-verification "rerun npm test"
# Adversarial: aiwf state record-testing --status adequate --supports-plan PLAN-XXX --supports-goal GOAL-XXX --adversarial-mode --cross-task-risk "Repeated parser changes lack integration coverage"
```

## When Tests Fail

Record: failure_summary, failed_obligations, failed_commands, suspected_route (executor/tester/planner/environment), required_verification. Final route confirmed by Reviewer/Planner.
