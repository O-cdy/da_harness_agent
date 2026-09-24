# 30 · 评估量表（Eval Rubric）

> 唯一职责：定义候选报告封包后的评估量表。任一适用项「不通过」即阻断 C3/正式发布；确认属于新错误家族时落 `errors/E-NNNN`，修复后重跑。
> 版本 v0.3 | 建立：2026-09-22 | 最后更新：2026-09-24 | 状态：**生效**。通用基线适用于全部任务；场景要求由 playbook overlay 声明（ADR-068/069，R-95/R-99～R-101）。

## 六项评分

| 项 | 判据 | 通过标准 | 证据来源 |
|---|---|---|---|
| **1 口径正确** | 正式报告指标能追到 metric registry，探索草稿的 provisional 有完整定义与状态 | 正式指标为可实现的 canonical/platform-native；provisional 未混入正式报告；平台映射按 adapter contract | `plan.md` + metric refs + adapter manifest |
| **2 可复现** | 三要素齐备，且同输入重跑数字一致 | 快照 hash + 代码留档 + 模型版本齐全；重跑核心指标**零差异** | `runs/<task>/` + 重跑对比 |
| **3 无臆造** | 缺数据处按 G-21 标注，无估算填充；核因细节在证据包不在主报告 | 抽查 5 个关键数字，全部能在 SQL/代码中复算；主报告无堆砌脚注 | `sql/` + `artifacts/` + `report.md` |
| **4 任务目标达成** | 输出覆盖 `plan.acceptance_criteria`，结论与证据匹配 | manifest 声明的必需步骤与 eval overlay 全通过；不得用未声明的月报指标评估其它场景 | `plan.md` + manifest + report |
| **5 平台与能力覆盖** | 本次 `target_platforms`、核心/可选能力、逐平台 readiness 与省略章节均可追溯 | 目标平台核心能力全有；可选能力缺失有 current-run waiver 或 alignment ticket；unsupported 章节已省略而非补 0/空表 | `source_manifest.json` + capability matrix + alignment records |
| **6 候选包同一性** | Evaluator 与 C3 审阅同一份不可变候选包 | `candidate_package_hash`、`source_manifest_hash`、`plan_hash`、`evaluation_hash` 均进入 C3 指纹；评估后内容变化必须重新封包与评估 | sealed envelope + approval record |

## 阈值

- 所有适用项全通过，且报告等级门禁满足 → 方可进入 C3；C3 通过后才可正式发布。
- 可选能力被声明为 `unsupported` 且已按契约省略章节时，该能力相关项记 `not_applicable`，不算失败；不得用空表或 0 值冒充通过。
- 任一适用项不通过 → **阻断**；新错误家族才新增错误档案，普通数据等待/待业务对齐分别进入 `waiting_data` / `awaiting_alignment`。
- 「重跑一致」允许 LLM 表述差异，**不允许数字差异**。

## 报告等级判定

| 等级 | 必须满足 | 禁止 |
|---|---|---|
| `dry_run` | 可使用 draft/active Profile；清楚标出 readiness、能力缺口与待对齐项 | C3、任何 formal 发布 |
| `formal_partial` | active Profile；全部目标平台核心能力完整；仅 source readiness 尚未齐；候选包评估通过；当次 C3 通过 | 核心能力缺失、有效金额缺 FX、存在未关闭业务 alignment |
| `formal_final` | active Profile；全部目标平台核心能力和必需源均齐备；quality checks 通过；无未关闭业务 alignment；候选包评估与当次 C3 均通过 | 用迟到数据覆盖旧版；用上期/邻近月/实时 FX 兜底 |

`formal_partial` 与 `formal_final` 是报告等级，不是 `run_status`。`data_completeness` 只表示目标平台源齐备状态。三者必须独立记录。

## Playbook eval overlay

| 场景 | 附加判据 |
|---|---|
| `monthly-business-review` | Top 异动须有能力允许范围内的 M401/M402；动态目标平台总览给逐平台 readiness 与 capability matrix；仅水位未齐可 `formal_partial` |
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
| 核心能力/FX 缺失仍发布 partial | R-98 / R-100 |
| 可选能力缺失后静默补 0 或保留空章节 | R-98 |
| Evaluator 在封包前运行或 C3 审批哈希不一致 | R-101 |
| 迟到数据覆盖同报告月旧版本 | R-100 |
