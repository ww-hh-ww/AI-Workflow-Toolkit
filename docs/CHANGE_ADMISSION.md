# Change Admission — Stage 4 Design Contract

**Depends on:** `AIWF_DESIGN_AXIOMS.md`, `NODE_CONTRACT.md` (both frozen).
**Status:** Stage 4.6: Entry Protocol & Role Alignment. Full pipeline: Day-1 Foundation Tree → Semantic Admission → Action Plan → Operation Plan → Admission-aware Review. All 5 core role skills (Planner, Planner-execute, Reviewer, Executor, Tester) aligned to Rooted Functional Tree. Keyword heuristic is appendix-only fallback. Shell commands hidden from human output.

---

## 1. Purpose

The Rooted Functional Tree (Stage 3) defines the structural machine. But keyword-based admission (Stage 4.0–4.1) is unreliable for structural judgment: "fix the admission mechanism" could be a simple patch under an existing Goal, or a structural redesign of how admission itself works. Keywords can't tell the difference.

**Stage 4.2 pivots to Semantic Change Admission:**

- **Planner/LLM** makes the semantic judgment — produces a structured Admission Decision
- **AIWF machine** validates the decision's structure — checks required fields, references, constraints
- **Keyword heuristic** stays as a deterministic fallback, clearly marked as non-authoritative

The machine does not pretend to be intelligent. It validates that intelligent decisions are structurally complete.

---

## 2. The Three Admission Paths

### 2.1 `attach_plan` — Attach Plan to Existing Goal

**Trigger:** The change modifies implementation under an existing functional skeleton. No new Goal is needed; the work fits inside an existing Goal's scope.

**Keyword signals:**
- fix, patch, update, improve, enhance, refactor, optimize, cleanup
- bug, typo, error, regression, performance
- implement, build, add (under existing capability)
- test, verify, validate

**Result:**
- `target_goal_id` = the matching existing Goal
- `plan_kind` = `implementation` (default) or `verification` / `migration`
- No tree structure change

**Examples:**
- "fix typo in README" → attach_plan, implementation
- "improve test coverage for Goal Tree registry" → attach_plan, verification
- "optimize cycle detection in goal_tree_ops.py" → attach_plan, implementation

### 2.2 `graft_goal` — Graft New Goal Through Interface

**Trigger:** The change alters the functional skeleton — it adds, removes, or restructures what the system can do. A new Goal must be grafted through an explicit interface.

**Keyword signals:**
- new capability, new feature, new module, new system, new component
- structural change, architecture, redesign, restructure
- interface change, API change, boundary change
- add support for, introduce, design, create (new functional unit)

**Result:**
- A new Goal is created as a child of the best-matching existing Goal
- The graft must record `interface_consumed`, `capability_provided`, `relation_to_parent`
- `plan_kind` = `structural` (to define the new skeleton first)

**Examples:**
- "add recursive Goal Tree registry" → graft_goal, structural
- "add Impact Cone computation module" → graft_goal, structural
- "redesign task activation to use plan registry" → graft_goal, structural

### 2.3 `temporary_root` — Temporary Root for Exploration

**Trigger:** Ownership is unclear. The change might belong under multiple Goals, might need a new Goal but the interface isn't clear, or is experimental/spike work.

**Keyword signals:**
- experiment, explore, spike, trial, prototype
- unsure, unclear, investigate, research
- maybe, possibly, could, alternative

