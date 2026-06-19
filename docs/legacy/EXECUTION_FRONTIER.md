> **LEGACY — not authoritative for AIWF V1.**
> See docs/V1_DESIGN_CONTRACT.md for current rules.

# Execution Frontier — Stage 4.7 Design Contract

**Depends on:** `CHANGE_ADMISSION.md`, `AIWF_DESIGN_AXIOMS.md`, `NODE_CONTRACT.md` (all frozen).
**Status:** Stage 4.7–4.7.1: Semantic Execution Frontier + Work Packet + Precision Hardening. Frontier validation (dispatch_to required for all types, verify_plan requires target_goal_id), Work Packet preparation, agent wrappers aligned, Architect skill updated for structural frontiers, change admit shell commands removed from default output. 1346 contract tests passing.

---

## 1. Purpose

Stage 4.2–4.3 solved "how does a change enter the system?" (Admission Decision → Action Plan).

Stage 4.7 solves "what should be worked on now, by whom, with what boundaries, and where does the evidence go?"

The Rooted Functional Tree broke the single-timeline assumption: Plans can be structural (defining interfaces) or implementation (building within them). A structural Plan may need to be framed before its child implementation Plans can execute. An implementation Plan may need verification before integration. These dependencies are semantic — the Planner must judge them, not a script.

**Core principle:**

```
Planner decides frontier.
AIWF validates frontier.
AIWF prepares Work Packet.
Agents consume Work Packet.
No automatic scheduling.
No automatic execution.
No weight-based ranking.
```

---

## 2. Relationship to Admission

| Concept | Question | Answer |
|---------|----------|--------|
| Admission Decision | How does this change enter the system? | attach_plan / graft_goal / temporary_root |
| Frontier Decision | What should be worked on now? | execute_plan / verify_plan / review_plan / integrate_goal / architect_structure / explore_temporary_root |
| Work Packet | What does the agent receive? | Structured scope, interfaces, constraints, expected evidence |

Admission is the entry gate. Frontier is the dispatch gate. Work Packet is the execution contract.

---

## 3. Frontier Decision Schema

```json
{
  "frontier_type": "execute_plan",
  "selected_plan_id": "PLAN-001",
  "target_goal_id": "GOAL-001",
  "dispatch_to": "executor",
  "reason": "Why this is the correct frontier now.",
  "active_phase": "implementation",
  "scope": "What should be done in this work packet.",
  "interfaces": [],
  "constraints": [],
  "expected_evidence": [],
  "forbidden_changes": [],
  "rollup_target": "GOAL-001",
  "review_focus": [],
  "confidence": "high",
  "needs_human_confirmation": false
}
```

### 3.1 Allowed Values

**frontier_type:**
- `execute_plan` — implement within a Plan
- `verify_plan` — test/verify a Plan's outputs
- `review_plan` — review a Plan's work
- `integrate_goal` — integrate child Goals/Plans under a parent Goal
- `architect_structure` — design structure, interfaces, boundaries
- `explore_temporary_root` — exploratory/spike work under a Temporary Root

**dispatch_to:**
- `executor` — implementation agent
- `tester` — testing agent
- `reviewer` — review agent
- `architect` — architecture/structural agent
- `planner` — Planner inline (for exploration, framing)

**confidence:** `low` | `medium` | `high`

**active_phase:** `framing` | `implementation` | `integration` | `seal`

### 3.2 Field Requirements by frontier_type

| Field | execute_plan | verify_plan | review_plan | integrate_goal | architect_structure | explore_temporary_root |
|-------|-------------|-------------|-------------|----------------|---------------------|------------------------|
| `selected_plan_id` | **required** | **required** | **required** | — | — | — |
| `target_goal_id` | **required** | **required** | — | **required** | **required** | — |
| `dispatch_to` | executor | tester | reviewer | architect or reviewer | architect | planner/architect/executor |
| `reason` | **required** | **required** | **required** | **required** | **required** | **required** |
| `scope` | **required** | — | — | — | — | — |
| `expected_evidence` | **required** | **required** | — | — | — | — |
| `rollup_target` | **required** | — | — | — | — | — |
| `review_focus` | — | — | at least one of review_focus or expected_evidence | — | — | — |
| `interfaces` | — | — | — | — | at least one of interfaces/constraints/child_goal_policy | — |

---

## 4. Validation Rules

`validate_frontier_decision(base_dir, decision)` performs structural validation only — no semantic judgment, no state mutation.

### 4.1 Universal Checks

1. `frontier_type` is a valid value
2. `dispatch_to` is a valid value **and is required for all frontier types**
3. `confidence` is low/medium/high
4. `reason` is non-empty
5. `selected_plan_id` (if present) exists in `plans.json`
6. `target_goal_id` (if present) exists in `goals.json`, or GOAL-001 fallback when goals.json is empty
7. If both `selected_plan_id` and `target_goal_id` are present, Plan's `target_goal_id` should match decision's `target_goal_id` or the mismatch must be explicitly explained (warning)
8. `rollup_target` (if present) should match `target_goal_id` or be an ancestor Goal
9. `confidence=low` → warning: `needs_human_confirmation` should be true
10. No state mutation

### 4.2 Type-Specific Checks

**execute_plan:**
- Must have: `selected_plan_id`, `target_goal_id`, `dispatch_to=executor`, `scope`, `expected_evidence`, `rollup_target`
- If Plan.kind is `structural` → warning: executor work under structural plan should be scoped carefully

**verify_plan:**
- Must have: `selected_plan_id`, `target_goal_id` (required), `dispatch_to=tester`, `expected_evidence`
- If `expected_evidence` is empty → fail
- If `target_goal_id` is missing → fail

