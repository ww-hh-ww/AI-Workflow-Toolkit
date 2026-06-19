> **LEGACY — not authoritative for AIWF V1.**
> See docs/V1_DESIGN_CONTRACT.md for current rules.

# AIWF 使用教程：从会用到用好

这份教程面向第一次拿到 AIWF 的项目使用者。你不需要记住所有命令，也不需要进入 `.aiwf/` 手工翻状态文件。日常入口很简单：

```text
/aiwf-init
然后直接和 Claude Code / Reasonix 对话
```

AIWF 的作用不是替你写代码，而是在原生编码会话外面加一层治理：让目标、边界、证据、测试、审查、返工和闭合都可见、可恢复、可验证。

## 先记住 5 件事

### 1. 你和编码 Agent 说目标，AIWF 管流程

推荐的工作方式是：

```text
用户描述目标
→ Planner 理解项目和当前状态
→ Planner 建 Goal / Plan / Task / Context
→ Executor 实现
→ Tester 测试
→ Cleanup
→ Reviewer 审查
→ Planner 处理风险和返工
→ prepare-close
→ close
```

你通常不需要手工调用 Executor、Tester、Reviewer。`/aiwf-init` 会先看 `aiwf status`，再把当前请求路由到正确阶段。

### 2. `.aiwf/` 是机器状态，不是用户 UI

`.aiwf/` 里有很多 JSON 和报告文件，它们是系统真相和接力材料。用户正常不需要进去看。

稳定入口是：

```bash
aiwf status
aiwf doctor
aiwf goal-tree show
aiwf plan list
aiwf task status
aiwf project-map show
```

如果你想知道“现在到底卡在哪里”，优先让 Agent 解释 `aiwf status`，不要自己猜状态文件。

### 3. Goal Tree 是能力结构，不是文件目录

Goal 表示产品或系统能力，例如：

```text
GOAL-PRODUCT
├── GOAL-NOTES
├── GOAL-EDITOR
└── GOAL-SYNC
```

不要把 `src/notes`、`frontend`、`backend` 直接当 Goal，除非它们本身就是有清晰结果的系统能力。文件和模块归属放在 PROJECT-MAP、Plan scope 和 Context 里。

### 4. Plan 是实践脚手架，Task 是一次执行窗口

简单理解：

```text
Mission  = 为什么做这个项目
Goal     = 项目有哪些能力
Plan     = 这次怎么推进某个能力
Task     = 当前这一轮实际执行什么
Context  = 这轮允许读写什么
Evidence = 发生过什么，有什么证据
```

一个 Plan 可以服务一个 Goal，也可以挂到共同父 Goal 作为跨功能基础设施脚手架。多个 Plan 可以 ready，但同一工作区通常只允许一个 active Task。

### 5. 闭合不是“感觉做完了”

AIWF 的 done 需要机器门禁：

```text
实现证据
→ 测试记录
→ cleanup fresh
→ review accepted
→ adversarial observations 已处置
→ prepare-close 通过
→ task close
```

如果 Review 发现主链路断了，不能用“以后修”直接闭合。应该开 fix-loop，修完重新测试、清理、审查。

## 安装与进入

### Claude Code

```bash
cd /path/to/project
aiwf install claude
aiwf doctor
claude
```

进入 Claude Code 后：

```text
/aiwf-init
```

### Reasonix

```bash
cd /path/to/project
aiwf install reasonix
aiwf doctor
reasonix code .
```

进入 Reasonix 后：

```text
/skill aiwf-init
```

以后每次回来继续工作，先用同一个入口：

```text
/aiwf-init
```

然后自然语言说明你要做什么、检查什么、继续什么。

## 路径 A：新项目怎么用

新项目的重点是先建立“能力地图”，不要一上来就让模型直接写文件。

### 第 1 步：说清楚项目目标和边界

你可以这样说：

```text
/aiwf-init

我要做一个本地优先的手写笔记应用。先不要写代码，
先帮我建立 Mission、Goal Tree、PROJECT-MAP 初稿和第一阶段 Plan。
目标是 iPad 手写体验，先支持笔记列表、创建删除、手写画布和基础笔刷。
```

好的 Planner 应该先问或推断：

- 这个产品的核心能力是什么？
- 哪些能力是第一阶段必须有？
- 哪些只是未来方向？
- Goal 之间是父子关系，还是 supports / depends_on？
- 第一批 Plan 怎么切，哪些有真实执行依赖？

### 第 2 步：确认 Foundation Tree

新项目常见结构像这样：

```text
MISSION-001 本地优先手写笔记
└── GOAL-PRODUCT
    ├── GOAL-APP-SHELL
    ├── GOAL-NOTE-MANAGEMENT
    ├── GOAL-HANDWRITING-EDITOR
    └── GOAL-DATA-PERSISTENCE
```

判断 Goal 父子关系用三问：

