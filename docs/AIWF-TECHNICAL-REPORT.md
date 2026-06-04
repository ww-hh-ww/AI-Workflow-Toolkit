# AIWF 技术报告

日期：2026-06-01

## 当前结论

项目已统一为两种嵌入式主线：Embedded Claude Code / Embedded Reasonix + `.aiwf` 状态契约。

旧的外部 orchestration 主线已经移除：

- 不再生成 `.ai-workflow/`
- 不再暴露 `aiwf planner` / `aiwf handoff` / `aiwf action` / `aiwf executor` 等旧入口
- 不再保留旧 native launch / session registry / external evidence index / external review index 模块
- release audit 改为验证 embedded installation

AIWF 的产品边界现在更清晰：

```text
Claude Code / Reasonix 负责工程智能
AIWF 负责 .aiwf 状态、hooks、skills、subagents、证据、测试、审查、闭环和收尾
```

## 保留架构

```text
aiwf_core/
  cli.py                    embedded CLI 入口
  commands/parser.py        CLI parser wiring
  commands/*_commands.py    command group handlers
  install_claude.py         Claude Code 集成安装器
  embedded_templates/       skills, agents, hook scripts, CLAUDE.md 模板
  io.py                     小型项目本地 IO helper
  constants.py              版本与少量共享常量
  utils.py                  小型通用工具
  core/                     backend-neutral 状态、门禁、策略、记忆、规则、环境、git 等
  hooks/common/             hook 复用逻辑
  adapters/claude/          Claude hook event 适配
  assets/                   project asset layer
  commands/flow.py          embedded status surface
```

安装后项目状态：

```text
.aiwf/
  state.json
  goal.json
  contexts.json
  evidence.json
  testing.json
  review.json
  fix-loop.json

.claude/
  skills/
  agents/
  settings.json

scripts/
  aiwf_*.py
```

## 清理内容

已删除旧外部主线模块：

- `aiwf_core/fs.py`
- `aiwf_core/actions.py`
- `aiwf_core/context_assembly.py`
- `aiwf_core/contexts.py`
- `aiwf_core/handoff.py`
- `aiwf_core/native/`
- `aiwf_core/planner*.py`
- `aiwf_core/planning.py`
- `aiwf_core/sessions.py`
- `aiwf_core/sync.py`
- `aiwf_core/evidence.py`
- `aiwf_core/review.py`
- `aiwf_core/review_quality.py`
- `aiwf_core/testing.py`
- `aiwf_core/cleanup*.py`
- `aiwf_core/closure.py`
- `aiwf_core/decisions.py`
- `aiwf_core/policy.py`
- `aiwf_core/ui.py`
- `aiwf_core/templates/`

已删除旧测试入口和旧外部契约测试：

- `tests/run-legacy-self-test.sh`
- `tests/v45-*`
- `tests/v46-*` external orchestration tests

保留的是 `tests/embedded/`，也就是当前正确主线的测试集合。

## 质量评估

### 优点

- 状态面大幅收敛，只剩 `.aiwf`。
- 用户入口更清晰：`aiwf install claude -> claude -> /aiwf-planner`。
- CLI help 不再展示旧 external commands。
- release audit 不再依赖旧 `.ai-workflow` 模板。
- embedded install contract 已经明确验证不会创建 `.ai-workflow`。

### 本轮改进

- `install_claude.py` 已拆出模板目录 `aiwf_core/embedded_templates/`，模板服务 Embedded `.aiwf` 主线。
- `cli.py` 已缩减为入口门面；parser 和 command group handlers 已拆到 `aiwf_core/commands/`。
- 新增 `tests/run-all-embedded-tests.sh`，逐文件执行完整 `tests/embedded/*.py`。
- `tests/embedded/test_no_external_orchestration.py` 明确禁止 `.ai-workflow` 在运行时代码中复活。
- 旧 `guides/` 与历史结构审计文档已删除，避免旧 pilot / `.ai-workflow` 说明继续误导。
- `aiwf state prepare-close` 现在是前置门，不再在 evidence/testing/review 未满足时推进到 `closing` 或设置 `close_attempt`。
- 新增 `aiwf_core/core/current_state.py`，`aiwf status` 和 UserPromptSubmit 能区分 `current-state.md` 的 missing / available / stale / incomplete。
- `aiwf_rebase_state.py` 和 `aiwf task close` 会生成/更新 `.aiwf/history/task-history.json`，记录轻量任务历史，用于暴露最近 fix-loop 次数、未测风险和重复改动文件。
- `aiwf_export_report.py` 新增 Task History Trend 区块，把跨任务质量趋势放进 human-readable closure report。
- 新增 `.aiwf/task-ledger.json` 和 `aiwf task ...` 命令：Planner 可以保留多个 candidate/ready 任务，但 activation 是受机械检查的执行发布窗口。
- 新增 `.aiwf/reports/质量摘要.md`：rebase 时生成短摘要，给 Planner/Tester/Reviewer 读取跨任务质量信号，而不是回读完整历史。
- `testing.json` 和 `review.json` 增加跨任务观察字段：`cross_task_risks`、`testing_debt`、`repeated_change_hotspots`，review 侧额外有 `architecture_drift`。
- `state.json` 增加 `cross_task_quality_escalation_required` / `cross_task_quality_escalation_reason`，由 quality digest 刷新链路自动写入。