**review_plan:**
- Must have: `selected_plan_id`, `dispatch_to=reviewer`
- Must have at least one of `review_focus` or `expected_evidence`

**integrate_goal:**
- Must have: `target_goal_id`, `dispatch_to=architect` or `reviewer`, `reason`
- Warning if Goal has no attached plans and no child goals

**architect_structure:**
- Must have: `target_goal_id`, `dispatch_to=architect`
- Must have at least one of `interfaces`, `constraints`, or `child_goal_policy`

**explore_temporary_root:**
- Must have: `target_goal_id` or the decision should reference a temporary root
- Must have: `dispatch_to=planner`, `architect`, or `executor`
- Must have: `reason`
- Warning: exploration that may enter the main tree will need subsequent graft/prune

---

## 5. Work Packet Preparation

`prepare_work_packet(base_dir, decision)` runs validation first, then produces structured output.

### 5.1 Output Modes

**Default (human-readable):** Work Packet Proposal — paragraphs and bullet lists. No shell commands. No raw JSON.

**`--json`:** Full Agent Work Packet as structured JSON with `work_packet_version: 1`.

### 5.2 Human Work Packet

Text output showing:
- Dispatch target and frontier type
- Target Goal (id + title)
- Selected Plan (id + kind + phase)
- Why this frontier (reason)
- Scope
- Constraints
- Expected Evidence
- Forbidden Changes
- Rollup target
- Review Focus
- Human confirmation needed?

No shell commands. No raw JSON. No `Next:` command lines.

### 5.3 Agent Work Packet

```json
{
  "work_packet_version": 1,
  "valid": true,
  "frontier_type": "...",
  "dispatch_to": "...",
  "target_goal_id": "...",
  "selected_plan_id": "...",
  "plan_kind": "...",
  "active_phase": "...",
  "scope": "...",
  "interfaces": [],
  "constraints": [],
  "expected_evidence": [],
  "forbidden_changes": [],
  "rollup_target": "...",
  "review_focus": [],
  "mutates_state": false
}
```

The `plan_kind` is read from `plans.json` using `selected_plan_id` — it is NOT taken from the decision (the registry is authoritative).

`mutates_state` is always `false` in prepare output — Work Packet preparation never writes state files.

---

## 6. CLI

```
aiwf frontier validate --file frontier.json
aiwf frontier prepare --file frontier.json
aiwf frontier prepare --file frontier.json --json
```

Both read a Frontier Decision JSON file. Both are read-only — they never mutate state.

`validate` returns exit 0 on valid, exit 1 on invalid.
`prepare` returns exit 0 on valid (outputs Work Packet), exit 1 on invalid (outputs issues).

---

## 7. Integration with Planner

The Planner skill must:

1. After Admission Decision is accepted and structure exists, judge semantically which frontier should execute next.
2. Produce a Frontier Decision JSON (the schema in Section 3).
3. Validate: `aiwf frontier validate --file frontier.json`
4. Prepare: `aiwf frontier prepare --file frontier.json`
5. Review the Work Packet Proposal with the user when confidence is low.
6. Dispatch the Agent Work Packet to the appropriate role.

The Planner must NOT:
- Use DFS/BFS traversal order as the default execution plan
- Auto-select the next Plan by weight or score
- Let a script decide the frontier

The Planner must distinguish:
- **Admission Decision:** how a change enters the system
- **Frontier Decision:** what should be worked on now
- **Work Packet:** what an agent receives to execute/test/review

---

## 8. Agent Role Guidelines

### Executor
- Consumes Work Packet with `dispatch_to=executor`
- Stays within Plan scope, interfaces, constraints, and `forbidden_changes`
- Must not modify Goal Tree, graft/prune branches, or change admission decisions
- Must produce `expected_evidence`
- Reports back if scope is wrong or interface is insufficient

### Tester
- Consumes Work Packet with `dispatch_to=tester`
- Validates `expected_evidence`
- For implementation work: tests behavior
- For structural work: tests interfaces, boundaries, prompt/status invariants
- Records evidence that rolls up to Plan/Goal

### Reviewer
- Checks whether the work followed the Work Packet
- Checks evidence rollup
- Checks orphan patches
- Checks whether work exceeded constraints or `forbidden_changes`

### Architect
- Handles structural frontier: framing, integration, graft/prune/seal, interface stability, Goal decomposition
- Consumes Work Packet with `dispatch_to=architect`

---

## 9. Non-Goals

- AIWF does NOT auto-select the next frontier
- AIWF does NOT rank Plans by weight or score
- AIWF does NOT implement DFS/BFS traversal as execution policy
- AIWF does NOT auto-execute Work Packets
- `validate` and `prepare` do NOT mutate state
- This does NOT add automatic scheduling
- This does NOT change `status --prompt` length
- This does NOT change task activation or close gates
- This does NOT build Context Pack

---

## 10. Contract Tests

1. valid execute_plan frontier passes validation
2. execute_plan missing selected_plan_id fails
3. execute_plan missing expected_evidence fails
4. verify_plan requires dispatch_to=tester
5. review_plan requires review_focus or expected_evidence
6. integrate_goal works with target_goal_id
7. architect_structure requires interfaces/constraints/child_goal_policy signal
8. explore_temporary_root warns about graft/prune follow-up
9. low confidence warns human confirmation
10. prepare emits human_work_packet with no shell commands
11. prepare --json emits work_packet_version=1
12. prepare does not mutate goals.json/plans.json/milestones.json/task ledger
13. selected_plan.target_goal_id mismatch warns
14. status --prompt unchanged
15. existing Stage 1/2/3/4 tests pass
