# AI Workflow Toolkit (AIWF)

AIWF 是围绕 Claude Code 长周期工程会话构建的治理与可见性层。

Claude Code 继续负责理解代码、探索项目、设计方案、编辑文件、运行命令和处理失败。AIWF 负责保存长期语义、安排独立角色、记录可追溯证据、约束错误顺序，并把任务可靠地收口。

> Intelligence belongs to Claude Code. Governance belongs to AIWF.

AIWF 也支持 Reasonix，但当前主要使用和验证路径是 Claude Code。

## 目录

- [AIWF 解决什么问题](#aiwf-解决什么问题)
- [什么时候适合使用](#什么时候适合使用)
- [五分钟开始](#五分钟开始)
- [第一次对话](#第一次对话)
- [完整工作流](#完整工作流)
- [Mission、Goal、Plan、Task 与 Milestone](#missiongoalplantask-与-milestone)
- [角色分工](#角色分工)
- [Markdown、JSON 与 Memory](#markdownjson-与-memory)
- [Git、Task 快照与提交](#gittask-快照与提交)
- [Plan 并行与 Worktree](#plan-并行与-worktree)
- [Testing、Review 与 Fix-loop](#testingreview-与-fix-loop)
- [人工中断与紧急关闭](#人工中断与紧急关闭)
- [Architect 与 Critic](#architect-与-critic)
- [Hooks 与写保护](#hooks-与写保护)
- [配置](#配置)
- [状态、UI 与诊断](#状态ui-与诊断)
- [命令索引](#命令索引)
- [目录结构](#目录结构)
- [故障排除](#故障排除)
- [升级、迁移与移除](#升级迁移与移除)
- [开发与验证](#开发与验证)
- [安全边界](#安全边界)

## AIWF 解决什么问题

长任务里，模型往往不是不会写代码，而是会逐渐丢失最初设计、跳过真实入口、混淆“代码存在”和“能力可用”，或者在测试和审查已经失效后仍然宣布完成。

AIWF 为这些问题增加了一个项目内闭环：

```text
讨论与项目研究
-> Mission / Goal / Plan / Task 设计
-> 激活前两次现实批判
-> Executor 实现
-> Tester 独立验证
-> Reviewer 独立判断
-> Planner 处置问题并记录实际结果
-> Task close 创建正式提交
-> Plan 集成、合并和关闭
```

它重点保护以下事情：

- 项目长期方向不会只存在于聊天记忆中。
- Planner 在规划前读真实代码，而不是凭印象写合同。
- Task 激活前必须说明主路径、消费者、证明方式和旧路径。
- 首次实现可以强制交给独立 Executor。
- Tester 可以增加测试资产，并记录期望输出和实际输出。
- Reviewer 审查同一份最终测试快照，而不是只看局部 diff。
- 测试或审查发现问题后进入返工，不允许静默降级为通过。
- 关闭时确认实现、测试、审查和当前工作树仍指向同一结果。
- 多个 Plan 可以并行，但每个 Plan 有独立 branch/worktree。
- 中断、上下文压缩或会话切换后，可以从项目状态继续。

AIWF 不会替代 Claude Code，也不会：

- 托管一个外部 Agent runtime。
- 接管终端或限制 Claude Code 正常探索代码。
- 自动替用户决定产品方向。
- 自动合并、推送或发布代码。
- 把流程字段当作架构质量本身。
- 把 hooks 当成操作系统级安全沙箱。

更强的模型不会让 AIWF 自动失去价值。模型能力决定单次判断的上限；AIWF 保存跨会话结构、独立角色、Git 快照和关闭条件，减少长流程中“本来知道、后来忘了”的损失。对于短而简单的工作，这部分收益可能小于流程成本，所以 Planner 应保持轻量。

## 什么时候适合使用

适合：

- 工作跨越多轮会话或多个 Task。
- 改动涉及真实入口、共享接口、状态、数据、部署或迁移。
- 需要独立测试和审查。
- 多个能力需要按依赖顺序交付。
- 需要让人和 AI 都能追溯“做了什么、测了什么、为什么通过”。
- 多个互不依赖的 Plan 希望并行推进。

可以保持轻量：

- 一次性的小脚本。
- 明确、局部、低风险的机械修正。
- 不需要跨会话保存结构和证据的短工作。

Planner 会先讨论工作是否值得进入 AIWF。讨论是默认行为；只有用户明确要求规划、更新规划、激活或继续执行时，Planner 才应写治理文档。

## 五分钟开始

### 1. 安装 AIWF

要求：

- Python 3.9+
- Git
- Claude Code，或 Reasonix

从源码安装：

```bash
git clone https://github.com/ww-hh-ww/AI-Workflow-Toolkit.git
cd AI-Workflow-Toolkit
python3 -m pip install -e .
aiwf --version
```

### 2. 在目标项目安装 Claude Code 集成

目标项目必须是 Git 仓库，并且至少有一个提交：

```bash
cd /path/to/project

# 仅当项目还不是 Git 仓库时需要
git init -b main
git add -A
git commit -m "Initial project"

aiwf install claude
aiwf doctor
```

安装会创建或更新：

- `CLAUDE.md` 中的 AIWF 托管区块。
- `.claude/settings.json` 中的 AIWF hooks，同时保留非 AIWF hooks。
- `.claude/skills/` 和 `.claude/agents/`。
- `scripts/aiwf_*.py`。
- `.aiwf/` 治理工作区。

安装产生的 Claude 集成文件属于项目变更。开始第一个 Task 前，先根据项目的版本控制策略提交或处理这些改动，确保项目工作树干净。AIWF 不会替你修改 `.gitignore`。

通常应保留 `CLAUDE.md`、`.claude/` 和 `scripts/`。如果团队决定提交 `.aiwf/`，不要把 `.aiwf/runtime/internal/` 当作稳定项目文档；那里保存本机路径、hook 日志和临时路由信息。

### 3. 启动 Claude Code

```bash
claude
```

然后直接描述目标、问题或想法，例如：

```text
先阅读当前项目，和我讨论如何把本地索引改成可恢复的增量索引。
不要急着创建 Plan 和 Task。
```

AIWF 的 prompt hook 会在状态变化时提醒 Claude Code 运行：

```bash
aiwf status --prompt
```

该命令会给模型明确的下一步和必须加载的 Skill。用户通常不需要手工调度 Executor、Tester 和 Reviewer。

如果自动路由没有发生，可以在 Claude Code 中手动加载：

```text
/aiwf-planner
```

### Reasonix

```bash
cd /path/to/project
aiwf install reasonix
aiwf doctor
reasonix code .
```

Reasonix 使用 `.reasonix/skills/` 中的 `runAs: subagent` 角色。它的 Stop hook 只报告，不承担 Claude Code 中的阻塞式退出门；权威关闭仍由 `aiwf task close` 完成。

## 第一次对话

一个健康的第一次使用过程通常是：

1. 用户描述问题或目标。
2. Planner 读取 `.aiwf/mission.md`、相关治理文档和必要代码。
3. Planner 与用户讨论需求、能力边界、技术方向、风险和证明方式。
4. 用户明确要求开始规划。
5. Planner 写 Mission、Goal、Plan 和 Task，并运行 `aiwf sync`。
6. Planner 对 Task 做两次激活批判。
7. Planner 创建或选择 Plan worktree，绑定 Plan，然后激活 Task。
8. AIWF 按状态依次路由 Executor、Tester、Reviewer 和 Close。

可以用这些表达控制节奏：

```text
先讨论，不要写治理文件。
```

```text
这个方向确定了，开始规划，但先只写 Goal 和 Plan。
```

```text
把 Task 合同写完整，批判两遍后再激活。
```

```text
先不要继续下一个 Task，向我解释这次实际完成了什么。
```

## 完整工作流

### 1. Planner 讨论和研究

Planner 先确认：

- 这项工作服务哪个固定 Mission outcome。
- 系统需要获得什么能力。
- 真实用户入口、运行路径或部署路径是什么。
- 最大不确定性是什么，怎样尽早证明。
- 当前代码有哪些调用者、消费者、接口、状态和旧路径。

当技术方向不清楚时，Planner 可以派只读 Explorer 查事实或独立比较方案。Explorer 不替 Planner 做决定。

### 2. 写结构和合同

Planner 通过 CLI 创建节点，再认真编辑对应 Markdown：

```bash
aiwf goal create GOAL-001 --title "Recoverable indexing"
aiwf plan create PLAN-001 --goal GOAL-001 --title "Incremental index mechanism"
aiwf task create TASK-001 --goal GOAL-001 --plan PLAN-001 --title "Index updates survive restart"
```

CLI 创建文档和机器索引。Markdown 负责语义，JSON 负责链接、状态和门禁。

### 3. 激活前批判

Planner 必须对即将激活的 Task 做两次真实检查：

- 第一次确认能力、主路径、消费者、共享不变量、证明和旧路径。
- 第二次尝试推翻第一次结论，查找猜测、遗漏的运行变体和被推迟的风险。

只有一轮没有发现需要修改的问题时，才记录一次：

```bash
aiwf task critique TASK-001
```

累计两次后才能激活：

```bash
aiwf task activate TASK-001
```

`critique` 是一个简单计数门。真正的质量来自 Planner 实际读取代码并修正合同，而不是把命令执行两次。

### 4. Executor 实现

当 `executor_required: true` 时，Task 的第一次项目实现必须由 `aiwf-executor` 子代理完成。

Executor 会：

- 进入 Task 分配的 worktree。
- 阅读完整 Task.md。
- 追踪真实调用链和消费者。
- 实现最小而完整的设计。
- 检查新路径是否被消费、旧路径是否仍绕过。
- 运行 Task 中的 Verification Commands。
- 保存实现快照并向 Planner 汇报。

如果合同和代码现实冲突，Executor 返回 Planner，而不是自行改写目标。

### 5. Tester 独立验证

Tester 在 Executor 返回后开始，不能与同一 Task 的 Executor 并行。

Tester 会：

- 自己建立失败模型。
- 运行每条 Verification Command。
- 对比 expected observable 与 actual output。
- 增加边界、错误、状态、并发、权限、迁移或旁路测试。
- 检查 mock、fixture 或旧路径是否造成假通过。
- 必要时创建测试和验证资产。
- 保存包含 Tester 改动的最终测试快照。

真实失败必须记为 `failed`。只有硬件、操作系统或环境确实无法提供所需证明时，才使用 `adequate`。

### 6. Reviewer 独立判断

Reviewer 审查 Tester 的同一份最终快照。它不实现，也不替 Tester 重跑完整测试工作。

Reviewer 要回答：

- Task 合同、实现、测试和实际运行路径是否形成完整可信的故事。
- 每个 changed file 是否有责任依据。
- 调用者和消费者是否真的使用新代码。
- 旧路径、重复实现、旁路和死代码是否仍在。
- 接口语义、单位、ID、状态、错误、权限和生命周期是否被下游正确消费。
- Tester 的结论是否足以证明 Task claim。
- 结构是否增加了不必要的间接层或错误边界。

Reviewer 必须返回具体报告，说明 Executor 做了什么、Tester 证明了什么、自己检查了什么，以及为什么可以或不可以继续。

### 7. Planner 处置和校准

Planner 处理 Reviewer observations 和其他发现。每个未解决问题必须有清楚结果：

- 现在修。
- 并入当前工作。
- 延后并记录原因。
- 用户明确接受风险。
- 中断并重新规划。

关闭前，Planner 把实际完成情况写入 Task.md 的 `Closure Calibration`：

```bash
aiwf task calibrate TASK-001 \
  --summary "实际完成内容；与原合同的重要差异；仍需跟进的事项"
```

原始 Task 合同不应被事后改写。前半部分保留当时的指导，Closure Calibration 记录最后的现实。

### 8. Task 关闭

```bash
aiwf task close TASK-001
```

关闭命令会检查：

- 当前 Task 的 required roles 是否有对应记录。
- Testing 是否基于当前实现快照。
- 每条严格 Verification Command 是否有 expected、observed 和 match 结论。
- Review 是否接受当前 tested snapshot。
- Reviewer observations 是否已经由 Planner 处置。
- Fix-loop 是否已解决。
- Review 后项目文件是否再次变化。
- Git 暂存区和工作树是否满足创建精确 Task commit 的条件。

通过后，AIWF 创建正式 Task commit，并把 Task 标为 closed。

### 9. Task 后和 Plan 后

每个 Task 返回 Planner 后，Planner 要对照 Plan 检查实际结果是否改变了后续假设、接口、责任或主路径，并克制地维护 Memory。

Plan 的全部 Task 关闭后：

1. 检查累计 diff 和真实集成行为。
2. 按既定顺序合并 Plan branch。
3. 在 base branch 上运行组合验证。
4. 关闭 Plan：

```bash
aiwf plan close PLAN-001 --summary "该 Plan 实际交付的机制和能力"
```

关闭后的 Plan 是完成记录，不再修改，也不能再链接新 Task。新工作创建新 Plan。

## Mission、Goal、Plan、Task 与 Milestone

```text
Mission
└── Goal tree
    └── Goal
        └── Plan
            └── Task

Milestone 横向选择一个需要共同验收的稳定切片。
```

### Mission

Mission 是项目固定方向，位于 Goal tree 之上。它不是一个根 Goal。

文件：`.aiwf/mission.md`

Mission 由 Planner 或人编辑，然后运行：

```bash
aiwf sync
aiwf mission show
```

Mission 不清楚时，不应先批量创建 Goals。

### Goal

Goal 表达 Mission 需要的一项能力，不表达模块、目录、工具、开发阶段或具体方法。

Goal 可以形成能力树。父子关系表示“没有子能力，父能力明显不完整”，不是代码目录嵌套。

Goal relation 用于表达横向能力关系：

```bash
aiwf goal link GOAL-A GOAL-B --type supports
aiwf goal link GOAL-A GOAL-B --type depends_on
```

Goal relation 是能力语义，不自动成为开发顺序门。真正的开发前置顺序使用 Plan dependency。

方向约定：`A supports B` 表示 A 提供能力、B 消费；`A depends_on B` 表示 A 是消费者、B 是前置能力。

### Plan

Plan 是一个 Goal 的技术机制和交付方向，也是 Git branch/worktree 的并行单位。

好的 Plan 应说明：

- 当前真实问题。
- 责任放在哪里。
- 数据流、控制流和消费者路径。
- 关键技术选择及依据。
- 共享接口、不变量和所有权。
- 旧路径的删除、兼容或迁移方式。
- 先证明什么，Task 如何排序。
- 多个 Task 最后怎样共同验证。

Plan 不是 Task 清单，也不要求代码模块照着 Goal tree 生长。

### Task

Task 是一个可执行、可证明的工作合同。激活后，其 Task.md 默认冻结。

Task 的核心内容是：

- Structural Home
- Objective
- Contract Responsibility
- Done When，标明 Built、Wired 或 Running
- Verification Commands 和 Expected Observable Output
- 经过验证的 Known Context
- 留给 Executor、Tester、Reviewer 的 Open Judgment

Task.md 不是文件 allowlist。Executor 可以追踪并修改为完成合同所必需的文件，但不能触碰明确的 `forbidden_write`。

独立角色由工作风险决定，不按文件数量机械选择：实现需要代码探索、设计判断或影响追踪时要求 Executor；独立测试可能发现有意义的失败模式时要求 Tester；调用关系、接口漂移、旧路径或复杂度值得独立判断时要求 Reviewer。

### Milestone

Milestone 是可选的真实验收切片。它可以跨多个 Goal 和 Plan，用于确认一组能力在真实环境和真实主路径上共同成立。

它不是普通进度标签。一个 Milestone 通常需要：

- Pass Standard
- 真实 integration test
- Architect architecture review
- PASS / PASS_WITH_RISK / REVISE / REJECT assessment
- 人类确认
- milestone verification Task 关闭

## 角色分工

| 角色 | 负责 | 不负责 |
|---|---|---|
| Planner | 讨论、研究、结构、技术方向、Task 合同、分发、问题处置、Memory 和收口 | 实现项目代码 |
| Explorer | 只读查事实、追调用链、比较方案 | 决策、写文件、记录完成 |
| Executor | 实现 Task，追主路径，自查并保存实现快照 | 独立测试、Review、关闭 |
| Tester | 尝试打破 claim，创建测试资产，保存 tested snapshot | 修实现、做最终 Review |
| Reviewer | 判断合同、代码、测试、主路径和结构是否整体可信 | 修改代码、关闭 Task |
| Architect | 用户手动触发的独立结构审查；也执行 Milestone acceptance | 创建 Task、实现、替 Planner 决策 |
| Critic | 用户手动触发的独立怀疑者 | 加入正常门禁、修改状态 |
| Close | 调用机器关闭门并报告结果 | 自行决定“差不多可以了” |

正常 Task 内部顺序始终是：

```text
Executor -> Tester -> Reviewer -> Planner -> Close
```

如果 Task frontmatter 中某个 `*_required` 为 `false`，该阶段仍然存在，但可以由主会话按对应 Skill 内联完成。`false` 不是跳过验证，而是不强制独立子代理。

## Markdown、JSON 与 Memory

### 两种真相

Markdown 保存项目语义：

- `.aiwf/mission.md`
- `.aiwf/goals/*.md`
- `.aiwf/plans/*.md`
- `.aiwf/tasks/*.md`
- `.aiwf/milestones/*.md`
- `.aiwf/memory/*.md`

JSON 保存机器状态和简洁记录：

- `.aiwf/state/*.json`
- `.aiwf/records/tasks/<TASK-ID>.json`
- `.aiwf/records/events.json`

阅读原则：

- 想知道“为什么、做什么、边界是什么”，读 Markdown。
- 想知道“现在是什么状态、哪个 gate 阻塞、测试和 Review 指向哪个 ref”，读 CLI 或 JSON。
- 不要把 JSON 当作语义文档。
- 不要手工编辑 `.aiwf/state/` 或 `.aiwf/records/`。

项目自己的 `docs/` 是详细技术资料，不是 Planner 每轮必读入口。只有用户指定、当前 Goal/Plan/Task 明确指向，或解决具体技术问题确实需要时才读。安装、配置、迁移、部署或公开行为发生变化时，Planner 应把对应文档作为交付面纳入 Plan 和 Task，而不是在最后顺手补文字。

### Sync

CLI 支持的结构和状态变更优先走 CLI。需要编辑语义正文时，编辑 Markdown，然后运行：

```bash
aiwf sync
```

只检查、不写入：

```bash
aiwf sync --check
```

Claude Code 内通过 Write/Edit 修改治理 Markdown 后，PostToolUse hook 会自动 sync。使用外部编辑器或人类终端修改时没有 hook，必须手工运行 `aiwf sync`。

### Memory

Memory 是 Planner 的小型长期笔记本，不是项目日志。

```text
.aiwf/memory/
├── project-facts.md   # 每次规划都读，最多 3-7 条，目标少于 100 字
├── MEMORY.md          # notes 索引
└── notes/             # 需要时才读的稳定指导
```

Planner 在两个时刻审查 Memory：

- 规划完成、准备交出工作前。
- 实现、测试、Review、Architect 或关闭结果回到 Planner 时。

每次都要判断是否保留、修改、删除或增加，但只有出现经代码、证明、Review、用户决定或完成任务确认的长期事实时才写。不要存临时进度、猜测和当前 Task 已经说清楚的内容。

## Git、Task 快照与提交

AIWF 使用 Git 证明各角色处理的是哪一份代码。

### 前置条件

Task 激活要求：

- 当前目录属于 Git 仓库。
- 仓库至少有一个提交。
- 当前是命名 branch，不是 detached HEAD。
- 不在 `main`、`master` 或 `trunk` 上执行 Task。
- Plan 绑定的 worktree 项目文件干净。

### 三个 ref

每个 Task 通常保存：

- `implementation_ref`：Executor 完成后的本地不可变快照。
- `tested_ref`：Tester 完成测试和测试资产后的快照。
- `reviewed_ref`：Reviewer 接受的 tested snapshot。

查看：

```bash
aiwf task proof TASK-001
```

输出同时给出可用的 diff 命令，例如：

```bash
git diff <origin_ref>..<implementation_ref>
git diff <implementation_ref>..<tested_ref>
git diff <origin_ref>..<tested_ref>
```

这些 snapshot 是本地 Git refs，不在当前分支是正常的。不要手工 commit、
cherry-pick、merge 或 reset 它们。Tester 如果新增测试文件，`tested_ref` 会自然包含它们。

### Task commit

活动 Task 期间不要手工 `git commit`。Bash hook 会阻止 AI 创建未审查提交。

`aiwf task close` 会确认当前工作树与 `reviewed_ref` 完全一致，然后只为这份已审结果创建正式 Task commit。提交标题包含 Task ID，并附带 Plan/Goal trailers。

AIWF 不自动 push，也不自动 merge Plan branch。

### 外部或人类改动

人类可以修改代码，AIWF 不要求一切都由 AI 完成。需要注意：

- Task 激活前的项目改动会使 clean-worktree gate 阻止激活。
- Testing 后修改项目文件，Reviewer 会要求重新记录 Testing。
- Review 后修改项目文件，Task close 会要求重新运行 Tester 和 Reviewer。
- 人类终端不经过 Claude hooks，但最终 snapshot、close gate 和 Git diff 仍会暴露多数变化。

## Plan 并行与 Worktree

AIWF 的并行单位是 Plan，不是同一 Task 内的多个角色。

规则：

- 一个主 Planner 维护全部治理状态。
- 一个 Plan 绑定一个 branch 和一个 Git worktree。
- 一个 worktree 同时最多一个 active Task。
- 同一 Plan 的 Tasks 按顺序执行。
- 不同 Plan 可以在不同 worktree 并行。
- 每个 Agent prompt 必须包含一个 Task ID 和它的 worktree 路径。

Planner 在 control root 为每个 Plan 创建或复用一个持久 worktree：

```bash
aiwf plan bind-worktree PLAN-001 --create
```

该命令可重复执行，默认使用 `.claude/worktrees/plan-001` 和
`aiwf/plan-001`。Control root 只保存共享治理状态和负责集成，不作为新的
Plan worktree。

如果人已经创建了 worktree，可以显式绑定：

```bash
aiwf plan bind-worktree PLAN-001 ../project-plan-001
```

派发 Executor、Tester、Reviewer 时，把 Agent 的 `cwd` 设置为这个已绑定的
worktree。Agent 只核对当前位置，不再调用 `EnterWorktree`。不要给这三个角色使用
`isolation: worktree`，否则 Claude Code 会为每个角色创建不同的临时 worktree，三者
无法顺序审查同一份结果。

所有 worktree 通过 Git common directory 找到主工作区中的同一个 `.aiwf` control root。`aiwf status` 会展示全部 active Tasks，并标记当前 worktree 对应的 Task。
Planner 不需要在这些 worktree 之间切换。它使用明确的 Task ID 管理状态，并把每个
Agent 的 `cwd` 设置为对应 Plan worktree；多个 Task active 时，`aiwf status --prompt`
始终给出全局路由。

### 什么时候可以并行

Planner 必须先读相关 Plans 和真实代码，检查：

- 是否修改同一文件。
- 是否改变同一责任或共享机制。
- 接口、输入输出和所有权是否已确定。
- 数据流、控制流、共享状态和部署路径是否互相依赖。
- 两个 Plan 能否各自实现、测试和 Review。
- 合并顺序与组合验证是否明确。

不同文件名不代表独立。只要两个 Plan 同时改变同一共享行为，就应重划边界或串行。

### Plan dependency

如果下游 Plan 需要上游 Plan 的结果：

```bash
aiwf plan dep add PLAN-DOWNSTREAM PLAN-UPSTREAM
aiwf plan dep show PLAN-DOWNSTREAM
```

上游 Plan 必须合并并关闭，下游才可激活。删除依赖必须给原因：

```bash
aiwf plan dep remove PLAN-DOWNSTREAM PLAN-UPSTREAM \
  --reason "原共享接口已被稳定替代"
```

### 并行常见陷阱

- 新 worktree 只包含创建时已提交的 Git baseline，不包含主工作区未提交的项目改动。
- 同一 Task 的 Executor、Tester、Reviewer 不能并行。
- 两个 Plan 即使不碰同一文件，也可能竞争同一 schema、状态或运行入口。
- 合并后必须验证组合结果，不能只依赖每个 Plan 的单独测试。

## Testing、Review 与 Fix-loop

### Task record

每个 Task 只有一份紧凑记录：

```text
.aiwf/records/tasks/TASK-001.json
```

它包含当前 implementation、testing、review 和 fix-loop。旧的全局 `evidence.json`、`testing.json` 和 `review.json` 不再是主路径。

用户通常不需要直接读 JSON，优先运行：

```bash
aiwf task proof TASK-001
```

### Record 命令

这些命令通常由对应角色调用。required role 未真实派发时，记录命令会拒绝伪造交付。

Executor：

```bash
aiwf record implementation --task-id TASK-001 \
  --summary "改了什么、谁消费、self-check 证明了什么" \
  --command "最强的一条精确自查命令"
```

Tester：

```bash
aiwf record testing --task-id TASK-001 --status passed \
  --command "pytest -q tests/test_index.py" \
  --verification-result "pytest -q tests/test_index.py:::exit 0 and restart case passes:::12 passed:::matched" \
  --summary "验证了重启恢复和增量更新"
```

没有 `aiwf task test` 命令。`/aiwf-test` 负责派发测试工作，Tester 完成后用
`aiwf record testing` 保存测试结果和 Git snapshot。

Reviewer：

```bash
aiwf record review --task-id TASK-001 --result accepted \
  --summary "合同、最终 diff、消费者路径和测试证据一致"
```

阻塞性 Review：

```bash
aiwf record review --task-id TASK-001 --result needs_fix \
  --summary "service 入口仍绕过新 pipeline" \
  --blocker "run_service_wrapper 未消费统一 pipeline"
```

### Reviewer observations

Reviewer 可以记录非阻塞但必须可见的 observations。`critical` 和 `high` 不能与 accepted 同时记录；`warn` 和 `low` 可以交给 Planner 处置。

```bash
aiwf record review --task-id TASK-001 --result accepted \
  --summary "整体可信，但有一个不阻塞当前合同的风险" \
  --adversarial-observations "warn:::migration:::旧数据迁移尚未在生产副本验证"

aiwf record disposition ADV-001 --task-id TASK-001 \
  --decision deferred \
  --reason "不影响当前合同，纳入下一 Plan 的迁移工作"
```

关闭前不能有 pending observation。

### Fix-loop

以下情况会打开 Task-local fix-loop：

- Testing 失败。
- Review 返回 `needs_fix` 或 `rejected`。
- Agent 发现合同需要 Planner 或用户决定。
- Scope 或其他已记录问题需要恢复。

查看：

```bash
aiwf fixloop status --task-id TASK-001
aiwf status --prompt
```

正常返工顺序是：

```text
确认问题
-> Executor 修复或 Planner 决策
-> 重新运行所需 Testing
-> 解决 fix-loop
-> 重新 Review 最终 tested snapshot
-> Close
```

满足 required fixes 和 required verification 后：

```bash
aiwf fixloop resolve --task-id TASK-001 \
  --resolution "修复 service 入口并重跑 service integration test"
```

`--force` 是显式覆盖机械验证的恢复手段，不应用来把真实失败改成通过。

## 人工中断与紧急关闭

这两个命令只能由人类在终端运行，AI 会被 command policy hook 阻止。

### Interrupt

暂停当前执行窗口，但不宣告完成：

```bash
aiwf task interrupt TASK-001 --reason "需要重新决定接口责任"
```

Task 变为 `suspended`。之后 Planner 可以修订、重新批判并激活，也可以取消：

```bash
aiwf task cancel TASK-001 --reason "方案已被 PLAN-002 替代"
```

Active Task 不能直接 cancel，必须先 interrupt。

### Force-close

紧急把 active Task 标为 closed，并记录未满足的 gates：

```bash
aiwf task force-close TASK-001 --reason "人类接受不完整状态并结束该执行窗口"
```

它绕过测试、Review 和 snapshot gate，不等同于正常完成。真不要这项工作时应 interrupt 后 cancel，而不是 force-close。

`--reason` 技术上可省略，但建议保留，因为这是以后判断异常关闭的唯一直接背景。

## Architect 与 Critic

### Architect

Architect 是用户手动触发的独立结构审查。普通 Task Review 不替代它。

在 Claude Code 中：

```text
/aiwf-architect
```

主会话会先向用户确认：

- Review slice：全项目、Milestone、最近完成工作、某条能力路径或指定问题。
- Lenses：
  - `mission-mechanism`：当前技术路径是否真的通向固定 Mission，是否有更高杠杆结构。
  - `code-reality`：调用者、消费者、主路径、旧路径、未接线和死代码。
  - `governance-truth`：Goal/Plan/Task/Milestone 结构与机器状态是否真实。
  - `milestone-acceptance`：真实验收一个 Milestone。
- 是否需要外部标准、当前 benchmark 或 WebSearch。

小切片可以由一个 Architect 完成。全项目、多 lens 或大量外部比较应先问用户是否拆成多个并行 Architect。每个 Agent 写入独立的：

```text
docs/architect/ARCH-YYYYMMDD/<lens>/
```

Architect 只报告，不创建 Task，不实现，也不替 Planner 决定后续。

### Milestone acceptance

Milestone 验收使用 Architect，但还需要机器记录和人类确认：

```bash
aiwf milestone integration-test MS-001 --status passed \
  --coverage-mode end_to_end_flow --main-path-status passed \
  --command "<command>:::<observed output>"

aiwf milestone arch-review MS-001 --status intact --notes "interfaces remain intact"
aiwf milestone assess MS-001 --verdict PASS --summary "Pass Standard 全部通过"
aiwf milestone confirm MS-001 --summary "用户接受当前结果和列出的残余风险"
aiwf milestone close MS-001
```

`confirm` 只能在用户看到验收结果并明确同意后运行。

### Critic

Critic 是用户主动调用的独立怀疑者：

```text
/aiwf-critic
```

它可以挑战全项目、Mission、Goal、Plan、Task、Milestone、技术决策、结果或指定 claim。Critic 不加入正常 workflow，不阻塞工作，也不修改文件。用户可以要求“只批判”或“批判并给更好方向”。

## Hooks 与写保护

Claude 安装会配置这些 hooks：

| 时机 | 作用 |
|---|---|
| UserPromptSubmit | 状态或问题变化时发一条短提醒，让模型运行 `aiwf status --prompt` |
| PreToolUse Write/Edit/MultiEdit | 检查 active Task、角色写权限、Task freeze 和 forbidden write |
| PreToolUse Bash | 阻止危险命令、直接写机器真相、活动 Task 内手工 commit 和 AI-only 禁令 |
| PreToolUse Agent/Task | 检查所需 Skill 已加载，prompt 只指定一个 active Task 和正确 worktree |
| PostToolUse Skill/Agent | 记录 Skill load、Agent dispatch 和 Agent completion |
| PostToolUse Write/Edit/MultiEdit | 治理 Markdown 变更后自动 sync |
| SubagentStop | 记录关键子代理结束 |
| Stop | 只在 Task 已进入 closing 且仍未正常关闭时阻止会话退出 |

Hook 提醒故意很短。完整下一步始终来自：

```bash
aiwf status --prompt
```

### 默认写保护

- 项目代码默认要求 active Task。
- 当前 active Task.md 默认冻结。
- `.aiwf/state/` 和 `.aiwf/records/` 只能通过 CLI 修改。
- Mission、Goal、Plan、非活动 Task、Milestone 和 Memory 是 Planner 治理文档，不依赖 active Task。
- Task 第一次实现可强制要求 Executor。
- Tester 默认只能写明显的测试或验证资产。
- Architect 默认只能写 `docs/architect/ARCH-*/` 下的 Markdown 报告。
- Explorer 和 Critic 默认只读。
- Reviewer 按角色合同只读。

## 配置

配置位于 `.aiwf/config/`。Planner 可以管理普通 AIWF 配置；`command-policy.json` 保护 human-only 命令，AI 不可自行修改。

### write-policy.json

默认值：

```json
{
  "project_writes_require_active_task": true,
  "freeze_active_task_md": true,
  "first_implementation_requires_executor": true,
  "tester_project_writes": "test_assets_only",
  "architect_project_writes": "reports_only",
  "explorer_project_writes": "deny",
  "critic_project_writes": "deny"
}
```

允许值：

| 字段 | 允许值 | 含义 |
|---|---|---|
| `project_writes_require_active_task` | `true`, `false` | 项目文件是否必须在 active Task 中写 |
| `freeze_active_task_md` | `true`, `false` | 执行时是否冻结当前 Task.md |
| `first_implementation_requires_executor` | `true`, `false` | 当 Task 要求 Executor 时，首次实现是否机械强制子代理 |
| `tester_project_writes` | `deny`, `test_assets_only`, `allow_all` | Tester 可写范围 |
| `architect_project_writes` | `deny`, `reports_only`, `allow` | Architect 可写范围 |
| `explorer_project_writes` | `deny`, `allow` | Explorer 是否可写项目文件 |
| `critic_project_writes` | `deny`, `allow` | Critic 是否可写项目文件 |

`allowed_values` 是文件内帮助信息，不参与 gate 判断。配置缺失或损坏时，hook 回退到严格默认值。

Task 自己的 `executor_required`、`tester_required`、`reviewer_required` 和可选 `tester_write` 写在 Task.md frontmatter 中，必须在激活前决定。

### agent-models.json

所有 Agent 默认使用：

```json
"aiwf-executor": "inherit"
```

`inherit` 表示继承当前后端模型。也可以填写 Claude Code 支持的模型 alias 或完整 model ID。修改后重新安装生成 Agent frontmatter：

```bash
aiwf install claude --force
```

AIWF 不给 Agent 额外设置一个低能力工具 allowlist。实际可用的原生工具、MCP、网络和权限由当前 Claude Code 环境决定；Agent 仍需遵守自己的角色边界和项目权限。

### skill-map.json

它把 workflow phase 映射到 Skill。通常不需要修改。`CLAUDE.md` 只提供方向，`aiwf status --prompt` 和该文件共同决定当前 Required skills。

### command-policy.json

它记录额外的 AI 命令禁令。`task interrupt` 和 `task force-close` 还有硬编码的人类专属保护，因此不能通过删除普通配置让 AI 调用。

## 状态、UI 与诊断

### 最常用的诊断顺序

遇到问题时按这个顺序查看：

```bash
aiwf status
aiwf status --prompt
aiwf task proof [TASK-ID]
aiwf fixloop status --task-id [TASK-ID]
aiwf sync --check
aiwf doctor
aiwf status --debug
```

含义：

- `status`：给人看的当前工作区、active Tasks 和下一角色。
- `status --prompt`：给模型看的精确下一步与 Required skills。
- `task proof`：某 Task 的 Git refs、实现、Testing 和 Review 真相。
- `fixloop status`：返工原因、路由和必需验证。
- `sync --check`：Markdown 和机器索引是否可编译。
- `doctor`：安装、hooks、skills、agents、scripts 和目录是否完整。
- `status --debug`：完整 JSON 调试面板。

### TUI

```bash
aiwf ui
```

主要按键：

- `Tab`：切换 Mission/Goal/Plan/Task、Milestone、Task、Plan dependency 等视图。
- `j` / `k`：移动。
- `Enter` 或 `e`：用 `$EDITOR` 编辑叙事 Markdown，随后 sync。
- `r`：刷新。
- `s`：sync。
- `d`：切换详情。
- `x`：显示或隐藏 cancelled 节点。
- `q`：退出。

TUI 需要支持 curses 的交互终端。它不是必须入口，全部治理仍可通过 Claude Code 和 CLI 完成。

### Hook 日志

如果 hook 明明安装却没有作用，查看：

```text
.aiwf/runtime/internal/hook-diag.log
.aiwf/runtime/internal/skill-loads.jsonl
.aiwf/runtime/internal/agent-dispatch.jsonl
.aiwf/runtime/internal/status-hook-last.json
```

这些是诊断材料，不是 Planner 的项目事实。

## 命令索引

查看入口：

```bash
aiwf --help
aiwf --help --all
aiwf <command> --help
```

### 安装与状态

```bash
aiwf install claude [--force]
aiwf install reasonix [--force]
aiwf doctor
aiwf status [--prompt | --debug]
aiwf sync [--check]
aiwf ui
```

### Mission

```bash
aiwf mission show
```

Mission 语义通过 `.aiwf/mission.md` 编辑，再 `aiwf sync`。

### Goal

```bash
aiwf goal create GOAL-001 --title "..."
aiwf goal create GOAL-002 --parent GOAL-001 --title "..."
aiwf goal show [GOAL-ID]
aiwf goal list
aiwf goal link GOAL-A GOAL-B --type supports
aiwf goal unlink GOAL-A GOAL-B
aiwf goal close GOAL-001 --summary "..."
aiwf goal cancel GOAL-001 --reason "..."
```

关系类型：`depends_on`、`blocks`、`conflicts_with`、`invalidates`、`supports`。

### Plan

```bash
aiwf plan create PLAN-001 --goal GOAL-001 --title "..."
aiwf plan show PLAN-001
aiwf plan list
aiwf plan bind-worktree PLAN-001 --create
aiwf plan bind-worktree PLAN-001 [EXISTING-PATH]
aiwf plan link-task PLAN-001 TASK-001
aiwf plan unlink-task PLAN-001 TASK-001
aiwf plan dep add PLAN-002 PLAN-001
aiwf plan dep remove PLAN-002 PLAN-001 --reason "..."
aiwf plan dep show PLAN-002
aiwf plan close PLAN-001 --summary "..."
aiwf plan cancel PLAN-001 --reason "..."
```

### Task

```bash
aiwf task create TASK-001 --goal GOAL-001 --plan PLAN-001 --title "..."
aiwf task show [TASK-ID]
aiwf task proof [TASK-ID]
aiwf task list
aiwf task critique TASK-001
aiwf task activate TASK-001
aiwf task calibrate [TASK-ID] --summary "..."
aiwf task close [TASK-ID]
aiwf task interrupt [TASK-ID] --reason "..."      # human only
aiwf task force-close [TASK-ID] --reason "..."    # human only
aiwf task cancel TASK-001 --reason "..."
```

### Records

```bash
aiwf record implementation --help
aiwf record testing --help
aiwf record review --help
aiwf record disposition --help
```

### Fix-loop

```bash
aiwf fixloop open --route executor --reason "..."
aiwf fixloop status [--task-id TASK-001]
aiwf fixloop resolve --resolution "..." [--task-id TASK-001]
```

### Milestone

```bash
aiwf milestone create MS-001 --goal GOAL-001 --title "..."
aiwf milestone show MS-001
aiwf milestone list
aiwf milestone link-plan MS-001 PLAN-001
aiwf milestone unlink-plan MS-001 PLAN-001
aiwf milestone link-task MS-001 TASK-001
aiwf milestone unlink-task MS-001 TASK-001
aiwf milestone integration-test --help
aiwf milestone arch-review --help
aiwf milestone assess --help
aiwf milestone confirm --help
aiwf milestone close MS-001
aiwf milestone cancel MS-001 --reason "..."
```

## 目录结构

目标项目安装后：

```text
CLAUDE.md
.claude/
├── settings.json
├── skills/
│   ├── aiwf-planner/
│   ├── aiwf-implement/
│   ├── aiwf-test/
│   ├── aiwf-review/
│   ├── aiwf-close/
│   ├── aiwf-architect/
│   └── aiwf-critic/
└── agents/
    ├── aiwf-explorer.md
    ├── aiwf-executor.md
    ├── aiwf-tester.md
    ├── aiwf-reviewer.md
    ├── aiwf-architect.md
    └── aiwf-critic.md

.aiwf/
├── mission.md
├── goals/
├── plans/
├── tasks/
├── milestones/
├── memory/
│   ├── project-facts.md
│   ├── MEMORY.md
│   └── notes/
├── state/
│   ├── mission.json
│   ├── goals.json
│   ├── plans.json
│   ├── tasks.json
│   ├── milestones.json
│   └── state.json
├── records/
│   ├── tasks/<TASK-ID>.json
│   └── events.json
├── config/
│   ├── write-policy.json
│   ├── command-policy.json
│   ├── agent-models.json
│   └── skill-map.json
└── runtime/internal/

scripts/
├── aiwf_status.py
├── aiwf_scope_check.py
├── aiwf_bash_guard.py
├── aiwf_agent_gate.py
├── aiwf_agent_log.py
├── aiwf_skill_log.py
├── aiwf_auto_sync.py
└── aiwf_review_gate.py
```

Toolkit 自身源码：

```text
aiwf_core/
├── commands/             # CLI 参数和用户输出
├── core/                 # 状态、Task ledger、Git、records、sync
├── hooks/common/         # 后端无关 gate
├── adapters/claude/      # Claude / Reasonix 事件适配
├── embedded_templates/   # 安装到目标项目的 skills、agents、config、scripts
└── install_claude.py     # 安装与 doctor

tests/embedded/           # 当前主链合同和端到端测试
```

`docs/legacy/` 是历史材料，不应作为当前操作指南。

## 故障排除

### `No embedded AIWF installation found`

确认在目标项目或其子目录中运行：

```bash
aiwf install claude
aiwf doctor
```

如果刚安装，重启 Claude Code，让项目 settings 和 hooks 重新加载。

### `aiwf: command not found`

确认安装环境和 PATH：

```bash
python3 -m pip install -e /path/to/AI-Workflow-Toolkit
python3 -m pip show aiwf
which aiwf
```

### Doctor 报 Skill、Agent、Script 或 Hook 缺失

刷新安装产物：

```bash
aiwf install claude --force
aiwf doctor
```

`--force` 会刷新 AIWF 托管区块、hooks、skills、agents 和 scripts，不会覆盖现有机器状态、Task records 或 Memory 内容。安装器会保留 `.claude/settings.json` 中不属于 AIWF 的 hooks。

### Claude 没有按 workflow 路由

运行：

```bash
aiwf status --prompt
```

确认 Claude 加载了输出中的 Required skills。必要时手动运行 `/aiwf-planner`。再检查：

```text
.aiwf/runtime/internal/skill-loads.jsonl
.aiwf/runtime/internal/hook-diag.log
```

### Agent dispatch 被拒绝

常见原因：

- 当前阶段要求的 Skill 没有先加载。
- prompt 没有写唯一 Task ID。
- prompt 没有写 Task 分配的 worktree path。
- Task 不在 active 状态。
- 一个 worktree 已有另一个 active Task。

先运行：

```bash
aiwf status --prompt
aiwf task show TASK-001
aiwf task proof TASK-001
```

然后按对应 Skill 重新派发，不要把多个 Task 塞进一个 Agent prompt。

### 写项目文件时提示 `no active task`

项目代码默认只能在 active Task 中修改。让 Planner 完成合同、两次批判和 Git 准备后运行：

```bash
aiwf task activate TASK-001
```

Mission、Goal、Plan、非活动 Task、Milestone 和 Memory 属于规划治理文件，不需要 active Task。机器 JSON 仍必须走 CLI。

### 写 `.aiwf/state/*.json` 或 `.aiwf/records/*.json` 被拒绝

这是正常保护。使用对应的 `aiwf goal`、`plan`、`task`、`record`、`fixloop`、`milestone` 或 `sync` 命令，不要用 Write/Edit/Bash 改 JSON。

### 修改 active Task.md 被拒绝

Task 激活后合同被冻结。小的实现判断留给 Executor；实际结果写 Closure Calibration。

如果合同确实错误：

1. 人类运行 `aiwf task interrupt TASK-001`。
2. Planner 修订 Task.md 并 `aiwf sync`。
3. Planner 重新执行两次 activation critique。
4. 再次激活。

不要为了让当前实现通过而回写 Done When。

### `first implementation must be performed by aiwf-executor`

当前 Task 要求 Executor，并且还没有第一次实现记录。加载 `/aiwf-implement`，派发 `aiwf-executor`。

第一次 Executor 完成后，微小、局部、完全理解的返工可以由 Planner 判断是否内联。涉及主路径、接口、状态、数据、并发、权限、安全或部署的返工仍应再派 Executor。

如果该 Task 确实不需要独立 Executor，必须在激活前由 Planner 把 `executor_required: false` 写入 Task.md，而不是激活后绕门。

### Tester 写测试文件被拒绝

默认 `tester_project_writes: test_assets_only`。AIWF 会识别常见的 `tests/`、`test/`、`spec/`、`e2e/`、fixtures、snapshot 和测试文件名。

特殊测试位置应在 Task 激活前写入 frontmatter：

```yaml
tester_write:
  - path/to/project-specific/test-area/**
```

或者由人修改 `write-policy.json` 为 `allow_all`。Tester 不能借此修改实现代码。

### Task 激活提示需要 Git 仓库或初始提交

```bash
git init -b main
git add -A
git commit -m "Initial project"
```

然后运行 `aiwf plan bind-worktree PLAN-001 --create`。Task 不允许在
protected branch 上执行。

### Task 激活提示 protected branch

不要在 `main`、`master` 或 `trunk` 上开始 Task。让 Planner 从 control root
创建 Plan worktree：

```bash
aiwf plan bind-worktree PLAN-001 --create
```

### Task 激活提示 worktree 不干净

AIWF 不会猜这些改动属于哪个 Task。先查看：

```bash
git status --short
git diff
```

然后由人决定提交、stash、移除，或把它们纳入新的规划。不要让 Planner擅自丢弃外部改动。

`.aiwf/` 内部变化会被项目 diff gate 过滤，但普通项目文件、安装脚本、`CLAUDE.md` 和 `.claude/` 仍是正常 Git 改动。

### Plan 已绑定其他 branch 或 worktree

查看：

```bash
aiwf plan show PLAN-001
git branch --show-current
git worktree list
```

Plan 一旦绑定，不能静默换到另一个 branch/worktree。回到原路径，或取消旧 Plan 并创建清楚的新 Plan。

### Plan dependency 阻止 Task 激活

```bash
aiwf plan dep show PLAN-002
aiwf plan show PLAN-001
```

依赖 Plan 必须完成 Tasks、合并并 close。不要仅因为两个分支都“写完了”就删除依赖。

### 当前 worktree 显示没有 active Task，但其他地方正在执行

```bash
aiwf status
aiwf task list
```

`status` 会列出所有 Plan worktrees。进入对应 worktree，或在命令中明确传 `--task-id`。不要在错误 worktree 记录 Testing、Review 或 fix-loop。

### Testing 提示没有 implementation record

当 `executor_required: true` 时，Tester 只能在 Executor 已记录实现后开始。运行：

```bash
aiwf task proof TASK-001
```

如果实现存在但没记录，让原 Executor 在正确 worktree 运行 `aiwf record implementation`。不要由 Planner 补一条假的 handoff。

### Review 提示没有 tested snapshot

Reviewer 只审查 Tester 的最终 snapshot。先完成 Testing。若 Testing 后有任何项目文件变化，重新记录 Testing，再运行 Reviewer。

### Testing 已通过，但 close 提示 Verification Command 缺失

严格 Task 的每条 Verification Command 都需要：

- 完整的 `--command`。
- 对应的 `--verification-result`。
- expected。
- 非空 observed。
- `matched`。

运行 `aiwf task proof TASK-001` 查看 `proof_validation`。不要把 summary 当作命令输出。

### Review 几乎总是 accepted，怎样判断它是否真正工作

不要只看 `result`。阅读 Reviewer 返回给 Planner 的 `REVIEW_REPORT`，并检查：

- 它是否说明 Executor 实际修改。
- 是否引用 Tester 命令和结果。
- 是否写明自己追踪的调用者、消费者、旧路径和完整 diff。
- 是否解释为什么整个 Task claim 成立。
- 是否明确剩余 Unknown。

`aiwf task proof` 保存的是精要机器记录；具体工作汇报存在当前会话 handoff 中。泛泛的“看起来很好”不符合 Reviewer Skill。

### Close 提示 pending Reviewer observations

Planner 必须逐条确认：

```bash
aiwf record disposition ADV-001 --task-id TASK-001 \
  --decision resolved --reason "已修复并在新 tested snapshot 中验证"
```

也可以对非阻塞风险使用 `deferred`、`dismissed` 或 `accepted`，但必须给真实理由。critical/high 问题不能通过 accepted Review 留到以后。

### Close 提示 open fix-loop

```bash
aiwf fixloop status --task-id TASK-001
aiwf status --prompt
```

完成 required fix 和 required verification，再运行 `aiwf fixloop resolve`。如果修复改变代码，通常还需要新的 Testing 和 Review。

### Close 提示 `project files changed after review`

Close 会列出相对 `reviewed_ref` 缺少、多出或修改的路径。Snapshot 不在当前
分支是正常的，不要先提交或 cherry-pick 它。确认列出的差异后，重新派 Tester，
再派 Reviewer。

### Close 提示 Git index 已有 staged files

AIWF 要精确创建 reviewed Task commit，不能混入已有暂存。先查看：

```bash
git diff --cached
```

由人决定如何处理这些 staged files，再关闭 Task。不要使用破坏性 reset 丢改动。

### Close 提示没有 reviewed project changes

Task 的最终 snapshot 与 origin 没有项目差异。确认：

- Task 是否本来只做治理变更。
- 实现是否写在错误 worktree。
- 改动是否已经被其他手工 commit 提前提交。
- Task 是否应该 cancel，而不是伪造 evidence。

### Close 警告缺少 Closure Calibration

让 Planner 记录实际结果：

```bash
aiwf task calibrate TASK-001 --summary "..."
```

CLI 当前给出警告；正常 Skill 流程把 Calibration 作为收口必要步骤。它用于事后理解 Task 实际交付，不用于改写原合同。

### Stop hook 不让 Claude Code 结束

Stop 只在 Task 已进入 closing 但还没通过 `aiwf task close` 时阻止退出。运行：

```bash
aiwf status --prompt
aiwf task proof TASK-001
```

完成缺失的 Planner disposition、Calibration 或 Close。如果人要暂停，使用终端中的 human-only `aiwf task interrupt`。

### Plan close 被拒绝

Plan close 要求：

- 全部 Task 已 closed 或 cancelled。
- 项目工作树干净。
- Plan 有 Git branch 历史。
- 当前已经切到识别出的 base branch。
- Plan 的最后 Task commit 已合并到当前 base HEAD。

典型顺序：

```bash
git switch main
git merge plan/PLAN-001
# 运行组合验证
aiwf plan close PLAN-001 --summary "..."
```

AIWF 不替人解决 merge conflict。

### MD 与 JSON 不同步

```bash
aiwf sync --check
aiwf sync
aiwf doctor
```

常见原因：

- 使用外部编辑器，没有触发 PostToolUse hook。
- frontmatter 无法解析。
- ID 与文件名不一致。
- link 指向不存在的 Goal、Plan、Task 或 Milestone。
- active Task.md 被修改，sync 拒绝改变当前合同。

修 Markdown 或使用正确 CLI，不要反向修 JSON。

### Memory 越来越大或不可信

删除临时进度、猜测和当前节点已说明的内容。`project-facts.md` 保持 3-7 条且少于约 100 字；详细稳定指导放 notes，并只在 `MEMORY.md` 留一行索引。所有事实必须可回到代码、证明、Review、完成 Task、Architect 报告或用户决定。

### Architect 工作太大、太慢或只看局部

触发前明确 slice、lenses 和外部比较。全项目审查时让主会话询问是否拆成多个独立 lens。不要让主会话自己搜索、又让一个 Architect 重复全量搜索；外部比较由被分配该 lens 的 Architect 完成。

### 两个并行 Plan 发生冲突

停止继续合并，回到 Planner 检查共享责任、接口和合并顺序。Plan dependency 只能表达先后，不能自动解决同一机制被同时重写。必要时中断其中一个 Task、调整 Plan 边界并重新批判。

### TUI 无法启动

使用普通终端并确认 curses 可用。即使 TUI 不可用，仍可使用：

```bash
aiwf status
aiwf goal show
aiwf plan list
aiwf task list
aiwf milestone list
```

## 升级、迁移与移除

### 升级 Toolkit

```bash
cd /path/to/AI-Workflow-Toolkit
git pull
python3 -m pip install -e .
```

然后在每个目标项目刷新集成：

```bash
aiwf install claude --force
aiwf doctor
aiwf sync --check
```

安装器会迁移已识别的旧 flat state 和旧 singleton Task records，并删除已退休的安装产物。它不会恢复外部 orchestration、legacy runner 或旧的一次性 evidence 主链。

升级前仍建议提交或备份项目状态，尤其是自定义配置和治理文档。

### 切换 Agent 模型

编辑 `.aiwf/config/agent-models.json`，然后：

```bash
aiwf install claude --force
```

安装器保留已有模型选择，并补充新 Agent 的默认键。

### 移除 AIWF

当前没有自动 `uninstall` 命令。移除前先提交或备份：

1. 保留或归档 `.aiwf/` 中需要的 Mission、结构、Memory 和 Task 历史。
2. 从 `CLAUDE.md` 删除 AIWF managed block。
3. 从 `.claude/settings.json` 删除命令指向 `scripts/aiwf_*.py` 的 AIWF hook handlers，保留其他 hooks。
4. 删除 `.claude/skills/aiwf-*`、`.claude/agents/aiwf-*` 和 `scripts/aiwf_*.py`。
5. 确认 `git diff` 只包含计划移除的文件。

不要直接删除整个 `.claude/settings.json`，其中可能有项目自己的权限和 hooks。

## 开发与验证

在 Toolkit 仓库中：

```bash
PYTHONPYCACHEPREFIX=/private/tmp/aiwf-pycache \
  python3 -m pytest -q tests/embedded

bash tests/run-embedded-self-test.sh
bash tests/release-audit.sh
```

完成标准：

- Embedded tests 通过。
- Release audit 通过。
- Claude 安装后的 skills、agents、hooks 和 scripts 一致。
- 主链没有恢复 legacy external runtime。
- 新 workflow 规则有正常路径、错误顺序、陈旧状态和安装产物合同测试。
- 真实 CLI、Git snapshot 和临时项目 smoke test 与文案一致。

项目核心原则：

- Intelligence belongs to Claude Code.
- Governance belongs to AIWF.
- Markdown 保存语义，JSON 保存机器状态。
- 状态变更走 CLI，语义变更走 Markdown + sync。
- Testing 不是 Review checklist。
- Reviewer observation 在 close 前必须处置。
- 一个 Plan 一个 worktree，一个 worktree 一个 active Task。
- 同一 Task 的 Executor、Tester、Reviewer 串行。
- Task close 只提交 reviewed snapshot。

## 安全边界

AIWF hooks 是工程治理机制，不是恶意代码隔离沙箱。

- 它能拦截 Claude Code 配置中的常见 Write/Edit/Bash/Agent 路径。
- 它不能控制人类终端、外部进程、未接入的工具或操作系统权限。
- `command-policy` 和危险 Bash 检查降低误操作风险，但不能替代 Git、备份、代码审查、最小权限和发布审批。
- MCP 和网络工具是否可用由 Claude Code 配置决定。
- 安全、数据迁移、生产部署和不可逆操作仍需要人类判断。

## License

MIT
