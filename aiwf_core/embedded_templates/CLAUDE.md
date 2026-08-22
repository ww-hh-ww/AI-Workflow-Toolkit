# AIWF Runtime Protocol

Run `aiwf status --prompt` first. It is the routing source of truth.

Load every skill listed under `Required skills:` and follow that skill. Do not
choose phase skills from memory.

Use AIWF assets first. Read MD docs for meaning: `mission.md`,
Goal/Plan/Task/Milestone docs, and memory. Read JSON/status/records for machine
state, gates, evidence, testing, and review results. Do not treat JSON as the
semantic contract.

Planner uses the `Planner memory root` printed by status as a tiny long-term
planning notebook. Before handing off work, and when finished work returns to
Planner, decide whether any memory should stay as-is, change, be deleted, or be
added.

Use Claude Code engineering judgment to verify those assets against code,
runtime, commands, and evidence. If AIWF assets and code reality disagree, do
not guess. Surface the mismatch and follow the phase skill.

## Hard Rules

- At Plan closeout, suggest `/aiwf-architect` and let the human choose whether
  to use it. It is also used for milestone acceptance when
  `aiwf status --prompt` routes there.
- One Planner owns governance. One Plan owns one worktree, and one worktree has
  at most one active Task. Different Plans may run in parallel after Planner
  checks real dependencies. Executor, Tester, and Reviewer remain sequential
  inside each Task.
- Give each workflow Agent one Task ID. AIWF supplies the current Task contract
  and assigned worktree, then keeps project tools in that worktree. Do not call
  `EnterWorktree` or copy changes between worktrees.
- Do not skip required skills, roles, proof level, or gates unless the user
  explicitly accepts that risk.
- Do not hand-edit `.aiwf/state/` or `.aiwf/records/`; use `aiwf` commands.
- Do not inspect AIWF toolkit source or generated hook implementation to infer,
  bypass, or appease workflow gates. Use the current Skill, `aiwf status
  --prompt`, `aiwf task proof`, `aiwf doctor`, and CLI help. If behavior still
  conflicts with those public surfaces, report the exact output to Planner.
  This restriction does not apply when the user's task is explicitly to develop
  or debug AIWF itself.
- Do not run `aiwf task force-close`; human emergency override only.
- Do not run `aiwf task interrupt`; human interruption only.
- Do not run `aiwf task restore`; ask the human to choose `ready` or `closed`
  and run it with a reason when a cancelled Task must return.
- Do not run `aiwf task reopen`. If a normal close is later proven false, ask
  Planner to assess consumption. A human may reopen only an unmerged,
  unconsumed latest Task result; otherwise create a corrective Task.
- Do not run `aiwf fixloop continue`; ask the human when repeated failures require a decision.

## Governance Git

At a Plan integration, Task/Plan close boundary, or after a Planner governance
edit, run `aiwf governance status` when the next action depends on Git state.
In `tracked` mode, `aiwf governance checkpoint` commits only pending stable
`.aiwf` governance files; it never commits project code. `aiwf governance
tracking tracked|local` changes the human's tracking choice and must not be run
unless the user asks for that choice. Do not invent `aiwf checkpoint`.
