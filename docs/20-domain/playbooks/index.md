# Playbook 注册表

> 唯一职责：登记可被编排器按 id 加载的场景剧本，以及预留剧本。正文步骤仍在各 playbook 文件。
> 版本 v0.2 | 建立：2026-09-24 | 最后更新：2026-09-24 | 状态：**生效**（登记；机器 manifest 与实现未开工）。ADR-067/068：核心不绑定单一场景或平台。

关系：入口 `run --playbook <id>` 经 registry 加载机器可读 manifest；本表与各 Markdown 只供人阅读。`ask` 不经过本表（探索路径）。新增场景 = 注册 manifest + 说明，不改编排器。

| id | 说明文件 | 计划中的 manifest | 状态 | 说明 |
|---|---|---|---|---|
| `monthly-business-review` | `monthly-business-review.md` | `monthly-business-review/manifest.yaml` | 已规划，第一份验收剧本 | 跨平台 canonical 总览 + 平台章节/原生附录（ADR-068） |
| `user-behavior` | （未建） | （未建） | **预留** | 用户行为分析。首期无事件 capability；启用前只许「无数据」 |
| `ads-spend` | （未建） | （未建） | **预留** | 广告费用分析。首期无 ads capability |
| `echo` | 仅测试夹具 | `tests/fixtures/playbooks/echo.yaml` | 合同测试用 | S0 证明核心可加载非月报剧本（ADR-067） |

> 表中“预留”项不要求现在创建正文或空目录；启用时再新增受引用的 manifest（R-81）。

manifest 必填：`id / contract_version / steps / metric_refs / skill_refs / rule_packs / required_capabilities / time_scope / outline / approval_policy / eval_overlays`。Registry 禁止解析 Markdown 推导步骤（R-86）。

未列入且无 `ask` 计划的问题：不得出正式报告数字（R-02 / G-07）；可按 provisional 规则生成探索草稿。
