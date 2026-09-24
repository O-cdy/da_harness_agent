# Playbook · 经营分析月报

> 唯一职责：定义经营分析月报的**执行步骤**。这是 harness 的**第一份场景剧本**（ADR-002 / ADR-032 / ADR-067），**不是产品重心，也不是唯一入口**。指标口径一律引用 `docs/20-domain/metrics.md`。登记见 `index.md`。
> 版本 v0.3 | 建立：2026-09-22 | 最后更新：2026-09-24 | 状态：**草案**（跨平台步骤已对齐，未实跑校准）。Shopify 细则见 ADR-019～065；跨平台/TikTok 见 ADR-068。执行以机器 manifest 为准，本文只作人读说明。

## 1. 场景目标

回答四件事：这个月卖了多少、净卖多少、达成没有、为什么变。成本/利润仍不在首阶段范围。

## 2. 指标清单（按层）

| 层 | 指标编码 | 说明 |
|---|---|---|
| 规模 | M101 / M102 / M103 / M104 / M105 / M106 | GMV、净销售额、订单、件数、AOV、ASP |
| 效率 | M105 / M106 / M210 / M207a / M207b | 客单价、件单价、转化率、退货率（金额 + 件数双轨；**不出原因维**，ADR-051） |
| ~~成本利润~~ | ~~M201–M206、M208、M209~~ | ⛔ **首期不纳入设计范围**（ADR-027 / ADR-058 / R-42）：毛利、毛利率、佣金率、广告费率、履约、仓储、净利、净利率 |
| 达成 | M301 / M302 / M303 | 目标达成率、同比、环比（分子分母同为 M102 净销售额，口径一致） |
| 异动 | M401 / M402 | 量价拆解、维度归因贡献度 |
| 客户 | M501–M507 | 新老客分层（gid 与首单月均在主表内，**不额外依赖任何其他表**） |

**首阶段平台**：Shopify platform pack 8 张 + TikTok platform pack 7 张，完整清单见 `data-sources.md` §1.2/§1.3。Playbook 只声明 capability 与 metric refs，不出现物理表名；表名只存在于 adapter。

能力差异：
- 跨平台 canonical 总览：M101–M106、M207（仅 capability 完整的平台参与，并给覆盖率）。
- Shopify：另有 M210、M301–M303、M501–M507。
- TikTok：Affiliate/LIVE 作为 platform-native 附录；不支持客户与统一流量指标时不得补 0。

## 3. 维度树

主轴（每维度独立计算、全量留档）：

```
时间（月 / 周）
  × 平台（Shopify / TikTok；平台原生指标不跨平台相加）
  × 站点（一店一码；`site=EU` 是独立店）
  × 市场（站点分组，按需；欧盟 = 泛欧经营区 EU/DE/FR/IT/ES/IE/UA；禁止与成员站点混加，G-22）
  × 店铺 SKU（金额原子粒，G-18）
       ├── NSSKU → 型号 → 品类/度数（件数；单型号金额）
       ├── 「套件未拆」（多型号金额，G-16）
       ├── NSSKU（仅无型号且唯一 NS 的金额降级，G-16 / ADR-039）
       └── 「未映射」（0 个 NS，或无有效型号且 ≥2 个 NS；后者须标注，ADR-046）
  × 新老客（仅 identity capability 可用的平台；TikTok 首阶段不支持）
```

