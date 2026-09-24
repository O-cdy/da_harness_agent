# 30 · 硬约束规则（机器可加载）

> 唯一职责：定义 harness 硬约束。本文件是约束的唯一来源，规则编号 R-xx，可被规则引擎直接引用。
> 违反「阻断级」规则必须中止流程，不得出报告。
> 版本 v0.8 | 建立：2026-09-22 | 最后更新：2026-09-24 | 状态：**生效**（R-01 ~ R-42 + **R-49～R-102**）。ADR-029 的 R-43~R-48 **编号占用且不复用，不生效**（ADR-030）。ADR-068 起规则按 scope 组合加载；ADR-069 冻结动态平台与发布契约；ADR-070 校正 S0 实现表达。

## 规则包与作用域

本文件仍是规则正文 SSOT；运行时不得整包全局加载。机器可加载的 pack→规则编号索引单源在 [`rule-packs.yaml`](rule-packs.yaml)，不得从本表或正文标题猜测。作用域职责如下：

| Rule pack | 适用范围 | 机器 id |
|---|---|---|
| Core | 所有任务 | `core` |
| 电商 Domain | 电商统一数据与指标 | `domain:ecommerce` |
| Shopify | Shopify adapter / 指标 | `platform:shopify` |
| TikTok | TikTok adapter / 原生指标 | `platform:tiktok` |
| 经营月报 | 月报流程与输出 | `playbook:monthly-business-review` |

`plan.rule_packs` 必须显式列出本次生效包；同级冲突阻断，更具体 scope 的覆盖必须能追到 ADR。规则正文中出现平台表名，不代表它对其他平台生效。

## R 级规则

| 编号 | 规则 | 级别 |
|---|---|---|
| R-01 | **LLM 不做算术。** 任何数字必须由 SQL / Python 产出；LLM 直接给出的数字视为无效，除非证据包中有对应计算过程 | 阻断 |
| R-02 | **正式报告指标门禁。** 正式报告中的每个指标必须登记为 `canonical` 或允许展示的 `platform-native`，且状态已确认/可实现。`provisional` 只可进入带醒目标识的探索草稿，禁止混入正式报告或自动升格 | 阻断 |
| R-03 | **禁臆造。** 数据缺失或口径未定义时输出「无数据 / 口径待确认」，禁止估算、插值、用行业均值填充 | 阻断 |
| R-04 | **SQL 只读**（ADR-065）。禁止 DDL / DML；禁止跨库写入。探索 / ad-hoc SQL 禁止无 LIMIT。月报原料 SQL 见 R-79 | 阻断 |
| R-05 | **跨口径不相加。** 不同平台 / 不同口径的指标必须先映射到内部口径再合并（G-06） | 阻断 |
| R-06 | **归因维度互斥可加**（ADR-064）。M402 每次只用一层；层内切片 ΔM102 之和必须等于整体。否则不得出贡献度 | 阻断 |
| R-07 | **env 门控。** 无凭据即 no-op 并显式报错，禁止静默降级 | 阻断 |
| R-08 | **可复现三要素。** 快照 hash + 代码留档 + 参数与模型版本，缺一不出报告 | 阻断 |
| R-09 | **原料 SQL 全量留档**。未经 C2 放行不得执行；仅 C2 完整组件指纹完全一致时可复用既有审批，仍须留档（ADR-057/069/070） | 阻断 |
| R-10 | **行数与耗时上限**，超限中止并记录；接近阈值可先告警 | 阻断 |
| R-11 | **token 预算**，分层路由：格式化与分片汇总走轻量模型 | 告警 |
| R-12 | **大促窗口识别**（ADR-054 收窄）：**有日历且已启用时**，判定异动异常前必须先识别促销窗口，禁止把大促虹吸写成经营恶化。无日历不适用本条，改走 R-70 | 阻断 |

