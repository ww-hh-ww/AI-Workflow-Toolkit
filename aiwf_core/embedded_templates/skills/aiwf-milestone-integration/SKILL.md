---
name: aiwf-milestone-integration
description: Exhaustive system connectivity audit at milestone boundaries
---

# AIWF Milestone Integration

## STOP — Check topology BEFORE any other action

Read `.aiwf/state/state.json` → `workflow_level`.
L0=inline, L1/L2/L3=SPAWN subagent.

**If workflow_level is NOT "L0_direct":**
You are planner-main. You do NOT test.

```
Agent({subagent_type: "aiwf-tester", prompt: "Milestone integration test for <MILESTONE-ID>. ..."})
```

**Only continue if workflow_level IS "L0_direct".**

---

## Purpose

Per-task tests verified individual changes. Now verify the WHOLE system connects
— exhaustively. Do not read the Goal tree. Do not trust declarations.

## STEP 1 — Pre-judge structure (planner-main, read-only)

Read the project structure. Identify:

- **Main path**: the primary user journey through the system. Start from the
  main entrypoint (CLI, server, UI). Trace which modules/files it touches.
- **Branches**: every other entrypoint, subcommand, route, or action path.
- **All project files**: list every source file (not build artifacts, not deps).
  This is the universe you will verify.

You are pre-judging — use code structure, imports, entrypoint registration.
Do NOT run anything yet. The pre-judgment tells subagents where to look.
It may be wrong — subagents will correct it.

## STEP 2 — Fan-out subagents

### Subagent A: Main path
```
Agent({subagent_type: "aiwf-tester", prompt: "
  Trace the MAIN path: <PRE-JUDGED-PATH>.
  Run it end to end. Record actual output.

  For EVERY file this path touches: list every function/method. Run the
  project's full test suite for those files. Any function that is not
  exercised by any test → mark as 'untested'.

  Return:
  - The actual main path observed (may differ from pre-judgment)
  - Every file touched
  - Every function in those files + whether it was exercised
  - Test results
"})
```

This subagent runs first. Its output (especially the actual main path
description) is shared with all branch subagents.

### Subagents B-N: Branches (parallel, one per branch)
```
Agent({subagent_type: "aiwf-tester", prompt: "
  Trace ONE branch: <PRE-JUDGED-BRANCH>.
  The main path (from subagent A) is: <MAIN-PATH-DESCRIPTION>.

  Run this branch end to end. Record actual output.

  For EVERY file this branch touches: list every function. Run full tests.

  Then trace: does this branch connect to the main path?
  - connected → main (data/control flows to main)
  - connected → branch only (connects to another branch, not main)
  - isolated (dead-ends, no consumer beyond itself)
  - internal loop (only calls itself, never leaves module boundary)

  Return:
  - The actual branch observed
  - Every file touched, every function exercised
  - Connection classification + evidence
  - Test results
"})
```

Run all branch subagents IN PARALLEL after subagent A completes.
Each subagent tests ONE branch exhaustively.

## STEP 3 — Reachability audit (planner-main)

Collect all subagent outputs. Build two sets:
- **Reachable**: every file/function touched by ANY subagent
- **All files**: the full project file list from STEP 1

This is a **reverse call-site audit**, not merely entrypoint reachability.
For every function/method in every source file, name its caller(s), or classify
it as an entrypoint, intentionally unused with a reason, untraced, or
disconnected. A file being touched once does not account for every function in it.

Files in `All files` but NOT in `Reachable` → **dead code candidates**.

For each reachable function: did it actually connect to main or a branch?
A function that is called but whose output goes nowhere → `isolated function`.

Build the connectivity table:

```
PATH               → DEST              STATUS
<entry-A> (main)   → <module>/<func>   main
<entry-B>          → <module>/<func>   connected → main
<entry-C>          → (none)            isolated — no consumer
<file-X>/<func-Y>  —                   dead — not reachable from any entry
```

## STEP 4 — Document

Generate `.aiwf/artifacts/reports/里程碑-<MILESTONE-ID>-描述.md`:

```markdown
# <MILESTONE-ID>: <TITLE> (<DATE>)

## 主链路
<ENTRY> → <module> → <module> → <EXIT>

## 旁支
| 入口 | 连接状态 | 触及文件 |
|------|----------|----------|
| <entry> | connected → main | <N> files |
| <entry> | isolated | <N> files |

## 可达性
- 总文件: <N>
- 可达: <N> (主链路 <N> + 旁支 <N>)
- 未达: <N>
- 疑死代码: <list>

## 测试回归
- 全回归: <M>/<N> passed
- 未测试函数: <list>

## 已知断点
- <entry> 隔断 — 原因

## 下个里程碑
- <NEXT>: <focus>
```

## STEP 5 — Recording

```
aiwf milestone integration-test <MILESTONE-ID> \
  --status passed|failed \
  --coverage-mode function_reverse_trace \
  --main-path-status passed|failed \
  --source-file "<every source file, repeat>" \
  --accounted-file "<file with no callable functions, repeat>" \
  --function-trace "FILE::FUNCTION::CALLER1,CALLER2::entrypoint|connected|intentionally_unused|untraced|disconnected[::REASON]" \
  --command "main path: <actual-cmd> ::: <actual-output>" \
  --summary "Main path passes. <N> branches, <M> isolated, <K> unreachable files."
```

- Main path broken → status=failed
- Unreachable file without documented reason → status=failed
- Any untraced or disconnected function → status=failed and return to fix-loop
- Intentionally unused requires a concrete reason; otherwise it is untraced
- Main path passes, every source file and function accounted for → status=passed
- The CLI rejects `passed` without the reverse trace inventory. A prose summary cannot satisfy the gate.
