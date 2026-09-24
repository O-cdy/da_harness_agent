# Playbook · 经营分析月报

> 唯一职责：定义经营分析月报的**执行步骤**。这是 harness 的**第一份场景剧本**（ADR-002 / ADR-032 / ADR-067），**不是产品重心，也不是唯一入口**。指标口径一律引用 `docs/20-domain/metrics.md`。登记见 `index.md`。
> 版本 v0.4 | 建立：2026-09-22 | 最后更新：2026-09-24 | 状态：**草案**（机器契约已冻结，未实跑校准）。Shopify 细则见 ADR-019～065；跨平台/TikTok 见 ADR-068；动态平台与发布契约见 ADR-069。执行以 `monthly-business-review/manifest.yaml` 为准，本文只作人读说明。

## 1. 场景目标

回答四件事：这个月卖了多少、净卖多少、达成没有、为什么变。成本/利润仍不在首阶段范围。

## 2. 指标清单（按层）

| 层 | 指标编码 | 说明 |
|---|---|---|
| 规模 | M101 / M102 / M103 / M104 / M105 / M106 | GMV、净销售额、订单、件数、AOV、ASP |
| 效率 | M105 / M106 / M210 / M207a / M207b | M105/M106/M207a 随核心总账；M210 需 traffic；M207b 需 return_quantity。缺可选能力先询问，不补 0 |
| ~~成本利润~~ | ~~M201–M206、M208、M209~~ | ⛔ **首期不纳入设计范围**（ADR-027 / ADR-058 / R-42）：毛利、毛利率、佣金率、广告费率、履约、仓储、净利、净利率 |
| 达成 | M301 / M302 / M303 | M301 需 targets；M302/M303 基于所选平台 canonical M102 |
| 异动 | M401 / M402 | M401 基于核心总账；M402 各维度按 product/identity 等 capability 条件执行 |
| 客户 | M501–M507 | 仅 customer_identity capability 可用的平台；原始主键由 adapter 映射 |

**平台选择**：Playbook 不预设平台名称或数量。每次交互 Run 必须由用户显式提供非空 `target_platforms`；定时任务在调度配置中显式声明。Shopify/TikTok 是当前已登记实现目标，未来 Amazon/eBay 等只需注册 adapter + platform pack 即可复用本 Playbook。

能力差异：
- 每个目标平台必须满足 manifest 的商业总账核心能力，否则进入 `awaiting_alignment`；无法补齐时只能经用户明确移出 `target_platforms` 并重审 C1。
- 可选能力缺失先逐项询问；用户确认本次跳过后记录 run-only waiver，在能力矩阵标 unsupported 并省略章节。
- 平台原生模块由 registry 与地区官方定义共同门控，只进对应平台附录，不参与 canonical 合计。

## 3. 维度树

主轴（每维度独立计算、全量留档）：

```
时间（月 / 周）
  × 目标平台（来自 `target_platforms`；平台原生指标不跨平台相加）
  × 经营账户（canonical `platform + account_id`）
  × 报告站点 / 市场 / 区域（Profile 映射，按 capability；禁止与成员账户混加）
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
**Shopify 映射**：店铺 SKU → NSSKU → 有效型号 → `产品型号度数范围.产品型号` → `产品类型` / `度数范围` / `产品型号_统一`。R-50～R-69 与 R-71 中的物理字段均只在 Shopify pack 生效；跨平台报告统一读取 canonical `order_created_date / order_id / product_identity / refund_event`。C1/C2、同比、归因与月报时间窗等通用/playbook 规则仍按 R-73～R-79。

派生交叉：品类 × 站点、度数区间 × 站点、新老客 × 品类、型号 Top N（仅单有效型号金额，ADR-064）。
**互斥性要求**：归因维度必须互斥可加（R-06 / R-78）。禁止市场与成员站点混加。

## 4. 执行步骤

| 步 | 动作 | 卡点 |
|---|---|---|
| 1 | 校验用户显式提交的 `target_platforms`；按核心能力调用各 adapter，生成逐源 manifest + canonical 工件 + capability/coverage | 缺核心能力进入 alignment，不得 waiver |
| 2 | Orchestrator 按 manifest + Profile **确定性物化** `plan.md`（非 LLM）：平台/维度/metric refs/rule packs/大纲/验收标准 | **C1**：平台集合或整体指纹变化重审 |
| 3 | 按分支生成原料 SQL，全量留档。时间窗声明 canonical `order_created_date`，由 adapter 映射物理字段；允许无 LIMIT | **C2**：未变化组件可按完整 step 指纹复用 |
| 4 | 执行派生计算（groupby / 透视 / 同比环比），自动放行并留档 | — |
| 5 | Validator 断言：对账、量纲、空值率、能力/映射覆盖率、逐源水位。新可选缺口逐项询问；无人值守生成 ticket | 未关闭 alignment 只能 dry-run |
| 6 | Reporter 渲染候选 `report.md` + `charts.html`；unsupported 可选章节经 run-only waiver 后省略，能力矩阵必须保留 | — |
| 7 | 封存候选证据包：报告、逐源 manifest、SQL/代码、参数/模型、断言、trace 索引；计算总 hash | 封存后内容不可变 |
| 8 | Evaluator 只读候选包，按 rubric 与 report tier 规则打分并执行重跑一致性校验 | — |
| 9 | 审核封存候选包 hash | **C3 每次人工审核** |
| 10 | 发布：水位未齐但其余正式条件满足 = formal_partial；全部目标核心源齐备 = formal_final；迟到数据出新版本，不覆盖 | alignment/draft/未认证组件只可 dry-run |

## 5. 报告结构（report.md）

1. 结论摘要（3–5 条，每条带支撑数字与指标编码）
2. 所选平台 canonical 总览（GMV / 净销售额 / 订单 / 件数 + 各平台覆盖率）
3. 按 `target_platforms` 生成的平台章节（只包含已满足或经确认跳过后的 capability）
4. platform-native 附录（仅地区官方定义与字段均认证的模块）
5. 异动归因（只对 capability 完整、互斥可加的范围执行 M401/M402）
6. 数据说明（目标平台、逐源 hash/截止点/延迟窗口/水位、报告等级、waiver、adapter 认证与未映射覆盖率）

## 6. 已知陷阱

| 陷阱 | 规避 |
|---|---|
| 大促虹吸被误判为异常 | R-12（有日历）/ R-70（无日历只许标注，禁止写成恶化） |
| 平台口径直接相加 | R-05，先映射 |
| 用 Amazon Unit Session % 当转化率 | M210 / K-03，内部按订单口径重算 |
| 订单 / 件 / order item 混用 | R-13 / K-05 |
