# AI Workflow Toolkit (AIWF)

AIWF 是嵌入 Claude Code 与 Reasonix 的长周期工程治理层。

它不替代编码 Agent，也不接管终端执行。Claude Code / Reasonix 继续负责理解项目、搜索代码、设计方案、编辑文件、运行命令、分析失败和迭代实现；AIWF 负责把长期工程工作变成可见、可恢复、可审查、可机械验证的流程。

> Intelligence belongs to the coding agent. Governance belongs to AIWF.

## 30 秒理解

安装 AIWF 后，目标项目会增加三类能力：

1. **Skills 与独立角色**：Planner 组织工作，Executor 实现，Tester 验证，Reviewer 审查，Architect 做周期性结构检查。
2. **Hooks 与 CLI 门禁**：捕获文件和命令证据，检查写入范围、执行顺序、测试、审查、清理和闭合条件。
3. **`.aiwf/` 状态**：Goal、Plan、Task、Context、Evidence、Testing、Review、Fix-loop 和 Milestone 都写入项目内的机器状态，不依赖对话记忆。

一个标准任务按以下顺序推进：

```text
讨论与研究
→ Goal / Plan / Contracts
→ Task 激活与 Context Dispatch
→ 实现
→ 独立测试
→ Cleanup
→ 独立 Review
→ 返工并重新验证（如果需要）
→ Planner Meta-critique
→ prepare-close
→ task close
→ Current State 接力
```

AIWF 的重点不是让流程更重，而是防止这些常见失败：

- 目标、范围和架构约束只存在于聊天记录中
- 模型跳过独立测试或把测试退化成审查清单
- Review 发现主链路问题，却把它降级为“以后修”
- 修复后没有重新测试、重新清理和重新审查
- 多轮任务后出现热点、结构漂移和测试债务，却无人汇总
- 上下文压缩或会话切换后，下一轮不知道真实进度
- 用一段完成声明覆盖机器证据和未解决风险

## 产品边界

AIWF 是原生编码会话周围的治理和可见性层，不是外部编排器。

AIWF 不会：

- 替代 Claude Code / Reasonix 的代码理解与工程判断
- 重新实现一个低能力 Agent runtime
- 自动生成所有任务并接管开发
- 通过外部 runner 托管终端
- 自动提交或推送代码
- 把 Markdown 文档当作流程真相

机器真相位于 `.aiwf/*.json`。Skills 负责指导模型如何判断，CLI 和 Hooks 负责记录事实与执行可机械验证的规则。

## 支持平台

| 能力 | Claude Code | Reasonix |
|---|---|---|
| Planner / Skills | `.claude/skills/` | `.reasonix/skills/` |
| 独立角色 | `.claude/agents/` | `runAs: subagent` Skills |
| Pre/Post Tool Hooks | 支持 | 支持 |
| Stop 行为 | 在关闭尝试中再次验证 | 只报告，不作为阻塞门 |
| 权威闭合门 | `prepare-close` + Stop 复核 | `prepare-close` |

要求：

- Python 3.9+
- Git
- Claude Code 或 Reasonix

## 安装

安装 AIWF 本体：

```bash
git clone https://github.com/ww-hh-ww/AI-Workflow-Toolkit.git
cd AI-Workflow-Toolkit
python3 -m pip install -e .
```

然后进入需要治理的项目。

### Claude Code

```bash
cd /path/to/project
aiwf install claude
aiwf doctor
claude
```

在 Claude Code 中：

```text
/aiwf-init
```

初始化完成后直接用自然语言描述目标、问题或想法，不需要手工调用 Planner、Executor、Tester 或 Reviewer。

### Reasonix

```bash
cd /path/to/project
aiwf install reasonix
aiwf doctor
reasonix code .
```

在 Reasonix 中：

```text
/skill aiwf-init
```

初始化完成后同样直接对话。`aiwf-init` 会读取当前状态并把请求路由到正确阶段；Planner 是主要协调者，实现、测试、审查和闭合是由 Planner 调度的 `planner-directed capabilities`。用户不需要记住或手工编排这些内部 Skills。