> 以下商品层级与物理字段细则**仅属于 `platform:shopify` + 当前 profile**，不得套到 TikTok；TikTok 先经 adapter 输出相同 canonical 商品键。
>
> ⚠ **Shopify 首期不含渠道 / UTM 维度（ADR-024 / R-29）**。
> ADR-024 商品维写 NSSKU。现层级：店铺 SKU → NSSKU → 有效型号 → 品类（`产品类型`）/ 度电带（`度数范围`）；户储 = 度数范围「户储」标签（ADR-041～043）。金额：单有效型号跟型号走，多有效型号进「套件未拆」，无有效型号唯一 NS 降级到该 NS（G-16 / ADR-038～040）。件数两套分标注（ADR-045）：店铺 SKU = M104 / R-30；NSSKU = G-17（有型号时与型号维同一套）。型号维 ASP 只对单有效型号、且分母只用同一批行件数（ADR-047）。JOIN 键 = `产品型号`；型号维对外呈现 = `产品型号_统一`（ADR-048）。首期以主产品为核心。「配件」不是型号。
**Shopify 映射**：店铺 SKU → NSSKU → 有效型号 → `产品型号度数范围.产品型号` → `产品类型` / `度数范围` / `产品型号_统一`。R-50～R-69 与 R-71 中的物理字段均只在 Shopify pack 生效；跨平台报告统一读取 canonical `order_created_date / adapter_order_id / product_identity / refund_event`。C1/C2、同比、归因与月报时间窗等通用/playbook 规则仍按 R-73～R-79。

派生交叉：品类 × 站点、度数区间 × 站点、新老客 × 品类、型号 Top N（仅单有效型号金额，ADR-064）。
**互斥性要求**：归因维度必须互斥可加（R-06 / R-78）。禁止市场与成员站点混加。

## 4. 执行步骤

| 步 | 动作 | 卡点 |
|---|---|---|
| 1 | 按 manifest 的 `required_capabilities` 调用平台 adapter，生成逐源 manifest + canonical 工件 + capability/coverage | — |
| 2 | Orchestrator 生成 `plan.md`：平台/维度/metric refs/rule packs/大纲/验收标准 | **C1**：新模板/新口径必须人工审；仅完整指纹相同才自动放行 |
| 3 | 按维度生成原料 SQL，全量留档。月报 SQL 必须带报告期时间窗，允许无 LIMIT（R-79）；禁止用 LIMIT 截断规模指标 | **C2**：同上 |
| 4 | 执行派生计算（groupby / 透视 / 同比环比），自动放行并留档 | — |
| 5 | Validator 断言：对账、量纲、空值率、能力/映射覆盖率、逐平台水位。未对齐分支进 `awaiting_alignment`；无日历只标缺失 | 阻断项未关闭不得发布正式报告 |
| 6 | Reporter 渲染 `report.md` + `charts.html` | — |
| 7 | Evaluator 按 rubric 打分；重跑一致性校验 | **C3 每次人工审核** |
| 8 | 落 `runs/<task>/` 证据包：写入 `data_completeness`（partial/final）、`report_version`、`fx_snapshot_hash`、`fx_rate_month` | — |
| 9 | **版本判定**：任一必需平台水位未齐 = partial；全部到齐 = 新 final；均不覆盖旧版，不得用上期平台数据补齐 | — |

## 5. 报告结构（report.md）

1. 结论摘要（3–5 条，每条带支撑数字与指标编码）
2. 跨平台 canonical 总览（GMV / 净销售额 / 订单 / 件数 + 各平台覆盖率）
3. Shopify 平台章节（其 capability 支持的效率、达成、客户、异动）
4. TikTok 平台章节（canonical 规模/退款 + 赠品/样品诊断）
5. TikTok platform-native 附录（Affiliate / LIVE；官方口径与归因窗口）
6. 异动归因（只对 capability 完整、互斥可加的范围执行 M401/M402）
7. 数据说明（逐源 hash、水位、partial/final、口径与 adapter 版本、未映射覆盖率、G-21 P0 标注）

## 6. 已知陷阱

| 陷阱 | 规避 |
|---|---|
| 大促虹吸被误判为异常 | R-12（有日历）/ R-70（无日历只许标注，禁止写成恶化） |
| 平台口径直接相加 | R-05，先映射 |
| 用 Amazon Unit Session % 当转化率 | M210 / K-03，内部按订单口径重算 |
| 订单 / 件 / order item 混用 | R-13 / K-05 |
