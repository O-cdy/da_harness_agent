# E-0002 · 用关键词扫描表名找数据源，漏掉 `month_basic_data`，导致误判「转化率不可实现」

| 字段 | 内容 |
|---|---|
| 编号 | E-0002 |
| 发现日期 | 2026-09-22 |
| 模块 | ingest / 数据源盘点 |
| 状态 | fixed |
| 关联 ADR | ADR-025 |
| 关联规则 | R-37 |

## 1. 现象

我在 `data-audit.md` §7 判定「M210 转化率不可实现：主表无 session/visit，独立站流量数据不在此库」。
用户指出：**`month_basic_data` 可以看流量**。实查该表为 `bluetti_new` 下的**视图**，
含 GA4 漏斗 8 列（sessions / engagedSessions / itemViewEvents / checkouts / transactions / totalRevenue / market），8,149 行。

## 2. 触发条件

盘点数据源时用关键词过滤表名：
`cost / price / margin / cogs / ad_ / ads / advert / traffic / session / visit / inventory / stock / fulfil / ship / promo / campaign / budget`
—— `month_basic_data` 不含任何上述关键词，且是**视图**（当时只扫了 BASE TABLE），故完全漏检。

## 3. 根因

- 表象根因：关键词表不完备，且未扫描 VIEW。
- **架构根因**：用「猜名字」代替「枚举全量」。information_schema 一次 `SELECT table_name, table_rows WHERE table_schema=?`
  就能拿到全部表与视图，成本极低；关键词过滤省下的成本远小于漏检的代价。

## 4. 最小复现

```
错误做法：SELECT table_name FROM information_schema.tables
          WHERE table_schema='bluetti_new' AND (table_name LIKE '%session%' OR ...)   -- 0 命中
正确做法：SELECT table_name, table_rows FROM information_schema.tables
          WHERE table_schema='bluetti_new' ORDER BY table_name                       -- 32 表 + 5 视图
```

## 5. 修复

- 改为**全量枚举**：两库 32+31 张表与 5+3 个视图全部列出，写入 `data-audit.md` §8；
- M210 由「不可实现」改为「可实现」，数据源 = `month_basic_data`，口径定案见 ADR-025；
- 新增 R-37（转化率必须同源）。

## 6. 防回归门禁

- **门禁（流程级）**：数据源盘点禁止关键词过滤，**必须枚举 `information_schema.tables` 全量（含 VIEW）**。
- 已写入 `data-audit.md` §8 开头的白名单表，作为后续接入的唯一入口。

## 7. 复盘备注

第 1 次。同类风险：任何"用关键词/正则代替全量枚举"的盘点动作都可能漏。
若再犯第 2 次，升级为硬规则写入 `rules.md`。