AIWF 命令会从当前目录向上寻找项目根目录，因此在项目子目录执行 `aiwf status`、`aiwf task` 等命令时会复用同一个顶层 `.aiwf/`，不会创建嵌套状态目录。

## 第一次使用

进入编码会话后只需初始化一次：

```text
# Claude Code
/aiwf-init

# Reasonix
/skill aiwf-init
```

之后直接对话。`aiwf-init` 会先运行 `aiwf status`，根据 `PRIMARY`、`REQUIRED NEXT` 和 `[ATTN]` 自动选择需要的内部能力。日常使用不要求用户手工输入 `/aiwf-planner` 或逐个调用实现、测试、审查与闭合 Skills。

`aiwf doctor` 用于安装健康检查；`aiwf status` 用于诊断当前阶段和阻塞原因。

默认入口只展示最常用命令：

```text
install   doctor   status
plan      task     route
fixloop   workspace
```

完整命令列表：

```bash
aiwf --help --all
```

建议从 Planner 开始，而不是手工拼接整条 CLI 流程。CLI 是 Skills 和 Hooks 共享的机器状态接口，也可以用于诊断和恢复。

## 两层工作模型

AIWF 将工程过程分成两层。

### Layer 1：结构与合同

Planner 负责：

- 理解用户意图和已有代码
- 判断是讨论、澄清、研究、探索还是执行
- 维护 Mission、Goal Tree 和 Plan
- 明确 Evaluation Contract 与 Architecture Brief
- 定义 Plan scope、interfaces、risks、verification 和 Impact
- 创建 Task 与 Context Dispatch

这一层决定“为什么做、做什么、边界在哪里、如何证明完成”。

### Layer 2：执行生命周期

Plan 和 Context 准备好后：

- Executor 在 Plan 的允许范围内实现
- Tester 独立验证目标、边界、回归和真实入口
- Cleanup 在 Review 前完成
- Reviewer 审查合同、实现、证据、测试和影响
- Planner 处置对抗观察并管理返工
- `prepare-close` 验证闭合条件
- `task close` 归档任务并产生下一轮接力状态

这一层决定“实际怎么做、证据是什么、问题是否已修、是否允许闭合”。

## 状态机

```text
discussing
→ planned
→ implementing
→ testing
→ reviewing
→ closing
→ closed
```

主要转换：

| 转换 | 典型入口 | 关键检查 |
|---|---|---|
| discussing → planned | Planner 创建结构、Plan 和 Task | 目标与计划进入机器状态 |
| planned → implementing | `aiwf task activate` | Plan、scope、contracts、依赖、路由和执行窗口 |
| implementing → testing | `aiwf state record-testing` | 实现证据存在，测试结果与验证层被记录 |
| testing → reviewing | `aiwf state record-review` | 测试充分；L2/L3 要求 Cleanup 已验证 |
| reviewing → closing | `aiwf state prepare-close` | Review、观察处置、Meta-critique、证据与清理 |
| closing → closed | `aiwf task close <ID>` | `prepare-close` 已通过，且没有新的失效变化 |

`prepare-close` 必须在 Task 仍为 active 时执行。只有它通过后，Task 才能关闭。

## 请求模式

Planner 在冻结执行合同前先判断请求模式：

| 模式 | 用途 | 是否可作为最终实现闭合 |
|---|---|---|
| `discussion` | 讨论方向，不进入实现 | 否 |
| `clarification` | 信息不足，先澄清 | 否 |
| `research` | 先做外部或项目研究 | 否 |
| `spike` | 边界实验和可行性探索 | 否 |
| `execution` | 正式实现 | 是 |

这避免模型把一句尚未澄清的想法直接冻结成实现任务。

## Goal、Plan 与 Task

AIWF 使用三种不同层级表达长期工作：

### Goal Tree：功能结构

