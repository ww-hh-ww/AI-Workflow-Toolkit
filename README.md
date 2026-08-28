# AI Workflow Toolkit (AIWF)

AIWF 是围绕原生编码 Agent 长周期工程会话构建的治理与可见性层。主线支持
Claude Code、Codex 和 OpenCode；Reasonix 是兼容目标。

编码 Agent 继续负责理解架构、搜索代码、编辑文件、运行命令、分析失败和作出工程判断。
AIWF 负责长期语义、状态顺序、证据身份、角色边界、Git 快照、审查门禁和闭环。

> Intelligence belongs to the coding agent. Governance belongs to AIWF.

## 三个 Task 角色

AIWF 的 Task 工作只有三个角色：

| 角色 | 核心职责 | 权力边界 |
| --- | --- | --- |
| Executor | 改变现实 | 修改稳定 Plan 工作区；实现；运行并记录全部 V-* / FIX-* 构造证据 |
| Experimenter | 认识现实 | 在一次性完整项目工作树中探索、测量、复现和证伪；只产出事实 |
| Reviewer | 判断现实 | 对当前 implementation ref 和已有证据作 acceptance judgment；不修改项目 |

一句话：

```text
Executor changes. Experimenter discovers. Reviewer judges.
```

这三个角色不是固定阶段。合法形态包括：

```text
Executor -> Reviewer
Experimenter -> Executor -> Reviewer
Executor -> Experimenter -> Reviewer
Experimenter -> Executor -> Experimenter -> Reviewer
```

Experiment 只在存在决策相关的 empirical uncertainty 时出现。它不是每个 Task 必经的
“Testing stage”，也不接手 Executor 本应完成的验证义务。

Planner 是上层规划和治理角色，不是第四个 Task 执行角色。Explorer、Critic 和 Architect
是规划或跨 Plan 分析能力，也不改变上述三角色模型。

## 安装与启动

要求 Python 3.9+ 和 Git。

### Claude Code

```bash
pip install -e .
aiwf install claude
claude
```

从 `/aiwf-planner "describe the goal"` 开始。

### Codex

```bash
pip install -e .
aiwf install codex
codex
```

从 `$aiwf-planner "describe the goal"` 开始。

### OpenCode

```bash
pip install -e .
aiwf install opencode
opencode --agent aiwf-planner
```

从 `/aiwf-planner "describe the goal"` 开始。

安装不会创建外部 managed runtime，也不会用低能力 runner 代替宿主 Agent。

## 状态与语义真相

AIWF 使用两层真相：

- Markdown 保存 Mission、Goal、Plan、Task 的含义和结构；
- `.aiwf/state/*.json` 与 `.aiwf/records/*.json` 保存运行状态和简明证据。

不要手改 JSON。Markdown frontmatter 的受支持字段通过以下命令编译：

```bash
aiwf sync
aiwf sync --check
```

任何时候先看：

```bash
aiwf status --prompt
```

查看一个 Task 的完整证据故事：

```bash
aiwf task proof TASK-001
```

## Task.md 合同

Task.md 必须回答：

- Structural Home：它为何属于这个 Goal / Plan；
- Objective：要实现什么结果；
- Contract Responsibility：本 Task 负责交付和证明什么；
- Proof Standard：Built / Wired / Running 的完成要求；
- Verification Commands：最小、可运行、带稳定 ID 的基线验证；
- Known Context：源码支持的入口和关键事实；
- Open Judgment：真正需要角色独立判断的问题。

验证命令使用稳定 ID：

```markdown
| ID | Command | Expected Observable Output |
| --- | --- | --- |
| V-001 | pytest -q tests/test_auth.py | all tests pass |
```

V-* 是 Executor 的构造义务。Executor 不应只“写完代码”，然后把主路径、错误路径或
回归验证拖给 Experimenter。

## 标准 Task 生命周期

常见主线是：

```text
Planner discussion and project research
-> Mission / Goal / Plan / Task
-> two activation critiques
-> optional pre-implementation EXP
-> Executor implementation + complete V evidence
-> optional post-implementation EXP
-> Reviewer judgment
-> Planner disposition + Closure Calibration
-> Task close
```

建立并激活 Task：