1. 没有这个子能力，父能力是否明显不完整？
2. 子能力是否主要归属于这个父能力，而不是被多个能力平等消费？
3. 子能力能否脱离父能力独立产生产品或系统结果？

`是 + 是 + 否` 才适合做父子 Goal。否则用兄弟 Goal + relation。

### 第 3 步：让 Planner 生成第一批 Plan

推荐的说法：

```text
按依赖关系拆 Plan，不要按文件拆。
基础设施 Plan 可以挂到共同父 Goal；笔记管理和手写编辑器如果互不依赖，可以并行 ready。
每个 Plan 说明 target_goal、scope、interfaces、risks、verification 和 Impact。
```

示例：

```text
PLAN-001 应用骨架 + 数据层 → GOAL-PRODUCT
PLAN-002 笔记管理          → GOAL-NOTE-MANAGEMENT
PLAN-003 手写编辑器        → GOAL-HANDWRITING-EDITOR

PLAN-002 depends_on PLAN-001
PLAN-003 depends_on PLAN-001
```

注意：Goal relation 是能力图，Plan dependency 才是执行门禁。不要机械地把 Goal 父子关系复制成 Plan 依赖。

### 第 4 步：开始第一个 Task 前要求白盒说明

AIWF 现在要求任务开始前有轻量确认。Agent 应该先说清楚：

```text
这轮我准备做 PLAN-001 的应用骨架：
- scope: Xcode 工程、导航入口、SwiftData 基础模型
- risk: 影响后续所有功能的结构边界
- verification: build + smoke + project-map validate
确认后我记录 start confirmation 并激活 task。
```

对应机器记录是：

```bash
aiwf task confirm-start TASK-001 \
  --summary "scope: app shell and data model; risk: foundation boundary; verify: build + smoke"
aiwf task activate TASK-001
```

用户如果明确说“这轮不用汇报，直接做”，Agent 可以记录：

```bash
aiwf task confirm-start TASK-001 \
  --skip \
  --reason "user explicitly asked to proceed without start report"
```

### 第 5 步：让 AIWF 帮你守住闭合

任务做完时，不要只问“代码写完了吗”。应该问：

```text
按 AIWF 流程闭合这轮任务：测试、cleanup、review、meta-critique、prepare-close、task close 都走一遍。
如果 review 或测试发现问题，不要闭合，开 fix-loop 修完再关。
```

## 路径 B：已有项目或半成品项目怎么用

已有项目最容易犯的错是：只把“未来要做的东西”放进 Goal Tree，忽略已经存在的能力。这样 AIWF 会看不懂项目真实结构。

### 第 1 步：先做能力盘点，不急着改代码

你可以这样说：

```text
/aiwf-init

这是一个已有项目。先不要改代码。
请从当前 README、入口文件、测试、主要模块和已有行为出发，
盘点已经实现的能力，并把它们作为一等 Goal 纳入 Goal Tree。
文件路径不要直接变成 Goal，文件归属放进 PROJECT-MAP。
```

Planner 应该检查：

- 用户入口是什么？
- 已有核心流程有哪些？
- 哪些能力已经可用？
- 哪些是半成品？
- 哪些模块只是技术实现，不是独立能力？
- 哪些能力横向支持多个 Goal？

### 第 2 步：建立 Goal Tree + PROJECT-MAP

已有项目推荐先形成两个出口：

- Goal Tree：能力结构
- PROJECT-MAP：能力到模块、入口、接口的映射

示例：

```bash
aiwf project-map bind GOAL-NOTE-MANAGEMENT \
  --module src/notes \
  --entrypoint src/notes/index.ts \
  --interface "note repository"

aiwf project-map validate
aiwf project-map show
```

用户不需要去 `.aiwf/assets/project-map.json` 里看。让 Agent 总结 `project-map show` 即可。

### 第 3 步：半成品也要有位置

半成品不要藏在 TODO 或对话记忆里。推荐表达：

```text
已有能力：GOAL-NOTE-LIST status=active/implemented
半成品：GOAL-HANDWRITING-EDITOR status=planned 或 partial
风险：写入 Plan risks / PROJECT-MAP deferred_risks
```

如果能力已经存在但质量不稳，不要删掉 Goal；应该在 Plan、Evidence、Testing、Review 或 Project Map 中记录风险。

### 第 4 步：增量需求走 Admission

已有树之后，新需求不要每次都重建结构。让 Planner 判断它进入哪里：

```text
这个需求是：
1. 挂到已有 Goal 下的新 Plan？
2. 新增一个子 Goal？
3. 临时探索 Temporary Root？
4. 只是已有 active Plan 下的小 patch？

请给 Admission Decision，再决定是否创建新结构。
```

小改动可以直接归入已有 Plan，不要为了仪式创建一堆 Plan。

### 第 5 步：周期性整理，而不是每轮都写总结大文档

已有项目需要两类文档出口：

