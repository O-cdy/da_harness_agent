# 10 · 架构与模块职责（唯一定义处）

> 唯一职责：定义架构与模块职责。本文件是架构事实的唯一来源，`PROJECT_STATUS.md` 第 2 节只做链接引用。
> 版本 v0.4 | 建立：2026-09-22 | 最后更新：2026-09-24 | 状态：**生效**（能力层为「已规划·未实现」；S0 代码未开工）。ADR-029 写入已撤回（ADR-030）。产品化分期见 ADR-066；核心与场景解耦见 ADR-067；跨平台 canonical 内核、TikTok 首阶段接入与生产运行契约见 ADR-068。

## 1. 分层

```
┌─ 入口层 ──── harness/cli/（S0：`run` + `ask` 并列） · harness/web/（预留） · harness/schedule/（预留）
├─ 编排层 ──── harness/core/orchestrator/   registry 加载剧本 → plan.md（C1）；`ask` 走探索
├─ 注册层 ──── harness/core/registry/       playbook / metric / skill / tool / adapter / rule-pack / provider
├─ 规范层 ──── harness/core/canonical/      跨平台订单 / 行项 / 退款 / 商品 / 客户 / 流量 / 归因契约
├─ 适配层 ──── harness/core/adapters/       Shopify / TikTok → canonical；声明 capability
├─ 能力层 ──── harness/core/skills/         可复用能力单元（受 policy 约束）
├─ 工具层 ──── harness/core/tools/（SQL / Python） · harness/mcp/（预留）
├─ 模型层 ──── harness/core/llm/            provider 可插拔，strong/light，env 门控
├─ 记忆层 ──── harness/core/memory/         口径 / 错误 / 证据包；session·vector 预留
├─ 策略层 ──── harness/core/policy/         组合 core/domain/platform/playbook rule packs
├─ 核心层 ──── ingest · executor · validator · evaluator · reporter
├─ 观测层 ──── harness/core/trace/          span 轨迹；OTel 导出预留
├─ 契约层 ──── runs/<task>/{source_manifest.json, plan.md, sql/, artifacts/, report/, metrics.json, trace.jsonl}
└─ 事实层 ──── docs/ · errors/ · config/profile.yaml（业务配置按组织/profile 隔离）
```

核心原则：**入口可换、平台可换、核心不变；平台原始数据必须先经 adapter；报告只消费证据包，不碰数据源；未实现能力有稳定 Port + 显式 no-op，不改调用点。**

行业对应（ADR-066 / ADR-067，检索 2026-09-24）：Agent = Model + Harness。本产品的交付物是通用数据分析 harness，不是经营月报专用机。月报只是第一份确定性剧本。

## 1.1 五个易混概念的职责边界

| 概念 | 是什么 | 存放位置 | 被谁用 |
|---|---|---|---|
| **Rule** | 硬约束（必须 / 禁止），可机器加载 | `docs/30-constraints/rules.md` | policy + 所有层 + 校验器 |
| **Playbook** | 场景剧本（月报分几步、每步做什么） | `docs/20-domain/playbooks/` | 编排器 |
| **Skill** | 可复用能力单元（**一件事的方法**：量价拆解、归因、异常检测…） | `harness/core/skills/`（实现）+ `docs/20-domain/skills/`（说明） | 编排器调用 |
| **Tool** | 本地执行能力（SQL 查询、Python 计算），只读 | `harness/core/tools/` | skill 调用 |
| **MCP** | 外部系统接入协议（平台开放 API / ERP / 文档库），**当前不需要，预留** | `harness/mcp/` | tool / skill 调用 |

关系：**playbook 编排 skills → skills 调用 tools → 全程受 policy/rules 约束**。
Skill 本身不含公司特定值，需要参数时从 `config/profile.yaml` 读（守则 7.5）。**Skill 禁止依赖「当前正在跑经营月报」**（ADR-067 / R-82）。