Goal 表达产品或系统能力，可以组成递归有根树。它描述项目完整的能力结构，而不只是下一阶段准备交付的内容。对于已有项目，安装 AIWF 之前已经存在并可工作的能力也要作为一等 Goal 纳入树中：

```text
GOAL-PRODUCT
├── GOAL-INFRA
├── GOAL-NOTES
└── GOAL-EDITOR
```

Goal relation（如 `depends_on`、`blocks`、`supports`）用于结构展示和语义参考，不直接充当 Plan 激活门。

关系方向约定：

- `A supports B`：A 是提供者，B 是消费者。
- `A depends_on B`：A 是消费者，B 是前置能力。
- 不同父节点之间使用 `--cross`。
- 横向能力可以保持为兄弟 Goal；兄弟关系不表示彼此独立。

```bash
aiwf relation add GOAL-EVIDENCE-GRADING GOAL-QUERY-STRATEGY supports \
  --cross --reason "query strategy consumes graded evidence"
aiwf relation add GOAL-ANALYSIS-FRAMEWORK GOAL-SEARCH-STRATEGY depends_on \
  --cross --reason "analysis consumes search strategy output"
```

Goal relation 只表达产品能力图。如果它同时代表真实开发前置顺序，Planner 还需要单独建立 Plan dependency。

Goal 父子关系使用三问判断：

1. 没有这个子能力，父能力是否明显不完整？
2. 子能力是否主要归属于该父能力，而不是被多个能力域平等消费？
3. 子能力能否脱离父能力独立产生产品或系统结果？

`是 + 是 + 否` 才建立父子 Goal。被多方消费时使用兄弟 Goal + `supports`；消费其他能力输出时使用兄弟 Goal + `depends_on`。同目录、同实施阶段或同 Milestone 都不能构成父子关系。

Goal 不能按文件路径、目录、纯技术分层、实施批次或 Milestone 切割。文件与目录属于 `module_boundaries`、Plan scope 和 Context；Milestone 只通过 `covered_goal_ids` 横向引用本次交付涉及的 Goals，不拥有 Goal Tree，也不反向决定 Goal 边界。

Goal 与代码结构通过 PROJECT-MAP 集中连接：

- `goals.json`：能力身份与父子结构的权威来源。
- `.aiwf/assets/project-map.json`：机器权威索引，保存文件、依赖和人工确认的 `goal_bindings`。
- `.aiwf/artifacts/reports/项目地图.md`：人类投影，解释架构方向、模块职责、开放决策和延迟风险，不复制完整文件清单。

用户不需要日常进入 `.aiwf/` 翻文件。稳定入口是命令和 agent 摘要：

```bash
aiwf project-map bind GOAL-NOTES \
  --module src/notes \
  --entrypoint src/notes/index.ts \
  --interface "note repository"
aiwf project-map relations
aiwf project-map validate
aiwf project-map show
```

### 文档出口：生长文档与架构快照

AIWF 同时保留两种文档能力，但出口不同：

- **生长性文档**：普通任务中，当 Plan 的 `Impact.docs=yes` 时更新 README
  或 `docs/` 子系统文档。它随着代码生长，服务当前改动，不承担整套系统总结。
- **总结性文档 / 架构快照**：在用户明确要求、Milestone/Release/Handoff
  边界，或 Architect 判断系统结构已经稳定时，使用 `aiwf-architecture-doc`
  生成 `.aiwf/artifacts/reports/架构详细设计.md`。

PROJECT-MAP 是两者之间的结构索引：它保存 Goal-to-module 绑定、架构方向、
开放决策和延迟风险；架构快照从 PROJECT-MAP、Goal Tree、Plan/Task 证据、
测试、审查和源码入口汇总生成。不要把长期架构真相只散落在闭合报告、
review 评论或模型记忆里。

`.aiwf/` 中的报告是治理与接力产物，不是要求用户手工浏览的 UI。需要给人读时，
Planner 应在对话中总结，或在 Plan scope 允许时把稳定版本镜像到 `docs/`。

