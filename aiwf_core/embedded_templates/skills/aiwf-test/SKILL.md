---
name: aiwf-test
description: Template-guided testing based on planner-selected test_template
---

# AIWF Test

Template-guided tester. Depth comes from `test_template`, NOT a universal checklist. **workflow_level decides depth. surface_type decides failure-mode directions.**

## Reading Strategy

Command output is the #2 token cost. Filter ruthlessly:
- **Run full tests → read only failures**: pipe through `grep -E "FAIL|Error|assert|Traceback"`. Passing tests don't need reading.
- **Read source only when tests fail**: let test results tell you what to read.

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

Full project test suite + targeted reading of failures. Use `task-history.json` hotspots to prioritize re-runs. Let test results guide what to read — don't read first.
Cross-task quality observation is part of Tester responsibility.

## Acceptance & System Coverage

Acceptance coverage is required. Map acceptance criteria to coverage: covered/not covered/manual.

System Coverage is required when system_integration_obligations exist. Verify the affected system path end to end when feasible, not just the local function. Record it with `--system-coverage "..."` alongside acceptance coverage. Record cross_task_risks if systemic issues found.

## Architecture Awareness

Check: integration_points tested?, public_api_changes verified?, forbidden_restructures violated in evidence? If testing reveals gap → suspected_route=executor (path declared but missed) or planner (path never declared → request ACR).

## Recording Results (REQUIRED — gate will block closure without this)

You MUST call `aiwf state record-testing` before exiting. Without testing.json with status=adequate|passed, prepare_close will reject.


```bash
# Pass: aiwf state record-testing --status adequate --command "pytest -xvs" --untested-risk "performance not tested"
# Fail: aiwf state record-testing --status failed --command "npm test" \
#         --failure-summary "divide by -0 did not throw RangeError" \
#         --failed-obligation "Cover +0/-0 divisor behavior" \
#         --suspected-route executor --required-verification "rerun npm test"
# Adversarial: aiwf state record-testing --status adequate --adversarial-mode --cross-task-risk "Repeated parser changes lack integration coverage"
```

## When Tests Fail

Record: failure_summary, failed_obligations, failed_commands, suspected_route (executor/tester/planner/environment), required_verification. Final route confirmed by Reviewer/Planner.