## 1.2 LLM 的定位：可选，不是必经路径

| 路径 | 触发条件 | 是否需要 LLM | 可复现性 |
|---|---|---|---|
| **确定性路径** | `run --playbook <id>`，剧本已固化 | **不需要** —— 按该剧本 + skills 执行 | 完全可复现 |
| **探索路径** | `ask <问题>`，尚无剧本或即席 SQL | 需要 LLM 生成 plan.md，或人工写入 plan.md → C1 | 审核后可固化成新剧本 |

因此 `无 key 即 no-op` 的实际含义是：**没有 LLM 时，已固化剧本照常 `run`**；`ask` 不可自动出计划，但命令必须存在，允许人工补 `plan.md`。不得把 `ask` 做成月报的别名。

调用留痕：每次 LLM 调用必须记录 `model / prompt_hash / token / response_hash` → 写入 `metrics.json`（可复现三要素之一）。探索循环的每一步另写入 `trace.jsonl`。

## 2. 模块职责

| 模块 | 输入 | 输出 | 职责 | 约束点 | 首期 |
|---|---|---|---|---|---|
| Registry | 磁盘上的 playbook/skill/tool 清单 | 可发现目录 | 按 id 解析实现，禁止硬编码调用表 | 未注册不得调用 | S0 |
| Orchestrator | 目标或 playbook id + 口径引用 + 记忆 | `plan.md`（DAG） | `run` 按 registry 展开剧本；`ask` 走探索（LLM 或人工 plan） | 禁止写死某一剧本（R-82）；未声明数据源或口径 → 不得取数（C1） | S0 壳 / S2 接通 |
| Policy | scoped rule packs + profile + plan | 放行 / 阻断 | 组合 core/domain/platform/playbook 四层规则；输入、工具、输出护栏 | 未声明 scope 的平台/剧本规则不得全局加载 | S0 加载 / S2 执行 |
| Memory | docs / errors / 上期 runs | 装配上下文 | 见 §10 | 上期数字不得当本期事实（R-80） | S0 读适配 |
| Platform Adapter | 平台原始表/API + profile | canonical facts + capability report | 隔离字段、状态、时点、粒度和平台口径差异 | 原始表名不得泄漏到 Playbook/Skill | S1 |
| Metric Registry | metric id + canonical facts | `MetricResult` | 解析 canonical / platform-native / provisional / diagnostic 实现 | 编排器禁写 `compute_mxxx()` 分支 | S0 壳 / S3 实现 |
| Ingest | 配置 + MySQL / 本地文件 | 逐源 manifest + Artifact Envelope | 双通道接入、快照、水位、schema 指纹 | 每个源独立 hash；无凭据 no-op，禁止静默降级 | S1 |
| Executor | `plan.md` + 数据 | 中间结果 + SQL/代码留档 | 每维度独立 SQL、沙箱执行 | 只读（R-04）；月报须时间窗、允许无 LIMIT（R-79）；ad-hoc 须 LIMIT；R-10 | S2 |
| Validator | 中间结果 + 源数据 | 断言报告 | 对账、量纲、空值率、同比环比、显著性 | 阻断级失败 → 不得出报告 | S5 |
| Evaluator | 断言 + 报告草稿 + eval overlays | rubric 分数 + 错误归档 | 通用量表 + 当前 playbook overlay；失败落 `errors/E-NNNN` | 禁止强制所有场景执行月报指标 | S5 |
| Reporter | `runs/` 证据包 + `plan.outline` | `report.md` + `charts.html` | 按计划大纲渲染，禁止写死月报六章 | 只消费证据包 | S6 |
| LLM | prompt + schema | 结构化计划或解释文本 | 分层路由；禁止产出作为事实的数字 | 无 key 显式 no-op | S0 no-op / S7 接通 |
| Trace | 每步 span | `trace.jsonl` | 工具、护栏、LLM、handoff 轨迹；可回放 | 不得含凭据 | S0 文件 / 导出预留 |
| MCP | 外部系统 | 工具结果 | 平台 API / ERP / 文档库 | 未启用显式 no-op | 预留 |
| Web / Schedule / Plugins | — | — | 见 §9 预留槽 | 未启用显式 no-op | 预留 |