**Result:**
- A Temporary Root is created (`root_type=temporary`)
- `visibility = hidden_from_prompt` (won't clutter status)
- Must be grafted or pruned before closure

**Examples:**
- "explore whether we need a separate Context Pack module" → temporary_root
- "prototype multi-agent orchestration" → temporary_root

---

## 3. Admission Decision Schema

The Admission Decision is a structured JSON object produced by the Planner (LLM semantic judgment) and validated by the AIWF machine. This is the authoritative format — keyword heuristics are a fallback only.

```json
{
  "admission_type": "attach_plan | graft_goal | temporary_root",
  "target_goal_id": "GOAL-ID or null",
  "target_parent_goal_id": "GOAL-ID or null (for graft_goal)",
  "new_goal_title": "string or null",
  "plan_kind": "structural | implementation | verification | migration | exploration",
  "active_phase": "framing | implementation | integration | seal",
  "interface_consumed": "string or null (for graft_goal)",
  "capability_provided": "string or null (for graft_goal)",
  "relation_to_parent": "string or null (for graft_goal)",
  "affected_plan_ids": ["PLAN-ID", ...] or null,
  "reason": "string (required)",
  "impact_notes": "string or null",
  "confidence": "low | medium | high",
  "needs_human_confirmation": true | false
}
```

### Field Requirements by admission_type

| Field | attach_plan | graft_goal | temporary_root |
|-------|------------|------------|----------------|
| `target_goal_id` | **required** | — | — |
| `target_parent_goal_id` | — | **required** | — |
| `new_goal_title` | — | required | suggested |
| `plan_kind` | **required** | structural (default) | — |
| `interface_consumed` | — | **required** | — |
| `capability_provided` | — | **required** | — |
| `relation_to_parent` | — | **required** | — |
| `reason` | **required** | **required** | **required** |
| `confidence=low` | needs_human_confirmation should be true | same | same |

---

## 4. Admission Protocol — Planner Questions

Before producing an Admission Decision, the Planner must answer:

1. Does this change alter the functional skeleton? (new capability, new module, restructure?)
2. Is there an existing Goal that can naturally contain this change?
3. If attaching a Plan: is it structural / implementation / verification / migration / exploration?
4. If grafting a Goal: what interface of the parent does it consume? What capability does it provide?
5. How does the new Goal relate to the parent? (extends, implements, replaces, depends on)
6. If ownership is unclear: why is a Temporary Root needed? What would clarify it?
7. Does this decision change the parent Goal's meaning?
8. Does this need human confirmation? (low confidence → yes)

---

## 5. CLI — Two Modes

### 5.1 Heuristic Fallback (non-authoritative)

```
aiwf change admit --summary "one-line description"
```

Output includes: `⚠ Heuristic recommendation only. Do not treat as authoritative.` The keyword-based heuristic stays as a quick-check fallback but is explicitly downgraded.

### 5.2 Machine Validation (authoritative gate)

```
aiwf change validate-decision < admission.json
# or
aiwf change validate-decision --file admission.json
```

Reads an Admission Decision JSON object. Validates:
- `admission_type` is a valid value
- Required fields are present per admission_type
- `target_goal_id` exists in goals.json (unless empty and GOAL-001 fallback)
- `target_parent_goal_id` exists in goals.json
- `plan_kind` is valid
- `active_phase` is valid
- `affected_plan_ids` exist in plans.json
- `confidence=low` → `needs_human_confirmation` should be true

Returns: `{valid: bool, issues: [...], warnings: [...]}`. Does NOT mutate state.

---

## 6. Integration with Planner

The Planner skill must follow the Admission Protocol:

1. Read user request
2. Answer the 8 admission protocol questions (Section 4)
3. Produce a structured Admission Decision (Section 3 schema)
4. Validate it: `aiwf change validate-decision --file admission.json`
5. Resolve any validation issues
6. Ask user for confirmation when `needs_human_confirmation=true` or `confidence=low`
7. Only then: `aiwf plan create` / `aiwf goal-tree graft` / `aiwf goal-tree init-root --type temporary`

The Planner must NOT rely on `aiwf change admit` as an authoritative judgment. Use it only as a quick heuristic check — never as the final decision.

---

## 7. Review Orphan-Patch Detection

During review, the following warnings are checked:

| Check | Condition | Severity (L0/L1) | Severity (L2/L3) |
|-------|-----------|-------------------|-------------------|
| Task without plan | `task.plan_id` is empty or missing | warning | review_attention |
| Plan without target_goal | `plan.target_goal_id` missing or invalid | warning | review_attention |
| Goal without graft interface | parent set but no `graft_interface` or `graft_history` | warning | review_attention |
| Cross relation without reason | `cross_parent: true` but no reason | warning | review_attention |

These are **advisory only** — they appear in review output but do not block closure.

---

## 8. Non-Goals

- AIWF does NOT call an LLM API for admission judgment — the Planner (which IS an LLM) does the semantic work
- `validate-decision` does NOT do semantic judgment — only structural validation
- `admit` heuristic is explicitly non-authoritative
- This does NOT change `status --prompt` length
- This does NOT add context pack, multi-agent, or auto-scheduling

---

## 9. Contract Tests

**Heuristic fallback (existing, downgraded):**
1. `admit_change` returns recommendation with "heuristic" in notes
2. CLI `change admit` output says "heuristic recommendation only"

**Validation:**
3. `validate_admission_decision` passes valid attach_plan
4. `validate_admission_decision` rejects attach_plan missing target_goal_id
5. `validate_admission_decision` passes valid graft_goal with interface/provides/relation
6. `validate_admission_decision` rejects graft_goal missing interface_consumed
7. `validate_admission_decision` passes valid temporary_root
8. `validate_admission_decision` warns when confidence=low and needs_human_confirmation=false
9. `validate_admission_decision` rejects invalid target_goal_id
10. `validate_admission_decision` rejects invalid admission_type

**Integration:**
11. Review orphan checks include severity grading
12. Status --prompt stays within budget (regression)
