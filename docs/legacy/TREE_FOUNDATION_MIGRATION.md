> **LEGACY — not authoritative for AIWF V1.**
> See docs/V1_DESIGN_CONTRACT.md for current rules.

# Rooted Functional Tree — Migration & Implementation Strategy

**Depends on:** `AIWF_DESIGN_AXIOMS.md`, `NODE_CONTRACT.md` (both must be frozen).
**Status:** Stage 3.0–3.9 complete. Stage 4.0–4.6: Change Admission, Action Plan, Admission-aware Review, Day-1 Foundation Tree, Entry Protocol hardening, Role Skill Alignment. Stage 4.7–4.7.2: Semantic Execution Frontier + Work Packet + Source-of-Truth & Node Contract Alignment. Five core nodes (Mission/Goal/Milestone/Plan/Task) explicitly defined. Evidence downgraded to lightweight proof artifact. Milestone defined as structural convergence node. Truth source contract written (object truth vs relationship truth). Milestone schema enhanced with structural convergence fields. 1359 contract tests passing. Readiness: structure, validation, role skills, agent wrappers, frontier dispatch, precision hardening, and node contract alignment complete; ready for Stage 5 Context Pack.

---

## 1. Migration Strategy

### 1.1 Principle: Registry Authority, Not Legacy Preservation

- New state files are created alongside existing ones; Plan Registry and Goal
  Tree Registry are new additions that do not destroy old data.
- Existing fields may be kept as display/write aliases, but authority moves to
  the new machine-readable fields immediately.
- `schema_version` bumps signal the migration point.
- This track does not guarantee smooth activation for old `.aiwf` workspaces.
  When old task-bound markdown plans are detected, the system fails with a
  clear remediation message instead of auto-migrating.

### 1.2 Stage Dependencies

```
Stage 3.0 (Design Contracts)
  └─ Stage 3.1 (Goal Tree Registry Skeleton)
       └─ Stage 3.2 (Goal Tree CLI)
            └─ Stage 3.3 (Plan attaches to any Goal)
                 └─ Stage 3.4 (Plan-to-Goal rollup)
                      └─ Stage 3.5 (Temporary Root)
                           ├─ Stage 3.6 (Graft and Prune)
                           ├─ Stage 3.7 (Sibling Relations)
                           └─ Stage 3.8 (Impact Cone)
```

Stages 3.5-3.8 are parallel-ready after 3.4 completes, but should be built
incrementally to keep each change reviewable.

### 1.3 What This Sequence Does NOT Touch (Until Later)

- Task activation gates (no new blockers from Goal Tree)
- Task close gates (no new blockers from Goal Tree)
- `prepare-close` hard gates (Plan Registry does not participate)
- `fix-loop` mechanism
- `review.json` / `testing.json` schemas
- `evidence/records.json` schema
- `status --prompt` budget (strictly preserved)

---

## 2. Implementation Stages

### Stage 3.0: Design Contracts (this document set)

**Deliverables:**
- `docs/AIWF_DESIGN_AXIOMS.md` — authoritative 12-axiom design
- `docs/NODE_CONTRACT.md` v2.0 — unified node model aligned to axioms
- `docs/TREE_FOUNDATION_MIGRATION.md` — this document

**Acceptance:**
- All three documents internally consistent
- No five-layer chain language remains
- Contract tests enumerated in NODE_CONTRACT.md Appendix B

---

### Stage 3.1: Goal Tree Registry Skeleton

**New files:**
| File | Purpose |
|------|---------|
| `.aiwf/state/goals.json` | Goal Tree registry |
| `aiwf_core/core/state/goal_tree_ops.py` | CRUD + validation |

**Schema:**
```json
{
  "schema_version": 1,
  "active_goal_id": null,
  "roots": [],
  "goals": [],
  "relations": []
}
```

**Goal entry:**
```json
{
  "id": "GOAL-001",
  "title": "...",
  "root_type": "main",
  "parent_goal_id": null,
  "child_goal_ids": [],
  "children_order": [],
  "intent": "",
  "acceptance_boundary": "",
  "attached_plan_ids": [],
  "status": "active",
  "visibility": "default",
  "created_at": "",
  "updated_at": ""
}
```