## 3. agent 与工具 / 模型的交互方式

- **LLM 只做规划与解释，不做算术。** 任何数字必须由 SQL / Python 产出；LLM 输出的数字一律视为无效，除非能在证据包中找到对应计算过程。
- **工具调用全部结构化**：所有工具走显式 schema，参数与返回值入 trace，禁止自然语言隐式调用。
- **模型分层路由**：编排 / 校验 / 报告用强模型；格式化与分片汇总用轻量模型。provider 可插拔，env 切换，无 key 即 no-op。
- **代码留档优先于代码优雅**：派生计算（groupby / 透视 / 同比环比）自动放行，但代码全量入 `runs/<task>/sql|artifacts/`。
- **Handoff**：技能之间用注册表 id 交接，不把状态塞进一段超长 prompt。多 agent 运行时目录预留，首期单编排器。

## 4. harness 的三层机制

| 层 | 机制 | 具体手段 |
|---|---|---|
| **约束**（前置） | policy 加载规则 + 指标白名单 + 工具 schema | `rules.md`：SQL 只读、月报须时间窗、禁臆造、指标必须来自字典 |
| **监控**（过程） | 全链路 trace + checkpoint 断言 + token 预算 | 每步入 `trace.jsonl`；中途断言失败即中止；预算超限告警 |
| **评估**（后置） | rubric + 重跑一致性 + 轨迹回放（预留） | `eval-rubric.md`；同输入重跑数字必须一致 |

## 5. 三级人工卡点

| 卡点 | 审核对象 | 放行条件 | 不通过后果 |
|---|---|---|---|
| C1 | `plan.md` | 每个引用指标能在 `metrics.md` 找到条目；数据源可解析出 manifest。**同 playbook + 同口径版本首次放行后可自动放行**（ADR-057） | 回炉重规划 |
| C2 | 原料 SQL（不含派生） | 只读、行数上限内、字段与口径映射匹配。**同上，首次放行后可自动**（ADR-057） | 阻断执行 |
| C3 | 报告 + 证据包 | rubric 四项通过 + 与源数据对账一致 | 落 `errors/E-NNNN`，修复后重跑 |

**自动放行**：派生 groupby、透视、同比环比、格式化、图表渲染 —— 全量留档，事后按 C3 追溯。同模板同口径的 C1/C2 重跑亦自动放行（ADR-057），计划和 SQL 仍留档。**C3 每次都审。**

## 6. 目录结构（按稳定接口演进）

```
harness/
├── core/
│   ├── contracts/       # Protocol / ABC / 错误类型；所有模块只依赖这里
│   ├── registry/        # playbook / metric / skill / tool / adapter / rule-pack / provider
│   ├── orchestrator/    # 只经 registry 展开剧本；禁止写死月报（ADR-067）
│   ├── canonical/       # 平台中立事实契约与 schema version
│   ├── adapters/        # Shopify / TikTok；以后平台以插件注册
│   ├── metrics/         # MetricPort 实现，按 id 注册
│   ├── policy/          # 四层 rule pack 组合、SQL AST、PII/secret 护栏
│   ├── memory/
│   │   ├── caliber.py       # 读 docs 索引 + profile（实现）
│   │   ├── errors.py        # 读 errors/index，注入 planner（实现）
│   │   ├── episodes.py      # 读上期 runs，禁止当本期事实（实现）
│   │   ├── session.py       # 【预留】对话工作记忆
│   │   └── vector.py        # 【预留】向量检索
│   ├── skills/          # SK-01~08 实现位；由 Playbook/Plan 按 capability 编排
│   ├── tools/
│   │   ├── sql/
│   │   └── python/
│   ├── llm/             # provider 可插拔；无 key 显式 no-op
│   ├── ingest/
│   │   ├── mysql/
│   │   ├── files/
│   │   └── platforms/   # 只放已启用 adapter；未来平台不提前铺空目录
│   ├── executor/        # 沙箱执行、代码留档
│   ├── validator/
│   ├── evaluator/
│   ├── reporter/
│   └── trace/           # jsonl span；otel.py 【预留】
├── mcp/                 # 【预留】client/ + server/
├── cli/                 # `run --playbook` 与 `ask` 并列（ADR-067）
├── web/                 # 【预留】HTTP，只调 core
├── schedule/            # 【预留】周期性任务（不绑定月报）
├── plugins/             # 【预留】外部 skill / adapter 包
├── config/              # 读取 docs/ 与 config/profile.yaml
└── tests/
    ├── unit/
    ├── contract/        # 预留槽的接口稳定性
    └── replay/          # 【预留】轨迹回放评估
```

