# AI Workflow Toolkit (AIWF)

AIWF 是嵌入 Claude Code 与 Reasonix 的长周期工程治理层。

它不替代编程智能，也不把 Agent 变成低能力执行器。Claude Code / Reasonix 继续负责理解代码、设计方案、编辑文件、运行命令和分析错误；AIWF 负责把长期工程流程变成可见、可恢复、可审查、可机械验证的状态。

> Intelligence belongs to the coding agent. Governance belongs to AIWF.

## 为什么需要 AIWF

原生 AI 编程很擅长完成单次任务，但项目持续多个任务和会话后，常见问题会逐渐累积：

- 目标和范围只存在于对话记忆中，容易漂移
- Planner 知道流程，却跳过独立 Tester、Reviewer 或架构审查
- 测试结果和审查结论缺少机器证据
- 修复后没有重新测试、清理和审查
- 子代理连接中断后，已完成工作难以安全续接
- 下一个会话不知道项目为什么变成现在这样

AIWF 使用项目内的 `.aiwf/*.json` 作为唯一流程真相源，并通过 Skills、Subagents、Hooks 和 CLI 将这些约束接入原生编码会话。

## 核心能力

- **完整状态机**：规划、复杂度路由、实现、独立测试、清理、审查、Meta-critique、闭合和接力
- **机械复杂度路由**：根据文件范围、跨模块影响、风险、Fix-loop 历史和 Gravity 自动选择 L0-L3 最低深度
- **独立角色验证**：L2+ 使用独立 Executor、Tester 和 Reviewer，并保留角色证据
- **范围约束**：通过 `allowed_write` / `forbidden_write` 和 Hook 阻止越界写入
- **对抗审查闭环**：Reviewer 记录合同缺口，Planner 必须逐条处置后才能闭合
- **周期架构审查**：约每 10 个任务、Gravity 升高或 PROJECT-MAP 过期时触发
- **连接恢复**：子代理中断时返回可续接包，不因网络问题降低测试或审查深度
- **Plan-first 连续性**：为长任务维护可恢复的 task plan artifact，但不把 Markdown 当成流程真相源
- **不确定性路由**：先区分讨论、澄清、研究、探索和执行，避免一有想法就冻结错误合同
- **外部能力治理**：把社区 skills、hooks、MCP、动态工作流归类为可用能力，而不是让它们覆盖 AIWF 门禁
- **白盒状态**：`aiwf status` 解释当前 Level、机械信号、下一角色和阻塞原因

## 支持平台

| 能力 | Claude Code | Reasonix |
|---|---|---|
| Planner / Skills | `.claude/skills/` | `.reasonix/skills/` |
| 独立子代理 | `.claude/agents/` | `runAs: subagent` Skills |
| Hooks | 支持 | 支持 |
| Stop 闭合行为 | 可在 `close_attempt=true` 时阻塞 | 仅报告，不阻塞 |
| 权威闭合门 | `prepare-close` + Stop 再验证 | `prepare-close` |

要求：Python 3.10+、Git，以及 Claude Code 或 Reasonix。

## 安装

```bash
git clone https://github.com/ww-hh-ww/AI-Workflow-Toolkit.git
cd AI-Workflow-Toolkit
python3 -m pip install -e .
```

然后进入需要治理的项目，选择对应平台安装：

### Claude Code

```bash
cd /path/to/project
aiwf install claude
aiwf doctor
claude
```

在 Claude Code 中：

```text
/aiwf-planner "我想实现一个功能，先和我讨论"
```

### Reasonix

```bash
cd /path/to/project
aiwf install reasonix
aiwf doctor
reasonix code .
```

在 Reasonix 中：

```text
/skill aiwf-planner "我想实现一个功能，先和我讨论"
```

**用户主要只需要和 Planner 对接。** 实现、测试、审查和闭合都是由 Planner 调度的 `planner-directed capabilities`；用户只需确认目标、范围、重大风险和最终闭合。

## 完整执行流程

```text
安装与状态定向
→ Planner 讨论和预规划研究
→ 冻结 Evaluation Contract 与 Architecture Brief
→ 复杂度路由、Context Dispatch、任务激活
→ Scoped Executor 实现
→ Independent Tester 验证
→ Cleanup before Review
→ Adversarial Reviewer 审查
→ Fix-loop（需要时重新实现、测试、清理、审查）
→ Planner Meta-critique 与观察处置
→ Task Close
→ prepare-close
→ Current State / Report 接力
```

流程不是固定重流程。AIWF 会根据机械信号选择最低 Level，Planner 再根据代码语义风险主动提高深度和广度。
在执行前，Planner 还会记录 request mode：讨论、澄清和研究不会激活实现；spike 只能产出发现，不能作为最终实现闭合；只有 execution 才进入 scoped task、测试、审查和闭合链路。

