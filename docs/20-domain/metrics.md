# 20 · 指标字典：内部口径（唯一定义处）

> 唯一职责：定义内部指标口径。**本文件是内部指标口径的唯一来源**，任何模块、报告、脚本引用指标时必须指向本文件的条目编码。
> 结构：**A canonical** → **B platform-native 官方口径** → **C 平台映射** → **D 待确认清单**
> 版本 v0.4 | 建立：2026-09-22 | 最后更新：2026-09-24 | 状态：**部分生效** —— 已确认且 adapter capability 完整的条目可作硬约束；TikTok 官方口径与映射见 ADR-068。

## 指标类型与状态（ADR-068）

| 类型 | 编码约定 | 用途 | 正式报告 |
|---|---|---|---|
| `canonical` | `Mxxx` | 跨平台统一分析 | 已确认且 capability 完整时可用 |
| `platform-native` | `PN-<PLATFORM>-xxx` | 保留平台官方定义 | 只进对应平台章节/附录，不跨平台相加 |
| `provisional` | `PX-<run>-xxx` | `ask` 临时探索 | 只进探索草稿；须留定义、SQL/代码、快照 |
| `diagnostic` | `DQ-xxx` | 数据质量、覆盖率、对账 | 只进数据说明/证据包 |

---

## 0. 通用约定（贯穿全部指标）

