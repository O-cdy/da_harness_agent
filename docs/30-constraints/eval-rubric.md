# 30 · 评估量表（Eval Rubric）

> 唯一职责：定义报告出稿前的评估量表。任一项「不通过」即判定本次分析失败，落 `errors/E-NNNN` 并修复后重跑。
> 版本 v0.2 | 建立：2026-09-22 | 最后更新：2026-09-24 | 状态：**生效**。通用基线适用于全部任务；场景要求由 playbook overlay 声明（ADR-068 / R-95）。

## 四项评分

| 项 | 判据 | 通过标准 | 证据来源 |
|---|---|---|---|
| **1 口径正确** | 正式报告指标能追到 metric registry，探索草稿的 provisional 有完整定义与状态 | 正式指标为可实现的 canonical/platform-native；provisional 未混入正式报告；平台映射按 adapter contract | `plan.md` + metric refs + adapter manifest |
| **2 可复现** | 三要素齐备，且同输入重跑数字一致 | 快照 hash + 代码留档 + 模型版本齐全；重跑核心指标**零差异** | `runs/<task>/` + 重跑对比 |
| **3 无臆造** | 缺数据处按 G-21 标注，无估算填充；核因细节在证据包不在主报告 | 抽查 5 个关键数字，全部能在 SQL/代码中复算；主报告无堆砌脚注 | `sql/` + `artifacts/` + `report.md` |
| **4 任务目标达成** | 输出覆盖 `plan.acceptance_criteria`，结论与证据匹配 | manifest 声明的必需步骤与 eval overlay 全通过；不得用未声明的月报指标评估其它场景 | `plan.md` + manifest + report |

## 阈值

- 四项全通过 → 出报告。
- 任一项不通过 → **阻断**，落错误档案，修复后重跑。
- 「重跑一致」允许 LLM 表述差异，**不允许数字差异**。

## Playbook eval overlay

| 场景 | 附加判据 |
|---|---|
| `monthly-business-review` | Top 异动须有 M401 量价 + M402 贡献度；跨平台总览给逐平台覆盖率；未齐只可 partial |
| `ask` 探索 | provisional 指标有定义/SQL/快照/醒目标识；未经确认不得发布为正式报告 |
| TikTok platform-native | 官方来源、适用地区、检索日期、归因窗口与实现状态齐备；不得进入 canonical 合计 |

## 常见失败模式（预防清单）

| 失败模式 | 预防规则 |
|---|---|
| 用平台原始口径直接跨源相加 | R-05 / K-01~K-05 |
| 大促窗口被误判为异常 | R-12 / R-70 |
| 无日历却整报失败，或把未识别窗口下跌写成恶化 | R-70 |
| 用 order items 当订单数 | R-13 / K-05 |
| 数据缺失处用行业均值兜底 | R-03 |
| 改了 SQL 模板或口径却跳过 C1/C2 | R-73 |
