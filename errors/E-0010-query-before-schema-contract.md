# E-0010 · 未等 schema 契约返回即猜字段名查询

> 唯一职责：记录 TikTok Affiliate 探针因猜字段名失败及防回归门禁。
> 版本 v1.0 | 最后更新 2026-09-24 | 状态：生效

| 字段 | 内容 |
|---|---|
| 编号 | E-0010 |
| 发现日期 | 2026-09-24 |
| 模块 | ingest / 数据源盘点 |
| 状态 | fixed |
| 关联 ADR | ADR-068 |
| 关联规则 | R-36 / R-83 |

## 1. 现象

`(1054, "Unknown column 'order_create_time' in 'field list'")`

## 2. 触发条件

并行发起 `DESCRIBE tiktok_affiliate_orders` 与聚合查询，在 schema 结果返回前猜测时间字段为 `order_create_time`；真实字段为 `time_created`。

## 3. 根因

- 表象根因：字段名猜错。
- 架构根因：探针未建立“先读取 schema contract，再生成字段引用”的依赖顺序，复发了 E-0002 的猜测式盘点家族。

## 4. 最小复现

```sql
SELECT MIN(order_create_time)
FROM bluetti_new.tiktok_affiliate_orders
LIMIT 1;
```

## 5. 修复

读取真实 schema 后改用 `time_created`，查询成功。S1 adapter 必须从 schema contract 校验字段，不允许未声明字段进入 SQL。

## 6. 防回归门禁

R-36 / R-83；数据源盘点的依赖顺序固定为：枚举表 → DESCRIBE → 生成查询 → 执行。并行仅限互不依赖的表。

## 7. 复盘备注

与 E-0002 同属“用猜测代替 schema 枚举”家族，本次为该家族第 2 次。
