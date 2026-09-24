# E-0005 · 复盘写「profile 已对齐」但生效文件未改

| 字段 | 内容 |
|---|---|
| 编号 | E-0005 |
| 发现日期 | 2026-09-22 |
| 模块 | ingest / 配置 |
| 状态 | archived（文件保留；ADR-029 的「修复」已按 ADR-030 撤回，profile 故意回到改前值并标待对齐） |
| 关联 ADR | ADR-029（未生效）/ ADR-030 |
| 关联规则 | R-46（随 ADR-029 撤回，不生效） |

## 1. 现象

`PROJECT_STATUS.md` 第 6.1 节第 9 条写：`profile.yaml` 客户主键 / 目标维度 / 映射表 / 转化率「已全部对齐」，并新增 `new_customer_rule`。独立复核读到的文件仍是 `identity_key: customer_id`、`dimensions: [month, site, category]`、`mapping_tables: null`，没有 `new_customer_rule`。

## 2. 触发条件

Edit 工具返回成功但未写入（同轮已登记的工具缺陷），且未 grep 复核就宣布完成。

## 3. 根因

- 表象根因：配置文件与复盘声明不一致。
- 架构根因：把「进度文档写了已修复」当成「生效配置已修复」。进度文档不是配置源。

## 4. 最小复现

打开 `config/profile.yaml` 搜 `identity_key` / `targets.dimensions` / `mapping_tables`，与 `PROJECT_STATUS` 第 6.1 节第 9 条对照。

## 5. 修复

ADR-029 曾把 gid / 目标维 / 映射表 / 商品双路径写入 `profile.yaml`，当作本条的修复。2026-09-23 用户要求撤回：那些写入未对齐，按 ADR-030 已回滚。本条记录的**过程错误**仍成立——进度文档宣称对齐 ≠ 生效配置已改。回滚后的 profile 是故意的「待对齐」，不是又一次静默撒谎。

## 6. 防回归门禁

R-46 随 ADR-029 撤回，**不生效**。防回归仍靠：改配置后立刻 grep 复核，不采信 Edit 返回状态。

## 7. 复盘备注

与 F-01 同源（未充分核验就宣布定案）。F-01 已 3 次（E-0001、E-0004、本条）。R-46 未生效。
