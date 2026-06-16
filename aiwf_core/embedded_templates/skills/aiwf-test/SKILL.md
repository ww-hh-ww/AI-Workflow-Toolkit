---
name: aiwf-test
description: Template-guided testing based on planner-selected test_template
---

# AIWF Test

> **L1+ = Agent tool. L0 = scroll down. Testing inline at L2+ is a GATE VIOLATION — review will reject it because no independent tester evidence exists.**

## DISPATCH GATE — READ FIRST, ACT NOW

Read `.aiwf/state/state.json` → `workflow_level`.

### L0_direct → skip to "L0 Testing" section at bottom of this file

### L2_standard_team / L3_full_power → CALL AGENT TOOL NOW (aiwf-tester)

You are planner-main. Running tests yourself is a gate violation. The review phase checks that an independent tester produced the evidence.

**Step 1 — Read state to build the prompt:**

1. `.aiwf/state/state.json` — `active_task_id`, `workflow_level`, `test_template`, `verification_need`
2. `.aiwf/state/plans.json` — active Plan: `allowed_write`, `test_focus`, `work_intent`, `plan_kind`, `active_phase`
3. `.aiwf/artifacts/evidence/records.json` — executor's changed files

**Step 2 — Call Agent({...}) with:**

| Parameter | Value |
|-----------|-------|
| subagent_type | `"aiwf-tester"` |
| description | `"Test TASK-XXX"` |
| prompt | Task ID + `test_template` + `verification_need` + `allowed_write` + `work_intent` + `plan_kind` + `test_focus` + changed files from evidence + `"Run aiwf status first. Read .aiwf/state/ for full context. Write NEW tests covering changed behavior AND uncovered paths — do NOT just run existing tests. Record with aiwf state record-testing --supports-plan <PLAN-ID> --supports-goal <GOAL-ID>. Recording is REQUIRED."` |

**Step 3 — Wait for tester to finish.** Forward results to the review phase.

### L1_review_light → CALL AGENT TOOL NOW (aiwf-reviewer as reviewer-light)

L1 uses ONE sub-agent for both testing AND review.

| Parameter | Value |
|-----------|-------|
| subagent_type | `"aiwf-reviewer"` |
| description | `"Test + review TASK-XXX"` |
| prompt | Task ID + `test_template=targeted_plus_small_regression` + `verification_need=standard` + `allowed_write` + `work_intent` + `plan_kind` + changed files from evidence + `"You are reviewer-light for this L1 task. Do TWO jobs: (1) Test first — write new tests, run them, record with aiwf state record-testing --supports-plan <PLAN-ID> --supports-goal <GOAL-ID>. (2) Then review — check scope, goal match, test adequacy, overengineering. Record review with aiwf state record-review --verdict PASS (or REVISE/REJECT). Read .aiwf/state/ for full context."` |

This ONE agent handles both phases. Do NOT spawn a separate tester or reviewer after this.

---

**>>> STOP HERE IF NOT L0_direct. Content below is L0 only. <<<**

---

## L0 Testing (inline, self-test OK)

YOUR JOB IS TO WRITE TESTS, NOT JUST RUN THEM.

Running the existing test suite is verification, not testing. Your primary deliverable is **new tests** that cover what the executor wrote and what the executor missed.

**If you find uncovered paths and only list them in the report without writing tests, you have not done your job. Status=adequate is the maximum for a report-only pass — and only if you wrote at least one new test.**

Before recording any result, ask: "Did I write new tests?" If the answer is no, you are not done.

---

### Work Intent Discipline

Testing strategy varies by work_intent. Read the active Plan's `work_intent`:
- **feature**: test new capability, verify interfaces, check documentation matches behavior.
- **bugfix**: test root cause is fixed, add regression test, verify no behavior regression.
- **refactor**: test external behavior preserved, no new coupling, old tests still pass.
- **cleanup**: test required files remain, machine truth intact.
- **migration**: test old→new path consistency, data integrity, fallback works.
- **verification**: test evidence sufficiency, coverage completeness.
- **exploration**: test hypotheses, record findings, isolate from stable structure.
- **documentation**: test docs match actual behavior, no overclaiming.
- **integration**: test cross-module paths, interface stability, contract enforcement.
- **release**: test package integrity, version boundaries, audit compliance.

