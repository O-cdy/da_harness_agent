# 项目级长期记忆：跨境电商数据分析 harness agent

## 项目定位
构建面向**跨境电商行业数据分析**的 harness agent：用一层"约束 + 监控 + 评估"的外壳（harness）包住 LLM 与 SQL/Python 分析工具，使分析过程可约束、可监控、可复现、可评估。工作区 `D:\cdy\AI\data analysis harness agent`，截至 2026-09-22 仍为空目录（规划阶段）。

## 协作约定（用户指定，长期有效）
- **对齐流程**：多轮目标对齐，每轮只提 **1 个** 问题，基于回复递进追问；到 95% 把握后再动代码，前期规划优先，避免返工。
- 本轮（第 1 轮）状态：未创建任何项目文件。规划草案见 `2026-09-22.md`。

## 外部资产坐标
- ima 知识库「不知渭河-数据分析知识库」`kb_id=7452382921234335`（1098 条）。
- **只读限制**：该库 `search_knowledge` 无命中、`fetch_media_content` 报 220030、`can_fetch_content=false` → 只有标题 + introduction 摘要可用，引用须标注证据等级。

## 项目红线 / 硬规则
- **单一同步文档（核心守则）**：根目录唯一 `PROJECT_STATUS.md` 是项目上下文唯一信息源；禁止 PROGRESS/TODO/ROADMAP/阶段总结等重复进度文档；8 节固定结构；agent 在「开始/切换/完成」三时点必须更新；新 agent 必须先读再续写，禁覆盖；历史决策只归档不删除。守则全文见 `AGENTS.md`。
- 边界划分：`PROJECT_STATUS.md` 只管状态与进度，`docs/` 只管事实与规格；前者引用后者，**禁止复制正文**（否则双源过期冲突）。
- env 门控 + 无凭据即 no-op，禁止静默降级通路。
- 可复现三要素（快照 hash + 代码留档 + 参数模型版本）缺一不得出报告。

## 已对齐决策（2026-09-22，Q1–Q6）
ADR-001 双通道接入（MySQL 默认 + 文件导入，配置文档切换）｜ADR-002 首场景=经营分析月报｜ADR-003 先 CLI 后 Web，core/cli 解耦｜ADR-004 Python｜ADR-005 三级人工卡点（计划/原料SQL/报告）｜ADR-006 LLM 分层路由 + 可插拔 provider｜ADR-007 单一同步文档守则。
## 对齐状态（2026-09-22 完成 Q1–Q15，已达成 95%+）
已定 17 项 ADR：001 双通道接入 / 002 经营分析月报 / 003 先 CLI 后 Web / 004 Python / 005 三级卡点 / 006 LLM 分层可插拔 / 007 单一同步文档 / 008 Markdown+HTML / 009 双层口径体系 / 010 收入时点与退款冲减 / 011 本位币 CNY + N+1 汇率 / 012 成本口径（GMV 不含运费、COGS 到岸成本）/ 013 月报版本 partial-final / 014 退货率双轨 + 转化率订单口径 + 新老客分层 / 015 首期仅 Shopify / 016 目标表口径 / 017 新老客主键 customer_id。
**D-01~D-10 口径待确认项全部关闭。** 剩余工作不是架构问题，而是：接入真实 Shopify 数据并登记字段映射。

## 关键业务口径速查（避免重复问）
- 本位币 CNY，用户月度固定汇率表（DB `shared_data.exchange_rate` 或 Excel），**N+1 规则**（8月报用9月汇率，缺则回退当月）。
- 月内生成 = partial（回退汇率），次月重生成 = final（N+1），**两版本并存不覆盖**。
- 收入按下单时点；退款/取消在发生月冲减，不回溯。
- GMV 不含运费；COGS = 采购成本 + 头程物流 + 关税；FBA/尾程/仓储归费用项。
- 目标表「月 × 站点 × 品类」，口径=净销售额，缺目标禁止下推。
- 新老客主键 `customer_id`/`legacy_customer_id`；**游客单（`customer_exists_flag=0`）归「未识别」，不得计入新客**（实测仅 0.004%）。

## 字段级实现（实测核实，勿再推断）
- 数据源：远程 MySQL `14.21.30.26:33061`，库 `bluetti_new`（主业务）+ `shared_data`（共享维表）。
- 主事实表 `bluetti_new.shopify_sales_by_order`（45 列，128.9 万行，19 站点/15 币种）。
- **M101 = `gross_sales`；M102 = `gross_sales + discounts`（discounts 已为负）**，剔除 `cancelled_at IS NOT NULL`。
- **退款走 `refunds_lineitems.refund_subtotal` 按 `refund_created_at` 发生月冲减**；**禁用主表 `net_sales` / `returns_amount` / `tableau_sales`**（R-19）。
- 汇率 `shared_data.exchange_rate` 最新 2026-09；NSSKU `shared_data.nssku对应映射表` 键 `名称`→`成员货品`，匹配率 98.48%；度数 `shared_data.产品型号度数范围`；目标 `bluetti_new.market_goal`（年月×站点，**无品类**）。
- 内部口径 ≠ 公司 tableau 报表口径，差额为跨月退款归属差异，**必须显式对账（G-13）**。

## 商品维度：NSSKU（内部统一商品主键）
各电商 SKU 编码不通用，**月报商品维度一律以 NSSKU 聚合**，原始电商 SKU 仅用于溯源（否则同一商品被拆多行）。
映射链：电商 SKU → NSSKU → 型号/度数区间 → 品类。本地库含 4 张表：`exchange_rate`、`shopify_sales_by_order`、产品型号度数范围、nssku 对应映射表（后两张表名待确认）。

## 业务背景不得耦合（用户明确要求，ADR-018）
换公司 / 新业务背景时**只改 `config/profile.yaml` + `.env`**，不改核心代码。
核心代码禁止出现公司名、表名、币种、平台名、商品主键名；**禁止 `if company == xxx` 分支**（差异一律抽象成 profile 参数）。
profile 只放值，每项必须 `source` 指向 `docs/` 口径条目，不复制正文。迁移指南见 `config/profiles/README.md`。

## 配置职责边界（防双源，务必遵守）
`.env` 只放**凭据 / 端点 / 运行参数**；业务默认值（默认接入模式、汇率规则、指标口径）**只在 docs 单源维护**，禁止在 `.env` 重复定义。模板见 `.env.example`。
**多平台口径原则（用户提出）**：内部 canonical 口径单源维护 + 记录各平台官方口径 + 维护映射表；平台口径仅用于溯源对账，不得直接当内部指标用。