```bash
aiwf task create TASK-001 --goal GOAL-001 --plan PLAN-001 --title "..."
aiwf task critique TASK-001
aiwf task critique TASK-001
aiwf task activate TASK-001
```

一个 Plan 使用持久工作树：

```bash
aiwf plan bind-worktree PLAN-001 --create
```

同一 Plan 的 Task 串行。结构独立、工作树分离的多个 Plan 可以并行。

## Executor：实现和构造证据

Executor 在稳定 Plan 工作树中修改生产代码、正式测试、构建配置和其他交付资产。
它必须执行 Task.md 中的全部 V-*，并把 observed result、verdict 和 basis 绑定到同一
implementation snapshot：

```bash
aiwf record implementation \
  --task-id TASK-001 \
  --summary "implemented the authenticated entry path" \
  --check V-001 \
  --observed "42 passed" \
  --verdict matched \
  --basis "pytest completed against the assigned Plan worktree"
```

多条检查可重复传入相同参数，或使用 `--proof-file`。AIWF 在记录快照前检查：

- V/FIX ID 是否来自当前 Task 合同或 fix loop；
- 每个义务是否都有完整、matched 的结果；
- 当前目录是否为该 Task 的 Plan 工作树；
- 是否仍有未 finish 的 Experiment；
- 禁止写范围是否被破坏。

新的 implementation 会使旧 Review 失效，并使针对旧实现的 post-implementation EXP
变为 stale。

## Experimenter：一次性认识现实

Experiment 必须先声明一个明确的未知事实和稳定 subject ref：

```bash
aiwf experiment open EXP-001 \
  --task-id TASK-001 \
  --timing post_implementation \
  --question "真实入口是否绕过新的鉴权路径？" \
  --hypothesis "所有生产入口都会经过 authenticate()"

aiwf experiment start EXP-001
```

`start` 创建 detached、一次性的完整项目工作树。Experimenter 可以在其中任意修改项目
文件，创建 reproducer、benchmark、fault injection、prototype、临时 fixture 或诊断脚本。
它不能修改稳定 Plan 工作树，也不能修改控制根的 `.aiwf` 治理状态。

实验完成后，把事实冻结为不可变 Git ref 和结构化记录：

```bash
aiwf experiment record EXP-001 \
  --conclusion falsified \
  --summary "legacy service entry bypasses authenticate()" \
  --command "pytest -q exp/service_entry.py" \
  --observation "legacy mode returned 200 without calling authenticate" \
  --promotion-candidate "promote the reproducer into a regression test"

aiwf experiment finish EXP-001
```

`record` 至少需要一个 observation。`finish` 删除一次性工作树，但保留：

- immutable subject commit；
- immutable experiment ref；
- commands、observations、conclusion；
- 值得由 Executor 正式化的 promotion candidates。

实验假设被 falsify 只是事实，不会自动伪装成实现修复或 acceptance decision。Planner 或
Reviewer 根据事实决定是否需要 Executor 修改稳定系统。值得永久保留的实验资产必须由
Executor 提升为正式测试或工具，并重新记录 implementation 与相关 V 证据。

## Reviewer：判断当前实现

Reviewer 读取：

- Task.md 合同；
- 当前 `implementation_ref`；
- Executor V/FIX 证据；
- 与当前 subject 相关且已 finish 的 Experiment；
- 代码结构、调用路径、兼容性和清理状态。

Reviewer 不写项目文件，也不重复承担 Executor 的常规验证工作。结果只有：

```text
accepted
needs_change
needs_experiment
rejected
```

示例：

```bash
aiwf record review \
  --task-id TASK-001 \
  --result accepted \
  --summary "current implementation satisfies the Task contract"
```

当缺少一个真实 empirical fact 时，Reviewer 可以明确开启实验问题：

```bash
aiwf record review \
  --task-id TASK-001 \
  --result needs_experiment \
  --summary "production routing remains empirically unknown" \
  --experiment-id EXP-002 \
  --experiment-question "生产配置下实际选择哪个入口？" \
  --experiment-hypothesis "production selects the new entry"
```

`needs_change` 路由回 Executor；`needs_experiment` 创建针对当前实现的事实问题；
`rejected` 表示当前 change 不应接受。

