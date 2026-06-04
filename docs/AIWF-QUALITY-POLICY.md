# AIWF Quality Policy Kernel

## Task Types

| Type | Test Focus | Review Focus | Escalation |
|------|-----------|-------------|------------|
| code_label_or_text_change | targeted | correctness + scope | file count > 2 |
| small_function | happy + edge | correctness + simplicity | cross-module import |
| bug_fix | regression + root cause | correctness + regression risk | API change |
| api_endpoint | boundary + adverse + auth | correctness + security + compatibility | auth/permission change |
| refactor | regression + equivalence | simplicity + overengineering | public API change |
| numeric_semantics | risk matrix + boundary + adversarial | correctness + security + deferred risks | architecture impact |
| security_sensitive | adversarial + penetration + auth matrix | full_review; requires user decision, recommends L3_full_power | ANY test failure |

## Workflow Level → Quality Depth

| Level | Test | Review | Exploration | Asset | Cleanup | Git |
|-------|------|--------|-------------|-------|---------|-----|
| L0 | targeted | review-lite | no broad (2 files) | not default | close-light | no auto commit |
| L1 | targeted + small regression | reviewer-light | target+test (5 files) | optional | close-light | no auto commit |
| L2 | regression + boundary/adverse | standard review | asset-first (15 files) | when useful | reviewer validates | reviewer checks diff |
| L3 | risk matrix + integration/adversarial | full review + structure + cleanup + deferred risks | structured packet (50 files) | required if fresh | explicit phase if stale | planner proposes, user confirms |

## Key Rules

- **Planner selects** task_type + workflow_level + templates BEFORE execution
- **Tester/reviewer follow** templates; may request escalation, not unilaterally expand
- **Security-sensitive**: requires user decision, recommends L3_full_power, uses full_review minimum
- **Asset-first** only for L2/L3; stale assets are advisory, source is truth
- **Exploration budget** is per-level; L0 reads 2 files max, L3 reads up to 50
- **No auto git commit** at any level; planner suggests, user confirms