- 生长性文档：README、docs 子系统文档，随功能变化更新。
- 总结性文档：架构详细设计，在 milestone、release、handoff 或用户明确要求时生成。

如果你想要完整架构文档，可以说：

```text
请基于当前 Goal Tree、PROJECT-MAP、Plan/Task 证据、测试和审查，
生成一份总结性架构快照。先检查是否需要 aiwf architecture-doc require。
```

## 日常怎么和 AIWF 对话

### 想开始一个需求

```text
/aiwf-init

我想增加 X。先判断它属于已有 Goal，还是需要新 Goal。
不要急着写代码，先给我 Plan、风险、验证方式和是否需要独立 Tester/Reviewer。
```

### 想继续上次工作

```text
/aiwf-init

继续上次任务。先解释 aiwf status 里的当前阶段、阻塞项和下一步。
```

### 想检查有没有问题

```text
重新端到端走一遍，覆盖主链路和旁枝。
请区分 reproduced bug、流程摩擦、设计风险。
发现主链路断了不要闭合，开 fix-loop。
```

### 想让模型不要太啰嗦

```text
每个任务开始前只给我 3 行确认：scope、risk、verify。
后续除非阻塞或需要我决策，不要长篇汇报。
```

### 想允许一次降级

AIWF 默认把推荐最低等级当作硬地板。比如跨模块语义变化会抬到 L2。只有你明确确认后，Planner 才能记录降级：

```text
这个任务我接受降级到 L1。
请说明为什么安全、替代验证是什么，并记录到 AIWF。
```

机器记录形如：

```bash
aiwf route downgrade --task-id TASK-001 --to light_review \
  --reason "scope is mechanical and fully command-verifiable" \
  --substitute "targeted regression + release audit" \
  --user-confirmed
```

有安全、迁移、破坏性命令、核心门禁等硬约束时，不应该降级。

## 最小命令表

你不需要背完整 CLI。常用的是这些：

```bash
aiwf doctor                  # 安装健康检查
aiwf status                  # 当前阶段、下一步、阻塞项
aiwf status --debug          # 详细诊断
aiwf goal-tree show          # 能力树
aiwf project-map show        # 能力到模块的映射摘要
aiwf plan list               # 当前 Plan 状态
aiwf task status             # 当前 Task 状态
```

当系统卡住时，把 `aiwf status --debug` 的关键信息给 Agent，让它解释：

```text
解释 status --debug，告诉我：
1. 当前 phase 是什么
2. active Plan/Task 是什么
3. 现在 blocked 在哪里
4. 下一条合法命令是什么
```

## 常见误区

### 误区 1：把 AIWF 当成另一个 Agent runtime

AIWF 不负责替代 Claude Code / Reasonix 的理解、搜索、编辑和调试。它负责状态、门禁和证据。

### 误区 2：把 Goal Tree 当目录树

目录属于 PROJECT-MAP 和 Plan scope。Goal 是能力，不是路径。

### 误区 3：把 Milestone 当 Goal 父节点

Milestone 是横向交付切片。它引用 Goals，不拥有 Goal Tree。

### 误区 4：Review 发现问题还继续闭合

如果主链路断了，应该 REVISE / fix-loop，而不是 PASS_WITH_RISK。

### 误区 5：用户完全不参与

AIWF 不要求用户微管理，但关键地方需要用户确认：

- 从讨论切到正式执行
- 任务开始前的轻量白盒说明
- 降级 workflow level
- milestone 用户验收
- destructive / migration / release 风险

### 误区 6：每次都创建新 Goal / 新 Plan

小改动应归入已有结构。只有新能力、新边界或新执行脚手架才需要新 Goal / Plan。

## 一个完整小例子

用户：

```text
/aiwf-init

我要给已有笔记应用增加“删除笔记”。
先判断它属于已有 Goal 还是新 Goal，不要直接写代码。
```

Planner 应该：

1. 运行 `aiwf status`
2. 查看 Goal Tree 和 PROJECT-MAP
3. 判断“删除笔记”属于 `GOAL-NOTE-MANAGEMENT`
4. 如果已有 Plan 可容纳，复用；否则创建 Plan
5. 写清楚 scope：笔记列表 UI、删除动作、持久化删除、测试
6. 开始前给用户三行确认：

```text
scope: 删除笔记入口、状态更新、持久化删除
risk: 删除是破坏性用户操作，需要确认边界和回归测试
verify: 单元测试 + UI smoke + 数据不会误删其他笔记
```

7. 记录 `task confirm-start`
8. 激活 Task
9. 实现、测试、cleanup、review
10. 如果 review 发现误删风险，开 fix-loop
11. 修完重新测试和 review
12. `prepare-close`
13. `task close`
14. 更新 Current State

这就是 AIWF 的理想使用方式：用户不用背流程，但每一轮工作的目标、边界、证据和闭合都不再靠模型记忆撑着。
