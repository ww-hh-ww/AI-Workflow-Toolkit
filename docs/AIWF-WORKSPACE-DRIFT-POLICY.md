# AIWF Workspace Drift Policy

## When to scan

- At phase boundaries: new task start, before execution, before review, before close
- After user mentions external changes (git pull, IDE edits, other agent)
- NOT on every UserPromptSubmit

## What the scan reports

- Modified/added/deleted/renamed/untracked files (from git status)
- Separated into project_changes and governance/support changes
- Does NOT read file contents, generate evidence, or auto-commit

## Planner handling

| Drift | Action |
|-------|--------|
| None | Continue |
| Project changes within allowed_write | Ask user: adopt as external contribution? |
| Project changes outside scope | Request user decision: scope expansion, split task, or revert |
| Governance files changed | Review before continuing; treat as high-risk |
| Deleted files | Verify intent; may need scope adjustment |

## Rules

- External changes are NOT AIWF evidence until explicitly reviewed/adopted
- Drift scan does NOT auto-modify scope, evidence, or state
- Governance drift needs extra caution

## Fresh install governance drift

Fresh AIWF install may show .aiwf/, .claude/, scripts/aiwf_*, and CLAUDE.md as governance/support drift until the project baseline is committed. Planner should distinguish expected AIWF setup files from unexpected hook/settings changes — both appear as governance_changes.