运行环境：托管 Python 3.13.12 + 独立 venv，依赖不污染全局。
S0 必须冻结 Port、注册类型与 no-op 语义；只创建当前实现需要的包。未来平台通过 registry/plugin 增加实现，**不要求为每个平台预建空目录**（ADR-068 修订 R-81）。

## 7. 能力层落地计划（Skills / MCP / LLM）

| 项 | 状态 | 落地时机 |
|---|---|---|
| **LLM provider** | 原则已定（ADR-006）+ `.env` 配置位已留；**接口与调用留痕未实现** | S0 no-op 接口；S7 接通 |
| **Skills** | **已规划** —— SK-01~08 契约见 `docs/20-domain/skills/index.md` | SK-07 随 S0；SK-08 随 TikTok 原生模块；其余按 S4～S7 |
| **MCP** | **预留** —— 当前 MySQL + 本地文件用不上 | 接入外部系统时填 `harness/mcp/`，不改 skill 调用签名 |
| **Memory** | **已规划**（ADR-066） | S0 读适配；session/vector 保持 no-op |

**首批 Skill 契约**（详见 `docs/20-domain/skills/index.md`）：

| 编号 | Skill | 对应指标 / 规则 | 首期 |
|---|---|---|---|
| SK-01 | 量价拆解 | M401 | S4 |
| SK-02 | 维度归因贡献度（要求互斥可加） | M402 / R-06 / R-78 | S4 |
| SK-03 | 异常检测（**含大促窗口识别**） | R-12 / R-70 | S4 |
| SK-04 | 口径校验（对账 / 量纲 / 空值率） | Validator | S5 |
| SK-05 | 报告框架 | Reporter | S6 |
| SK-06 | 输出精简（配合 light model） | ADR-006 | S7 |
| SK-07 | 记忆装配 | R-80 | S0 薄封装 |
| SK-08 | 平台原生分析 | R-84 / R-87 / ADR-068 | S4（TikTok Affiliate/LIVE） |

SK-03 与 SK-05 可直接从 ima 知识库资产翻译：`20260327_大促对AB的影响`（大促前后复购塌陷）→ 大促窗口识别；
`review-report-data-analysis-reporting.md`（报告框架）→ SK-05。证据等级：摘要级（B-01）。

## 8. 行业控制面映射（ADR-066）

规划不另开文件。本表把行业原语钉在本仓库模块上，避免后期用第三方框架把分层冲掉。

