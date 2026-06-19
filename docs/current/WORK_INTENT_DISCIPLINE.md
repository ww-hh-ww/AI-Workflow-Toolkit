# Work Intent Discipline — Stage 4.7.4

**Depends on:** `NODE_CONTRACT.md`, `EXECUTION_FRONTIER.md`, `AIWF_DESIGN_AXIOMS.md`.
**Status:** Stage 4.7.4. Work Intent Discipline defines behavioral discipline for every work item.

---

## 1. Purpose

AIWF already has `plan_kind` to define the structural role of a Plan. But structural role
alone doesn't tell an agent *how* to behave during execution. A migration Plan should not
behave the same as a feature Plan. A refactor Plan needs different guardrails than cleanup.

`work_intent` fills this gap:

| Concept | Question | Example |
|---------|----------|---------|
| `plan_kind` | What structural role does this Plan play? | migration / structural / implementation |
| `work_intent` | What behavioral discipline should this work follow? | refactor / feature / bugfix |

They are **orthogonal and combinable**.

---

## 2. Allowed Values

| Value | Summary |
|-------|---------|
| `feature` | New user-visible or system-visible capability |
| `bugfix` | Fix an error; restore expected behavior |
| `refactor` | Restructure internals while preserving external behavior |
| `cleanup` | Remove redundancy, pollution, stale artifacts |
| `migration` | Move old structure to new while preserving compatibility |
| `verification` | Verify, review, prove; do not change implementation |
| `exploration` | Explore uncertain direction; use Temporary Root |
| `documentation` | Update docs, contracts; do not change machine semantics |
| `integration` | Integrate completed branches; check convergence |
| `release` | Package, release boundary, final delivery check |

---

## 3. plan_kind vs work_intent

```json
// Example: this is a migration Plan, but the behavioral discipline is refactor
{
  "plan_kind": "migration",
  "work_intent": "refactor"
}
// → preserve behavior, require regression, require compatibility, no feature creep

// Example: this is an implementation Plan adding new capability
{
  "plan_kind": "implementation",
  "work_intent": "feature"
}
// → acceptance tests, demonstrate new behavior, document interfaces

// Example: this is a verification Plan doing verification only
{
  "plan_kind": "verification",
  "work_intent": "verification"
}
// → no implementation changes, focus on evidence, state uncertainty
```

---

## 4. Default Derivation

If `work_intent` is not explicitly set, it's derived from `plan_kind`:

| plan_kind | default work_intent |
|-----------|-------------------|
| implementation | `feature` |
| structural | `feature` |
| verification | `verification` |
| exploration | `exploration` |
| migration | `migration` |
| integration | `integration` |

Default is `feature` when plan_kind doesn't imply another intent. Explicit `work_intent` always wins over the default.

---

## 5. Work Packet Integration

`prepare_work_packet()` reads `work_intent` and automatically appends to the Work Packet:

- `constraints` — behavioral boundaries
- `forbidden_changes` — prohibited actions
- `expected_evidence` — minimum evidence requirements
- `review_focus` — what the Reviewer should check

Planner's explicit fields are never overwritten — only missing items are appended.

Full rule tables are in `aiwf_core/core/work_intent_rules.py`.

---

## 6. Validation Rules

| Condition | Severity |
|-----------|----------|
| invalid `work_intent` value | **fail** |
| refactor + preserve_behavior=false | **fail** |
| bugfix without expected_evidence | **fail** |
| migration + compatibility_required=false | **fail** |
| release without expected_evidence | **fail** |
| verification + dispatch_to not tester/reviewer | **fail** |
| cleanup missing machine truth guard | warning |
| exploration missing isolation | warning |
| documentation missing semantic drift guard | warning |
| integration dispatch not architect/reviewer/tester | warning |

---

## 7. Agent Behavior Summary

### Executor
- **feature**: implement, document, don't refactor unrelated
- **bugfix**: minimal fix, add regression, preserve behavior
- **refactor**: restructure, preserve behavior, no features
- **cleanup**: remove only, don't touch machine truth
- **migration**: preserve data, provide fallback, generate report
- **verification**: don't implement, only verify
- **exploration**: isolate, record findings, don't pollute
- **documentation**: don't change semantics
- **integration**: don't change interfaces
- **release**: don't change behavior, only package

### Tester
- **feature**: acceptance tests
- **bugfix**: reproduction + regression
- **refactor**: compatibility + regression
- **cleanup**: no required files removed
- **migration**: old path + new path
- **verification**: evidence rollup
- **exploration**: capture findings
- **documentation**: docs match behavior
- **integration**: interface consistency
- **release**: audit + full tests

### Reviewer
- All intents: check work_intent-appropriate evidence, constraints, and scope
- **refactor**: especially check no behavior drift, no feature creep
- **migration**: especially check no data loss, compatibility preserved
- **release**: especially check package is clean

### Architect
- **structural + *feature***: interface reasonability
- **refactor**: coupling reduction
- **migration**: truth source clarity
- **exploration**: graft/prune decision
- **integration**: structural convergence
- **release**: readiness assessment

---

## 8. Constraints

- `work_intent` is NOT a node — it does not replace Goal/Plan/Task
- `work_intent` does NOT replace `plan_kind` — they are orthogonal
- `work_intent` must have real operational effect — not just exist in JSON
- Do NOT build a heavy behavior engine
- Do NOT expand `status --prompt`

---

## 9. Contract Tests

See `tests/embedded/test_work_intent_stage474.py`.
