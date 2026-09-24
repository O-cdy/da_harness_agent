# 20 · 数据源与接入配置（唯一定义处）

> 唯一职责：定义数据源与接入配置。**本文件是数据源配置的唯一来源**，`harness/config/` 只读取本文件，不得在代码中硬编码默认值。
> 版本 v0.4 | 建立：2026-09-22 | 最后更新：2026-09-24 | 状态：**生效**（§5.3/§5.4 为实测登记；平台白名单以 `data-audit.md` §8 为准）。Shopify 口径见 ADR-019～065；跨平台 canonical 与 TikTok 首阶段接入见 ADR-068。

## 1. 默认接入模式（单源开关）

```yaml
default_datasource_mode: mysql   # 可选值：mysql | file
```

- 默认值 **`mysql`**（ADR-001）。
- 切换方式：**只改本文件**，不在命令行、不在环境变量里另设一套（避免多源冲突）。
- 单次任务可在 `plan.md`（C1 审核）中显式覆盖，但必须在 `source_manifest.json` 中留痕。

## 1.0 配置职责边界

| 配置类型 | 存放位置 | 说明 |
|---|---|---|
| 凭据 / 端点 / 运行参数 | `.env`（模板见 `.env.example`，**不入库**） | 账号、密码、API Key、BASE_URL、超时与行数上限 |
| **业务默认值** | **本文件 + `metrics.md`** | 默认接入模式、汇率规则、口径映射 —— **单源，禁止在 `.env` 中重复定义** |

`default_datasource_mode` 的权威值在本文件 §1，改模式**只改这里**，不改环境变量。

## 1.1 连接与 schema（ADR-056）

同一 MySQL 实例 **一套连接**（host / port / user / password 在 `.env`）。事实表与维表分属两个 schema，**名字**写在 `config/profile.yaml` 的 `facts_schema` / `dims_schema`，禁止写入核心代码。查询必须 `schema.table`。可选 `MYSQL_DATABASE` 只给驱动一个默认库，不替代 profile。缺凭据或缺 schema → 显式 no-op（守则 4）。

## 1.2 Shopify 权威表清单

| 表名 | 用途 | 在口径体系中的角色 | 字段映射状态 |
|---|---|---|---|
| `exchange_rate` | 各币种折算 CNY 的月度固定汇率 | 支撑 G-02 / ADR-011（N+1 回退） | 已登记，见 §5.1 |
| `shopify_sales_by_order` | Shopify 订单级销售明细（45 列，128.9 万行） | 规模、效率、达成、异动四类指标的**主事实表** | 已实测登记，见 §5.3 |
| `产品型号度数范围` | 商品型号 → 度数 / 品类标签（**210** 行，`COUNT(*)` @ 2026-09-23） | 品类=`产品类型`；度电带=`度数范围`整列；户储=该列取值「户储」标签（ADR-041～043） | JOIN 键 `产品型号`；型号维呈现=`产品型号_统一`（ADR-048） |
| `nssku对应映射表` | 店铺 SKU（`名称`）→ 成员 NSSKU + 型号（**73,858** 行，`COUNT(*)` 实测） | **挂载**：`名称` = 事实表 `sku`；**型号挂在成员行**（G-19） | 表名已确认；键 `名称`→`成员货品` + `型号`，**主表匹配率 100%**（早期 66,144 / 98.48% 已作废，见 E-0003） |

**补充事实表**：`refunds_lineitems`（退款发生时间）、`refunds_adjustments`（退款调整）、`market_goal`（销售目标）—— 均在 `bluetti_new` 库，见 §5.3。

**NSSKU 映射表的意义**（ADR-032～036）：`名称` = **店铺 SKU** = 事实表 `sku`（金额原子行，G-18）。`成员货品` = **NSSKU**（件数/路径，G-17，可空）。`型号` = NSSKU 行字段（G-19，可空）。层级：店铺 SKU → NSSKU → 型号。
2026-09-23 `COUNT(*)`：73,877 行；48,415 个名称中 17,011 多型号、8,994 单型号单 NS、952 单型号多 NS、18,827 无成员无型号、2,631 有成员无型号。有值 NS→型号一对一。1,837 个有值 NSSKU 全部也是某个 `名称`。