| 行业原语 | 本产品落点 | 首期策略 |
|---|---|---|
| 控制循环 | Orchestrator：任意 playbook 展开；`ask` = 探索循环 | S0 两个入口都在；LLM 后接 |
| Tools + schema | `core/tools` + registry | S2 SQL 工具（月报与 ad-hoc 共用） |
| Guardrails | `core/policy` + C1/C2/C3 | S0 加载文本规则；S2 执行 SQL 护栏 |
| Memory | `core/memory` 三类文件源 | 工件优先；按 playbook 指纹检索 |
| Tracing | `core/trace` → `trace.jsonl` | S0 写文件；OTel 预留 |
| Evals | Evaluator + rubric；`tests/replay` 预留 | S5 |
| HITL | C1 / C2 / C3 | ADR-057 |
| Session | `memory/session.py` | 预留，默认关 |
| Handoffs | skill id 交接；多 agent 运行时预留 | 首期单编排器 |
| MCP | `harness/mcp/` | 预留 |
| Sandbox | Executor | S2 进程内只读；隔离升级预留 |
| Scheduler | `harness/schedule/` | 预留；调用 `run --playbook`，不绑死月报 |

禁止把任一场景做成「一个 notebook 里跑完」。禁止在 core 内 `import harness.cli` 或反向依赖入口。禁止编排器硬编码某一 playbook（R-82）。

## 9. 预留槽位（接口先在，实现后填）

| 槽 | 路径 | 为何预留 | 填入时不得改动的调用点 |
|---|---|---|---|
| Web 入口 | `harness/web/` | ADR-003 后接 Web，复用 core | `core` 不感知 HTTP |
| 调度 | `harness/schedule/` | 周期性任务 | 只调与 CLI 相同的 `run_playbook(id)`，id 来自配置 |
| MCP | `harness/mcp/` | 外部系统 | tools 经 registry 调 port，不直连 SDK |
| 插件 | `harness/plugins/` | 第三方 skill | registry 扫描入口已留 |
| 新平台接入 | adapter plugin + platform rule pack | Amazon/eBay/AliExpress/第三方后接 | `PlatformAdapterPort` 与 canonical schema |
| 广告花费 | adapter capability `ads` + playbook `ads-spend` | 费用类 R-42 暂不纳入 | 无源时只许「无数据」 |
| 用户行为 | playbook `user-behavior` | 首期无行为事件表白名单 | 同上，不改编排器 |
| 渠道 / UTM | playbook 维 + ingest 字段 | ADR-024 首期禁止当归因维 | 维度注册表可加维，不改 M102 公式 |
| 成本利润计算 | metrics M201–M206 条目已留档 | R-42 不纳入设计范围 | 指标注册表按状态跳过，不删编码 |
| 大促日历事件 | `profile.promo_calendar` | 用户暂不提供 | SK-03 已处理 `calendar_missing` |
| Session 记忆 | `memory/session.py` | Web 多轮对话 | MemoryPort 多后端 |
| 向量记忆 | `memory/vector.py` | 工件记忆不够时 | 同上；禁止当口径源 |
| OTel 导出 | `trace/otel.py` | 生产观测 | TracePort |
| 租户 / 鉴权 | `AuthPort`（实现时建包） | 多品牌 profile 之上 | CLI 不依赖鉴权 |
| 多 agent | `AgentHandoffPort`（实现时建包） | 以后分工编排 | OrchestratorPort |
| 轨迹回放评估 | `tests/replay/` | 回归数据集 | 读 `trace.jsonl`，不重连生产库 |

未启用时：对应 Port 的实现必须 raise / 返回结构化 `noop`，带 `module_id` 与原因，写入 trace。禁止静默跳过成另一条通路（守则 4 / R-81）。

## 10. 记忆层（ADR-066 / R-80）

记忆是控制面的一部分，不是聊天机器人的附赠。分层如下。

| 类型 | 源 | 谁读 | 谁写 | 首期 |
|---|---|---|---|---|
| 语义 / 口径 | `docs/` + `config/profile.yaml` | planner、validator | 人改 SSOT，agent 不写口径 | 实现 |
| 程序 / 失败 | `errors/index.md` + E-NNNN | planner 开工注入 | evaluator 失败时追加 | 读实现；写随 S5 |
| 情节 / 工件 | `runs/<task>/` | 需要时引用**同 playbook 指纹**的上期结论 | 每次任务结束 | 读实现 |
| 工作 / Session | 预留 | Web 多轮 | 预留 | no-op |
| 向量 | 预留 | 探索检索 | 预留 | no-op |

