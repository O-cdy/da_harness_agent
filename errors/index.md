# 错误档案索引

> 一错一档。归档后，**同类任务开工前必须检索本索引并注入 planner 上下文**（`AGENTS.md` 守则 0 / 守则 3）。
> 建立：2026-09-22 | 最后更新：2026-09-24 | 状态：生效

## 状态与编号

- 编号：`E-NNNN`，递增不复用。
- 状态：open（未闭环）→ fixed（已修复且有防回归门禁）→ archived（长期无复发，归档留痕）。

## 索引表

| 编号 | 标题 | 模块 | 状态 | 发现日期 | 关联 ADR |
|---|---|---|---|---|---|
| [E-0001](./E-0001-units-caliber-single-month-sample.md) | 件数口径用单月切片定案，双向错误（多算赠品 + 漏算无 SKU 行） | ingest / 口径定案 | fixed | 2026-09-22 | ADR-023 |
| [E-0002](./E-0002-keyword-scan-missed-table.md) | 关键词扫描表名漏掉 `month_basic_data`，误判转化率不可实现 | ingest / 数据源盘点 | fixed | 2026-09-22 | ADR-025 |
| [E-0003](./E-0003-information-schema-estimate-rows.md) | `information_schema.table_rows` 估算值当实测行数（**复发 4 次**） | ingest / 数据源盘点 | fixed（已升级 R-36） | 2026-09-22 | ADR-026 |
| [E-0004](./E-0004-customer-created-at-as-new-customer.md) | 误用 `customer_created_at`（注册时间）判定新客，误差 9.2 倍 | 客户分层口径 | fixed | 2026-09-22 | ADR-026 |
| [E-0005](./E-0005-profile-claimed-aligned-not-written.md) | 复盘写「profile 已对齐」但生效文件未改 | ingest / 配置 | archived（029 修复已撤回） | 2026-09-22 | ADR-030 |
| [E-0006](./E-0006-unauthorized-canon-write.md) | 把参考当确认、替用户拍板写入 canonical | orchestrator / 口径定案 | fixed | 2026-09-23 | ADR-031 |
| [E-0007](./E-0007-shop-sku-model-as-siblings.md) | 把店铺 SKU 与型号画成同级 | orchestrator / 口径定案 | fixed | 2026-09-23 | ADR-035 |
| [E-0008](./E-0008-overstated-confirmed-grain.md) | 把未确认推断写进已确认颗粒度 | orchestrator / 口径定案 | fixed | 2026-09-23 | ADR-036 |
| [E-0009](./E-0009-cross-schema-collation-mismatch.md) | 跨 schema SKU 直接 JOIN 触发 collation 冲突 | ingest / platform adapter | fixed | 2026-09-24 | ADR-068 |
| [E-0010](./E-0010-query-before-schema-contract.md) | 未等 schema 契约返回即猜字段名查询 | ingest / 数据源盘点 | fixed | 2026-09-24 | ADR-068 |

## 已升级为硬规则的错误

| 来源 | 升级后规则 | 内容 |
|---|---|---|
| E-0003（复发 4 次） | **R-36** | 行数一律以 `COUNT(*)` 为准，`information_schema` 估算值不可用于口径判断；**登记行数须同时标注实测日期**（第 4 次连 R-36 自己的产物都混入估算值） |
| E-0006（F-01 第 4 次 + F-04） | **守则 0 + R-49** | 未用户确认禁止写入 canonical；参考 ≠ 确认；每次一问；换 agent / 仓库被更新必须重读宪法 |
| E-0007 | **R-51 / G-19** | 型号只从 NSSKU 行读；禁止店铺 SKU 与型号同级 |
| E-0009 | **R-96** | 跨源关联键必须显式规范化字符集/collation/大小写/空白/Unicode，禁止隐式转换 |

## 错误家族（用于提前预警）

| 家族 | 成员 | 计数 | 处置 |
|---|---|---|---|
| F-01 定案前证据不足 | E-0001、E-0004、E-0005、**E-0006**、**E-0007**、**E-0008** | 6 | 已升级 **守则 0 + R-49**；E-0007 另升 R-51 |
| F-02 用猜测代替全量枚举 / schema | E-0002、E-0010 | 2 | R-36 全量枚举；adapter 查询必须先过 schema contract |
| F-03 估算值当实测值 | E-0003 | 4 | 已升级 R-36 |
| F-04 越权拍板 / 参考当确认 | E-0006、**E-0008** | 2 | 守则 0 + R-49；颗粒度推断不得标已确认 |
| F-05 跨源键未规范化 | E-0009 | 1 | 已升级 R-96 |

## 使用规则

1. 捕获错误 → 新建 `E-NNNN-<slug>.md`（复制 `_template.md`）。
2. 归档 → 在本表登记一行。
3. 注入 → 同类任务开工前检索本表，把命中条目塞进 planner 上下文。
4. 复盘 → 月度合并同类项，重复 3 次以上的错误升级为硬规则（写入 `docs/30-constraints/rules.md`）。
