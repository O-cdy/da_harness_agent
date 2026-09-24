# E-0009 · 跨 schema SKU 直接 JOIN 触发 collation 冲突

> 唯一职责：记录 TikTok SKU 与共享 NSSKU 映射跨 schema 关联失败及防回归门禁。
> 版本 v1.0 | 最后更新 2026-09-24 | 状态：生效

| 字段 | 内容 |
|---|---|
| 编号 | E-0009 |
| 发现日期 | 2026-09-24 |
| 模块 | ingest / platform adapter |
| 状态 | fixed |
| 关联 ADR | ADR-068 |
| 关联规则 | R-96 |

## 1. 现象

`(1267, "Illegal mix of collations (utf8mb4_0900_ai_ci,IMPLICIT) and (utf8mb4_general_ci,IMPLICIT) for operation '='")`

## 2. 触发条件

直接用 `bluetti_new.tiktok_sales_by_order.seller_sku = shared_data.nssku对应映射表.名称` 跨 schema JOIN。

## 3. 根因

- 表象根因：两列 collation 不同。
- 架构根因：平台适配层缺少统一的关联键规范化契约，依赖数据库隐式转换。

## 4. 最小复现

```sql
SELECT 1
FROM bluetti_new.tiktok_sales_by_order t
JOIN shared_data.`nssku对应映射表` m ON t.seller_sku = m.`名称`
LIMIT 1;
```

## 5. 修复

规划中要求 adapter 在 JOIN 前显式统一字符集/collation，并登记大小写、空白与 Unicode normalization 策略；实测使用显式 `CONVERT(... USING utf8mb4) COLLATE utf8mb4_general_ci` 后完成覆盖率核验。

## 6. 防回归门禁

R-96；S1 adapter 合同测试必须覆盖不同 collation 的同值 SKU 与规范化后未命中桶。

## 7. 复盘备注

首次。不能只在单条 SQL 上补 `COLLATE`，规范化必须成为所有跨源键的 adapter 契约。