架构快照有轻量机器契约，用来防止交付/交接时被模型漏掉：

```bash
aiwf architecture-doc require --reason "milestone handoff"
aiwf architecture-doc status
aiwf architecture-doc validate
aiwf architecture-doc satisfy
aiwf architecture-doc waive --reason "project still changing; PROJECT-MAP is enough"
```

`require` 不会自动生成文档；它只让 `aiwf status --prompt` 提醒模型，并在
Milestone confirm/close 前检查快照是否已经 validate + satisfy。

### Plan：实践脚手架

Plan 是实现或验证某个 Goal 的实践方案：

- 通过 `target_goal_id` 挂到一个 Goal
- 包含 `plan_kind`、`work_intent`、scope、interfaces、constraints 和 Impact
- 可以拥有多个 Task
- 可以依赖另一个 Plan

跨功能的基础设施 Plan 可以挂到共同父 Goal：

```text
PLAN-001  应用骨架与数据层   → GOAL-PRODUCT
PLAN-002  笔记管理           → GOAL-NOTES
PLAN-003  手写编辑器         → GOAL-EDITOR

PLAN-002 depends_on PLAN-001
PLAN-003 depends_on PLAN-001
```

Plan dependency 是机器执行顺序。依赖 Plan 未完成时，下游 Plan 和 Task 不能激活；上游取消或被替代时，可以通过有原因记录的 dependency removal 解锁下游。

多个 Plan 可以同时 ready，但同一工作区仍只允许一个 active Task。

### Task：原子执行单元

Task 是进入执行窗口的最小单位：

- 必须属于一个 Plan
- 可以有 Task 内部依赖
- 激活后绑定当前 Context
- 产出 Evidence、Testing 和 Review
- Task 完成不等于 Goal 自动完成

## 路由与执行深度

Task 激活时，AIWF 根据当前变更的机械信号选择最低工作流等级。Planner 可以基于语义风险提高深度，但不能随意绕过硬风险。

| Level | 典型场景 | 执行与验证 |
|---|---|---|
| L0 | typo、极小机械改动 | Planner 内联、自测、轻量自审查 |
| L1 | 小功能、局部 Bugfix | Scoped Executor + 轻量独立验证 |
| L2 | API、多模块、共享逻辑 | 独立 Executor、Tester、Reviewer |
| L3 | 安全、数据、迁移、高风险结构变化 | 完整团队、Checkpoint、对抗测试和深度审查 |

路由会综合：

- 修改范围和跨模块影响
- 安全、数据、发布、迁移风险
- 语义核心门禁或合同变化
- 历史 Fix-loop 与重复修改热点
- 验证是否可机械执行
- 当前 Architecture Brief 是否足够

路由同时产生：

- `verification_need`
- `review_need`
- 执行拓扑
- `test_template`
- `review_template`
- 是否允许降级或角色替代

## Context Dispatch 与写入边界

Context Dispatch 将 Plan 转换为当前执行者可消费的工作包，包括：

- `allowed_write`
- `forbidden_write`
- test focus
- review focus
- non-goals
- interfaces
- escalation triggers

Hooks 在 Write/Edit/Bash 期间检查：

- 是否存在 active Task
- 当前模式是否允许执行
- 写入是否超出 Plan scope
- 是否触碰 protected files 或 forbidden restructures
- 是否存在未解决的 scope violation
- 是否处于受控 Fix-loop 修复窗口
- 命令是否命中危险操作策略

状态 JSON 不应手工修改。Skills 和用户通过 `aiwf` 命令更新机器状态。

## Evidence、Testing 与 Review

### Evidence

证据来自两条正规路径：

1. Hooks 捕获主会话中的 Write、Edit 和 Bash 行为。
2. `record-role-evidence`、`record-testing` 和 `record-review` 记录子代理或角色交付。

Evidence 可以声明它支持哪个 Plan 和 Goal。L2/L3 会检查独立角色和会话证据，不接受纯口头 handoff 代替执行记录。