| 编号 | 约定项 | 内部规则 | 状态 |
|---|---|---|---|
| G-01 | 记账本位币 | **CNY（人民币）**。所有报告默认折算到 CNY | 已确认（ADR-011） |
| G-02 | 汇率 | **用户提供的月度固定汇率**，来源二选一：① MySQL `shared_data.exchange_rate` 表（优先）；② 用户 Excel 提供（与表同构）。**N+1 规则**：M 月报告用 M+1 月汇率；若 M+1 月未结束、库中无该月汇率，**回退用 M 月当月汇率**。所用的汇率月份与数值必须写入证据包 | 已确认（ADR-011） |
| G-03 | 收入确认时点 | **按 canonical 下单事件**；退款/取消在**发生月**处理，不回溯调整原月。Shopify adapter 映射 `sale_date`，TikTok adapter 映射 `created_time`；平台官方支付/发货时点指标留在 platform-native | 已确认（ADR-010 + ADR-068） |
| G-04 | 时区 | **首期统一 UTC**。canonical 日/月切分认 adapter 输出的 `order_created_date`；Shopify 来源 `sale_date`，TikTok 来源 `created_time`。禁止按站点本地时区重切 | 已确认（ADR-055 + ADR-068） |
| G-05 | 财月日历 | **首期自然月**。禁止 4-5-4。改财月须另立 ADR | 已确认（ADR-055） |
| G-06 | 跨口径相加 | **禁止。** 不同平台/不同口径的指标不得直接相加，必须先按 C 节映射到内部口径 | 已定（ADR-009 / R-05；非报告指标） |
| G-07 | 缺数处理 | 无数据或口径未定义的指标，输出「无数据 / 口径待确认」，**禁止估算填充** | 已定（ADR-009 / R-03；非报告指标） |
| G-08 | 报告版本不可变 | **已生成的报告版本永不修改**（退款/取消在发生月冲减即可实现）。这是「重跑一致、可复现」的硬前提。注意区分：**重跑**（同输入再跑一次）必须一致；**重生成**（数据窗口变完整、汇率规则变化）产出的是**新版本**，不是修改旧版本 —— 见 G-12 | 已确认（ADR-010，边界由 ADR-013 修订） |
| G-09 | 取消与退款的区别 | **取消**：订单作废，不计入订单数/件数/GMV，取消事件字段由 adapter 映射（Shopify=`cancelled_at`；TikTok=取消事件/`cancelled_time`）。**退款**：订单保留在原下单月，退款金额在发生月冲减净销售额，不改变原下单月订单数与 GMV | 已确认（ADR-010 + ADR-052 + ADR-068） |
| G-10 | 原币双留档 | 任何折算金额必须同时留档四元组：`amount_original` + `currency` + `fx_rate` + `amount_base`（另记 `fx_rate_month`，即实际采用 N+1 还是当月）。否则无法对账 | 已确认（ADR-011） |
| G-11 | 本位币例外 | 用户特别要求、且报告**不涉及多市场多币种**时，可改用本位币（原币）出报告；此时报告必须标注「未折算，原币口径」 | 已确认（ADR-011） |
| G-13 | 与现有报表的差异 | 内部口径（M102）**不等于**公司现有 tableau 报表口径 —— tableau 用主表 `net_sales`（已回溯扣退款）。两者差额 = 跨月退款的时间归属差异。报告须在「数据说明」章节给出差额对账，不得直接混用 | 已确认（ADR-019） |
| G-12 | 月报版本与数据完整度 | 月内生成的是 **partial 版**（数据不完整，汇率走回退），次月生成的是 **final 版**（完整数据 + N+1 汇率）。两者是**两个版本并存**，final 不覆盖 partial。每次生成都必须按**当时的**正确汇率规则取值，不得因"上次用了 9 月汇率"就在 10 月沿用。报告须显式标注 `data_completeness` 与 `fx_rate_month` | 已确认（ADR-013） |
| G-16 | 金额类商品上卷键 | **有效型号** = `TRIM(型号)` 非空且不等于「配件」（ADR-040）。**单有效型号**跟该型号走。**多有效型号**进「套件未拆」。**无有效型号且恰好 1 个 NS** 降级到该 NS。**无有效型号且 0 个 NS，或 ≥2 个 NS** 进「未映射」（≥2 须按需标注，ADR-046）。件数按 G-17。站点合计仍 G-18。禁止用前缀替代型号列。**型号维报告按 `产品型号_统一` 呈现**（ADR-048），金额仍先落到有效型号 | 已确认（ADR-038～048） |
| G-17 | 件数 / 路径原子维 | **件数与路径拆到 NSSKU**。NS 件数 = `quantity × COALESCE(NULLIF(成员数量,0), 1)`（ADR-044）。有有效型号时上卷到型号，与型号维件数同一套（ADR-045）；「配件」不上卷。NSSKU 维默认禁止出金额；例外见 G-16。**金额禁止 ×成员数量**。M104 ≠ Σ NS 件数；报告两套分标注 | 已确认（ADR-033 / ADR-044 / ADR-045） |
| G-18 | 金额原子粒 | **金额留在事实表 `sku`（店铺 SKU）行，不拆到 NSSKU**（用户原话 + ADR-034）。套件订单上成员不成行；成员货品也可以作为独立店铺 SKU 成交，那一行仍按本条计金额 | 已确认（ADR-034；边界收窄 ADR-036） |
| G-19 | 商品维层级 | **店铺 SKU（`名称`）→ NSSKU（`成员货品`）→ 型号**。型号只从 NSSKU 行读，禁止与店铺 SKU 同级（用户原话 + ADR-035）。有值 NS→型号为一对一。映射可缺成员、缺型号（见 data-sources）。品类/度数见 G-20 | 已确认（ADR-035；空值边界 ADR-036） |
| G-20 | 品类 / 度数挂载 | **品类列 = `产品类型`**（ADR-041）。**度电带列 = `度数范围` 整列**（ADR-042）。**户储 = `度数范围` 精确等于「户储」的型号标签/筛选，不另开列**（ADR-043）。**JOIN 键 = `产品型号`；型号维对外呈现主键 = `产品型号_统一`**（ADR-048）。统一列不当成品类、不当 JOIN 键。路径 = 店铺 SKU → NSSKU → 有效型号 → `产品型号` → 产品类型 / 度数范围 / 产品型号_统一。禁止 NSSKU.`型号` 直接 JOIN 统一列。禁止与店铺 SKU 同级出金额。金额只承接已进入有效型号的部分；「套件未拆」、「未映射」、无型号降级 NS、型号「配件」都不进具体品类/度电带 | 已确认（ADR-037～048） |
| G-21 | 报告标注分层 | 主报告标注须分优先级，数量合理，禁止堆砌。**P0**（改变数字解读，触发才出）：未匹配退款不冲 M102、套件未拆/未映射金额桶、与 tableau 差额（G-13）、**无日历时异动章 `calendar_missing`（ADR-054）**、**新站不参与同比（ADR-059）**。同类全篇只出现一次，放「数据说明」；图表最多脚注编号。核因细节进 `runs/` 证据包。不设死条数上限 | 已确认（ADR-050 + ADR-054 + ADR-059） |
| G-22 | 站点与市场两粒 | **站点** = `site` 一店一码；**市场** = 站点分组，按需展示。`site=EU` 不是欧盟市场。**「欧盟」= 泛欧经营区**（ADR-061），已确认成员 = EU/DE/FR/IT/ES/IE/**UA**，名单只在 profile。UK 不进该组。禁止站点与其所属市场混加。一个站点只属一个市场。未分组进「未分组」。市场达成由成员站点加总，不用空站点的市场目标行。市场同比走同店（ADR-059） | 已确认（ADR-060 + ADR-061） |
| G-23 | 口径可追溯 | 每条「已确认」G/M/R 必须能追到 ADR + 本文件条目。profile 参数必须有 `source`。报告数字必须能追到指标编码 + SQL/代码 + 快照 hash。状态「已定」不得进报告 | 已确认（ADR-062） |
| G-24 | 平台映射与能力 | canonical 指标只消费 adapter 输出；平台字段、状态、时点与能力在 C 节和 adapter manifest 映射。能力缺失或映射未确认时，该平台分支进入 `awaiting_alignment`，不得把空值当 0 | 已确认（ADR-068） |
| G-25 | 多平台完整度 | 每个平台独立记录水位、hash 与 completeness。必需平台未齐只出带覆盖率的 partial；齐备后出新 final；禁止沿用上期数据补齐 | 已确认（ADR-068） |

---

## A. 内部标准口径（canonical）

状态列：`已定` = 结构确定；`待确认` = 需业务校正具体口径。

### A1 规模类

| 编码 | 指标 | 定义 | 公式 | 单位 | 状态 |
|---|---|---|---|---|---|
| M101 | GMV 成交总额 | 按 canonical 下单时点统计的**商业商品原价额** | `SUM(item_gross_amount)`；不扣折扣/退款，不含税与运费；剔除取消、样品及非商业赠送。平台字段映射见 C 节 | 本位币 | 已确认（ADR-012 + ADR-019 + ADR-052/053 + ADR-068） |
| M102 | 净销售额 Net Revenue | 商业商品成交净额，退款按事件发生月冲减 | `SUM(item_gross_amount + seller_discount_amount) - SUM(refund_item_subtotal)`；取消、样品、非商业赠送剔除；税与运费不进入。Shopify 财务差额与 TikTok 退款映射见 C 节 | 本位币 | 已确认（ADR-010/019/022/023/050/052/053 + ADR-068） |
| M103 | 订单数 Orders | 有效商业订单数；取消与样品单剔除，退款单保留原下单月 | `COUNT(DISTINCT platform + shop_id + order_id)`；平台原始订单键由 adapter 映射 | 单 | 已确认（ADR-010 + ADR-049 + ADR-068） |
| ~~M102b~~ | ~~净销售额（毛口径临时方案）~~ | ⛔ **已作废**（ADR-028 关闭 B-13，退款两表已补入首期白名单） | ~~Σ(`gross_sales` + `discounts`)，不冲减退款~~ —— 曾因退款表被排除而设；**M102 恢复 ADR-019 / ADR-023 定案口径**，本条目仅作留痕，不得实现 | 本位币 | **作废**（ADR-028） |
| M104 | 件数 Units | 商业售出件数，按下单时点；取消/样品/赠品剔除，退货件数在退货发生月冲减 | canonical `SUM(commercial_quantity)`；当前 profile 的 NSSKU/型号展开仍遵守 G-17 与两套件数分标注。平台过滤见 C 节 | 件 | 已确认（ADR-010 + ADR-045 + ADR-052/053 + ADR-068） |
| M105 | 客单价 AOV | 平均每单金额 | 净销售额 / 订单数（M102 / M103） | 本位币 | 已确认（ADR-062，派生） |
| M106 | 件单价 ASP | 平均每件金额 | **站点 / 店铺 SKU** = 净销售额 / M104（店铺 SKU 件数）。**型号维**仅对金额已进入该有效型号的店铺 SKU（G-16 单有效型号）计算：分子 = 这些行的净销售额；分母 = 同一批行的 G-17 件数。禁止用该型号全部件数（含套件成员件数）作分母。报告型号维按 `产品型号_统一` 合并展示（ADR-048），同家族下上述行加总，仍遵守本条。套件未拆、未映射、配件降级 NS 不出型号 ASP。NSSKU 维默认禁止 ASP（G-18）；本条不开配件 NS 维 ASP（ADR-047） | 本位币 | 已确认（站点 ADR-010；型号维 ADR-047 / ADR-048） |

### A2 效率类

| 编码 | 指标 | 定义 | 公式 | 状态 |
|---|---|---|---|---|
| ~~M201~~ | ~~毛利 Gross Profit~~ | ⛔ **首期不纳入设计范围**（ADR-027 / R-42） | ~~净销售额 − COGS~~；COGS 口径仍登记于 ADR-012，**仅作留档，首期不实现** | **不纳入**（敏感指标 + 无数据源） |
| ~~M202~~ | ~~毛利率~~ | ⛔ **首期不纳入设计范围**（ADR-027 / R-42） | ~~毛利 / 净销售额~~ | **不纳入**（依赖 M201） |
| ~~M203~~ | ~~平台佣金率~~ | ⛔ **首期不纳入设计范围**（ADR-027 / R-42） | ~~佣金 / 净销售额~~ | **不纳入** |
| ~~M204~~ | ~~广告费率 / ACoS / TACoS~~ | ⛔ **首期不纳入设计范围**（ADR-027 / R-42；用户另确认广告部分暂不实现） | ~~广告花费 / 对应销售额~~ | **不纳入** |
| ~~M205~~ | ~~履约费率~~ | ⛔ **首期不纳入设计范围**（ADR-027 / R-42） | ~~履约费 / 净销售额~~ | **不纳入** |
| ~~M206~~ | ~~仓储费率~~ | ⛔ **首期不纳入设计范围**（ADR-027 / R-42） | ~~仓储费 / 净销售额~~ | **不纳入** |
| ~~M208~~ | ~~净利~~ | ⛔ **首期不纳入设计范围**（ADR-058 / R-42） | ~~毛利 − 全部费用（佣金+广告+履约+仓储+关税+其他；关税已在 COGS，此处不重复）~~；公式仍登记于 ADR-012，**仅作留档** | **不纳入**（依赖 M201 与费用，无数据源） |
| ~~M209~~ | ~~净利率~~ | ⛔ **首期不纳入设计范围**（ADR-058 / R-42） | ~~净利 / 净销售额~~ | **不纳入**（依赖 M208） |
| M207a | 退货率（金额口径） | canonical 商品退款金额占比 | `refund_item_subtotal / M102`；Shopify 映射 `refunds_lineitems.refund_subtotal`，TikTok 映射 `tiktok_returns.refund_subtotal`。未匹配退款不进分子并单列诊断；不出原因维 | 已确认（ADR-014/023/028/050/051 + ADR-068） |
| M207b | 退货率（件数口径） | canonical 退货件数占比 | `refund_quantity / M104`；Shopify 映射 `refunds_lineitems.refund_quantity`。TikTok 当前 `return_items` **无数量字段**，首阶段 capability=unsupported，禁止用行数代替件数 | 已确认（ADR-014/028/050/051 + ADR-068） |
| M210 | 转化率（订单口径） | **内部统一按订单算**，不按件算；Amazon `Unit Session Percentage` 仅作平台原生指标展示，**不参与跨品牌对比**。⚠ 数据源 = GA4 视图 `month_basic_data`，**必须同源** | **主口径 = `transactions / sessions`**（GA4 同源，2026-08 US 0.364%）；辅助 = `checkouts / sessions`（2.285%）；对账项 = GA4 `transactions` / Shopify 订单数（US 36.6%，合计 52.4%）。**禁止跨源配比**（R-37 / ADR-025）。覆盖 2025-06-09 起 | 已确认（ADR-014 + ADR-025，K-03/K-04） |

> ⛔ **「首期不纳入设计范围」≠「暂不输出」**：M201–M206、M208、M209 在首期**不定义、不建模、不留空占位、不在报告中留标题**（R-42 / ADR-058）。
> 保留条目仅为留档与后续可追溯，删除线表示首期不可用。

### A5 客户分层类（新增，适用受限）

> **适用范围硬限制**：仅适用于**独立站 / 自有渠道**（Shopify 等能拿到顾客身份的渠道）。
> **Amazon Business Reports 不提供新老客维度**（平台不向卖家披露买家身份），因此该类指标**不可跨 Amazon 计算**，也**不可与 Amazon 数据合并**出全渠道新老客指标。

| 编码 | 指标 | 定义 | 公式 | 状态 |
|---|---|---|---|---|
| M501 | 下单顾客数 Customers | 期内下过单的去重已识别顾客数；身份只在平台/店铺命名空间内有效 | `COUNT(DISTINCT customer_subject_hash)`；Shopify 映射 gid，TikTok 首阶段 capability=unsupported | 已确认（ADR-017 + ADR-062 + ADR-068） |
| M502 | 新客数 New Customers | 期内**首次**下单的已识别顾客 | 该 `customer_subject_hash` 的 `MIN(order_created_date)` 落在报告期。Shopify 禁用注册时间 `customer_created_at`；TikTok 首阶段 identity capability=unsupported | 已确认（ADR-017 + R-39 + ADR-062 + ADR-068） |
| M503 | 老客数 Returning Customers | 期内下单且此前已有历史订单的已识别顾客 | 同一平台/店铺命名空间内首单日 < 报告期且期内有下单。Shopify 实测闭合；TikTok 首阶段不计算 | 已确认（ADR-017 + R-39 + ADR-062 + ADR-068） |
| M504 | 回头客率 | 老客占已识别顾客比例 | 老客数 / 下单顾客数；仅 identity capability 可用的平台计算（Shopify 2026-08 实测 28.6%） | 已确认（ADR-017 + ADR-062 + ADR-068） |
| M505 | 新/老客销售额 | 分别统计新客与老客贡献的净销售额 | 按 `customer_subject_hash` 分组；须先按币种折算。仅 identity capability 可用的平台参与 | 已确认（ADR-017 + ADR-062 + ADR-068） |
| M506 | 新/老客客单价 | 分别统计 AOV，用于对比客层质量 | 对应客层净销售额 / 对应 canonical 订单数；须折算，且仅 identity capability 可用的平台计算 | 已确认（ADR-017 + ADR-062 + ADR-068） |
| **M507** | **顾客可识别率（数据质量）** | 能生成 `customer_subject_hash` 的订单占比；低于阈值时客户结论不可信 | canonical 判定 subject hash 非空。Shopify adapter 原始主键=`shopify_customer_gid`，实测 99.83%；TikTok 首阶段 unsupported | 已确认（ADR-017 + R-35 + ADR-062 + ADR-068） |

**主键规则（ADR-062 / ADR-068）**：canonical 只存“平台 + 店铺命名空间 + 不可逆 subject hash”。Shopify adapter 输入为 `shopify_customer_gid`；禁止用 email/手机号自动跨平台合并。TikTok 首阶段不声明 identity capability。
**统计范围（R-40）**：客户指标默认**站点内统计** —— gid 按站点唯一（实测 2,229,529 个 gid 均只属 1 个站点），跨站点不共享；9.2% 的邮箱跨多站点，全局客户数须按 `email` 归并并显式标注，不得与站点内口径混用。
**游客单处理（关键）**：`shopify_customer_gid` 为空的订单**单独归为「未识别」客群，禁止计入新客**（R-18 / ADR-062）—— 否则老客用游客身份复购会被算成新客，系统性高估新客、低估回头客率。未识别订单的金额仍计入总销售额，只是在客户分层中单列。
**报告要求**：新老客章节必须同时给出 M507 可识别率；低于阈值时须标注「样本存在偏差，结论仅供参考」。

### A3 达成类

| 编码 | 指标 | 公式 | 状态 |
|---|---|---|---|
| M301 | 目标达成率 | 实际值(CNY 元) / (目标值 × 10000)；分子分母均为 M102。当前目标 capability 仅 Shopify profile 可用；TikTok 无目标时不得补 0。Shopify 退款两表已在其 platform pack，口径一致 | 已确认（ADR-016 + ADR-020 + ADR-028 + ADR-068） |
| M302 | 同比 YoY | (本期 − 去年同期) / 去年同期。**仅够龄站**：完整月数 ≥ 12（锚点月 = 该站 `MIN(sale_date)` 所在 UTC 月，月差相对报告期）。不够龄不出 YoY。合计同比 = 同店（只含够龄站）；新站当期进规模、不进同比分子分母。禁止分母填 0。名单由数据算，禁止写死站点码（ADR-059） | 已确认（ADR-059） |
| M303 | 环比 MoM | (本期 − 上期) / 上期。新站可出；上期为空则不出，禁止填 0。停运仍按 R-32 排除同比与环比 | 已确认（ADR-059 收窄新站） |

### A4 异动类

| 编码 | 指标 | 公式 | 状态 |
|---|---|---|---|
| M401 | 量价拆解 | 解释 ΔM102。量 = 店铺 SKU 件数（M104 ①）；价 = 站点 ASP（M102 / M104 ①）。量贡献 = (本期件数 − 上期件数) × 上期 ASP；价贡献 = (本期 ASP − 上期 ASP) × 本期件数；残差 = ΔM102 − 量 − 价。三项之和必须等于 ΔM102。禁止用 G-17 NS/型号件数作本条的量（ADR-063） | 已确认（ADR-063） |
| M402 | 维度归因贡献度 | 解释 ΔM102。每次一层、层内互斥可加。首期维度：站点、品类、度电带、新老客。切片贡献 = 该取值的 ΔM102；层内之和必须等于整体。套件未拆 / 未映射 / 未识别必须出桶。市场不得与成员站点混加。型号只对单有效型号金额。禁止用 NS 件数当金额权重（ADR-064 / R-06） | 已确认（ADR-064） |

---

## B. 平台官方口径（溯源用，非内部口径）

> 本节记录**平台自己怎么算**，用于溯源与对账。**不得直接拿本节数字当内部指标用**，映射见 C 节。
> 证据：以下条目检索于 2026-09-22，来源为平台官方帮助文档。

### B1 Shopify Analytics

来源：Shopify 帮助中心《Analytics 數據點（欄位）參考》
`https://help.shopify.com/zh-TW/manual/reports-and-analytics/shopify-reports/report-types/analytics-fields`

| 平台指标 | 官方定义 / 公式 |
|---|---|
| Gross Sales | 原价 × 数量，**税前、运费前、折扣前、退货前** |
| Discounts | 折扣金额（行项折扣 + 订单级折扣分摊） |
| Returns | 退货金额（**不含运费退款**） |
| Net Sales | Gross Sales − Discounts − Returns |
| Total Sales | Net Sales + 额外费用 + 关税 + 运费 + 税额 |
| Orders | 订单数；**退货会建立订单记录**，需用「订单状态」筛选排除已退货订单 |
| AOV 平均订单价值 | (销售总额 − 折扣) / 订单数，**不含订单成立后的调整项目** |
| Gross Profit | 销货净额 − 销货成本（须先在 Shopify 设置 Cost per item） |
| Gross Margin % | 毛利 / 销货净额 |
| Gross / Net / Refunded Quantity | 售出件数 / 扣减后件数 / 退款件数 |
| Sessions | 网络商店访问数 |

### B2 Amazon Seller Central Business Reports

来源：Amazon Seller Central《By date, by ASIN and other Business reports》（G202142060）
`https://sellercentral.amazon.ca/help/hub/reference/external/G202142060`
以及《Business Reports glossary》
`https://sellercentral.amazon.com.br/gp/help/external/help.html?itemID=27691`

| 平台指标 | 官方定义 / 公式 |
|---|---|
| Ordered Product Sales (OPS) | Σ(ItemPrice × UnitsOrdered)；**按下单时点，非发货时点；未扣退货** |
| Shipped Product Sales | 已确认发货的 Σ(ItemPrice × UnitsOrdered) |
| Units Ordered | Σ(Ordered Units)；**未扣退货** |
| Total Order Items | Σ(Order Items)；一个订单可含多个 order items，每个 item 可含多个 units |
| Sessions | 24 小时窗口内的 distinct session count（期间内多次浏览计为 1 次） |
| Unit Session Percentage | Units Ordered / Sessions × 100%，**按件算，可大于 100%** |
| Order Item Session Percentage | Total Order Items / Sessions |
| Average Selling Price | Ordered Product Sales / Units Ordered |
| Buy Box Percentage | 页面浏览量中展示你的 offer 的占比（**对 page views，不是对竞品胜率**） |
| Session Percentage | 该 ASIN 有浏览的 sessions / 全部产品总 sessions；**是目录内部占比，不是竞争指标** |

### B3 TikTok Shop（platform-native）

> 官方来源检索于 **2026-09-24**；以下页面标注适用于美国站。其它地区启用前必须核对应地区版本与生效日期。

| 编码 | 官方指标 / 规则 | 官方定义摘要 | 实现状态与来源 |
|---|---|---|---|
| PN-TIKTOK-001 | GMV | 按**支付时间**；商品标价×件数 + 运费 − seller-funded discount − platform-funded discount − tax；**包含取消与退款订单** | 可从订单表映射；仅平台原生。[Shop analytics](https://seller-us.tiktok.com/university/essay?knowledge_id=813364865828654) |
| PN-TIKTOK-002 | AOV | GMV / orders | 可实现；分子分母均遵守 TikTok 原生 GMV。[同上](https://seller-us.tiktok.com/university/essay?knowledge_id=813364865828654) |
| PN-TIKTOK-003 | LIVE GMV | LIVE 商品带来的支付订单金额，含取消与退款；按支付时间 | `tiktok_live_performance` 字段可用，归因定义核验后启用。[同上](https://seller-us.tiktok.com/university/essay?knowledge_id=813364865828654) |
| PN-TIKTOK-004 | Affiliate LIVE/Video GMV | 创作者内容商品链接点击后 **14 天**内归因的支付订单，含退货退款 | `tiktok_affiliate_orders` 可用；只进原生模块。[同上](https://seller-us.tiktok.com/university/essay?knowledge_id=813364865828654) |
| PN-TIKTOK-005 | Direct / Indirect attributed GMV | Direct=内容交互中直接购买；Indirect=内容影响后延迟购买；升级后按 Affiliate/Seller + 内容类型拆解，间接归因使用 last-touch | 已登记，启用前核表字段能否区分。[Sales Metrics Breakdown Logic Upgrade](https://seller-us.tiktok.com/university/essay?knowledge_id=6494954580231950) |
| PN-TIKTOK-006 | LIVE CTOR | SKU orders / product clicks × 100% | 表字段可用；按 LIVE 粒度。[LIVE Traffic Playbook](https://seller-us.tiktok.com/university/essay?knowledge_id=3175988075644686) |
| PN-TIKTOK-007 | Free / Refundable Sample | Free sample 对创作者免费；Refundable sample 先购买，达到销量条件后退款；Sample ROI 的分母随类型不同 | 只作样品原生分析，均不进 canonical 商业销售。[Sample Analytics](https://seller-us.tiktok.com/university/essay?knowledge_id=8670842792888078) |
| PN-TIKTOK-008 | Settlement Net Sales | Gross sales + gross sales refund + seller discount + seller discount refund；退款销售额为负数 | 已登记未启用，首阶段 M102 使用 return event 表。[Settlement Report](https://seller-us.tiktok.com/university/essay?knowledge_id=2336057241700098) |

### B4 第三方 / 其他平台

`[待补充]` —— Amazon 以外的平台接入前按同样格式登记，并附官方链接、适用地区、检索日期、版本/生效日期与实现状态。

---

## C. 平台 → 内部映射

| 内部指标 | Shopify adapter | TikTok adapter（ADR-068） | Amazon 来源 | 转换要点 |
|---|---|---|---|---|
| M101 GMV | `gross_sales`；取消按 `cancelled_at` 剔除 | `sku_subtotal_before_discount`；时点=`created_time`；取消/样品/赠品剔除 | OPS | TikTok 官方 GMV 是 PN-TIKTOK-001，不等于 M101 |
| M102 净销售额 | `gross_sales + discounts`，退款=`refunds_lineitems + adjustments` | `sku_subtotal_after_discount`，按 `tiktok_returns.event_date` 冲 `refund_subtotal`；取消退款不二次冲 | OPS − 退款报告 | 商品净额不含运费/税；退款必须按事件月 |
| M103 订单数 | `order_name` | `order_id`；取消/样品剔除 | 需订单报告 | canonical 主键含 platform+shop，禁止跨店碰撞 |
| M104 件数 | R-30 店铺 SKU 口径；退款件数另供 M207b | 销售取 `quantity`，取消/样品/赠品剔除；`return_items` 无数量字段，不支持 TikTok M207b | Units Ordered | 平台原生 items sold 或退货行数不得替代 canonical 件数 |
| M105 AOV | M102/M103 | M102/M103；PN-TIKTOK-002 另存 | 无直接字段 | 原生 AOV 与 canonical AOV 分开 |
| M210 转化率 | GA4 `transactions/sessions` | 当前无统一 traffic capability；TikTok LIVE CTOR 仅 PN-TIKTOK-006 | Unit Session % 按件 | 不同分子/分母不得比较 |

### C1 五大口径冲突（必须显式处理）

| 编号 | 冲突 | 处理规则 |
|---|---|---|
| K-01 | **时点差异**：Amazon OPS 按下单、Shipped 按发货；Shopify Net Sales 已扣退货 | 内部统一按下单时点确认，退款在发生月冲减（G-03） |
| K-02 | **是否含税/运费**：Shopify Total Sales 含税+关税+运费，Net Sales 不含 | 内部规模类指标一律用商品净额，税与运费单列 |
| K-03 | **转化率分子**：Amazon 按件、Shopify 按订单 | 内部统一按订单（M210）；需件口径时单独标注 |
| K-04 | **Session 定义不同**：Amazon 24h 窗口去重，Shopify 为访问数 | 跨品牌 Session **不可直接加总**，只能分品牌看 |
| K-05 | **订单 / 件 / order item 三层混用** | 任何报表必须声明所用层级，禁止混用 |

---

## D. 已关闭口径清单（保留修订链路）

| 编号 | 待确认项 | 影响指标 |
|---|---|---|
| ~~D-01~~ | ~~记账本位币与汇率规则~~ **已确认 2026-09-22**：本位币 CNY；用户月度固定汇率（DB `exchange_rate` 表优先 / Excel 同构）；N+1 回退当月；原币双留档（G-10）；本位币例外（G-11） | 全部金额类（ADR-011） |
| ~~D-02~~ | ~~收入确认时点~~ **已确认 2026-09-22**：按下单时点，退款/取消在发生月冲减 | M101–M106（ADR-010） |
| ~~D-03~~ | ~~退款订单是否剔除~~ **已确认 2026-09-22**：取消单剔除；退款单保留在原下单月，金额在发生月冲减 | M103（ADR-010） |
| ~~D-09~~ | ~~GMV 是否含运费~~ **已确认 2026-09-22**：不含运费（商品口径），与 Shopify Gross Sales / Amazon OPS 对齐 | M101（ADR-012） |
| ~~D-04~~ | ~~COGS 边界~~ **已确认 2026-09-22**：到岸成本法 = 采购成本 + 头程物流 + 关税；FBA 配送/尾程/仓储归费用项 | M201、M202（ADR-012） |
| ~~D-05~~ | ~~退货率口径~~ **已确认 2026-09-22**：双轨并列 M207a（金额）+ M207b（件数） | M207a/M207b（ADR-014） |
| ~~D-06~~ | ~~转化率口径~~ **已确认 2026-09-22**：统一按订单口径 | M210（ADR-014） |
| ~~D-10~~ | ~~客户唯一标识口径~~ **已被 ADR-062/068 修订**：Shopify 原始主键为 gid；canonical 为平台/店铺命名空间内 subject hash；游客单单列未识别 | M501–M507 |
| ~~D-07~~ | ~~目标值来源与口径~~ **已被 ADR-020 修订**：目标表维度为年月 × 站点（无品类），口径=M102，快照 hash 入 manifest | M301 |
| ~~D-08~~ | ~~各平台实际接入清单与字段可用性~~ **ADR-068 修订 2026-09-24**：首阶段 Shopify + TikTok；均先过 adapter → canonical。字段见 `data-sources.md` §5.3/§5.4（原 ADR-015 仅 Shopify） | 范围 |
| ~~D-11~~ | ~~组合品成交额是否拆到 NSSKU~~ **已确认 2026-09-23**：金额留在店铺 SKU 不拆；只有件数/路径拆到 NS（G-17 / G-18） | M101 / M102 / M104 / M106（ADR-034） |
| ~~D-12~~ | ~~多型号套件金额如何进入型号维~~ **已确认 2026-09-23**：单型号跟该型号走；多型号进「套件未拆」；件数按各 NS 型号记（ADR-038） | M101 / M102 / M106 |
| ~~D-13~~ | ~~品类取哪一列~~ **已确认 2026-09-23**：品类 = `产品类型`；`产品型号_统一` 只作家族标签（ADR-041） | 品类维 |
| ~~D-17~~ | ~~度电带取哪一列~~ **已确认 2026-09-23**：`度数范围` 整列上卷（ADR-042） | 度数维 |
| ~~D-18~~ | ~~户储取哪一列 / 如何定义~~ **已确认 2026-09-23**：`度数范围`='户储' 的型号标签，不另开列（ADR-043） | 户储标签 |
| ~~D-14~~ | ~~无型号店铺 SKU 的金额进哪~~ **已确认 2026-09-23**：唯一 NS 降级到该 NS；0 个 NS 进未映射；不并进套件未拆（ADR-039） | M101 / M102 |
| ~~D-15~~ | ~~型号占位值「配件」是否视同未维护~~ **已确认 2026-09-23**：视同无有效型号，不进型号维/品类（ADR-040） | M101 / M102 |
| ~~D-16~~ | ~~无型号且 ≥2 个 NS 的金额桶名~~ **已确认 2026-09-23**：进「未映射」，报告按需标注（ADR-046） | M101 / M102 |
| ~~D-19~~ | ~~NS 件数是否 ×成员数量~~ **已确认 2026-09-23**：`quantity × 成员数量`，空或 0 当 1（ADR-044） | M104 / G-17 |
| ~~D-20~~ | ~~站点 M104 是否等于 Σ NS 件数~~ **已确认 2026-09-23**：不等于；两套分标注；NSSKU 有型号时与型号维同一套（ADR-045） | M104 / G-17 |
| ~~D-21~~ | ~~型号维是否出 ASP~~ **已确认 2026-09-23**：只对金额已进入该型号的单有效型号计算；套件未拆 / 未映射 / 配件降级 NS 不出型号 ASP；站点 ASP 用 M102 / M104（ADR-047） | M106 |
| ~~D-22~~ | ~~型号维对外主键用 `产品型号` 还是 `产品型号_统一`~~ **已确认 2026-09-23**：JOIN 用 `产品型号`；对外呈现用 `产品型号_统一`（ADR-048） | 型号维 |
| ~~D-23~~ | ~~M103 原始订单键~~ **ADR-068 收窄**：Shopify adapter=`order_name`（ADR-049）；TikTok adapter=`order_id`；canonical=`platform + shop_id + adapter_order_id` | M103 |
| ~~D-24~~ | ~~退款如何关联销售表；未匹配是否冲 M102~~ **已确认 2026-09-23**：连接键 `shop_name`+`name`↔`order_name`；未匹配不冲 M102 / 不进 M207；不把补拉当闭环；标注服从 G-21（ADR-050） | M102 / M207 |
| ~~D-25~~ | ~~`financialStatus` 是否等于退款原因~~ **已确认 2026-09-23**：不当退款原因；首期退货只出 M207a/b，不出原因维（ADR-051） | M207 |
| ~~D-26~~ | ~~Shopify 是否按 `payment_status` 过滤~~ **已确认 2026-09-23**：Shopify 不按支付状态过滤，取消认 `cancelled_at`；其他平台由 adapter 映射取消事件（ADR-052/068） | M101–M104 |
| ~~D-27~~ | ~~草稿单是否计入~~ **已确认 2026-09-23**：已转正草稿计入；不按 `source_name` 过滤（ADR-053） | M101–M104 |
| ~~D-28~~ | ~~无大促日历是否阻断规模章~~ **已确认 2026-09-23**：不阻断规模/效率/达成；异动须标 `calendar_missing`；禁止整报失败（ADR-054） | R-12 / M401 |
| ~~D-29~~ | ~~G-04 时区 / G-05 财月~~ **已确认 2026-09-24**：UTC + 自然月 × `sale_date`（ADR-055） | G-04 / G-05 |
| ~~D-30~~ | ~~双库是否拆两套 env~~ **已确认 2026-09-24**：同一连接；schema 走 profile；不拆 `MYSQL_DATABASE_*`（ADR-056） | 连接 |
| ~~D-31~~ | ~~C1/C2 同模板是否再审~~ **已确认 2026-09-24**：同 playbook 同口径首次放行后自动；C3 每次（ADR-057） | 卡点 |
| ~~D-32~~ | ~~M208/M209 是否随 R-42~~ **已确认 2026-09-24**：净利/净利率首期不纳入；不定义、不建模、不留标题（ADR-058） | R-42 |
| ~~D-33~~ | ~~新站是否出同比~~ **已确认 2026-09-24**：不足 12 个完整自然月不参与 M302；可出 M303 并标「新站」；合计同比同店（ADR-059） | M302 |
| ~~D-34~~ | ~~EU 是否可当四国汇总~~ **已确认 2026-09-24**：站点 EU ≠ 欧盟市场；可按市场展示；欧盟已确认成员 EU/DE/FR/IT/ES/IE（ADR-060） | G-22 |
| ~~D-35~~ | ~~UA 是否计入欧盟市场~~ **已确认 2026-09-24**：计入；「欧盟」= 泛欧经营区，不是成员国清单（ADR-061） | G-22 |
| ~~D-36~~ | ~~新老客主键~~ **ADR-068 修订**：Shopify adapter 输入 gid；canonical 使用平台/店铺命名空间内 subject hash；空值未识别 | M501–M507 |
| ~~D-37~~ | ~~M105 是否升格~~ **已确认 2026-09-24**：M102/M103 派生，已确认（ADR-062） | M105 |
| ~~D-38~~ | ~~M401 量价用哪套件数~~ **已确认 2026-09-24**：店铺 SKU 件数配 M102；禁止 NS 件数进本公式（ADR-063） | M401 |
| ~~D-39~~ | ~~M402 贡献度如何拆~~ **已确认 2026-09-24**：ΔM102 按互斥层拆；站点/品类/度电带/新老客；禁止混加市场与站点；禁止 NS 件数加权（ADR-064） | M402 |
| ~~D-40~~ | ~~月报 SQL 是否允许无 LIMIT~~ **已确认 2026-09-24**：必须有时间窗；允许无 LIMIT；LIMIT 只约束探索 / ad-hoc（ADR-065） | R-04 / R-79 |
| ~~D-41~~ | ~~记忆层是否单独成模块~~ **已确认 2026-09-24**：三类文件持久化；Session/向量预留；上期数字不得当本期（ADR-066） | 记忆层 |
| ~~D-42~~ | ~~是否做成单一经营分析 agent~~ **已确认 2026-09-24**：否；`run` 与 `ask` 并列；月报只是第一份剧本（ADR-067） | 产品入口 |

> 后续如出现新待对齐项，先进入 `awaiting_alignment` 并追加 ADR；已关闭条目只保留修订链路，不作为当前待办。