### Before testing, pull from the tree
1. **State**: `.aiwf/state/state.json` → `workflow_level`, `test_template`, `surface_types`.
2. **Goal Tree**: `.aiwf/state/goals.json` → parent Goal's `surface_types`, sibling relations.
3. **Plan**: `.aiwf/state/plans.json` → active Plan: `test_focus`, `interfaces`, `constraints`, `work_intent`.
4. **Evaluation Contract**: `.aiwf/state/goal.json` → `quality_brief.evaluation_contract`.
5. **Plan scope**: `.aiwf/state/plans.json` → active Plan: `allowed_write`, `test_focus`, `escalation_triggers`.
6. **Evidence**: `.aiwf/artifacts/evidence/records.json` → executor's changed files.

### Testing Basis Contract

Testing must verify the active plan's `Verification` section and the risk implied by changed files. Read `.aiwf/artifacts/plans/<PLAN-ID>.md`, `.aiwf/artifacts/evidence/records.json`, `.aiwf/state/state.json`, `.aiwf/state/plans.json`, and `.aiwf/state/goal.json` before choosing commands.

If the active plan no longer matches the observed changed files or feasible verification path, stop and return to Planner to update the plan before continuing. Do not paper over plan drift with ad hoc tests.

### Plan-Type-Based Testing (Stage 4.6)

Testing strategy must match the active Plan's `plan_kind` and `active_phase`:
- **implementation plan** → Test functional behavior: inputs, outputs, error paths, edge cases. The implementation must work correctly.
- **structural plan** → Test interface integrity, boundary enforcement, prompt/status invariants. The structure must hold — code may be minimal. Test that contracts are enforced, not that every path is exercised.
- **migration plan** → Test old→new path consistency, state compatibility, legacy reference removal. Both the old and new paths must be independently verifiable.
- **verification plan** → Test evidence sufficiency, coverage completeness, validation rigor. The evidence must convince an independent Reviewer.
- **exploration plan** → Test hypotheses, record findings. Scope is investigative; tests document what was learned, not what was built.

By active_phase:
- **framing** → Test that scope and interfaces are well-defined. Are boundaries clear? Are acceptance criteria testable?
- **implementation** → Test that the implementation satisfies declared interfaces.
- **integration** → Test cross-module paths and integration points. System coverage is required.
- **seal** → Test that all obligations are discharged and evidence is complete.

### Evidence Attribution

Every test result must state which Plan and Goal it supports:
```
aiwf state record-testing ... --supports-plan PLAN-XXX --supports-goal GOAL-XXX
```
Evidence without a Plan/Goal target does not roll up and will be flagged in Admission Review.

### Validation Layers Before Declaring Adequate

Do not confuse a passing unit-test command with adequate validation.

1. **Targeted** — focused tests for the changed behavior.
2. **Full regression** — the repository's complete available test suite.
3. **Integration/system path** — affected modules working together across declared integration points.
4. **Real usage** — exercise the actual user-facing entrypoint: installed CLI command, API request, application startup/UI workflow, package import/export, build artifact, or equivalent production-shaped path.

Full regression and real usage requirements are determined by `test_template`:
- **targeted (L0)**: run the exact changed behavior. Full suite and real usage are not required.
- **targeted_plus_small_regression (L1)**: target + nearby regression. Full suite recommended but not required.
- **regression_plus_boundary_adverse (L2)**: full project regression is required. Real usage is required.
- **risk_matrix_plus_integration_adversarial (L3)**: everything above plus risk matrix and integration adversarials.

- When the template requires it, run it. Only skip with a concrete, named reason.
- Not feasible ≠ not convenient. Record `not_feasible` only when the test physically cannot be automated.
- Never record `adequate` on targeted tests alone when the template requires more.
- A mocked integration test is not real usage. Name the actual entrypoint.

### Coupling-Aware Thinking Path

For tightly-coupled projects, a local change can break distant assumptions.

