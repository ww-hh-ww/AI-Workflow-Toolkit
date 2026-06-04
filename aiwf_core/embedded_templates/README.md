# AIWF 项目档案

这是 AIWF（AI Workflow Toolkit）为本项目生成的治理档案目录。

## 目录结构

### 机器状态（JSON）— 自动化流程读写
- `state/` — 当前阶段、活跃上下文、工作流层级
- `evidence/` — 操作级证据链（git diff 记录）
- `quality/` — 测试结果与审查记录
- `history/` — 任务历史与账本

### 人类可读（中文 Markdown）— 你关心的都在这里
- `reports/当前状态.md` — 接力摘要，新会话从这里开始
- `reports/闭合报告.md` — 最近一次任务闭合依据
- `reports/质量摘要.md` — 跨任务质量趋势
- `reports/项目地图.md` — 架构方向、决策、递延风险

### 其他
- `assets/` — 环境配置、能力扫描结果
- `checkpoints/` — 回滚快照
- `internal/` — 系统内部文件

## 审计方式

```
机器审计: 读 JSON 文件（evidence > testing > review > task-history）
人类审计: 读 reports/*.md（闭合报告 > 质量摘要 > 项目地图）
快速检查: 终端运行 aiwf status
完整报告: 终端运行 aiwf export-report
```

## 注意

不要手动编辑此目录中的 JSON 文件。
所有状态变更通过 `aiwf state` CLI 命令完成。