## Fix loop 与 Reviewer observations

实现缺陷、结构问题或未满足的 FIX-* 义务进入 fix loop。普通修复和回归证明仍属于
Executor，不能因为出现“验证”一词就交给 Experimenter。

```bash
aiwf fixloop open \
  --task-id TASK-001 \
  --route executor \
  --reason "the error path violates the contract" \
  --required-fix "repair the error path" \
  --verify 'FIX-001:::pytest -q tests/test_error.py:::all tests pass'
```

Reviewer 的 machine observations 必须逐条 disposition，不能只在聊天里说“已处理”。
高严重度未决 observation、开放 fix loop、stale snapshot 或未 finish EXP 都会阻止 close。

## Closure

Planner 在 Task.md 写入简洁的 `## Closure Calibration`，说明实际交付结果和仍需未来
知道的差异。然后运行：

```bash
aiwf task close TASK-001
```

关闭要求至少包括：

- implementation ref 对应当前稳定工作树；
- 全部 Executor V/FIX 证据完整；
- 没有 live Experiment；
- Reviewer 接受的 ref 与 implementation ref 相同；
- observations 已 disposition；
- fix loop 已处理；
- Closure Calibration 非空；
- Review 后项目没有再次变化。

Claude Stop hook 会阻止“已审查但尚未 close”的 Task 被静默遗忘。

## Git 与证据身份

Task 证据使用 Git 对象，不依赖会话记忆：

- `git_origin_ref`：Task 开始时的稳定基线；
- `implementation_ref`：Executor 完成实现和 V 证据时的快照；
- `reviewed_ref`：Reviewer 判断的 implementation ref；
- `refs/aiwf/experiments/<EXP-ID>/<attempt>`：Experiment 的不可变结果。

Experiment 工作树是 disposable；Plan 工作树是 stable。不要在它们之间手工
cherry-pick 临时实验改动。需要保留的资产由 Executor 在稳定工作树重新实现。

## 写边界

- Planner：拥有 Markdown 合同、Plan 治理和 disposition；常规 Task 实现由 Executor 完成。
- Executor：只能写分配的稳定 Plan 工作树和 Task 允许范围。
- Experimenter：只能写当前 running EXP 的一次性工作树。
- Reviewer：项目只读。
- JSON state/records：只通过 CLI 修改。
- closed Plan/Task 文档：历史记录，只读。

Hook 和适配器会拒绝跨 Plan 工作树、跨 EXP 工作树、直接改机械真相和角色越权。

## 常用诊断

```bash
aiwf status --prompt
aiwf task proof TASK-001
aiwf experiment list --task-id TASK-001
aiwf experiment show EXP-001
aiwf fixloop status --task-id TASK-001
aiwf doctor
aiwf doctor --host codex
aiwf sync --check
```

## 安装后主要文件

```text
.aiwf/
├── goals/ plans/ tasks/ milestones/   # Markdown meaning
├── state/                             # runtime state
├── records/
│   ├── tasks/                         # implementation/review/fix-loop records
│   └── experiments/                   # empirical facts and immutable refs
├── config/
└── memory/

.claude/agents/aiwf-{executor,experimenter,reviewer}.md
.claude/skills/aiwf-{implement,experiment,review}/

.codex/agents/aiwf-{executor,experimenter,reviewer}.toml
.agents/skills/aiwf-{implement,experiment,review}/
```

## 开发验证

```bash
python3 -m pytest tests/embedded -q
python3 -m pytest tests/v1_core/test_v1_release_gate.py -q
bash tests/release-audit.sh
```

每条新工作流规则都应有 contract test，覆盖正确路径、错误顺序、stale state、宿主安装
产物和已删除旧运行时不会复活。

## 明确不支持

不要重新引入：

- `.ai-workflow/`；
- 外部 runner 或 managed runtime；
- fake terminal executor；
- 外部 `aiwf planner` / `aiwf handoff` / `aiwf action`；
- 首条用户消息自动生成 Task；
- 把测试降为 checklist；
- 把 Experimenter 变成实现后的固定阶段；
- 由另一个角色补做 Executor 应完成的 V-* 义务。