1. **Change Surface**: Read changed files from evidence. What public APIs, contracts, or data formats changed? Did any global constants, base classes, or shared utilities change? (These have the widest ripple.)

2. **Ripple Tracing**: For every changed file that is a dependency of other code:
   - Who imports this? Each importer is a potential breakage site.
   - Who does this call? For every external function the changed code invokes, verify the call matches the callee's actual signature.
   - Which integration_points pass through here? If a declared integration path touches a changed file, the whole path needs testing.
   - Architecture Brief cross-check: changed files vs `allowed_files`, `protected_files`, `forbidden_restructures`.

3. **Coupling Hotspots**: Read `.aiwf/runtime/history/task-history.json` (hotspots), `.aiwf/artifacts/reports/质量摘要.md` (prior cross_task_risks, testing_debt).
   - Is this file a hotspot (>=3 changes)? If so, existing tests aren't catching the real problem.
   - Does this change cross `architecture_brief.module_boundaries`? Cross-module changes are the #1 source of integration bugs.

4. **Architecture Consistency**: Do `architecture_brief.architecture_invariants` still hold? Did the change introduce new coupling?

5. **Signal for the Next Task**: What did you learn? Record as `--cross-task-risk`, `--testing-debt`, or `--repeated-change-hotspot`.

### Architecture Awareness

Check: integration_points tested?, public_api_changes verified?, forbidden_restructures violated? If testing reveals gap → suspected_route=executor (path declared but missed) or planner (path never declared → request ACR).

### Architecture Migration Evidence

If `architecture_brief` declares `migration_source_of_truth`, `legacy_paths`, `legacy_terms`, `default_entrypoints`, or `validators`:
- Run a legacy sweep such as `rg "old_term|old_path"` over the repository.
- Run each declared default entrypoint with `--dry-run`, `--check`, or the closest non-destructive equivalent.
- Run each declared validator/CI command.
- Unit tests alone are never adequate for an architecture migration.

### Adversarial Mode (L2+)

Full project test suite + real user-facing entrypoint validation + targeted reading of failures. Use `task-history.json` hotspots to prioritize re-runs. Let test results guide what to read — don't read first. Cross-task quality observation is part of Tester responsibility.

### Reading Strategy

Command output is the #2 token cost. Filter ruthlessly:
- Run full tests → read only failures: pipe through `grep -E "FAIL|Error|assert|Traceback"`.
- Read source only when tests fail: let test results tell you what to read.

### Recording Results (REQUIRED — gate will block closure without this)

Every recording MUST include `--supports-plan <PLAN-ID> --supports-goal <GOAL-ID>`.

```bash
# Pass:
aiwf state record-testing --status adequate --supports-plan PLAN-XXX --supports-goal GOAL-XXX --command "pytest tests/unit/test_changed.py" --validation-layer targeted --command "pytest" --validation-layer full_regression --full-suite-status passed --command "mycli --version" --validation-layer real_usage --real-usage-status passed --real-usage-reason "installed CLI started and returned its version"

# Environmental deferral:
aiwf state record-testing --status adequate --supports-plan PLAN-XXX --supports-goal GOAL-XXX --validation-layer targeted --full-suite-status not_feasible --full-suite-reason "suite requires unavailable GPU" --real-usage-status not_available --real-usage-reason "staging API credentials unavailable" --untested-risk "GPU and staging API paths remain unverified"

# Fail:
aiwf state record-testing --status failed --supports-plan PLAN-XXX --supports-goal GOAL-XXX --command "npm test" --failure-summary "divide by -0 did not throw RangeError" --failed-obligation "Cover +0/-0 divisor behavior" --suspected-route executor --required-verification "rerun npm test"

# Adversarial:
aiwf state record-testing --status adequate --supports-plan PLAN-XXX --supports-goal GOAL-XXX --adversarial-mode --cross-task-risk "Repeated parser changes lack integration coverage"
```

### When Tests Fail

Record: failure_summary, failed_obligations, failed_commands, suspected_route (executor/tester/planner/environment), required_verification. Final route confirmed by Reviewer/Planner.
