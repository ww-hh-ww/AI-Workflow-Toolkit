---
name: aiwf-test
description: Template-guided testing based on planner-selected test_template
---

**Goal-driven verification:** Map each acceptance criterion to concrete evidence. A command that does not exercise the changed behavior is not sufficient. Prefer real tool invocations with captured output over prose claims about what was tested.

# AIWF Test

This skill contains role instructions for the AIWF Tester. Loading this skill does not create an independent tester session.

If you are planner-main, do not test by roleplaying tester for L2/L3 work. Dispatch the `aiwf-tester` subagent and pass it the active task/context, selected `test_template`, acceptance criteria, and system integration obligations. Inline testing is allowed only for L0_direct or explicitly light L1 self-checks where the workflow level permits it.

When executed inside the AIWF Tester subagent, perform template-guided testing. Depth comes from `test_template`, NOT a universal checklist. **workflow_level decides depth. surface_type decides failure-mode directions.**

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
Read `.aiwf/evidence/records.json` (changed files), `.aiwf/state/goal.json` (architecture_brief).
Ask: what files changed? What public APIs, contracts, or data formats? Did any global constants, base classes, or shared utilities change? (These have the widest ripple — every importer is affected.)

### 2. Ripple Tracing
For every changed file that is a dependency of other code (library, utility, base class, constant definition), trace outward:
- **Who imports this?** Search for imports of the changed module. Each importer is a potential breakage site.
- **Which integration_points pass through here?** (from architecture_brief.integration_points). If a declared integration path touches a changed file, the whole path needs testing.
- **Architecture Brief cross-check**: changed files vs `allowed_files`, `protected_files`, `forbidden_restructures`.

Pay special attention to **single-point-of-truth files** (like `paths.py`, `state_schema.py`, `constants.py`) — a one-line change there can silently affect dozens of call sites.

### 3. Coupling Hotspots
Read `.aiwf/history/task-history.json` (hotspots), `.aiwf/reports/质量摘要.md` (prior cross_task_risks, testing_debt).
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


```bash
# Pass (keep this as one shell command; do not use line-continuation backslashes):
# aiwf state record-testing --status adequate --command "pytest tests/unit/test_changed.py" --validation-layer targeted --command "pytest" --validation-layer full_regression --full-suite-status passed --command "mycli --version" --validation-layer real_usage --real-usage-status passed --real-usage-reason "installed CLI started and returned its version"
# Explicit environmental deferral:
# aiwf state record-testing --status adequate --validation-layer targeted --full-suite-status not_feasible --full-suite-reason "suite requires unavailable GPU" --real-usage-status not_available --real-usage-reason "staging API credentials unavailable" --untested-risk "GPU and staging API paths remain unverified"
# Fail:
# aiwf state record-testing --status failed --command "npm test" --failure-summary "divide by -0 did not throw RangeError" --failed-obligation "Cover +0/-0 divisor behavior" --suspected-route executor --required-verification "rerun npm test"
# Adversarial: aiwf state record-testing --status adequate --adversarial-mode --cross-task-risk "Repeated parser changes lack integration coverage"
```

## When Tests Fail

Record: failure_summary, failed_obligations, failed_commands, suspected_route (executor/tester/planner/environment), required_verification. Final route confirmed by Reviewer/Planner.