### Testing

Tester 不只是确认测试命令返回 0，还要说明：

- 验证了哪些 acceptance criteria
- 执行了哪些 targeted、regression、integration 或 real-usage 层
- 哪些风险仍未验证
- 修复后哪些证据失效、哪些验证被重新执行
- 是否发现跨任务测试债务或重复热点

### Review

Reviewer 将 Goal、Plan、Scope、Evidence、Testing 和 Impact 作为一个合同审查。

完整 V2 Review（L2/L3 或治理敏感任务）的 verdict：

- `PASS`
- `PASS_WITH_RISK`
- `REVISE`
- `REJECT`

完整 V2 Review 会评分八个质量维度，并记录六类 review basis；低风险 L0/L1 可以使用轻量 Review。无论采用哪种深度，CRITICAL/HIGH 观察都不能通过 `PASS_WITH_RISK` 延期，也不能标记为 ignored/deferred：

```text
CRITICAL/HIGH finding
→ REVISE 或 REJECT
→ 修复
→ 重新测试
→ 带 resolution 与 evidence 重新 Review
→ 才能继续闭合
```

Review 历史会保留，不能通过覆盖最新状态抹掉此前问题。

## Cleanup、Fix-loop 与闭合

Review 必须发生在 Cleanup 之后。

当测试或 Review 发现需要返工的问题时，Fix-loop 负责：

- 记录 required fixes 和 required verification
- 限定允许修复的文件
- 使旧测试、Review 或 Cleanup 状态失效
- 要求修复后重新测试和重新审查
- 在连续失败后升级给 Planner 或用户

闭合顺序：

```text
测试通过
→ Cleanup fresh
→ Review accepted
→ 对抗观察已处置
→ Planner Meta-critique
→ aiwf state prepare-close
→ aiwf task close <TASK-ID>
```

`prepare-close` 会综合检查：

- 当前阶段和 active Task
- accepted Evidence
- 测试状态和验证层
- Review verdict 与 closure permission
- 未处置或未解决的严重观察
- Cleanup freshness
- Plan Impact 与实际变化
- L2/L3 独立角色、会话与证据要求
- 开放 Fix-loop、Scope violation 和 Architecture Change Request

如果通过后又出现新证据或实现变化，必须重新验证，而不能沿用旧闭合结论。

## Gravity 与周期架构 Review

Gravity 是只读纯函数。它从任务历史中计算长期工程压力：

- 重复修改热点
- Fix-loop 趋势
- 测试债务
- 架构漂移观察
- 模块共同变化和依赖面扩张
- PROJECT-MAP 陈旧程度

当达到周期、Gravity 升高或结构信号累积时，普通 Task 激活会被暂停，Planner 需要运行周期架构 Review。

周期 Review 有独立机器状态：

```text
ARCH-* Review
→ intact：普通任务可继续
→ issues_found：普通任务保持阻塞
→ ARCH-FIX-* 返工任务
→ 新 ARCH-* Review + resolution evidence
→ intact
```

仅仅关闭一个名为 `ARCH-*` 的 Task 不代表审查完成。必须记录架构 Review 结果；高风险发现必须经过明确返工和复审。

周期 Architect 不阻塞已经在执行的当前 Task，但会阻止下一个普通 Task 激活。

## Milestone

Milestone 是可选的横向阶段交付切片，可横跨多个 Goal。它适合长周期项目，不强加给轻量任务。Goal Tree 始终保留完整能力结构；Milestone 只选择其中本阶段需要集成验证和闭合的一部分。

Milestone 闭合包括：

- Stage synthesis
- 跨 Goal 集成检查
- 架构 Review
- 残余风险与稳定性声明

通过的 Milestone integration 必须记录源码文件和逐函数反向调用追踪，而不是只从入口正向跑通：

- 每个相关源码文件被纳入或有明确排除理由
- 每个函数有调用者、入口或 intentionally unused 分类
- `untraced` / `disconnected` 会阻止通过
- 主链路失败会阻止闭合