> **金额不拆到 NSSKU**（ADR-034）：套件订单一行成交，同单无成员行。成员可单独作为店铺 SKU 出售。禁止按比例拆。单有效型号跟型号走；多有效型号进「套件未拆」；无有效型号且唯一 NS 降级到该 NS；「配件」视同无有效型号（ADR-038～040）。

**Shopify 官方金额粒度（2026-09-23 核官方文档）**：Admin `LineItem` 的成交价挂在顾客买下的 **product variant** 上（`sku` / `originalUnitPriceSet`）。ShopifyQL `sales` 按 `product_variant_sku` 分析。这就是店铺 SKU 维，**不会**自动拆到内部 NSSKU。唯一例外是 **Shopify 原生 Product Bundles**（`requiresComponents`）：订单行变成组件，父件只在 `LineItemGroup` 里引用。本库 `shopify_sales_by_order` 与「单 variant 成交」一致，不是原生 bundle 展开。出处：[LineItem](https://shopify.dev/docs/api/admin-graphql/latest/objects/LineItem)、[LineItemGroup](https://shopify.dev/docs/api/admin-graphql/latest/objects/LineItemGroup)、[sales schema](https://shopify.dev/docs/api/shopifyql/latest/schemas/sales_revenue/sales)、[About product bundles](https://shopify.dev/docs/apps/selling-strategies/bundles)。

## 1.3 TikTok 首阶段权威表（ADR-068）

| 表 | 角色 | 实测规模（`COUNT(*)` @ 2026-09-24） |
|---|---|---|
| `bluetti_new.tiktok_sales_by_order` | 订单 × SKU 销售事实 | 20,809 行 / 20,314 单 / 6 店 / 3 币种 |
| `bluetti_new.tiktok_returns` | 退货/退款事件主表 | 1,132 行；有 `event_date` 与退款金额 |
| `bluetti_new.tiktok_return_items` | 退货商品行 | 1,151 行；可关联 order/line/SKU；**无退货数量字段，不得以行数代件数** |
| `bluetti_new.tiktok_cancellations` | 取消事件主表 | 1,607 行 |
| `bluetti_new.tiktok_cancel_items` | 取消商品行 | 1,935 行 |
| `bluetti_new.tiktok_affiliate_orders` | Affiliate 订单与佣金 | 12,244 行 |
| `bluetti_new.tiktok_live_performance` | LIVE 流量、互动与成交 | 18,918 行 |

禁用/非 canonical 源：`tiktok_sales_by_order_0731`（旧快照）、`tb_tiktok_tableau` 与 `vw_tiktok_tableau`（展示/派生口径）。TikTok adapter 只读上述七张权威表。

销售覆盖 `DE/ES/FR/GB/IT/US`、`EUR/GBP/USD`；`created_time` 从 2024-07-11 至 2026-09-23，最新同步水位 2026-09-24 08:31:41。表含 PII 与 `raw_json`，adapter 必须在 canonical 边界删除或不可逆哈希（R-92）。

## 1.4 平台接入范围（ADR-015，ADR-068 修订）

| 平台 | 首期状态 | 说明 |
|---|---|---|
| **Shopify 独立站** | **首阶段接入** | 官方口径见 `metrics.md` B1；平台白名单 8 张 |
| **TikTok Shop** | **首阶段接入** | canonical 销售/退款 + Affiliate/LIVE 原生模块；官方口径见 `metrics.md` B3；平台白名单 7 张 |
| Amazon 多站点 | 未接入 | 官方口径**已登记**（`metrics.md` B2），未来接入时直接复用映射，无需重新调研 |
| eBay / AliExpress / Walmart / 迪卡侬等 | 未接入 | 接入前补官方口径、adapter 与 capability；无官方口径前不得臆造映射 |
| 自有 ERP | 未接入 | 待定 |

**首阶段不是单平台**：跨源合并只允许读取 canonical；platform-native 指标不得直接相加。逐平台 capability、映射覆盖率、水位与 completeness 必须进入 manifest。

**新建数据流前必须做的**：多币种/多市场依然成立 → 汇率折算（ADR-011）**仍然生效**。

## 2. MySQL 直连模式

| 配置项 | 说明 |
|---|---|
| 连接凭据 | 走 env（`MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DATABASE`），**不入库、不写文件** |
| 权限 | 只读账号 |
| 门控 | **无凭据即 no-op 并显式报错，禁止静默降级到文件模式**（`AGENTS.md` 守则 4） |
| 留痕 | 连接目标（host + db）、执行时间、SQL 全文入 `runs/<task>/sql/`。月报原料 SQL 必须带报告期时间窗，允许无 LIMIT（R-79 / ADR-065）；探索 / ad-hoc 必须有 LIMIT（R-04） |

## 3. 本地文件导入模式

| 配置项 | 说明 |
|---|---|
| 支持格式 | `.xlsx` / `.csv` |
| 强制产出 | schema 推断结果入档 + 字段→指标口径映射表 + 源文件 hash / 行数 / 导入时间 |
| 映射表位置 | 本文件第 5 节 |
| 禁止 | 静默丢弃无法识别的列（必须列出未映射字段并告警） |

## 4. 统一契约：source_manifest.json

两种模式必须产出同一 Artifact Envelope；下游只认 manifest 与 canonical contract，不认来源。顶层 manifest 只做索引，`sources[]` 每个表/文件独立留证：

```json
{
  "manifest_version": "1.0",
  "mode": "mysql | file",
  "profile_id": "组织/profile",
  "metric_version": "metrics.md 的版本号",
  "data_completeness": "partial | final",
  "report_version": "v1 | v2 | ...（同报告月内递增，不可覆盖）",
  "sources": [{
    "source_id": "platform.table-or-file",
    "platform": "shopify | tiktok | ...",
    "adapter_id": "adapter 标识",
    "adapter_contract_version": "semver",
    "schema_fingerprint": "hash",
    "query_hash": "hash",
    "snapshot_hash": "hash",
    "row_count": 0,
    "time_range": {"min": "ISO8601", "max": "ISO8601"},
    "watermark": "ISO8601",
    "completeness": "partial | final",
    "capabilities": [],
    "unmapped_fields": []
  }],
  "fx": {"snapshot_hash": "hash", "rate_month": "YYYY-MM"}
}
```

`data_completeness = partial` 表示报告月尚未过完、数据不完整（汇率通常走回退）；`final` 表示次月重生成、数据完整且已能用 N+1 汇率（ADR-013）。
**同报告月的 partial 与 final 版本并存**，重生成产出新 `report_version`，不覆盖旧版本。
任一必需平台水位未到报告截止时间时，顶层只能是 `partial`，并在报告给出逐平台覆盖率；禁止用上期快照补齐（ADR-068 / R-93）。

## 5. 字段 → 内部口径映射表

### 5.1 汇率表 `shared_data.exchange_rate`（已登记，证据：用户提供的库表截图 2026-09-22）

| 源字段 | 含义 | 映射 / 用途 |
|---|---|---|
| 年度月份 | 汇率所属月，如 `2026-09` | N+1 匹配键（见下方算法） |
| 货币中文名称 | 币种中文名，如「美元」 | 仅展示用 |
| 国家或地区 | 如「美国」 | 仅展示用 |
| 基本货币 | 目标币种，固定 `CNY` | 校验项：必须为 CNY，否则拒绝该表 |
| 货币 | 币种代码，如 `USD` / `JPY` / `EUR` | 与业务表的 `currency` 匹配键 |
| 汇率 | 1 外币 = X CNY（如 USD 6.78633152） | `fx_rate` |

**约束**：
- 每月每币种应唯一一行；若出现重复行，以最新录入为准并**告警**（不静默取值）。
- `基本货币 != CNY` 的行拒绝使用，报错不降级。
- 汇率表来源也可以是 Excel（与上表同构：年度月份 / 货币 / 汇率三列必需），走文件导入通道，同样产出 manifest。

### 5.1b 目标表（已登记，ADR-016）

| 项 | 说明 |
|---|---|
| 实际表 | `bluetti_new.market_goal`（916 行；字段 `所属部门/市场/销售目标/年月/站点/实际销售额/目标完成率`） |
| 来源 | 库表优先（已存在），Excel 亦可，与汇率表同样支持两种通道 |
| 维度 | **年月 × 站点**（+ 所属部门 / 市场）。**实际无品类维度**（实测，ADR-020 修订 ADR-016） |
| 口径 | **净销售额（M102）**，与达成率实际值口径一致 |
| 币种 / 单位 | **CNY，单位「万元」** → 目标值 × 10000 = CNY 元，再与实际值（CNY 元）比。**换算必须显式，禁止隐式**（R-22） |
| 数据现状 | 2022 年目标全为 NULL → 输出「目标未设置」；2026 年月目标已录至 12 月 |
| 留痕 | 目标表快照 hash 入 `source_manifest.json` |
| 缺失处理 | 某维度无目标 → 输出「目标未设置」，**禁止**用父级/总量目标按比例下推（R-17） |

### 5.2 汇率选择算法（N+1 回退，G-02）

```
输入：报告月份 M，币种 c
1. 在汇率表中查 (年度月份 = M+1, 货币 = c)
2. 命中 → fx_rate_month = M+1
3. 未命中（M+1 月未结束未录入）→ 查 (年度月份 = M, 货币 = c)
   命中 → fx_rate_month = M（回退当月）
   未命中 → 报错「缺 {c} 的 {M} 月汇率」，禁止用其他月份或实时汇率顶替
4. 四元组留档：amount_original + currency + fx_rate + fx_rate_month → amount_base
```

**可复现关键**：本次报告实际用了哪些 `fx_rate` 与 `fx_rate_month`，必须全量写入 `source_manifest.json`（汇率表快照 hash 一并写入）。

### 5.3 实测字段登记（2026-09-22 直连数据库核实）

> 来源：MySQL `14.21.30.26:33061`，库 `bluetti_new` / `shared_data`，MySQL 8.0.37。
> 以下均为**实测结果**，不是推断。

**主事实表 `bluetti_new.shopify_sales_by_order`**（45 列，1,289,508 行，订单行级）

| 字段 | 类型 | 用途 / 映射到内部指标 |
|---|---|---|
| `sale_date` | date | 销售归属日（ShopifyQL day）。**月份归属用本列**（R-34）。**报告期 = UTC 自然月**（ADR-055） |
| `shop_name` / `site` / `shop_domain` | varchar | 店铺 / 站点（`COUNT(DISTINCT site)` = **21** @ 2026-09-24：AU/BR/CA/CL/DE/ES/EU/FR/IE/IT/JP/KR/MX/NG/NZ/PH/SA/UA/UK/US/ZA） |
| `currency` | varchar | **原币币种**（15 种）→ 必须走 G-10 四元组双留档 |
| `order_name` / `sku` / `quantity` | varchar/int | 订单号 / 销售 SKU / 件数 → M103 = `COUNT(DISTINCT order_name)`（ADR-049） / M104 |
| `gross_sales` | decimal | 商品原价额 → M101 GMV 基准 |
| `discounts` | decimal | 折扣（**已为负数**）→ M102 |
| `returns_amount` / `return_fees` | decimal | 退货额（**按 sale_date 归属，即已回溯**）⚠ 见下方冲突 C-01 |
| `net_sales` | decimal | = gross + discounts + returns（**已回溯扣退款**）⚠ 见 C-01 |
| `shipping_charges` / `taxes` / `total_sales` | decimal | 运费 / 税 / 总额 → K-02 |
| `tableau_sales` | decimal | ⚠ **口径不一致**：US/CA 取 net_sales，其他站点取 total_sales → **禁止作为内部指标源** |
| `contact_email` / `shopify_customer_gid` / `legacy_customer_id` | varchar | 客户标识 → M501–M506 |
| `customer_exists_flag` | tinyint | 1=有 customer 节点；**实测 flag=0 仅 57 行 / 128.9 万（0.004%）** → M507≈99.996% |
| `cancelled_at` / `cancel_reason` | datetime | 取消单标记，**实测 75,702 行** → 按 G-09 剔除 |
| `payment_status` | varchar | 支付状态。**首期不按本列过滤**（ADR-052）。取消只认 `cancelled_at` |
| `source_name` | varchar | 来源。**已转正草稿计入规模，首期不按本列过滤**（ADR-053）。不出渠道维（ADR-024） |
| `order_created_at` / `order_processed_at` | datetime | 下单时间（ADR-010 按下单时点） |
| `dedup_fingerprint` | char(64) | MD5(sale_date\|shop_name\|order_name\|sku)，**已自带去重指纹** |

**退款表 `bluetti_new.refunds_lineitems`**（46,509 行）：`refund_created_at`（**退款发生时间**）、`refund_subtotal`、`refund_totalTax`、`refund_quantity`、`currency`、`order_id`、`name`

> `payment_status` 不过滤（ADR-052）。已转正草稿计入、不按 `source_name` 过滤（ADR-053）。无日历不阻断规模（ADR-054）。报告期 UTC 自然月（ADR-055）。双库同一连接（ADR-056）。C1/C2 同指纹自动放行（ADR-057）。净利不纳入（ADR-058）。新站不参与同比（ADR-059）。站点 ≠ 市场（ADR-060）。UA 计入泛欧经营区（ADR-061）。新老客主键 gid（ADR-062）。行数以当日 `COUNT(*)` 为准。退款关联销售表已确认（ADR-050）。`financialStatus` 不当退款原因（ADR-051）。
→ **支持 ADR-010「退款在发生月冲减」**。实测存在跨月退款（下单 2026-03-12，退款 2026-04-20）。
**`bluetti_new.refunds_adjustments`**（43,919 行）实测结构（2026-09-22 深挖，C-04 证据）：

| `adjust_reason` | 行数 | 正 / 负 | 净额 |
|---|---|---|---|
| `Refund discrepancy` | 30,069 | 14,725 / 15,344 | **+179,316,454.79** |
| `Pending refund discrepancy` | 12,666 | 0 / **12,666（全负）** | **-172,213,941.56** |
| `Shipping refund` | 1,236 | 391 / 845 | -31,308.44 |
| `Full return balancing adjustment` | 382 | 245 / 137 | +4,503.75 |

- 按「订单 + 退款时间」分组共 25,199 组：**7,407 组净额 ≈ 0（完全抵消的零和记账）**、15,697 组净 < 0、2,095 组净 > 0。
- 典型样本（同一订单同一时刻 3 行）：`-X (Refund discrepancy)` + `-X (Pending refund discrepancy)` + `+X (Refund discrepancy)` → 净 `-X`。
- 2026-06 起按月：`Pending` 恒为负（-9.33M / -30.50M / -9.02M / -0.70M），`Discrepancy` 恒为正（+10.94M / +32.93M / +10.21M / +2.62M），**两者高度重叠、疑似同一笔退款的双重记账**。
- 与 `refunds_lineitems` 的关系：**adjustments 涉及 23,441 单，其中 13,538 单（57.8%）在 lineitems 中完全没有退款明细** → 不是 lineitems 的子集，不能相互替代。
→ ⚠ **禁止逐行 `SUM(adjust_amount)`**（29.4% 的组是完全抵消的成对记账），且**禁止原币求和**（见下方 [X]）。

#### 退款三表与 Shopify 官方对象映射（C-04 定案依据，2026-09-22）

| 本库表 | Shopify 对象 | 官方语义 | 行数 |
|---|---|---|---|
| `refunds_lineitems` | `Refund.refundLineItems` | **计算**退款额（按行项、可按 SKU 归因） | 46,509 |
| `shopify_orders_mongo_refunds` | `Refund.transactions` / `OrderTransaction` | **实际**退款交易额，带 `status` | 58,462 |
| `refunds_adjustments` | `OrderAdjustment` | **计算与实际退款之间的差额**（对账科目） | 43,919 |

**官方文档依据**（检索日期 2026-09-22）：
- `OrderAdjustment`：「An order adjustment accounts for the **difference between a calculated and actual refund amount**」—— `https://shopify.dev/docs/api/admin-graphql/latest/objects/OrderAdjustment`
- REST Refund：「If you refund line items for less than their calculated amount… an order adjustment is created automatically to **account for the discrepancy in the store's financial reports**」—— `https://shopify.dev/docs/api/admin-rest/2024-10/resources/refund`
- `Refund`：「The existence of a Refund object doesn't guarantee that the money has been returned… To determine if money has **actually** been refunded, check the **status** of the associated transactions」—— `https://shopify.dev/docs/api/admin-graphql/latest/objects/Refund`
- `OrderAdjustmentDiscrepancyReason` 枚举含 `PENDING_REFUND_DISCREPANCY`（「pending refund」）与 `REFUND_DISCREPANCY`（「not one of the predefined reasons」，即兜底值）—— `https://shopify.dev/docs/api/admin-graphql/latest/enums/OrderAdjustmentDiscrepancyReason`

**实测：折算 CNY 后三口径对账**（汇率 2026-09，N+1 规则）

| 月 | A. lineitems（计算） | B. 交易额（全部） | C. 仅 `status='success'` | D. failure+error | E. pending | F. adjustments（差额） | A+F |
|---|---|---|---|---|---|---|---|
| 2026-06 | 4,810,371.17 | 4,813,599.38 | 4,695,249.84 | 78,004.47 | 40,345.07 | **-271,536.53** | 4,538,834.64 |
| 2026-07 | 6,044,047.53 | 6,216,897.31 | 6,010,986.80 | 114,864.43 | 91,046.08 | **-360,078.38** | 5,683,969.15 |
| 2026-08 | 4,893,092.51 | 4,390,858.08 | 4,257,980.00 | 92,591.38 | 40,286.70 | **-325,701.62** | 4,567,390.89 |
| 2026-09 | 2,813,029.45 | 2,905,391.97 | 2,801,967.78 | 23,760.09 | 79,664.10 | **-288,864.15** | 2,524,165.30 |

**两条决定性发现**：

1. **adjustments 折算后是负数**（每月 -27万 ~ -36万 CNY），而**原币裸和是正数**（+119万 ~ +243万）。符号被原币颠倒 —— 这是 R-24 存在的理由，任何未折算的 `SUM` 都会得出方向相反的结论。
2. **A + F ≈ C**（偏差 -3.3% ~ +9.9%，量级对齐）→ 印证官方说法：Shopify 用 adjustment 让「计算 + 差额」落到财务报告口径。残余偏差源于统一用 2026-09 汇率、月份归属差异与 void 类交易未计入。
3. ⚠ **新缺口**：2026-08 有退款行项的 1,046 单中，**114 单（10.9%）在交易表中找不到任何 `status='success'` 记录**（失败 / 在途 / 未处理）。全额按 lineitems 冲减会把未实际退回的钱算成退款 → **低估净销售额**。

`shopify_orders_mongo_refunds.status` 实测分布（全期原币）：`refund+success` 55,764 行 / `refund+failure` 1,066 行 / `refund+pending` 377 行 / `refund+error` 21 行 / `void+success` 1,023 行等。

**汇率表 `shared_data.exchange_rate`**（**1,169** 行，`COUNT(*)` 实测；早期的 911 是 `information_schema` 估算值，已作废）：`年度月份 / 货币中文名称 / 国家或地区 / 基本货币(=CNY) / 货币 / 汇率`
→ 最新月份为 **2026-09**（USD=6.78633152、EUR=7.82060677、JPY=0.04259082），币种 29 种。
**N+1 实测可用**：2026-10 汇率尚不存在 → 9 月月报按规则回退用 2026-09 ✓

**`shared_data.nssku对应映射表`**（**73,858** 行，`COUNT(*)` @ 2026-09-22）：`名称` = **店铺 SKU**（= 事实表 `sku`）→ `成员货品` + `型号`
→ **2026-08 销售 SKU 命中 `名称` 1,369 / 1,369**（`COUNT(DISTINCT sku)`）。其中 1,359 有 NS、1,011 有型号、476 为多型号套件。`型号` 在成员行上（G-19），可空。金额原子行是店铺 SKU（G-18）。
注意：一名称可多成员、多型号；成员也可作为独立 `名称` 成交。禁止 JOIN 展开后对金额求和（R-50）；禁止给店铺 SKU 赋单一型号（R-51）。

> 型号维 ASP 已确认（ADR-047 / M106）：只对金额已进入该型号的单有效型号计算；套件未拆 / 未映射 / 配件降级 NS 不出型号 ASP。

**`shared_data.产品型号度数范围`**（**210** 行，`COUNT(*)` @ 2026-09-23）：`序号 / 产品类型 / 度数范围 / 产品型号 / 产品型号_统一`
（样例：储能 / `0.5度电-` / ac60）→ 关联键 `产品型号`，经 NSSKU.`型号` 桥接（G-20 / ADR-037）。**品类列 = `产品类型`**；**度电带列 = `度数范围` 整列**；**户储 = 度数范围取值「户储」**；**JOIN 键 = `产品型号`；型号维对外呈现 = `产品型号_统一`**（ADR-041～043 / ADR-048）。早期正文写 204 行已作废。

**目标表 `bluetti_new.market_goal`**（916 行）：`所属部门 / 市场 / 销售目标 / 年月 / 站点 / 实际销售额 / 目标完成率`
→ ⚠ **实际维度是「年月 × 站点」（+部门/市场），无品类维度**；`销售目标` 单位 = **CNY 万元**（**ADR-020 已定案**，须 ×10000 显式换算，R-22），2026-09 合计 5,796.9 万元；2022 年目标全为 NULL；`实际销售额` 列**全为 NULL**，不可用于交叉验证。

**其他已存在但未接入**：`shared_data.aba_asin_sku对照`（Amazon ASIN↔SKU，1,540 行）、`shared_data.product_parameters`（155 行商品参数）。TikTok 系列已由 ADR-068 接入，见 §1.3 / §5.4。

#### 三套 Shopify 订单表的关系（B-10 实测，2026-09-22）

| 表 | 行数 | 订单数 | 站点/店铺 | 时间字段 | 层级 |
|---|---|---|---|---|---|
| `shopify_sales_by_order` | 1,289,508 | 594,868 | 21 `site` | `sale_date` | 订单×SKU 行级（2.29 行/单） |
| `shopify_orders_mongo` | 750,518 | 593,789 | 23 `shop_name` | `created_at` | 订单×明细行级（1.31 行/单） |
| `shopify_orders_mongo_total` | 610,526 | **593,789（与 mongo 相同）** | 23 `shop_name` | `created_at` | **订单级**（1.002 行/单） |

**关键实测**：

1. **订单集合几乎完全重合** —— 全表按订单号比对，仅出现在 `sales_by_order` 的只有 **3 单**（CA/CAD 2 单、IT/EUR 1 单，金额均为 0.00），仅出现在 `orders_mongo` 的 **0 单**。→ 两套表**同源**，不是互相独立的两份数据。
2. **但时间字段不可互换** —— `sale_date` ≠ `created_at`。加月份窗口后立刻产生假性差异（2026-08：12,130 单 vs 11,272 单，相差 7.1%）；去掉窗口后差异归零。→ **跨表对账必须先对齐时间口径**（R-23）。
3. **金额在折算后才可比** —— 原币裸加会出现 15% 的假差异（JPY / CLP 原币数值量级差百倍）。折算 CNY 后（2026-08，N+1 汇率 2026-09）：`sales_by_order` 66,899,728 vs `orders_mongo` 72,424,609，差 **8.3%**；同币种 USD 单看则只差 **1.96%**（4,067,924.04 vs 4,147,504.69）。→ 差额主要来自行级拆分粒度与月份归属，不是本质口径冲突。
4. ⚠ **`orders_mongo.rate` 是税率，不是汇率**（USD 取值 0.06 / 0.01 / 0.0025 / 0.0625；JPY 0.1）→ **禁止当作汇率用于折算**（R-24）。汇率唯一来源是 `shared_data.exchange_rate`。
5. `orders_mongo` 独有维度（主表没有）：`utm_source/medium/campaign/term/content`、`referring_site_domain`、`user_agent`、`gateway`、`discount_code`、`billing/shipping_*`、`fulfillment_status`。

#### 实测暴露的口径冲突（需决策）

| 编号 | 冲突 | 影响 |
|---|---|---|
| ~~C-01~~ | ~~主表 net_sales 已回溯扣退款~~ **已决策 2026-09-22（ADR-019）** | M102 = `gross_sales + discounts`，退款按 `refund_created_at` 发生月冲减；禁 net_sales / tableau_sales 作为源（R-19/R-20） |
| **C-02** | `tableau_sales` 站点口径不一致（US/CA 净额、其他总额） | 与 ADR-012「不含运费」冲突，禁止作为内部指标源 |
| ~~C-03~~ | ~~目标表实际维度无品类，单位未确认~~ **已决策（ADR-020）** | 维度=年月×站点；单位 CNY 万元，×10000 显式换算（R-22） |
| ~~C-04~~ | ~~`refunds_adjustments` 正负成对，处理方式待定~~ **已定性 2026-09-22（ADR-022）** | 官方定义 = 计算与实际退款的**差额**（对账科目），非退款额本身；折算后恒为负；**须纳入**使 A+F 对齐财务口径，但必须组内取净额 + 折算后汇总（R-25/R-26） |

## 5.4 TikTok 字段 → canonical 映射（2026-09-24 实测）

| canonical | TikTok 来源 | 处理 |
|---|---|---|
| order key | `shop_id + order_id` | 再加 `platform=tiktok` 构成全局键 |
| order created time | `created_time` | canonical 下单时点；`sale_date` 实测等于 paid date，不用于 M101–M104 时点 |
| platform-native GMV time | `paid_time` | 仅 PN-TIKTOK-001 等原生指标 |
| product key | `seller_sku` | 先统一字符排序/规范化，再接 NSSKU；158/166 命中，未命中进桶 |
| gross amount | `sku_subtotal_before_discount` | 不含税运；取消/样品/赠品过滤 |
| net before refund | `sku_subtotal_after_discount` | 退款另从 event 表按发生月冲减 |
| quantity | `quantity` | 取消/样品/赠品不进商业 M104 |
| gift/sample/cancel | `is_gift` / `is_sample_order` / `cancelled_time` 或取消事件 | 赠品保留单列；样品和取消筛除 |
| refund event | `tiktok_returns.event_date` + `refund_subtotal` | 冲 M102；`refund_shipping_fee/refund_tax` 不进商品净额 |
| refund item | `tiktok_return_items` | `order_line_item_id/sku_id/seller_sku` 仅作商品归因；无数量字段，M207b unsupported |
| cancellation | `tiktok_cancellations` + `tiktok_cancel_items` | 用于剔除与诊断；其退款金额不得二次冲 M102 |
| customer | 无可用 canonical capability | PII 字段与 raw_json 禁入；首阶段不算 TikTok M501–M507 |
| Affiliate/LIVE | 对应两张原生表 | 只输出 platform-native；归因窗口按官方来源 |

## 6. 已知风险

| 风险 | 说明 |
|---|---|
| 平台导出口径不一致 | 同一指标在不同平台导出文件中含义不同，必须先映射再合并（ADR-009、冲突 K-01~K-05） |
| 文件模式数据陈旧 | 导出文件无时间戳语义时，须以导入时间作为快照时间并在报告中标注 |
