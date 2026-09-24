# Skills 契约（SK-01 ~ SK-08）

> 唯一职责：定义「可复用能力单元」的输入 / 输出 / 依赖口径 / 参数来源。
> 版本 v0.3 | 最后更新 2026-09-24 | 状态：**已规划，未实现**（SK-07 记忆装配为首期薄封装；SK-08 为平台原生扩展；Session/向量不实现；错误语义由 ADR-070 校正）
> 与 playbook 的关系见 `docs/10-architecture.md` §1.1：playbook 编排 skills；**Skill 禁止依赖某一 playbook id**（ADR-067 / R-82）。

## 通用约定（所有 Skill 适用）

| 项 | 约定 |
|---|---|
| 参数来源 | 业务特定值一律从 `config/profile.yaml` 读，**禁止硬编码公司名 / 表名 / 币种**（守则 7.5）。**禁止读取「当前是否经营月报」**（R-82） |
| 口径来源 | 正式指标必须引用 MetricRegistry；provisional 必须有运行内定义与证据。禁止 Skill 直读平台物理表 |
| 数字产出 | 只能由 SQL / Python 计算；LLM 产出的数字一律无效（`10-architecture.md` §3） |
| 留档 | 每个 skill 执行完写 `runs/<task>/artifacts/<skill_id>.json` + 代码留档 |
| 失败处理 | 阻断级失败 → 中止并生成脱敏 `ErrorEnvelope`，禁止静默跳过；只有可复发的新错误家族、口径/架构缺陷或需要防回归门禁时才新增 `errors/E-NNNN` |

## SK-01 量价拆解

| 项 | 内容 |
|---|---|
| 输入 | 本期 / 基期 的 `销量` 与 `均价`（内部 canonical） |
| 输出 | 量贡献、价贡献、残差（三项之和 = 差额） |
| 依赖口径 | M401（ADR-063：量 = 店铺 SKU 件数，禁止 NS 件数）；货币已按 ADR-011 折 CNY |
| 断言 | \|量贡献 + 价贡献 + 残差 − 实际差额\| < 1e-6 |
| 参数 | `profile.yaml: volume_price` |

## SK-02 维度归因贡献度

| 项 | 内容 |
|---|---|
| 输入 | `ctx.dimensions` 声明的互斥维度 + 各切片 Δmetric；月报首阶段可用站点/品类/度电带/新老客 |
| 输出 | 各切片贡献度排序 + 覆盖率 |
| 依赖口径 | M402 / R-06 / R-78（ADR-064） |
| 断言 | 各切片贡献之和 = 总 ΔM102；套件未拆 / 未映射 / 未识别必须出桶；禁止市场与站点混加；禁止 NS 件数加权 |
| 参数 | `profile.yaml: attribution` |

## SK-03 异常检测（含大促窗口识别）

| 项 | 内容 |
|---|---|
| 输入 | 时间序列 + 大促日历 |
| 输出 | 异常点列表 + 是否落在大促窗口内（避免把虹吸误判为恶化） |
| 依赖口径 | R-12（有日历：先识别窗口再判异常）+ R-70（无日历不阻断规模） |
| 断言 | **有日历**：每个异常点必须标注 `in_promo_window: true/false`。**无日历**：输出 `calendar_missing=true`，禁止默认 `in_promo_window=false`，禁止因此整报失败；异动结论不得写成经营恶化 |
| 参数 | `profile.yaml: promo_calendar`（`enabled=false` 时走 R-70；B-06 日历仍待补） |

## SK-04 口径校验

| 项 | 内容 |
|---|---|
| 输入 | `plan.metric_refs` 对应的中间结果 + canonical 工件 + 当前 eval overlay |
| 输出 | 断言报告（对账 / 量纲 / 空值率 / 同比环比合理性） |
| 依赖口径 | 仅 `plan.metric_refs` + manifest eval overlay；G-23/G-24 |
| 断言 | 任一阻断级失败 → 不得发布正式报告且必须有 ErrorEnvelope；只有符合通用失败处理条件时归档 E-NNNN；禁止把月报 M401/M402 或 M101–M507 全集强制到其他场景 |
| 参数 | `profile.yaml: currency`（量纲阈值） |

## SK-05 报告框架

| 项 | 内容 |
|---|---|
| 输入 | `runs/` 证据包 + Artifact Envelope |
| 输出 | `report.md`（ADR-008）+ `charts.html` |
| 依赖口径 | `plan.outline`（由当前 playbook 或 `ask` 的计划提供，禁止写死经营月报六章，ADR-067）；只消费证据包，不直连数据源 |
| 断言 | 报告中每个数字可在证据包中追溯 |
| 参数 | `profile.yaml: report` |

## SK-06 输出精简

| 项 | 内容 |
|---|---|
| 输入 | 长文本 / 分片结果 |
| 输出 | 精简摘要 |
| 依赖口径 | ADR-006（轻量模型承担格式化与分片汇总） |
| 断言 | 精简不得改变数字；无 key 时走确定性截断，不 no-op |
| 参数 | `profile.yaml: report` |

## SK-07 记忆装配

SK-07 是 Orchestrator 的跨场景 pre-plan hook，不属于某个 Playbook 的 `skill_refs/steps`，避免每份 manifest 重复声明。

| 项 | 内容 |
|---|---|
| 输入 | 任务 id、完整审批指纹、可选上期 run 路径 |
| 输出 | `MemoryBundle`（口径索引、错误注入列表、上期指纹/线索；不含上期指标数值） |
| 依赖口径 | R-80 / ADR-066；G-23 |
| 断言 | 输出中不得出现可作为本期事实的上期金额/件数；Session/向量关闭时字段为显式 `noop` |
| 参数 | `profile.yaml: memory` |

## SK-08 平台原生分析

| 项 | 内容 |
|---|---|
| 输入 | adapter 暴露的 platform-native facts + 官方指标元数据 + capability |
| 输出 | 带 `platform / native_metric_id / official_source / region / definition_version` 的结果 |
| 依赖口径 | ADR-068 / R-84 / R-87；TikTok PN-TIKTOK-001～008 |
| 断言 | 不得并入 canonical 合计；官方来源、适用地区、检索日期、归因窗口与实现状态缺一即不可启用 |
| 参数 | `profile.yaml: datasource.platforms.<id>.native_modules` |