**Required operations:**
- `load_goal_tree()` / `save_goal_tree()`
- `list_goals()` / `get_goal(id)`
- `upsert_goal(entry)` / `add_child_goal(parent_id, child_id)`
- `validate_goal_tree()` — roots reference existing Goals, root Goals have no
  parent, child IDs exist, children_order references only child_ids, parent-child
  consistency, no cycles

**Existing singleton mapping:**
- `goal.json` maps to legacy node id `GOAL-001`
- `goals.json` is created alongside, not replacing, `goal.json`
- `GOAL-001` is auto-populated from existing `goal.json` on first access

**Contract tests:**
1. `test_goal_tree_empty_on_install` — goals.json created with empty registry
2. `test_goal_tree_add_child` — add_child_goal updates parent and child
3. `test_goal_tree_no_cycles` — creating a cycle is rejected
4. `test_goal_tree_root_no_parent` — root with parent_goal_id set is rejected
5. `test_goal_tree_legacy_goal_maps_to_GOAL_001` — existing goal.json → GOAL-001

**Must NOT:**
- Change task activation
- Change task close
- Change Plan Registry behavior
- Add CLI yet (Stage 3.2)

---

### Stage 3.2: Goal Tree CLI

**New files:**
| File | Purpose |
|------|---------|
| `aiwf_core/commands/goal_tree_commands.py` | CLI handlers |

**Modified files:**
| File | Change |
|------|--------|
| `aiwf_core/commands/parser.py` | Add `goal-tree` command group (ADVANCED tier) |

**Commands:**
```
aiwf goal-tree init-root <ID> [--type main|temporary|branch]
aiwf goal-tree add <ID> --parent <PARENT-ID>
aiwf goal-tree show [<ID>]
aiwf goal-tree list
aiwf goal-tree validate
```

**Constraints:**
- `show` without ID displays the active root's tree
- `show` output is a compact tree, not full node detail
- No activation integration yet
- No close integration yet

**Contract tests:**
1. `test_goal_tree_cli_init_root` — creates root Goal in goals.json
2. `test_goal_tree_cli_add_child` — adds child, updates children_order
3. `test_goal_tree_cli_show` — output contains tree structure
4. `test_goal_tree_cli_validate_rejects_orphan` — orphan child detected

---

### Stage 3.3: Plan attaches to any Goal

**Modified files:**
| File | Change |
|------|--------|
| `aiwf_core/core/state/plan_ops.py` | Add `target_goal_id`, `plan_kind`, `interfaces`, `constraints`, `child_goal_policy` |
| `aiwf_core/core/state_schema.py` | Extend `default_plans()` schema |
| `aiwf_core/commands/parser.py` | `plan create` adds `--target-goal`, `--kind` flags |

**New plan create syntax:**
```
aiwf plan create PLAN-001 --goal-id GOAL-001 --kind structural
aiwf plan create PLAN-002 --goal-id GOAL-003 --kind implementation
```

**Constraints:**
- `plan_kind` defaults to `implementation` for backward compat
- `target_goal_id` defaults to `goal_id` when not specified
- Structural Plans may have zero Tasks
- Implementation Plans follow existing Task attachment rules

**Contract tests:**
1. `test_plan_create_with_kind` — structural plan created with correct kind
2. `test_plan_target_goal_defaults_to_goal_id` — backward compat
3. `test_structural_plan_allows_zero_tasks` — no task requirement for structural
4. `test_plan_kind_validation` — invalid kind rejected

---

### Stage 3.4: Plan-to-Goal rollup

**Modified files:**
| File | Change |
|------|--------|
| `aiwf_core/core/state/reconcile_ops.py` | Add Plan→Goal rollup logic |
| `aiwf_core/core/task_ledger.py` | Extend `close_task()` for Goal rollup |

**Behavior:**
- Task close updates Plan progress (existing Stage 1.5)
- Plan `complete` writes soft rollup to parent Goal's `evidence_rollup`:
  ```json
  {
    "plan_id": "PLAN-001",
    "status": "complete",
    "closed_task_count": 3,
    "total_task_count": 3,
    "key_files_changed": [...],
    "testing_status": "passed",
    "review_status": "accepted"
  }
  ```