Milestone 架构 Review 发现问题后会将综合结论恢复为 `REVISE`。修复后必须重新运行 integration、重新进行架构 Review、重新评估，再允许 close。

技术验收通过与正式闭合是两个步骤。`checkpoint` / `manual` Milestone 在集成、架构和综合评估通过后，Planner 必须展示完成内容、范围外内容、残余风险和下一阶段，并取得用户确认：

```bash
aiwf milestone confirm MS-001 \
  --summary "用户接受当前阶段成果及列出的残余风险"
aiwf milestone close MS-001
```

`PASS_WITH_RISK` 始终需要确认；只有低风险、`advance_policy=auto` 且 verdict 为 `PASS` 的内部 Milestone 可以在展示摘要后自动闭合。任何重新评估、重新集成或重新架构审查都会使旧确认失效。

## Rooted Structure

完整结构关系：

```text
Mission
├── Goal Tree
│   └── Goal
│       └── Plan
│           └── Task
│               ├── Context
│               ├── Evidence
│               ├── Testing
│               └── Review
└── Milestones（可横跨多个 Goal）
```

| 层级 | 作用 | 主要机器状态 |
|---|---|---|
| Mission | 项目为什么存在、长期边界 | `mission.json` |
| Goal Tree | 功能结构与父子关系 | `goals.json` |
| Plan | 实践方案、范围、依赖和接口 | `plans.json` |
| Task | 原子执行窗口 | `task-ledger.json` |
| Context | 当前角色的工作包 | `contexts.json` |
| Evidence | 文件、命令和角色交付证据 | `records.json` |
| Testing | 验证结果、层次和风险 | `testing.json` |
| Review | 质量结论、问题和处置 | `review.json` |
| Architecture Review | 周期结构审查结果 | `architecture-review.json` |
| Fix-loop | 返工与恢复状态 | `fix-loop.json` |
| Milestone | 跨 Goal 阶段交付 | `milestones.json` |

## `.aiwf/` 目录

目标项目中的主要状态布局：

```text
.aiwf/
├── state/
│   ├── state.json
│   ├── mission.json
│   ├── goal.json
│   ├── goals.json
│   ├── plans.json
│   ├── milestones.json
│   ├── contexts.json
│   └── fix-loop.json
├── artifacts/
│   ├── plans/
│   ├── evidence/records.json
│   ├── quality/
│   │   ├── testing.json
│   │   ├── review.json
│   │   └── architecture-review.json
│   └── reports/
└── runtime/
    ├── history/
    │   ├── task-ledger.json
    │   └── task-history.json
    ├── checkpoints/
    └── internal/
```

Markdown Plan 和报告用于人类阅读与 Agent 接力；JSON registry 和 state 才是机器权威。

## 常用命令

### 日常入口

```bash
aiwf status
aiwf doctor
aiwf plan list
aiwf plan show PLAN-001
aiwf task status
aiwf route explain
aiwf workspace scan
```

### Plan 与 Task

```bash
aiwf plan create PLAN-001 --target-goal GOAL-001
aiwf plan create PLAN-002 --target-goal GOAL-002 --depends-on PLAN-001
aiwf plan dep add PLAN-002 PLAN-001
aiwf plan dep remove PLAN-002 PLAN-001 --reason "dependency superseded"
aiwf task plan TASK-001 --plan PLAN-001 --status ready
aiwf task activate TASK-001
aiwf task suspend TASK-001 --note "waiting for user decision"
aiwf task close TASK-001
```

### 验证与恢复

```bash
aiwf cleanup check
aiwf state record-testing --help
aiwf state record-review --help
aiwf state prepare-close
aiwf fixloop --help
aiwf checkpoint --help
aiwf state record-architecture-review --help
```

### 长周期结构

```bash
aiwf mission --help
aiwf goal-tree --help
aiwf relation --help
aiwf milestone --help
aiwf project-map --help
```

## Skills 与角色

