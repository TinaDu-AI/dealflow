# MFV Deal Flow — 开发状态

> 这份文档描述 **dev 分支**当前正在进行的变动。  
> 每完成一项改动，更新本文件，记录"这次改了啥"。

## 当前迭代目标

（暂无进行中的开发任务）

## 变更日志

### 2026-04-29 — 建立分支管理体系
- 创建 `dev` 分支用于日常开发
- 新增 `MFV-Deal-Flow-验收状态.md`、`MFV-Deal-Flow-开发状态.md` 两份状态文档
- main = 验收版（稳定，不动）
- dev = 开发中版（合并验收后再 merge 回 main）

## 待办（按优先级）

### P1 — LLM 模块优化
- [ ] 在独立分支 `feature/llm-rework` 上优化 Rubric 评分 prompt
- [ ] 加入降级链（Qwen → DeepSeek → 智谱）

### P2 — 实验方法论
- [ ] 建立 `experiments/` 目录结构
- [ ] 准备标注样本（20-50 条已知评分项目）
- [ ] 控制变量法对比 prompt 优化前后的准确率

### P3 — 长内容处理
- [ ] 长帖子分段 + RAG 方案

## 开发约定

- 每完成一个独立功能 → commit + push + 更新本文件
- 重大节点完成 → 准备从 dev 合并到 main，同步更新 `验收状态.md`
- 分支命名：`feature/xxx`（新功能）、`fix/xxx`（修 bug）、`exp/xxx`（实验性）
