# E-0001 · 件数口径用单月切片定案，导致双向错误（多算赠品 + 漏算无 SKU 行）

| 字段 | 内容 |
|---|---|
| 编号 | E-0001 |
| 发现日期 | 2026-09-22 |
| 模块 | ingest / 口径定案流程（尚未进代码，定案阶段捕获） |
| 状态 | fixed |
| 关联 ADR | ADR-023（同批次定案） |
| 关联规则 | R-30（v2） |

## 1. 现象

R-30 v1 定案为 `件数 = SUM(quantity) WHERE sku IS NOT NULL AND quantity > 0`。
复核（近三年 953,639 行）后实测：

```
近三年件数对比：
  v1: sku非空 & qty>0           537,791
  v2: qty>0 且 gross<>0         484,657      ← 差 9.9%
被 v1 排除的金额：114,775,280 CNY（5.05%）
赠品行（gross=0 & qty>0）：40,515 行 / 64,587 件
无 SKU 但有金额（sku IS NULL & gross<>0 & qty>0）：10,310 行 / 90,912,458 CNY（4.00%）
```

件单价随之从 4,227.6 变成 4,691.2（**差 11%**）。

## 2. 触发条件

定案时只取 **2026-08 单月**切片做统计分析，且该月恰好无 SKU 行的金额几乎为 0（929 元），
掩盖了「无 SKU 行在全期贡献 4% 金额」这一事实；同时该月赠品行占比也未单独统计。

## 3. 根因

- 表象根因：v1 排除了有金额的无 SKU 行，又纳入了零金额的赠品行。
- **架构根因（方法论级）**：用**小样本（单月）**推导**全局口径定义**。
  数据质量在逐年改善（无 SKU 行金额占比：2023 约 30% → 2026 年 0.1%），
  单月切片无法代表历史区间，必然漏掉已在历史期存在的大量异常行。

## 4. 最小复现

```sql
SELECT SUM(quantity) FROM shopify_sales_by_order WHERE sale_date>='2026-08-01' AND sale_date<'2026-09-01' AND sku IS NOT NULL AND quantity>0;  -- 15,049
SELECT SUM(quantity) FROM shopify_sales_by_order WHERE sale_date>='2023-09-01' AND sku IS NOT NULL AND quantity>0;                              -- 537,791
SELECT SUM(quantity) FROM shopify_sales_by_order WHERE sale_date>='2023-09-01' AND quantity>0 AND gross_sales<>0;                                -- 484,657
```

## 5. 修复

- R-30 改为 v2：`件数 = SUM(quantity) WHERE quantity > 0 AND gross_sales <> 0`；
- `data-audit.md` §3 记录 v1 作废原因与四类行处理约定；
- `metrics.md` M104 同步为 v2。

## 6. 防回归门禁

- **门禁（流程级）**：任何指标口径定案，**必须用覆盖报告期全长的全量数据验证**（本项目 = 近三年），
  禁止用单月切片下结论。已写入 `data-audit.md` §3 与 E-0001。
- 复用规则：errors/index.md 第 4 条「重复 3 次以上升级为硬规则」—— 本类「小样本定案」若再犯第 2 次即升级为硬规则。

## 7. 复盘备注

第 1 次（本类：小样本 / 单切片推导全局口径）。
连带教训：核验发现的问题必须在**同一量级的数据**上复核，不能只复核"看起来对"的那部分。
