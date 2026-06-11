# AIWF Testing Principles

Tests must protect current design. When a test fails because the product
changed intentionally, fix the test — not the product.

## Non-Negotiable Contracts

- **Prompt shortness**: `status --prompt` / UserPromptSubmit hook context stays short
  (~200–800 chars). No surfaces, obligations, history, or capability lists dumped
  into the prompt context.

- **Skill diet**: Parent skills (`aiwf-planner`, `aiwf-review`) are entry points
  that delegate to sub-skills. Detailed rules (surface obligations, quality policy
  fields, fix-loop routes, environment checks) live in sub-skills
  (`aiwf-planner-contracts`, `aiwf-planner-meta`, `aiwf-review-trace`, etc.).

- **Human status is a glance**: `aiwf status` shows ~15 lines. Detailed diagnostics
  (quality policy, surfaces, context dispatch, awareness, gravity, environment)
  are in `aiwf status --debug`.

- **Impact-aware human docs**: Current-state and quality-digest markdown are written
  only when `Impact.quality_summary=yes`. No auto-write without explicit opt-in.

- **Silent side surfaces**: Quality surfaces declarations are stored in goal.json
  and shown as a one-line summary in human status. They are NOT dumped into prompt
  context or expanded in parent skills.

- **Level-based Quality Verdict**: L0/L1 may use V1-compatible `review_lite`.
  L2/L3 require full V2 Quality Verdict (PASS/PASS_WITH_RISK/REVISE/REJECT).
  Tests must not force V2 onto all levels.

- **Delta verification after fix-loop**: `resolve_fix_loop` checks that
  `required_verification` items are covered in testing evidence before allowing
  resolution. Fix-loop route=executor/tester with real code changes invalidates
  old review/cleanup, requiring delta review.

- **No auto assets/docs refresh**: Install and close do NOT mechanically populate
  PROJECT-MAP, ideas.md, or quality-digest unless explicitly requested.

## Test Migration Rules

When a test checks for content that has moved:
| Old location | New location |
|---|---|
| Parent planner skill detail | `aiwf-planner-contracts` / `aiwf-planner-meta` |
| Parent reviewer skill detail | `aiwf-review-trace` / `aiwf-review-verify` |
| Human status debug section | `status --debug` |
| Prompt context bloat | Removed intentionally — update test to check absence |
| Auto-written report | Check Impact gate, or remove assertion |

## Anti-Regression Tests

Place anti-regression tests in `tests/embedded/` with clear names. They must:
- Assert prompt context stays under a byte/line limit
- Assert parent skills do NOT contain sub-skill detail keywords
- Assert Impact gates are enforced
- Assert L1 review_lite does not require full V2 verdict
