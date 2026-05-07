# MFV Deal Flow — 实验环境

> 本目录是 LLM/Pipeline 优化的**隔离实验区**。生产代码（webapp/）不受影响。

---

## 为什么有这个目录

少云方法论：
1. **禁止重写生产代码** —— 实验脚本必须直接 import 生产函数
2. **控制变量法** —— 每次只改一个变量（model / prompt / 参数 三选一）
3. **结果可视化、可回溯** —— 每次实验产出 `results.json` + `report.html`
4. **新旧对比** —— `experiments/README.md`（本文件）维护索引

---

## 目录结构

```
experiments/
├── README.md                         # 本文件 + 实验索引
├── _shared/                          # 共享工具
│   ├── runner.py                     # 通用执行器（读 corpus → 调生产函数 → 写 JSON）
│   ├── metrics.py                    # 准确率/MAE/Spearman/分歧对
│   ├── report.py                     # 生成 report.html
│   ├── corpus/                       # ⭐ 冻结的 XHS 帖子快照（JSONL）
│   └── samples/                      # ground truth（你手工/swipe 标注）
└── <编号>-<主题>/                    # 每次实验一个目录
    ├── config.yaml                   # 这次用的 model / prompt / 参数
    ├── prompt.txt                    # （如改 prompt）独立存档
    ├── run.py                        # 入口（≈10 行，调 _shared/runner）
    ├── results.json                  # 跑出来的原始结果
    └── report.html                   # 渲染后的对比报告
```

### 编号约定

| 编号段 | 对应 pipeline 节点 |
|---|---|
| **001-009** | 抓取阶段（关键词、排序、时间窗、max_per_keyword） |
| **010-019** | 筛选阶段（model 选型、prompt、temperature、Rubric 维度） |
| **020-029** | 推送阶段（Layer A 匹配、排序公式、Layer B 阈值） |
| **030-039** | 左滑分类（A/B1/B2 边界） |

---

## 设计原则（硬规则）

1. **冻结 corpus**：所有实验跑同一份 JSONL 快照。XHS 内容每天变，不冻结就失去可比性。
2. **三段解耦**：抓取 / 筛选 / 推送独立实验。例如做筛选实验时跳过抓取，直接读 corpus 喂 LLM。
3. **调用生产代码、不复制**：通过传 `model_name` / `prompt_template` 参数覆盖默认值。生产代码默认行为零变化。
4. **不写 mfv.db**：所有结果只写 `results.json`。DB 只读不写。
5. **每次 LLM 输出加 `evidence` 字段**：让模型先列证据再下结论，便于人工审计。
6. **双模型对比只在实验做**：生产永远单跑。选定模型后回到生产。

---

## 评审循环（人是有限带宽）

| 评审类型 | 频率 | 工作量 | 信号来源 |
|---|---|---|---|
| **隐式审计**（swipe vs LLM 评分分歧） | 周一次 | 10 min | Tina 日常划卡，系统自动算分歧 |
| **审核队列**（低置信度 LLM 判断） | 周一次 | 5-10 min | LLM 输出 `confidence`，<0.85 进队列 |
| **Canary 抽样**（1c 阶段被丢弃的帖子） | 持续 | 0（混在 feed 里） | 被判"非项目"的 5% 强制喂回 feed |
| **实验对比**（选模型/调 prompt） | 每次实验 | 30 min | 冻结 corpus + 多模型 |

---

## 实验索引

_（待填充——每次实验完成后在这里加一行：编号、主题、变量、结果指标、结论）_

| # | 主题 | 变量 | 关键指标 | 结论 |
|---|---|---|---|---|
| — | — | — | — | — |

---

## 落地顺序

| 阶段 | 做什么 | 状态 |
|---|---|---|
| 0. 基础设施 | `_shared/runner.py` / `metrics.py` / `report.py` 骨架 | ✅ 已搭（占位实现） |
| 0. 生产代码参数化 | `llm_service._call_qwen` / `score_company_rubric` 加 `model` / `prompt_template` 参数（默认值=现行生产值） | ✅ 已加 |
| 1. 标注 corpus | 从 mfv.db 导出 + 手工细标注 ~30 条 | ⬜ 待办 |
| 2. 跑筛选基线 | `010-score-qwen-baseline`：当前 prompt + Qwen | ⬜ 待办 |
| 3. 多模型对比 | `011/012/013`：DeepSeek / 智谱 / Claude | ⬜ 待办 |
| 4. prompt 优化 | `014~`：基于胜出模型，控制变量改 prompt | ⬜ 待办 |
| 5. 抓取实验 | `001~`：关键词集/排序/时间窗 | ⬜ 待办 |

---

## 待决定（动手前要拍板）

1. corpus 多大？（建议 100 条）
2. 手工细标注多少条？（建议先 30，后期补到 50+）
3. 多模型对比要不要带 Claude？（贵，建议只跑 30 条）