- Read-only rollup: does NOT auto-close Goals
- Does NOT become a hard gate

**Contract tests:**
1. `test_plan_complete_rolls_up_to_goal` — evidence_rollup populated on goal
2. `test_rollup_does_not_auto_close_goal` — goal remains active after plan complete
3. `test_rollup_preserves_multiple_plans` — multiple plan rollups coexist

---

### Stage 3.5: Temporary Root

**Modified files:**
| File | Change |
|------|--------|
| `aiwf_core/commands/goal_tree_commands.py` | Add `--type temporary` support |
| `aiwf_core/commands/flow.py` | `status --prompt` excludes temporary roots |
| `aiwf_core/core/state/goal_tree_ops.py` | Add `list_temporary_roots()` |

**Command:**
```
aiwf goal-tree init-root TMP-001 --type temporary
```

**Constraints:**
- Temporary roots do not appear in `status --prompt`
- Temporary roots appear in `status --debug`
- Temporary roots can have child Goals, Plans, Tasks like any Goal
- Temporary roots have no `active_goal_id` in state.json (main root retains it)

**Contract tests:**
1. `test_temporary_root_hidden_from_prompt` — not in --prompt output
2. `test_temporary_root_visible_in_debug` — present in --debug output
3. `test_temporary_root_can_have_children` — full subtree support

---

### Stage 3.6: Graft and Prune

**Modified files:**
| File | Change |
|------|--------|
| `aiwf_core/commands/goal_tree_commands.py` | Add `graft`, `prune` subcommands |
| `aiwf_core/core/state/goal_tree_ops.py` | Add `graft_branch()`, `prune_branch()` |

**Commands:**
```
aiwf goal-tree graft <SOURCE-ID> --target <PARENT-GOAL-ID> --reason "..."
aiwf goal-tree prune <BRANCH-ID> --reason "..."
```

**Graft operation:**
1. Validates source and target exist
2. Sets `parent_goal_id` on source to target
3. Removes `root_type` (no longer a root)
4. Updates target's `child_goal_ids` and `children_order`
5. Records graft metadata: `{grafted_from, grafted_to, reason, timestamp}`
6. Warns if source had sibling relations that may conflict

**Prune operation:**
1. Validates branch exists
2. Sets `status = archived`, `visibility = archived_only`
3. Does NOT delete files or evidence
4. Records prune metadata: `{pruned_branch, reason, evidence_validity, timestamp}`
5. Lists abandoned Plans and Tasks for human review

**Contract tests:**
1. `test_graft_moves_branch_to_target` — parent_goal_id updated
2. `test_graft_removes_root_type` — no longer a root after graft
3. `test_graft_requires_reason` — missing reason is error
4. `test_prune_archives_not_deletes` — status=archived, files intact
5. `test_prune_lists_abandoned_children` — warnings for Plans/Tasks

---

### Stage 3.7: Sibling Relations

**Modified files:**
| File | Change |
|------|--------|
| `aiwf_core/core/state/goal_tree_ops.py` | Add `add_relation()`, `remove_relation()`, `get_relations()` |
| `aiwf_core/commands/goal_tree_commands.py` | Add `relation add/remove/show` |
| `aiwf_core/commands/parser.py` | Add `relation` command group (ADVANCED tier) |

**Commands:**
```
aiwf relation add <SRC-ID> <TGT-ID> <TYPE> --reason "..."
aiwf relation remove <SRC-ID> <TGT-ID>
aiwf relation show <NODE-ID>
```

**Relation types:** `depends_on`, `blocks`, `conflicts_with`, `invalidates`, `supports`

**Constraints:**
- Relations stored in `goals.json` under `relations` array
- Relations are advisory only — do NOT gate activation
- No graph traversal engine; simple iteration only
- `depends_on` in relations is distinct from `task.dependencies[]`

**Contract tests:**
1. `test_relation_add_stores_in_registry` — appears in goals.json
2. `test_relation_does_not_block_activation` — advisory only
3. `test_relation_remove` — removed from registry
4. `test_relation_show` — lists all relations for a node

---