| Level | 典型场景 | 默认流程 |
|---|---|---|
| L0 | typo、极小改动 | Planner 内联实现、自测、自审查 |
| L1 | 小功能、有限范围 | Executor + 轻量独立验证 |
| L2 | API、多模块、共享逻辑 | Executor + Tester + 对抗 Reviewer |
| L3 | 安全、迁移、高风险结构变更 | 完整团队 + Checkpoint + 深度结构审查 |

## 机械状态与 Gravity

关键状态保存在目标项目的 `.aiwf/` 中：

| 文件 | 用途 |
|---|---|
| `.aiwf/state/goal.json` | 目标、Evaluation Contract、Architecture Brief |
| `.aiwf/state/contexts.json` | 上下文与读写边界 |
| `.aiwf/state/task-ledger.json` | 任务计划、依赖和执行窗口 |
| `.aiwf/evidence/records.json` | 机器观察到的证据 |
| `.aiwf/quality/testing.json` | 测试状态、命令与风险 |
| `.aiwf/quality/review.json` | 审查结果与对抗观察 |
| `.aiwf/state/fix-loop.json` | 修复路由和恢复状态 |
| `.aiwf/history/task-history.json` | 跨任务历史与 Gravity 数据源 |

Gravity 是从任务历史计算的纯函数。它不会修改状态，只将重复修改热点、修复趋势、结构漂移和历史风险转化为路由压力。项目轻时流程保持轻量，风险累积后自动提高治理强度。

Task plan artifact 与 PROJECT-MAP 分工不同：

- `PROJECT-MAP`：长期项目结构、模块边界和架构方向
- `.aiwf/plans/*.md`：单个任务的计划、检查项、验证策略、风险和续接说明

外部研究和社区工作流先进入低信任区：`aiwf research record` 记录 claims，`aiwf research promote` 才能把 Planner 认可的部分变成决策输入。`aiwf capability scan` 会标记外部技能是否重叠 AIWF 生命周期；重叠能力只能辅助对应阶段，不能替代 AIWF 的状态、证据、测试、审查和闭合门。

证据链有两条正规入口：

- Hook evidence：主会话的 Write/Edit/Bash 由 PreToolUse/PostToolUse 自动记录。
- Role delivery evidence：子 agent 或只读角色未被 hook 捕获时，用 `aiwf state record-role-evidence`、`aiwf state record-testing`、`aiwf state record-review` 记录角色交付证据。

L2/L3 闭合要求 Executor、Tester、Reviewer 都有可审计 role-bound evidence；口头 handoff 不算证据。

两类外部治理是硬门禁：

- 如果 Planner 设置 `external_research_required=true`，执行激活前必须有 promoted research，或用 `aiwf research skip --reason "..."` 记录显式跳过理由。
- 如果 Planner 用 `aiwf capability plan-use <ID>` 标记将使用生命周期重叠能力，执行激活前必须用 `aiwf capability decide <ID> --decision "..."` 记录决策。仅仅扫描到高风险能力不会阻塞项目。

## 常用命令

```bash
aiwf status             # 查看状态、复杂度路由、下一步和阻塞原因
aiwf doctor             # 检查平台安装完整性
aiwf cleanup check      # 只读检查陈旧资产和结构问题
aiwf plan create        # 创建 task plan artifact
aiwf recipe recommend   # 获取 advisory workflow recipe
aiwf research record    # 记录低信任外部研究
aiwf state record-testing # 记录测试结果并生成 Tester evidence
aiwf state record-review  # 记录审查结果并生成 Reviewer evidence
aiwf state record-role-evidence # 为子 agent hook 断裂补正式角色证据
aiwf capability scan    # 归类外部 skills/hooks/MCP/commands
aiwf capability plan-use # 标记将使用某个外部能力
aiwf capability decide   # 为生命周期重叠能力记录 Planner 决策
aiwf export-report      # 生成闭合报告
aiwf checkpoint list    # 查看回滚检查点
```

完整命令：

```bash
aiwf --help
```

## 关键边界

- `.aiwf/*.json` 是流程真相源，模型记忆和文字说明不是
- Review 必须在 Cleanup 之后
- Testing 不能退化成 Reviewer checklist
- Fix-loop 后必须重新执行受影响的测试、清理和审查
- 周期 Architect 不阻塞当前任务关闭，只阻塞下一个普通任务激活
- Claude Stop 只在 `prepare-close` 已建立关闭尝试后参与阻塞
- Reasonix Stop 永不阻塞，成功的 `prepare-close` 是权威闭合门
- AIWF 不会自动提交或推送代码

## 开发与发布验证

```bash
python3 -m pytest -q tests/embedded
bash tests/release-audit.sh
./make-release.sh
```

每条新增流程规则都应包含合同测试，至少覆盖正常路径、错误顺序、陈旧状态、Planner rebase、Context Dispatch，以及不会复活已移除的外部运行时。

## License

MIT，见 [LICENSE](LICENSE)。