硬约束：上期 `metrics.json` 的数字不得直接当作本期 M101–M507；本期必须重算。上期只允许提供叙事线索与指纹（同 playbook / 同口径版本）。向量库不得升格为口径。开发 agent 的会话记忆不是本产品的记忆层。

## 11. 施工切片（S0 待确认后才写代码）

每一刀必须：可安装、可跑通该刀的测试、证据留在 `runs/` 或 `tests/`。不用假数据连库（S1 起）。月报聚合在 SQL 侧完成，返回的是聚合结果；`MAX_QUERY_ROWS` 约束的是结果行数，不是事实表扫描行数。

| 切片 | 目标 | 做 | 不做 | 完成判据 |
|---|---|---|---|---|
| **S0 骨架** | 产品外壳可启动 | contracts + typed registry；CLI `run --playbook`、`ask`、`playbooks`、`--help`；机器可读 fixture manifest；Run 状态机 / ErrorEnvelope / Artifact Envelope；预留槽 no-op Port；policy / memory / trace | 业务 SQL、真库、把 ask 做成 monthly 别名、为未来平台铺空目录 | 无凭据启动不崩；`ask` 无 LLM 时显式 no-op；非月报 fixture 可加载；无效状态迁移/manifest 被拒绝 |
| **S1 接入** | 两平台快照可复现 | mysql + files 双通道；Shopify/TikTok adapter；canonical schema；逐源 manifest + schema/hash/watermark；capability matrix；PII 默认拒绝 | 指标计算、Affiliate/LIVE 结论 | 无凭据显式报错且不降级；两平台均产出 canonical 合同样本；PII 不进入工件 |
| **S2 执行** | 原料 SQL 受控 | SQL AST 只读护栏；rule-pack scope；月报时间窗（R-79）；ad-hoc LIMIT（R-04）；完整审批指纹；分支 `awaiting_alignment` | 归因技能 | 无时间窗月报 SQL、ad-hoc 无 LIMIT、错 scope 规则均被阻断；独立分支可继续留证据 |
| **S3 规模效率** | 跨平台 canonical 出数 | MetricRegistry；M101–M106/M207；Shopify/TikTok 映射与覆盖率；platform-native 指标隔离；provisional/diagnostic 状态 | 把指标写死在编排器；强行补齐缺能力 | 两平台统一总览可复算；TikTok 样品/取消/赠品/退款断言通过；未映射商品进桶 |
| **S4 场景能力** | 第一份剧本中后段 + TikTok 原生扩展 | 月报编排可用指标；SK-01/02/03；TikTok Affiliate/LIVE 只读模块；能力不足按 overlay 跳过 | 把 Skill 做成月报私有函数；原生归因进 canonical 合计 | Skill 单测不依赖月报；Affiliate/LIVE 官方口径与归因窗口有来源 |
| **S5 校验评估** | 出得去、挡得住 | Validator + Evaluator + 错误归档；C3 清单 | Web | 阻断级失败无报告；错误有 E-NNNN |
| **S6 报告** | 按 plan 大纲渲染 | SK-05 读 `plan.outline`；月报验收用月报大纲 | 写死经营月报六章 | 换 fixture 大纲能出不同结构的 md |
| **S7 探索路径** | LLM 填充 `ask` | provider 接通；SK-06；无 key 时 `run` 不退化、`ask` 仍显式 no-op | 对话 Session、MCP | 有 key 能出 C1 草稿；无 key 已固化剧本仍可 `run` |

S0 未完成前不准开始 S1。跳切片视为无效交付。S7 之后才考虑填 Web / MCP / 调度，各自单独 ADR。

## 12. 稳定接口（S0 必须落地的 Port，本条只定义名字）

实现放 `harness/core/contracts/`。规划阶段只锁名字与方向，不写 Python。