| R-13 | **声明口径层级**：任何涉及订单 / 件 / order item 的报表必须声明所用层级（K-05） | 告警 |
| R-14 | **Session 不可跨品牌加总**（K-04） | 阻断 |
| R-15 | **新老客指标仅限独立站 / 自有渠道**：Amazon 不提供新老客维度，禁止用 Amazon 数据计算或合并新老客指标（M501–M506） | 阻断 |
| R-16 | **Amazon `Unit Session Percentage` 只作平台原生展示**，不得当作内部转化率参与跨品牌对比（K-03） | 阻断 |
| R-17 | **达成率分子分母口径必须一致**（均为净销售额 M102）；目标表快照 hash 必须入 `source_manifest.json`；目标缺失的维度输出「目标未设置」，不得用父级目标下推填充 | 阻断 |
| R-18 | **游客单（`shopify_customer_gid` 为空）禁止计入新客**（ADR-062），须归入「未识别」客群单列；新老客章节必须同时给出 M507 可识别率。禁止用 `customer_id` 或 email 当站点内主键 | 阻断 |
| R-19 | **禁止用主表 `net_sales` / `returns_amount` / `tableau_sales` 作为内部指标源** —— 前者已回溯扣退款（违反 G-08），后者站点口径不一致 | 阻断 |
| R-20 | **退款必须按 `refunds_lineitems.refund_created_at` 归属退款发生月**，不得按销售月归属；报告须给出与 tableau 口径的差额对账（G-13）。**未匹配退款例外见 R-65** | 阻断 |
| R-21 | **未匹配到 NSSKU 的 SKU 归入「未映射」桶**。金额按店铺 SKU 计入总额（G-18）。有唯一 NS 只是没有型号的，走 R-54，不进本桶 | 告警 |
| R-22 | **目标单位换算必须显式**：`market_goal.销售目标` 为 **CNY 万元**，须 ×10000 后再与实际值（CNY 元）比；禁止隐式换算，换算因子须写入证据包 | 阻断 |
| R-23 | **跨表对账必须对齐时间口径**：`shopify_sales_by_order.sale_date` ≠ `shopify_orders_mongo.created_at`。两套表订单集合一致（差 3 单且金额为 0），加月份窗口即产生 7~8% 假性差异。跨表比对前先声明用哪个时间字段 | 阻断 |
| R-24 | **汇率唯一来源是 `shared_data.exchange_rate`**：`shopify_orders_mongo.rate` 是**税率**（USD 取值 0.06 / 0.01 / 0.0025 / 0.0625），**禁止当作汇率折算**；折算前禁止跨币种裸加（JPY / CLP 原币量级差百倍，裸加会产生 15% 假差异） | 阻断 |
| R-25 | **禁止对 `refunds_adjustments.adjust_amount` 逐行求和**：实测 25,199 个（订单+退款时间）组中 7,407 组（29.4%）为完全抵消的成对记账。必须先按（订单 + 退款时间）组内取净额再汇总 | 阻断 |
| R-26 | **退款差额须折算后汇总**：`refunds_adjustments` 折算 CNY 后恒为负（-27万~-36万/月），原币裸和却为正（+119万~+243万/月）—— **符号被原币颠倒**。任何未折算的求和结论一律无效 | 阻断 |
| R-27 | **退款口径必须显式声明**（ADR-023 已定案主口径）：**整体/站点/达成率用「财务」**= `refunds_lineitems.refund_subtotal` + `refunds_adjustments`（组内净额，折算后）；**商品维度拆解用「计算」**= `refunds_lineitems.refund_subtotal`，差额单列「不可归因」不得分摊；`实际到账`= `shopify_orders_mongo_refunds` 且 `status='success'` AND `kind='refund'`，**默认不启用**，仅按 `profile.yaml` 开关用于对账区 | 阻断 |
| R-28 | **主口径数据源约束**：金额一律取 `shopify_sales_by_order`，退款取 `refunds_lineitems` + `refunds_adjustments`；**`shopify_orders_mongo` / `_total` 不得用于出数**。唯一例外是 `refund_reconciliation.enable_success_check=true` 时只读 `shopify_orders_mongo_refunds` 供对账区使用，且不进净销售额计算 | 阻断 |
| R-29 | **首期不含渠道 / UTM 维度**（ADR-024）：`utm_source/medium/campaign`、`referring_site_domain`、`gateway`、`discount_code` 仅存在于被 R-28 排除的 mongo 系列。首期维度树限定为 站点 × 品类 × 度数区间 × NSSKU × 新老客；需要渠道归因时另立 ADR，不得绕过 R-28 私自取数 | 阻断 |
| R-30 | **件数口径 = `SUM(quantity) WHERE quantity > 0 AND gross_sales <> 0`**（v2，复核后修正）。四类行须分别处理：① **赠品行**（`gross_sales=0` 且 `qty>0`）**不计件数**（近三年 64,587 件，占 12%）；② **无 SKU 但有金额的行计入件数**（近三年 4.00% 金额、近 12 月仅 0.05%），商品维度拆解时归「未映射」；③ **套装父行**（`qty=0` 且 `gross<>0`）金额计入、件数记 0，须标注（近三年 0.96%）；④ **负数量行**（冲销 / 取消，近三年 -52,590 件）一律排除 | 阻断 |
| R-31 | **无汇率不得替代**：汇率表仅覆盖 **2022-01~2026-09**；按 N+1、缺失时回退当月的既定顺序，仍有 **24,763 行不可折算**（`COUNT` 复核 @ 2026-09-24）。禁止用邻近月替代或插值，须输出「不可折算」并单列；报告期默认从 2022-01 起 | 阻断 |
| R-32 | **停运站点须识别并排除**：末次数据距今 > 90 天的站点标为「停运」，**不得参与异动检测与同比环比**。实测停运站点：ZA(2025-08-31)、UA(2025-10-30)、KR(2026-04-19) | 阻断 |
| R-33 | **目标表站点须映射**：`market_goal.站点` 与销售表编码不一致（`NGA`↔`NG`），且含聚合行 `南亚` / `众筹`（非站点）。须经映射表关联并排除聚合值；缺目标按 R-17 输出「目标未设置」 | 阻断 |
| R-34 | **Shopify adapter 月份映射**：Shopify canonical `order_created_date` 取 `sale_date`；其与 `order_created_at` 有 3.97% 跨月。该物理字段规则只属 `platform:shopify`，不得用于其它平台或跨平台 SQL | 阻断 |
| R-35 | **顾客可识别主键 = `shopify_customer_gid`**（ADR-026 + ADR-062）：`customer_exists_flag` 有 **2,139 行 NULL**，不可作为判定依据。M507 实测 = 1,287,312 / 1,289,508 = **99.83%** | 阻断 |
| R-36 | **数据源白名单制：副本 / 备份 / mongo 系列一律禁用**（用户 2026-09-22 明确：老版本备份遗留，不纳入使用考虑）。权威表见 `data-audit.md` §8。禁用清单：`*_backup*` / `*_copy*` / `*_260422` / `*_0731` / `*_old_*` / `shopify_orders_mongo*`。实例：`nssku对应映射表` 主表匹配率 **100%** vs `_copy1` **26.51%**；`shopify_sales_by_order` 1,289,508 行 vs `_260422` 48.9 万行（仅到 2026-04）。**行数一律以 `COUNT(*)` 为准，`information_schema` 估算值不可用于任何口径判断**。登记行数时**必须同时标注实测日期**（见 E-0003：本规则自身的产物——§8 白名单表——也曾混入估算值，复发第 4 次） | 阻断 |
| R-37 | **转化率必须同源**：分子分母都取自 GA4（`month_basic_data.transactions / sessions`）。**禁止 GA4 sessions 配 Shopify 订单数** —— 实测 GA4 仅覆盖 Shopify 订单的 **52.4%**（US 36.6%、EU 16.8%），跨源比值是口径错误。报告须同时给出结账率 `checkouts/sessions` 与两源差异率 | 阻断 |
| R-38 | **站点编码三处不一致，跨源关联须映射**：销售表 `NG` / 目标表 `NGA` / GA4 `nga`；GA4 用小写须 `UPPER()` 归一 | 阻断 |
| R-39 | **新客判定 = canonical 首次下单月**：`MIN(order_created_date)` 落在报告期。Shopify adapter 来源 `sale_date`，禁止用账号注册时间 `customer_created_at`；其它平台只在 identity capability 可用时计算 | 阻断 |
| R-40 | **客户身份默认平台/账户内统计**：Shopify gid 按站点唯一；跨平台/账户合并只能使用当前组织已确认的 identity map。禁止用 email/手机号自动归并；不得与账户内口径混用 | 阻断 |
| R-41 | **Shopify platform pack 白名单 = 8 张表**（ADR-027/028，作用域由 ADR-068 收窄）：`shopify_sales_by_order` / `market_goal` / `exchange_rate` / `month_basic_data` / `产品型号度数范围` / `nssku对应映射表` / `refunds_lineitems` / `refunds_adjustments`。本条不得阻断 TikTok 或未来 adapter 自己声明的权威表。Shopify 禁用/不理会清单保持不变；扩大任一平台白名单必须另立 ADR | 阻断 |
| R-42 | **成本 / 利润 / 毛利类指标不纳入首期设计范围**（ADR-027 + ADR-058）：M201 毛利 / M202 毛利率 / M203 平台佣金率 / M204 广告费率 / M205 履约费率 / M206 仓储费率 / **M208 净利 / M209 净利率**及 COGS 口径 —— **不定义、不建模、不留空占位、不在报告中留标题**，而非「暂不输出」。R-03 照常生效：不估算、不插值、不用行业均值填充 | 阻断 |
| R-49 | **未用户确认的口径禁止写入 canonical 并标「已确认」**（ADR-031 / E-0006）。用户补充、扫描笔记、agent 默认值一律视为参考。与既有 ADR 冲突必须先列清再问，每次只问一个问题。R-43～R-48 编号不复用 | 阻断 |
| R-50 | **禁止把店铺 SKU 金额在 JOIN 映射表展开后求和**（ADR-034）。组合品一行成交价留在 `sku`；展开只用于件数与路径。对展开后的 `gross_sales` / `discounts` / 退款金额 `SUM` 会按成员数放大，产物无效 | 阻断 |
| R-51 | **型号只允许从 NSSKU 行读取**（ADR-035 / G-19 / E-0007）。禁止给店铺 SKU 直接赋一个型号，禁止把店铺 SKU 与型号画成同级。件数可经 NS 上卷到型号；型号维金额见 R-53 | 阻断 |
| R-52 | **品类 / 度数区间只允许从有效型号上卷**（ADR-037 / G-20）。品类取值列 = `产品类型`（ADR-041）；度电带取值列 = `度数范围` 整列（ADR-042）。禁止与店铺 SKU 同级出金额。件数可经 NS→有效型号再上卷；金额只承接已进入有效型号的部分，「套件未拆」、无型号降级 NS、型号「配件」不进具体品类/度电带 | 阻断 |
| R-53 | **多型号套件金额进「套件未拆」**（ADR-038 / G-16）。禁止记入任一成员有效型号或由其衍生的品类/度数。单有效型号金额跟该型号走。禁止拆金额、禁止 `MAX(型号)` | 阻断 |
| R-54 | **无有效型号且唯一 NS 时金额上卷键降级为该 NS**（ADR-039 / G-16）。原子行仍是店铺 SKU，禁止 JOIN 后对金额 SUM（R-50）。0 个 NS 或 ≥2 个无有效型号 NS 走「未映射」（ADR-046）。禁止用 A-/P- 前缀替代型号列。无有效型号金额不进品类 | 阻断 |
| R-55 | **型号值「配件」视同未维护**（ADR-040）。不进型号维、不进品类；按 G-16 无有效型号处理。只匹配去空白后的精确值「配件」，禁止类推其它占位词 | 阻断 |
| R-56 | **禁止把 `产品型号_统一` 当成品类维或 JOIN 键**（ADR-041 / ADR-048）。品类 = `产品类型`。JOIN 键 = 有效型号 → `产品型号`，禁止 NSSKU.`型号` 直接对统一列 | 阻断 |
| R-57 | **户储不是独立列**（ADR-043）。标签 = `TRIM(度数范围)` 精确等于「户储」。禁止把房车 / 阳台 / 冰箱并入户储；禁止从 `产品类型` 拆户储 | 阻断 |
| R-58 | **NS / 型号件数 = `quantity × COALESCE(NULLIF(成员数量,0), 1)`**（ADR-044 / G-17）。禁止对金额乘 `成员数量` | 阻断 |
| R-59 | **两套件数禁止混用**（ADR-045）。M104（店铺 SKU）≠ Σ NSSKU 件数。报告按需展示但必须分标注。有有效型号时 NS 件数与型号维同一套，不另造第三套 | 阻断 |
| R-60 | **无有效型号且多 NS 的金额进「未映射」**（ADR-046）。禁止并进「套件未拆」、禁止拆到各 NS。报告出现该桶须按 G-21 标注，不得每图重复 | 阻断 |
| R-61 | **型号维 ASP 只许用金额已进入该型号的行**（ADR-047 / M106）。分子分母必须是同一批单有效型号店铺 SKU。禁止用该型号全部件数（含套件成员）作分母；禁止给套件未拆 / 未映射 / 配件降级 NS 出型号 ASP；禁止用 M104 当型号 ASP 分母。站点 ASP = M102 / M104 | 阻断 |
| R-62 | **型号维对外呈现主键 = `产品型号_统一`**（ADR-048）。金额仍先落到有效型号。禁止报告型号维用 `产品型号` 原文当主键；禁止跳过 JOIN 直接对统一列。套件未拆 / 未映射 / 降级 NS 不贴统一标签 | 阻断 |
| R-63 | **Shopify adapter 的 M103 原始订单键 = `order_name`**（ADR-049，作用域由 ADR-069 收窄）。禁止在 Shopify 主表用不存在的 `order_id`，亦禁止用行级 `id` 或退款表 `order_id`。canonical M103 使用 `platform + account_id + order_id`；adapter 负责把 Shopify `order_name`、TikTok `order_id` 映射到 canonical `order_id` | 阻断 |
| R-64 | **退款关联销售表的连接键 = `shop_name` + `name`↔`order_name`**（ADR-050）。禁止用销售表不存在的 `order_id` 当连接键；禁止把 mongo 行写入销售表 | 阻断 |
| R-65 | **未匹配退款不冲 M102、不进 M207 分子**（ADR-050）。不把补拉当闭环。禁止把未匹配退款静默并进净额 | 阻断 |
| R-66 | **主报告标注服从 G-21**（ADR-050）。禁止堆砌核因细节；P0 同类全篇只出一次 | 阻断 |
| R-67 | **禁止把 `financialStatus` 当退款原因**（ADR-051）。亦禁止用 `adjust_reason` / `cancel_reason` 充当原因维。首期退货分析只出 M207a/b | 阻断 |
| R-68 | **规模指标不按 `payment_status` 过滤**（ADR-052）。M101–M104 只按 `cancelled_at` 剔除取消单。禁止「仅 PAID」口径。改过滤须另立 ADR | 阻断 |
| R-69 | **已转正草稿计入规模，不按 `source_name` 过滤**（ADR-053）。禁止剔除 `shopify_draft_order`。禁止把来源当渠道维（ADR-024）。未完成草稿不在销售表，本条不涉及 | 阻断 |
| R-70 | **无大促日历不阻断规模 / 效率 / 达成**（ADR-054）。禁止因日历缺失整份月报失败。异动章必须标 `calendar_missing=true`（G-21 P0）。禁止把未识别窗口的下跌写成经营恶化。禁止把 `in_promo_window` 默认成 false | 阻断 |
| R-71 | **报告期 = UTC 自然月 × canonical `order_created_date`**（ADR-055/068/069）。Shopify adapter 映射 `sale_date`，TikTok 映射 `created_time`；禁止跨平台规则引用物理时间列、按站点本地时区重切或使用 4-5-4 | 阻断 |
| R-72 | **双库同一连接**（ADR-056）。schema 名从 profile 读；SQL 必须 `schema.table`。禁止核心代码写死库名。禁止为同一实例拆 `MYSQL_DATABASE_FACTS` / `MYSQL_DATABASE_DIMS`。缺凭据或缺 schema → 显式 no-op | 阻断 |
| R-73 | **审批按完整口径指纹与组件复用**（ADR-057/068～070）。`caliber_fingerprint` 必须含 metric/rule 内容、manifest、不可变 Profile、adapter contract、adapter schema fingerprint、source contract、C1 前可解析的 SQL 模板注册契约及结果相关 env hash；C2 另含实际 `rendered_sql_hash`。平台组合变化重审整体 C1；未变化分支可按 step C2 指纹复用；C3 每个候选包 hash 每次审核 | 阻断 |
| R-74 | **新经营账户不参与同比**（ADR-059/069）。按 canonical `platform + account_id` 的 `MIN(order_created_date)` 判断完整月数；小于 12 不出 M302，可出 M303并标新账户。合计同比只含够龄账户；禁止分母填 0或写死清单 | 阻断 |
| R-75 | **站点 ≠ 市场**（ADR-060 / G-22）。禁止把 `site=EU` 当欧盟合计。市场成员只从 profile `markets.groups` 读。禁止市场行与成员站点混加。禁止一个站点属两个市场。禁止用 `market_goal` 空站点市场行当目标 | 阻断 |
| R-76 | **口径必须可追溯**（ADR-062 / G-23）。已确认条目须能追到 ADR；profile 参数须有 `source`；报告数字须能追到指标编码 + SQL/代码 + 快照 hash。禁止无 ADR 标已确认；禁止「已定」进报告 | 阻断 |
| R-77 | **M401 量必须与金额同粒**（ADR-063）。量 = 店铺 SKU 件数（M104 ①），价 = 站点 ASP。禁止用 G-17 NS/型号件数作 M401 的量。残差单列，三项之和必须等于 ΔM102 | 阻断 |
| R-78 | **M402 贡献度用金额切片**（ADR-064/069）。首期可选维度：经营账户 / 品类 / 度电带 / 客户层。每层仅在目标平台 capability 完整时执行；禁止把缺 identity 的平台金额塞入“未识别”凑闭合。市场与成员账户不得混加，NS 件数不得作金额权重 | 阻断 |
| R-79 | **月报原料 SQL 必须有 canonical 时间窗**（ADR-065/069）。计划声明 UTC 自然月 × `order_created_date`，adapter 映射物理谓词。允许无 LIMIT；禁止用 LIMIT 截断规模指标。Policy 禁止在跨平台层写死 `sale_date` | 阻断 |
| R-80 | **记忆不得污染本期数字**（ADR-066）。planner 可读口径、错误索引、上期证据包指纹与叙事线索。禁止把上期 `metrics.json` 数值当作本期 M101–M507。禁止向量库或会话记忆升格为口径。Session / 向量后端未启用必须显式 no-op | 阻断 |
| R-81 | **预留能力必须有接口占位**（ADR-066，ADR-068 修订）。未实现能力须有稳定 Port/注册类型 + 显式 no-op（带 `module_id`）。禁止调用方按目录是否存在分叉；禁止静默改走另一条通路；**禁止仅为未来平台批量创建无实现、无引用的空目录** | 阻断 |
| R-82 | **核心禁止绑定单一场景**（ADR-067）。编排器 / CLI / Reporter / Skill 禁止写死经营月报步骤或章节。剧本只经 registry。`ask` 不得转调 monthly。Skill 必须能在非月报 `ctx` 下运行。无对应剧本且无探索计划时走 G-07，禁止塞进月报当新章 | 阻断 |
| R-83 | **平台原始数据必须先经 `PlatformAdapter` 映射 canonical**（ADR-068）。Playbook/Skill/Metric/Reporter 禁止直接读取平台表名；platform-native extension 也必须经已注册 adapter 暴露 | 阻断 |
| R-84 | **指标状态隔离**（ADR-068）。`canonical`、`platform-native`、`provisional`、`diagnostic` 禁止混用。platform-native 不得跨平台相加；provisional 必须留定义/SQL/代码/快照并禁止进正式报告；升格须用户确认 + ADR | 阻断 |
| R-85 | **规则按 scope 组合**（ADR-068）。`plan.rule_packs` 必须声明 core/domain/platform/playbook；未声明 scope 的平台规则不得加载；同级冲突阻断，覆盖必须追到 ADR | 阻断 |
| R-86 | **Playbook 只从机器可读 manifest 执行**（ADR-068/070）。Registry 禁止解析 Markdown 推导步骤；manifest 必须声明 schema/contract version、steps、metric/skill refs、rule packs、`core_capabilities`、`optional_capabilities`、time scope、unsupported/report policy、outline、approval 与 eval overlay | 阻断 |
| R-87 | **capability 门禁**（ADR-068）。Adapter 必须声明数据能力、覆盖期、水位与质量；缺能力输出 unsupported/coverage，不得估算或假装空值为 0 | 阻断 |
| R-88 | **未对齐映射进入 `awaiting_alignment`**（ADR-068）。每次只问一个口径问题；受影响分支暂停、独立分支可继续留证据；全部阻断项关闭前不得发布正式报告，禁止静默跳过 | 阻断 |
| R-89 | **客户身份默认按 `platform + account_id` 隔离**（ADR-068/069）。跨账户合并必须有当前组织/profile 已确认的 identity map；禁止用 email/手机号自动合并；业务审批不得跨组织复用 | 阻断 |
| R-90 | **TikTok canonical 订单规则**（ADR-068）。收入按 `created_time`；样品单筛除；取消单筛除且取消退款不得二次冲减；赠品保留并单列但不进 M101–M106；TikTok 官方按 `paid_time` 且含取消/退款的 GMV 仅作 platform-native | 阻断 |
| R-91 | **TikTok 退款按事件月冲减**（ADR-068）。M102 商品净额只冲 `tiktok_returns.refund_subtotal`，时间取 `event_date`；商品归因用 `tiktok_return_items`。运费/税不得并入商品净销售额；取消表退款不得重复冲减 | 阻断 |
| R-92 | **PII 默认拒绝**（ADR-068）。姓名、电话、地址、买家账号及含 PII 的 raw JSON 禁止进入 canonical、trace、证据包和报告；客户分析仅用平台命名空间内不可逆哈希。原始 PII 访问须独立授权并留痕 | 阻断 |
| R-93 | **逐源快照与多平台完整度**（ADR-068）。每个平台/表/文件必须独立 hash、schema、行数、时间范围、水位和 completeness；缺必需平台只可生成带覆盖率的 `partial`，齐备后生成新 `final`；禁止上期数据补齐或覆盖旧版 | 阻断 |
| R-94 | **运行状态与幂等**（ADR-068/070）。状态迁移必须符合架构 §16；取消/恢复从 checkpoint 执行；同 `run_id + plan_revision + step_id + input_fingerprint` 重试不得产生重复副作用；所有阻断失败必须返回脱敏 `ErrorEnvelope` | 阻断 |
| R-95 | **评估按通用基线 + playbook overlay 执行**（ADR-068）。禁止把 M401/M402 或 M101–M507 全集强制到所有场景；只评 `plan.metric_refs` 与 manifest 声明的 overlay | 阻断 |
| R-96 | **跨源关联键必须先规范化并记录策略**（ADR-068 / E-0009）。字符集、collation、大小写、首尾空白与 Unicode normalization 必须显式；禁止依赖数据库隐式转换。规范化后仍未命中才可进入未映射桶 | 阻断 |
| R-97 | **Playbook 平台集合运行时显式选择**（ADR-069）。交互 Run 必须提交非空 `target_platforms`；定时任务必须在调度配置声明。Playbook 禁止写死平台数量或组合；Profile `enabled` 不等于本次 required | 阻断 |
| R-98 | **月报核心与可选 capability 分层**（ADR-069）。目标平台必须具备商业总账核心能力；缺核心能力不得 waiver 或 final，只可补齐或经 C1 移出目标。可选能力缺失必须先问用户，不得默认跳过 | 阻断 |
| R-99 | **报告等级严格隔离**（ADR-069）。draft/未认证组件只可 dry-run；active 且仅水位未齐可经 C3 出 formal_partial；核心源齐备才可 formal_final；存在未关闭 alignment ticket 时禁止 C3/formal | 阻断 |
| R-100 | **数据齐备与汇率门禁**（ADR-069）。核心源须越过报告截止点 + 延迟窗口并通过质量断言；迟到数据出新版本不覆盖。报告期有效金额仍无法折算时阻断跨币种 formal，禁止排除或邻近月/实时汇率兜底 | 阻断 |
| R-101 | **C3 只审核封存候选包**（ADR-069）。报告、manifest、SQL/代码、参数/模型、断言与 trace 索引先封存并计算总 hash；C3 通过后只追加发布签名。驳回修复必须形成新 revision/hash | 阻断 |
| R-102 | **Profile/Adapter 组件认证**（ADR-069）。Profile 校准通过并显式批准后以新版本 active；adapter 按组织/profile + adapter/schema 版本独立认证。新增 adapter 不继承 active，也不使已认证组件退回 draft | 阻断 |

## 说明：R-12 的依据

来自 ima 知识库 `20260327_大促对AB的影响`（摘要级证据）：大促（3.8 / 6.18 / 11.11）前后一个月复购显著下降。
跨境同理（黑五 / 网一）：大促期间销量抬升、前后窗口塌陷是正常虹吸，不是异常。
因此**有日历时，归因前先标注促销窗口**是硬约束（R-12）。无日历时不阻断规模，异动只许标注缺失（R-70 / ADR-054）。

## 规则变更

修改本文件必须在 `docs/90-decisions/ADR.md` 追加记录，并同步更新 `PROJECT_STATUS.md` 的阻塞/进展状态。