### 当前质量链

关闭链条现在分两层：

```text
prepare-close preflight
  evidence accepted
  testing adequate/passed
  review accepted + closure_allowed
  cleanup fresh
  structure accepted
  fix-loop clear
  scope clean
      ↓
Stop hook closure gate
  重新机械验证 `.aiwf/state/`、`.aiwf/quality/`、`.aiwf/evidence/` 中的机器状态
      ↓
closed + report/current-state/task-history
```

这保留了 Stop hook 的最终权威，同时避免 Planner 在明显不完整的任务上提前制造 `closing` 状态。它减少的是流程性任务债，不假装能判断实现语义是否正确。

### 长期任务债雷达

`.aiwf/history/task-history.json` 是可选生成文件，不属于安装时 7 个 MVP state files，因此不会扩大初始状态面。它在任务关闭 rebase 或 `aiwf task close` 时写入：

- goal version 和任务类型
- workflow level
- contexts involved
- accepted evidence 数量
- changed files 摘要
- testing/review 结果
- fix-loop attempts
- untested risk count

超过 100 条任务时，旧任务会被截断，但其 `changed_files` 会累积进 `archived_hotspots`，避免长期热点完全消失。

当前它仍是轻量趋势记录，不做语义判决。价值在于给 Planner 和人类 review 一个跨任务视角：如果最近多个任务反复改同一文件、fix-loop 次数上升、未测风险不断累积，说明项目可能正在产生系统性技术债。

### 多任务发布模型

AIWF 不强制线性任务队列。Planner 可以自由规划任务图：

```text
candidate / ready  可提前规划，允许多个
active             发布到执行窗口，默认一个
blocked/suspended  可保留现场
closed/rejected    完成或放弃
```

机械约束只发生在 activation：

- 依赖任务必须 closed。
- 默认 active execution window 为 1。
- 多 active 必须显式 `parallel_safe`。
- parallel-safe 任务的 `allowed_write` 不能与已 active 任务冲突。
- fix-loop open、closing/close_attempt、stale current-state 会阻止 activation。
- repeated-change hotspot 命中新任务 `allowed_write` 且缺少 Architecture Brief 时阻止 activation。
- fix-loop trend 等 escalation 信号会阻止 L0/L1 activation，要求 L2+。
- architecture_drift 未被 Architecture Brief 接住时阻止 activation。
- active 任务启动后若新出现热点，UserPromptSubmit 会注入 active task quality warning。
- suspended 任务保存轻量 `suspended_context`，恢复 activation 时写回关键 state 字段。

这保留了“先搭结构再填细节”的自然工程节奏，同时防止多个执行任务在边界不清时互相污染。

### Tester / Reviewer 的跨任务职责

跨任务质量检查是 Tester 和 Reviewer 的职责，不是机械状态可有可无的附加项。AIWF 的职责是把信号压缩并递给它们：

- Tester 从 `.aiwf/reports/质量摘要.md` 观察重复改动、未测风险、测试债；如果超出 test_template，记录风险并请求 Planner 升级。
- Reviewer 从 `.aiwf/reports/质量摘要.md` 判断是否存在架构漂移、任务拆分问题、测试债或需要升级 workflow level。
- AIWF 不自动判定“设计错了”，只记录信号、阻止明显危险的发布窗口，并要求观察进入 testing/review/report/current-state。

自动链路：

```text
aiwf task close
  -> append/update .aiwf/history/task-history.json
  -> refresh .aiwf/reports/质量摘要.md

aiwf task activate
  -> dependency/window/freshness checks
  -> cross-task quality checks
  -> activate or return blockers

UserPromptSubmit
  -> inject escalation-level signal details directly into Planner context
  -> warn when current active task hits a newly detected hotspot
```

### Current State Integrity

`current-state.md` 不只检查 mtime 新鲜度，也检查最低结构：

- Last closed task
- Changed project files
- Test result
- Review result
- Task history trend
- Raw audit references

结构缺失时状态为 `incomplete`，cleanup check 会提示重新 rebase。

### 仍需改进

- `commands/parser.py` 仍可继续拆小，例如按 subcommand family 注册 parser。
- `embedded_templates/scripts/` 中的 hook 脚本仍是安装时复制的脚本模板，后续可继续缩短脚本模板，把更多逻辑下沉到 `aiwf_core/hooks/common/`。
- `tests/run-embedded-self-test.sh` 仍保留为快速资格测试；深度验证应使用 `tests/run-all-embedded-tests.sh`。
- `task-history.json` 目前仍是摘要趋势；未来可以增加 context dependency 完成检查和更细的质量衰减阈值。
- `task-ledger.json` 目前只做执行窗口检查；未来可以把 context dispatch 与 task activation 更紧密绑定。
- `quality-digest.md` 现在可由 `aiwf quality digest` 主动刷新，并由 `task close` 自动刷新；未来可在更多阶段边界自动触发。

## 建议路线

1. 继续瘦身 `commands/parser.py`，按 state / quality / project-memory / ops 分拆 parser 注册函数。
2. 继续瘦身 hook script templates，让模板仅做 bootstrap 和 adapter 调用。
3. 将 release audit 纳入 `run-all-embedded-tests.sh` 之外的发布流程，避免本地深测和发布审计职责混在一起。