### Stage 3.8: Impact Cone

**Modified files:**
| File | Change |
|------|--------|
| `aiwf_core/core/state/impact_ops.py` | NEW: compute Impact Cone |
| `aiwf_core/commands/goal_tree_commands.py` | Add `impact` subcommand |

**Command:**
```
aiwf goal-tree impact <GOAL-ID>
```

**Output:**
```
Impact Cone for GOAL-Plan-Registry:
  Ancestors: GOAL-Long-Task-Foundation, GOAL-AIWF-V1
  Children: (none)
  Sibling relations:
    GOAL-Milestone depends_on GOAL-Plan-Registry
  Attached Plans: PLAN-Registry-Authority (structural, active)
  Active Tasks: TASK-Activation-Check, TASK-Close-Reconcile
  Related Milestones: MS-Stage-1 (active)
  Recent Evidence: EV-042, EV-043
  Potentially affected reviews: REVIEW-007
```

**Constraints:**
- Read-only, advisory output
- Does NOT block any gate
- May become a gate input after model stabilizes
- Computed from tree position + relations, not from stored weights

**Contract tests:**
1. `test_impact_cone_includes_ancestors` — all ancestors listed
2. `test_impact_cone_includes_sibling_relations` — relations shown
3. `test_impact_cone_readonly` — no state mutations
4. `test_impact_cone_nonexistent_node` — clear error for missing ID

---

## 3. Cross-Cutting Concerns

### 3.1 Plan Registry (parallel track from old Stages 1.x)

The Plan Registry work defined in the old migration doc (Stages 1.0-1.6) runs
as a parallel prerequisite track to Stages 3.1+. It is assumed complete or
in-progress when Stage 3.3 begins:

- Stage 1.0: Plan Registry Skeleton — `plans.json`, `default_plans()`, CRUD
- Stage 1.1: Plan Authority Definition — `plans.json` sole machine truth
- Stage 1.2: Task References — authoritative `plan_id` / `goal_id`
- Stage 1.3: Real Plan IDs — independent `PLAN-ID` support
- Stage 1.4: Activation Validation — L1+ validates against registry
- Stage 1.5: Plan Reconcile — task close updates plan progress
- Stage 1.6: Registry Authority Hardening — legacy markdown blocks activation

### 3.2 Milestone (parallel track from old Stage 2)

The Milestone work similarly runs as a parallel track:

- `milestones.json` with `active_milestone_id`
- CLI: create/list/show/close with stage synthesis
- Plan/Task `milestone_id` fields
- Legacy `task.milestone` string deprecated

### 3.3 Preserving Existing Tests

All 63 existing embedded tests must pass after each stage. New contract tests
are additive. No existing test behavior changes except where explicitly noted
(old milestone field becoming non-authoritative, plan-id validation, etc.).

---

## 4. Test Plan

### 4.1 Test Categories

| Category | Count (est.) | Description |
|----------|-------------|-------------|
| Goal Tree contract tests | ~15 | Stages 3.1-3.8 per-stage tests |
| Plan Registry contract tests | ~7 | From old Stage 1 |
| Milestone contract tests | ~4 | From old Stage 2 |
| Updated existing tests | ~5 | Field alias, legacy behavior changes |
| Regression suite | 63 | Full embedded test suite |
| Smoke test | 1 | `run-real-tester-smoke.sh` |

### 4.2 Stage Gating

No stage proceeds to implementation until:
1. Its contract tests are written and reviewed.
2. Previous stage tests pass on merged code.
3. `run-all-embedded-tests.sh` passes clean (0 failures).
4. `status --prompt` stays ≤800 characters (byte-count assertion).

---

## 5. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Goal Tree complexity leaks into prompt | Low | High | Strict byte-count test; temporary roots hidden |
| Plan Registry breaks existing task activation | Medium | High | Legacy blocks with remediation, not silent failure |
| Goal recursion creates cycles | Low | Medium | Cycle detection in `validate_goal_tree()` |
| Graft breaks parent Goal integrity | Medium | Medium | Graft records reason + affected Plans; human reviews |
| Impact Cone becomes a de facto gate too early | Low | Medium | Read-only advisory output; no gate integration |