| Port | 方向 | 调用方 |
|---|---|---|
| `PlaybookPort` | 读剧本步骤 | Orchestrator |
| `PlatformAdapterPort` | `extract -> normalize -> capability report` | Ingest / Orchestrator |
| `MetricPort` | `compute(metric_ref, canonical, ctx) -> MetricResult` | Orchestrator / Skill |
| `RulePackPort` | 按 scope 解析规则包 | Policy |
| `SkillPort` | `run(ctx) -> SkillResult` | Orchestrator |
| `ToolPort` | `invoke(name, payload) -> ToolResult` | Skill |
| `LlmPort` | `complete(messages, schema) -> LlmResult \| NoOp` | Orchestrator / SK-06 |
| `IngestPort` | `snapshot(plan) -> Manifest` | Orchestrator |
| `ExecutorPort` | `execute(plan, manifest) -> Artifacts` | Orchestrator |
| `ValidatorPort` | `assert_(artifacts) -> AssertionReport` | Orchestrator |
| `EvaluatorPort` | `score(report, assertions) -> EvalResult` | Orchestrator |
| `ReporterPort` | `render(run_dir) -> ReportFiles` | Orchestrator |
| `MemoryPort` | `assemble(task) -> MemoryBundle` | Orchestrator |
| `PolicyPort` | `check(event) -> Allow\|Deny` | 工具调用前后 |
| `TracePort` | `span(...)` | 全层 |
| `ApprovalPort` | 指纹生成、首次放行与失效 | Orchestrator / Policy |
| `ArtifactStorePort` | 原子写入、幂等读取、逐源 manifest | 全层 |
| `McpPort` | no-op until enabled | Tool registry |
| `SchedulePort` / `AuthPort` / `SessionPort` / `VectorPort` | no-op | 入口或 Memory |

新增能力只加 Port 实现并在 registry 登记，不改 Orchestrator 主干签名。

## 13. 核心与场景解耦（ADR-067 / R-82）

产品是通用数据分析 harness。经营月报、用户行为、广告费用、即席 SQL 都是场景；场景只能以 playbook 或 `ask` 的形式挂在核心上。

| 禁止 | 必须 |
|---|---|
| 编排器 `import` 月报 md 或写死九步 / 六章 | 只按 playbook id 向 registry 要步骤 |
| CLI 只有出月报 | S0 起 `run --playbook`、`ask`、`playbooks` 并列 |
| Skill 读取「当前是否月报」才工作 | Skill 只认指标编码 + `ctx` |
| Reporter 写死经营月报章节 | 大纲来自 `plan.outline` |
| 把新问题塞进月报当新章 | 新场景新增 playbook id，或走 `ask` 再升格 |
| `ask` 内部转调 monthly | `ask` 无剧本就走探索；无数据就 G-07 |

S0 合同测试最低要求：用 `tests/fixtures/playbooks/echo.yaml`（两步空操作）跑通 registry → orchestrator → no-op tools。经营月报不得作为这条测试的唯一输入。

剧本目录见 `docs/20-domain/playbooks/index.md`。

## 14. 跨平台 canonical 数据面（ADR-068）

canonical 是平台事实的最小公共语言，不是把所有平台字段塞进一张宽表。

| 实体 / 事件 | 必需键 | 核心字段 | 说明 |
|---|---|---|---|
| `OrderFact` | `platform + shop_id + order_id` | created/paid/cancelled、currency、status、is_sample | 同时保留多事件时间；指标自行声明 recognition event |
| `OrderLineFact` | 上述 + `line_item_id` | platform_sku、quantity、商品金额、discount、is_gift | 金额/件数粒度显式，不靠表名推断 |
| `RefundEvent` | `platform + shop_id + refund_id` | event_time、order_id、subtotal、shipping、tax、status | 商品净销售额只冲 subtotal；取消退款不得重复冲减 |
| `RefundLineEvent` | refund + line item | platform_sku、quantity、subtotal | 支撑商品归因与退货率 |
| `ProductIdentity` | platform_sku | NSSKU、型号、品类、映射状态 | 未映射保留总账，维度进桶 |
| `CustomerIdentity` | 平台/店铺命名空间 + hash | identity_quality | 默认不跨平台合并 |
| `TrafficFact` / `AttributionFact` | source-specific id | views/clicks/orders/native metrics | 只在 capability 存在时生成；原生归因不得冒充 canonical |