核心 Skills：

- `aiwf-init`（用户入口）
- `aiwf-planner`
- `aiwf-planner-contracts`
- `aiwf-planner-execute`
- `aiwf-implement`
- `aiwf-test`
- `aiwf-review`
- `aiwf-close`
- `aiwf-architect`
- `aiwf-architecture-doc`
- `aiwf-milestone-integration`
- `aiwf-milestone-arch-review`

独立角色：

- Executor
- Tester
- Reviewer
- Explorer
- Curator

用户通常只调用一次 `aiwf-init`，随后直接对话。其余 Skills 由当前状态和 Planner 按阶段调度。Skills 决定角色如何思考和执行；状态契约决定哪些事实必须留下；机器门禁阻止错误顺序和未经修复的闭合。

## 外部研究与能力

外部信息和社区能力不会自动获得权威：

- Research 先以低信任 claim 记录，由 Planner promote 或显式 skip。
- 外部 Skill、Hook、MCP 和命令可以被 capability scan 分类。
- 生命周期重叠能力必须由 Planner 记录使用决策。
- 外部能力不能覆盖 AIWF 的 scope、evidence、testing、review、cleanup 和 closure gates。

## 项目源码结构

```text
aiwf_core/
├── commands/                    # CLI 命令层
├── core/
│   ├── state/                   # 分域状态写入操作
│   ├── state_schema.py          # 默认 schema 与枚举
│   ├── phase_gates.py           # 阶段转换门
│   ├── task_ledger.py           # Task 执行窗口
│   ├── task_gravity.py          # 只读历史压力
│   ├── routing.py               # L0-L3 路由
│   ├── process_contract.py      # 当前流程与恢复指导
│   ├── closure_contract.py      # Stop/闭合复核
│   └── cross_task_quality.py    # 跨任务质量信号
├── hooks/common/                # Evidence、Scope 与 Protocol checks
├── embedded_templates/
│   ├── skills/                  # 安装到目标项目的 Skills
│   ├── agents/                  # Claude 独立角色定义
│   └── scripts/                 # 独立 Hook 脚本
└── adapters/                    # 平台事件适配

tests/embedded/                  # 独立合同与回归测试
```

模块应保持职责分离。AIWF 不把 Planner、状态写入、Context Dispatch、Testing、Review、Cleanup、Closure、Hooks 和 UI 混成一个运行时。

## 开发与验证

核心验证：

```bash
PYTHONPYCACHEPREFIX=/private/tmp/aiwf-pycache \
  tests/run-all-embedded-tests.sh

tests/run-embedded-self-test.sh
tests/release-audit.sh
```

发布前还应在隔离临时项目中验证：

```text
install
→ goal / plan / task
→ activate
→ implement evidence
→ testing
→ cleanup
→ review
→ prepare-close
→ task close
→ next cycle
```

Claude 和 Reasonix 两个入口都需要验证。

每条新增工作流规则都应有合同测试，覆盖：

- 正常路径
- 错误顺序拒绝
- 陈旧状态
- 返工后重新验证
- Context Dispatch
- 跨会话接力
- 不会复活已移除的外部 orchestration 路径

## 设计原则

1. **Model-centered**：让编码 Agent 保留完整工程能力。
2. **Machine truth**：影响正确性的事实必须进入 `.aiwf/*.json`。
3. **Evidence before claims**：完成声明不能替代真实执行记录。
4. **Cleanup before Review**：先清理，再审查。
5. **Issues require rework**：严重问题必须修复、重测和复审。
6. **Task is not Goal**：Task 完成不会自动宣告功能 Goal 完成。
7. **Gravity is pure**：读路径只计算压力，不偷偷修改状态。
8. **One active Task**：多个 Plan 可以 ready，但执行窗口保持单一。
9. **No managed runtime**：不恢复外部 runner、fake terminal 或自动任务生成。
10. **Recoverable by design**：中断、压缩和会话切换后仍能从机器状态继续。

## License

MIT
