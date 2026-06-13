# AIWF 技术文档

这是 AIWF 的技术文档，给维护者和贡献者看。每个子系统讲清楚做什么、关键函数、数据流转、边界条件、踩过的坑。

> 这不是一次性写的，是跟着 task 长出来的。改了哪个子系统就更新哪段。长章节拆成独立文件，短段落留在索引里。

## 证据管线

Hook 如何自动捕获每次文件变更为机器证据。

### 整体流程

```text
PreToolUse → aiwf_pre_snapshot.py → take_snapshot()
  → 扫描项目文件（MD5 hash），写入 .aiwf/runtime/internal/pre-tool-snapshot.json
  → 工具执行（Write/Edit/Bash）
PostToolUse → aiwf_capture_evidence.py → diff_snapshot()
  → 重新扫描文件，对比快照，找出 changed_files
  → record_post_tool_event() → 写入 evidence/records.json
  → attribution: strong（有快照对比）或 weak（回退到 dirty-set delta）
```

### 关键函数（`aiwf_core/hooks/common/snapshot.py`）

- `take_snapshot(cwd, tool_name, tool_input)` — 扫描全部项目文件，写快照。跳过 `.git`、`node_modules`、`.aiwf` 等目录。文件 < 1MB 做 MD5，大文件只用 mtime+size
- `diff_snapshot(cwd)` — 读快照，重新扫描，对比。返回 changed_files + attribution。快照不存在时返回 weak
- `clear_snapshot(cwd)` — PostToolUse 后清理快照

### 关键函数（`aiwf_core/hooks/common/evidence_writer.py`）

- `record_post_tool_event(event, cwd, ...)` — 创建 evidence record。优先用 pre/post snapshot 结果（strong），回退到 dirty-set delta（weak）。写入 `evidence/records.json`

### Bootstrap 机制

Hook 脚本在目标项目的 `scripts/` 下，运行时需要导入 `aiwf_core`。Bootstrap 代码在文件头：

1. 添加项目根到 `sys.path`
2. 尝试 `import aiwf_core` — pip install 后直接可用
3. 失败则读 `.aiwf/runtime/internal/toolkit-path.txt` — `aiwf install` 写入的 AIWF 安装路径
4. 写入 `.aiwf/runtime/internal/hook-diag.log` 诊断日志（持久化，不随快照清理）

### 踩过的坑

**stdin 空导致 PreToolUse 静默退出**（TASK-013）：`parse_claude_stdin()` 返回空 dict 时 `sys.exit(0)`，快照从未写入，全部 evidence 都是 weak。修复：stdin 空时仍用 `Path.cwd()` 写快照。

**路径空格导致 shell 断裂**（TASK-019）：项目路径含空格（如 `External Asset Lab`），settings.json 中的 hook command 未被引号包裹，shell 把空格前的路径当命令执行。修复：`_build_settings_json` 中所有命令用 `"${CLAUDE_PROJECT_DIR}/scripts/..."` 双引号包裹。

**硬编码绝对路径**（TASK-019）：`_AH_TOOLKIT_ROOT` 在生成脚本时被硬编码为 AIWF 源码路径。另一台机器或目录移动后脚本无法导入 `aiwf_core`。修复：改为运行时发现——先 `import aiwf_core`，失败则读 `toolkit-path.txt`。

**testing command 匹配不上**（TASK-019）：`testing.json` 存 `"bash scripts/ci-check.sh"`，machine evidence 存 `"cd /path && bash scripts/ci-check.sh 2>&1 | tail -1"`。精确字符串匹配失败。修复：子串匹配 + 接受所有 `status=accepted` 的 evidence 而非仅 Reviewer 指定的 ID + 不要求 `exit_code=0`。

**scope violation 跨 task 误报**（TASK-019-021）：旧 task 的 `scope_violation_events` 在 `review.json` 中不携带 task_id。新 task 修改相同文件时触发误报，`resolve_fix_loop` 在全部事件已 `resolved_reverted` 时走入错误分支。修复：`force` 参数跳过 git diff 检查，不清除 review result。

## 闭合门链

`prepare_close` 检查 5 个流程合规门，不是机械正确性。

### 5 个门（`aiwf_core/core/state_ops.py:prepare_close`）

1. Phase 序列 — 不能在 discussing/planned/closed 阶段闭合
2. Evidence 存在 — 至少一条 `status=accepted` 记录
3. Testing 记录 — `testing.status != "missing"`
4. Review 记录 — `review.result != "unknown"`
5. Cleanup 完成 — `cleanup_status == "fresh"` 且无 `stale_items`

全部通过 → `phase=closed, close_attempt=False`。不通过 → 返回 blocker 列表和 actionable 的解决命令。

### Stop hook（`aiwf_core/core/closure_contract.py:closure_conditions_met`）

独立重验证相同的 5 个门。`phase=closed` 时直接放行。`passed` 字段决定是否允许 Stop。

### 闭合理由

