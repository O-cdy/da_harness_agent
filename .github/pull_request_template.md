## Why

<!-- 说明本次改动解决什么问题。 -->

## Scope and risk

- 模块归属：core / adapter / skill / tool / playbook / docs
- 可独立回滚：
- 主要风险：

## Contract impact

- [ ] 不改变 SSOT、ADR、Profile、Port 或机器 schema
- [ ] 已先追加 ADR，并同步所有受影响 SSOT
- Harness 通用性：换平台或场景是否只需注册实现/配置：

## Security and data

- 数据分级：
- PII / 凭据影响：
- 网络 / LLM / MCP 数据出境：
- 数据留存与清理：
- 数据库权限与 NoOp 路径：

## Verification evidence

```text
# 实际执行的命令与结果摘要
```

- [ ] Ruff format/check
- [ ] mypy
- [ ] unit / contract / smoke tests
- [ ] import boundary
- [ ] secret / dependency / static security scan
- [ ] build and clean-install smoke
- [ ] 无凭据路径

## Unverified

<!-- 没跑过的项目必须明确列出；没有则写“无”。 -->