adapter 输出必须包含 `adapter_id`、`contract_version`、`schema_fingerprint`、capability、覆盖期、水位、未映射字段、质量断言。原始表名只允许出现在 adapter 与 source manifest。

## 15. 指标、规则与 Playbook 注册契约

### 15.1 指标状态

| 状态 | 用途 | 可进正式报告 | 可跨平台合计 |
|---|---|---|---|
| `canonical` | 已确认统一指标 | 是 | capability 与映射完整时是 |
| `platform-native` | 平台官方指标 | 平台章节/附录 | 否 |
| `provisional` | `ask` 探索指标 | 否；只可出探索草稿 | 否 |
| `diagnostic` | 数据质量/对账 | 数据说明/证据包 | 否 |

### 15.2 规则组合

`effective_rules = core + domain(ecommerce) + platform(adapter ids) + playbook(manifest id)`。冲突按更具体 scope 覆盖，但覆盖必须由 ADR 授权并写入计划；同级冲突直接阻断。Shopify R-18～R-41、R-50～R-79 不得默认套到 TikTok。

### 15.3 Playbook manifest

生产 Registry 只读取 `manifest.yaml`（或同 schema 的 JSON），不解析 Markdown。manifest 至少含：`id / contract_version / steps / metric_refs / skill_refs / rule_packs / required_capabilities / time_scope / outline / approval_policy / eval_overlays`。说明文档只解释“为什么”。

## 16. 生产运行契约

### 16.1 Run 状态机

`created → planned → awaiting_c1 → snapshotting → awaiting_c2 → running ↔ awaiting_alignment → validating → awaiting_c3 → completed`。任意可运行态可进入 `cancel_requested → cancelled`；可恢复态从最后一个已提交 checkpoint 继续。`failed` 必须携带 `ErrorEnvelope`。同一 `run_id + step_id + input_fingerprint` 重试必须幂等。

### 16.2 Artifact Envelope 与逐源 manifest

每个工件必须有 `artifact_id/type/schema_version/content_hash/producer/input_refs/created_at/classification`。`source_manifest.json` 顶层只做索引，`sources[]` 为每个平台/表/文件独立记录：连接逻辑标识、adapter/schema 版本、查询 hash、行数、时间范围、水位、快照 hash、完整度与 capability。多源不得只给一个整体 hash。

### 16.3 审批、错误与配置

- C1/C2 复用指纹 = org/profile + playbook manifest + metric/rule packs + adapter/schema + SQL template + source contract；任一变化即失效。
- `ErrorEnvelope` 至少含 `code/category/severity/retryable/module_id/run_id/step_id/safe_message/cause_ref`，禁止把凭据或 PII塞进 message。
- 配置必须有 `schema_version`、严格校验与 migration；`draft` profile 默认不可发布正式报告，只能 dry-run/partial。
- Tool 声明 capability（network/db-read/file-write 等）；Policy 在调用前后检查。SQL 安全以 parser/AST 为准，不靠字符串黑名单。

## 17. 安全与观测

Trace 默认记录参数 schema、hash、行数、耗时和结果摘要，不记录完整查询结果。凭据、token、电话、地址、姓名、买家账号与原始 JSON 必须在 adapter 边界删除或不可逆哈希；日志再做二次脱敏。原始 PII 访问是独立 capability，默认 deny，审批与用途入 trace。OTel 导出仍为可选实现，但事件 schema 在 S0 固定。