原来有 58+ 个检查条件（session diversity、命令匹配、exit_code、structure status、adversarial 处置……），每个条件都可能变成 blocker。正常的合法操作频繁撞上针对边缘情况设计的门。产生 7 个逃生口（`planner_inline_session`、`cancel-close`、`--force` fix-loop、auto-accept evidence、closure_allowed 自动提升、exit_code 过滤移除、子串匹配）。

削到 5 个门的理由：门应该保障流程被遵循，不是用规则穷举正确性。独立 Tester 和 Reviewer 负责发现质量问题；`aiwf status` 作为 advisory 展示全部机械信号。

### 踩过的坑

**closure_allowed 死锁**：Reviewer 调用 `record-review` 时忘传 `--closure-allowed` → review.json 中 closure_allowed=False → prepare_close 死锁。修复：`prepare_close` 在看到 `result=accepted` 时自动提升 closure_allowed。

**session diversity 硬门**：L2/L3 要求 3 个独立 session 的证据，但 Planner inline 执行只有 1 个。修复：`planner_inline_session` 豁免（后来随 58→5 门简化一起移除，因为 session diversity 不再是门）。

**close_attempt 死锁（已修复）**：prepare_close 无 blocker 时直接设置 phase=closed, close_attempt=False, closure_allowed=True，不再依赖 Stop hook 来清。`aiwf state cancel-close` 作为恢复路径可重置卡住的 closing 状态。

## Hook 架构

### 8 个脚本（`aiwf_core/embedded_templates/scripts/`）

| 脚本 | Hook 事件 | 职责 |
|------|---------|------|
| `aiwf_status.py` | UserPromptSubmit | 每轮注入 phase/route/blocker 状态 |
| `aiwf_pre_snapshot.py` | PreToolUse | 操作前拍文件快照 |
| `aiwf_capture_evidence.py` | PostToolUse | 操作后对比快照，写证据 |
| `aiwf_scope_check.py` | PreToolUse | 阻止范围外的文件写入 |
| `aiwf_bash_guard.py` | PreToolUse | 阻止危险 shell 命令 |
| `aiwf_review_gate.py` | Stop | 评估闭合门，决定是否允许 Stop |
| `aiwf_rebase_state.py` | — | Planner 手动调用，重建 carry-forward 状态 |
| `aiwf_export_report.py` | — | 生成闭合报告 (`.aiwf/artifacts/reports/闭合报告.md`) |

### 生成机制（`aiwf_core/install_claude.py:_write_scripts`）

`aiwf install` 从 `embedded_templates/scripts/` 读取模板，注入 bootstrap（项目根路径 + `aiwf_core` 发现逻辑），写入目标项目的 `scripts/`。`aiwf_status.py` 使用 stdlib-only bootstrap（不导入 `aiwf_core`，保持 prompt cache 友好）。

### 权限（`aiwf_core/install_claude.py:_build_settings_json`）

`settings.json` 的 `permissions.allow` 包括 `Bash(aiwf:*)`（CLI 命令）和 `Bash(scripts/aiwf_*.py:*)`（hook 脚本），以及 `.aiwf/**` 的 Read/Write/Edit。

## 状态机

### Phase 流转（`state.json:phase`）

```text
discussing → planned → implementing → testing → reviewing → closing → closed
```

- discussing/planned → 不能闭合
- 实现/测试/审查阶段 → 可以闭合（通过 prepare_close）
- prepare_close 无 blocker → 直接 closed
- closed → 可以激活下一个 task

### 关键文件

| 文件 | 维护方式 | 用途 |
|------|---------|------|
| `state/state.json` | CLI（`aiwf state ...`） | phase、level、context、task |
| `state/goal.json` | CLI（`aiwf state record-quality-brief`） | 目标、合同、架构约束 |
| `state/contexts.json` | CLI（`aiwf state start-context`） | 上下文和读写边界 |
| `state/fix-loop.json` | CLI（`aiwf fixloop ...`） | 修复路由 |
| `evidence/records.json` | Hook 自动写入 | 机器证据 |
| `quality/testing.json` | CLI（`aiwf state record-testing`） | 测试状态 |
| `quality/review.json` | CLI（`aiwf state record-review`） | 审查结果 |

核心机械 truth（state/goal/contexts/fix-loop/task-ledger）只能通过 CLI 修改，直接 Write/Edit 被 scope hook 阻断。

## 路由系统（`aiwf_core/core/routing.py`）

### L0-L3 评分

`compute_routing_score(factors, file_count)` 根据因子计算分数：
- 文件数 1-2: +0, 3-5: +1, 6+: +2
- 跨模块: +2, 公开 API: +2, 语义变更: +2
- 安全/数据风险: +3, 架构影响: +2, 历史延迟风险: +1

硬升级触发器：破坏性命令/发布/数据迁移/安全风险 → L3；跨模块+语义变更 → L2。

### Gravity（`aiwf_core/core/task_gravity.py`）

纯函数，从 task-history 计算历史压力。检查：文件热点（变更 >=3 次）、fix-loop 趋势、架构漂移、测试债务。输出 `history_weight`（0.0→1.0）、`suggested_min_level`、`hard_constraints`、`context_messages`。
