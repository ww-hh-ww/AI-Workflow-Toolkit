> **LEGACY — not authoritative for AIWF V1.**
> See docs/V1_DESIGN_CONTRACT.md for current rules.

# Day-1 Foundation Tree — Stage 4.5 Design Contract

**Status:** Stage 4.5: validate-only. Planner proposes, machine validates, human reviews.
No auto-creation of goals/plans/tasks.

---

## 1. Purpose

When a new project or complex task starts, the Planner should NOT immediately create individual tasks. It should first bootstrap a **minimal but well-structured Rooted Functional Tree** — a Foundation Tree.

The Foundation Tree is deliberately incomplete. It provides **structural scaffolding** for subsequent work: a root, a first level of functional decomposition, high-level structural Plans, interface declarations, an active path to start execution, and placement for uncertain areas.

---

## 2. Day-1 Output Requirements

A valid Foundation Tree MUST answer:

1. What is the root? (Root Goal)
2. What are the first-level functional domains? (2–5 first-level Goals)
3. What structural Plan defines interfaces and boundaries?
4. What are the key interfaces?
5. Where does execution start? (Active Path)
6. What is uncertain? (Temporary Roots / Open Questions)
7. How does evidence roll up? (Evidence Rollup Policy)

A valid Foundation Tree must NOT:

- Fully decompose all sub-Goals
- Generate all tasks up front
- Pretend exploration is a stable Goal
- Overload status --prompt

---

## 3. Schema

```json
{
  "project_title": "string",
  "project_summary": "string (1-3 sentences)",

  "root_goal": {
    "id": "GOAL-ROOT",
    "title": "string",
    "intent": "string",
    "acceptance_boundary": "string"
  },

  "first_level_goals": [
    {
      "id": "string (e.g. G1, G2...)",
      "title": "string",
      "intent": "string",
      "relation_to_root": "extends | implements | decomposes",
      "child_goals": [
        {
          "id": "string",
          "title": "string",
          "intent": "string",
          "hierarchy_rationale": {
            "composition": "why the parent is incomplete without this child",
            "primary_ownership": "why this child primarily belongs here",
            "independent_outcome": false
          }
        }
      ]
    }
  ],

  "structural_plan": {
    "plan_id": "PLAN-STRUCTURE",
    "target_goal_id": "GOAL-ROOT or first-level goal ID",
    "plan_kind": "structural",
    "active_phase": "framing",
    "purpose": "string",
    "interfaces": [
      {
        "owner": "string (which goal/module owns this interface)",
        "description": "string",
        "consumers": ["string (which goals consume it)"]
      }
    ],
    "constraints": ["string"]
  },

  "active_path": {
    "sequence": ["string (goal or plan IDs in execution order)"],
    "reason": "string (why start here)"
  },

  "temporary_roots": [
    {
      "title": "string",
      "reason": "string (why not yet stable)",
      "resolution_criterion": "string (what would clarify it)"
    }
  ],

  "evidence_rollup_policy": {
    "task_to_plan": "string (how task evidence feeds plan progress)",
    "plan_to_goal": "string (how plan completion feeds goal acceptance)",
    "test_surface": "string (what test surfaces are relevant)"
  },

  "initial_milestone": {
    "title": "string",
    "covers": ["string (goal/plan IDs)"],
    "acceptance_criteria": ["string"]
  }
}
```

---

## 4. Validation Rules

| Check | Rule |
|-------|------|
| root_goal | Required. Must have id, title, intent. |
| first_level_goals | 1–7 entries. Each must have id, title, intent, relation_to_root. |
| child_goals | Optional recursive decomposition. Every child requires hierarchy_rationale with composition, primary_ownership, and independent_outcome=false. If independent_outcome=true, use a sibling Goal plus relation. |
| structural_plan | Required. plan_kind must be "structural". active_phase must be "framing" or "implementation". Must have at least 1 interface. |
| interfaces | Each interface must have owner and description. |
| active_path | Required. Must reference only declared goal/plan IDs. |
| temporary_roots | Optional. Each must have reason. |
| evidence_rollup_policy | Required. Must have task_to_plan and plan_to_goal. |
| initial_milestone | Optional. If present, must have acceptance_criteria. |

---

## 5. Human Output

```
Foundation Tree Proposal

Root Goal:
  GOAL-ROOT: AIWF Long-task Governance Kernel

First-level Goals:
  G1: Work Structure Foundation
    → decomposes: Root
  G2: Change Admission Workflow
    → extends: Root
  ...

Structural Plan:
  PLAN-STRUCTURE: framing
  Target: GOAL-ROOT
  Interfaces:
    - Goal Tree owns: functional skeleton
    - Plan Registry owns: procedural scaffolds
    - ...

Active Path:
  GOAL-ROOT → G1 → PLAN-STRUCTURE
  Why: Structure foundation must be stable before admission.

Uncertain Areas:
  - Context pack design (Temporary Root)
    Resolution: When goal tree and plan scaffold stabilize

First Milestone:
  MS-001: Foundation Tree accepted and active path ready

Evidence Rollup:
  Task → Plan: closed tasks update plan evidence_rollup
  Plan → Goal: complete plans soft-roll into goal evidence_rollup
```

---

## 6. CLI

```
aiwf goal-tree validate-foundation --file foundation.json
```

Validates the Foundation Tree against the schema. Outputs to stdout. Does NOT create any goals/plans/tasks.

Returns exit code 0 if valid, 1 if invalid.

Human-readable by default. `--json` for machine output.

---

## 7. Non-Goals

- Does NOT auto-create goals/plans/tasks
- Does NOT mutate any state file
- Does NOT require a complete tree
- Does NOT change status --prompt
- Does NOT require LLM API
- Does NOT build context pack or multi-agent
